#!/usr/bin/env python3
"""Bounded, fresh CLI jobs. The controller must authorize each job before calling.

Only inline text is supplied. CLI restrictions are recorded, not represented as
a universal filesystem boundary. No authentication or persistent config is changed.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time

BINARIES = {'codex': 'codex', 'claude': 'claude', 'antigravity': 'agy'}
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_PROMPT_BYTES = 8 * 1024 * 1024
MAX_JOB_SECONDS = 3600
SYSTEM_SCOPE = ('Use only the supplied inline material. Do not use tools, read files, '
                'browse, execute commands, or seek other conversations. Return only the '
                'requested JSON object. This is text-only coverage, not visual inspection.')


class ProviderError(RuntimeError):
    def __init__(self, message: str, code: str = 'provider_error', receipt: dict | None = None):
        super().__init__(message)
        self.code = code
        self.receipt = receipt or {}
        # Transient diagnostic only: callers may inspect a rejected parsed
        # object privately. It is never copied into the payload-free receipt.
        self.output = None


def _redact(value: str) -> str:
    value = re.sub(r'(?i)(bearer\s+)[^\s"\']+', r'\1[redacted]', value)
    value = re.sub(r'\bsk-[A-Za-z0-9_-]+', '[redacted]', value)
    value = re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|authorization)\s*[=:]\s*)[^\s,;]+',
                   r'\1[redacted]', value)
    return value[:2048]


def _kill_group(process: subprocess.Popen) -> None:
    """Also stop descendants that retain pipes after the direct child exits."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            if os.name == 'posix':
                os.killpg(process.pid, sig)
            elif process.poll() is None:
                process.terminate() if sig == signal.SIGTERM else process.kill()
        except ProcessLookupError:
            pass
        except PermissionError:
            # macOS can report EPERM for an already reaped process group.
            if process.poll() is None:
                process.terminate() if sig == signal.SIGTERM else process.kill()
        try:
            process.wait(timeout=0.25)
        except subprocess.TimeoutExpired:
            pass
        if sig == signal.SIGTERM:
            time.sleep(0.05)


def _process(argv: list[str], cwd: Path, data: bytes, timeout: float,
             cancel_event=None, limit: int = MAX_OUTPUT_BYTES) -> tuple[int, str, str]:
    if cancel_event is not None and cancel_event.is_set():
        raise ProviderError('Job cancelled before provider launch.', 'cancelled')
    try:
        process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=(os.name == 'posix'))
    except OSError as error:
        raise ProviderError('Unable to start provider process: ' + _redact(str(error)), 'invocation_failed') from None
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()
    lock = threading.Lock()

    def read(stream, index):
        try:
            while True:
                block = stream.read(8192)
                if not block:
                    break
                with lock:
                    remaining = max(0, limit - sum(map(len, buffers)))
                    buffers[index].extend(block[:remaining])
                    if len(block) > remaining:
                        overflow.set()
                        break
        finally:
            stream.close()

    def write():
        try:
            process.stdin.write(data)
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                process.stdin.close()
            except OSError:
                pass

    readers = [threading.Thread(target=read, args=(process.stdout, 0), daemon=True),
               threading.Thread(target=read, args=(process.stderr, 1), daemon=True)]
    writer = threading.Thread(target=write, daemon=True)
    for thread in [*readers, writer]:
        thread.start()
    deadline = time.monotonic() + timeout
    error = None
    try:
        while True:
            if overflow.is_set():
                error = ProviderError('Provider output exceeded its recorded limit.', 'output_limit')
                break
            if cancel_event is not None and cancel_event.is_set():
                error = ProviderError('Provider job cancelled.', 'cancelled')
                break
            if time.monotonic() >= deadline:
                error = ProviderError('Provider job reached its time limit.', 'timeout')
                break
            if process.poll() is not None:
                break
            time.sleep(0.025)
        if error is not None:
            _kill_group(process)
        for thread in readers:
            thread.join(timeout=0.5)
        if any(thread.is_alive() for thread in readers):
            _kill_group(process)
            for thread in readers:
                thread.join(timeout=0.5)
            error = error or ProviderError('Provider left an unfinished output stream.', 'protocol_error')
        if overflow.is_set():
            error = error or ProviderError('Provider output exceeded its recorded limit.', 'output_limit')
        if error is not None:
            raise error
        return process.wait(timeout=1), *(bytes(value).decode('utf-8', 'replace') for value in buffers)
    finally:
        if process.poll() is None or any(thread.is_alive() for thread in readers):
            _kill_group(process)
        writer.join(timeout=0.5)


def detect(provider: str, *, cancel_event=None) -> dict:
    if provider not in BINARIES:
        raise ProviderError('Unknown provider: ' + str(provider), 'unsupported_provider')
    binary = shutil.which(BINARIES[provider])
    if not binary:
        raise ProviderError(BINARIES[provider] + ' is not installed or is not on PATH.', 'missing_binary')
    with tempfile.TemporaryDirectory(prefix='paper-provider-probe-') as temporary:
        cwd = Path(temporary)
        code, version, error = _process([binary, '--version'], cwd, b'', 10,
                                        cancel_event, limit=65536)
        if code:
            raise ProviderError('Provider version probe failed: ' + _redact(error), 'probe_failed')
        version = version or error
        args = [binary, 'exec', '--help'] if provider == 'codex' else [binary, '--help']
        code, help_text, error = _process(args, cwd, b'', 10, cancel_event, limit=262144)
        if code:
            raise ProviderError('Provider capability probe failed: ' + _redact(error), 'probe_failed')
        help_text += '\n' + error  # Some CLIs print successful --help on stderr.
    required = {
        'codex': ['--ignore-user-config', '--ephemeral', '--json', '--output-schema', '--sandbox'],
        'claude': ['--safe-mode', '--restricted', '--tools', '--strict-mcp-config',
                   '--json-schema', '--no-session-persistence', '--permission-prompts'],
        'antigravity': ['--settings', '--json-schema', '--print-timeout', '--output-format', '--input-format', '--mode'],
    }[provider]
    missing = [name for name in required if name not in help_text]
    if missing:
        raise ProviderError('Installed CLI lacks required options: ' + ', '.join(missing), 'unsupported_cli')
    return {'provider': provider, 'binary': str(Path(binary).absolute()),
            'version': _redact(version.strip().splitlines()[0] if version.strip() else 'unreported')}


def describe(provider: str, *, probe: bool = True, cancel_event=None) -> dict:
    """Approval-plan metadata; only help/version probes run, never a model call."""
    if provider not in BINARIES:
        raise ProviderError('Unknown provider: ' + str(provider), 'unsupported_provider')
    info = detect(provider, cancel_event=cancel_event) if probe else {
        'provider': provider, 'binary': BINARIES[provider], 'version': 'not_probed'}
    limitations = ['Inline text only; figures and PDF page layout were not inspected.',
                   'Managed host policy may still affect provider behavior.',
                   'Separate fresh process; universal filesystem isolation is not asserted.',
                   'Stopping the local client cannot prove an in-flight remote request has stopped.']
    if provider == 'antigravity':
        limitations += ['Antigravity has no documented no-persistence or skip-global-customizations flag; '
                        'global hooks/config discovery may run and conversation metadata may persist.']
    return {**info, 'scope': 'inline_text_only', 'tools_policy': 'disabled_or_denied',
            'model_policy': 'Explicit requested model or CLI/provider default; not inherited from the current chat.',
            'limitations': limitations,
            'default_timeout_seconds': 180, 'maximum_output_bytes': MAX_OUTPUT_BYTES}


def _resolve(schema: dict, root: dict) -> dict:
    if '$ref' not in schema:
        return schema
    ref = schema['$ref']
    if not isinstance(ref, str) or not ref.startswith('#/'):
        raise ProviderError('Only local schema references are supported.', 'unsupported_schema')
    value = root
    try:
        for part in ref[2:].split('/'):
            value = value[part.replace('~1', '/').replace('~0', '~')]
    except (KeyError, TypeError):
        raise ProviderError('Invalid local schema reference.', 'unsupported_schema') from None
    return {**value, **{k: v for k, v in schema.items() if k != '$ref'}}


def validate_output(value, schema: dict, *, _root: dict | None = None) -> None:
    """Validate the JSON Schema subset used by bundled output contracts."""
    annotations = {'$schema', '$id', '$defs', 'definitions', 'title', 'description',
                   'default', 'examples', 'format', 'readOnly', 'writeOnly'}
    supported = {'$ref', 'type', 'properties', 'additionalProperties', 'required',
                 'items', 'minItems', 'maxItems', 'uniqueItems', 'enum', 'const',
                 'minLength', 'maxLength', 'pattern', 'minimum', 'maximum',
                 'exclusiveMinimum', 'exclusiveMaximum', 'multipleOf',
                 'allOf', 'anyOf', 'oneOf', 'not', 'if', 'then', 'else'} | annotations

    def fail(path, detail):
        raise ProviderError(path + ': ' + detail, 'invalid_output')

    def accepts(item, sub, path, depth):
        try:
            check(item, sub, path, depth)
            return True
        except ProviderError as error:
            if error.code != 'invalid_output':
                raise
            return False

    def check(item, sub, path='$', depth=0):
        if depth > 64:
            raise ProviderError('Schema nesting limit reached.', 'unsupported_schema')
        if isinstance(sub, bool):
            if not sub:
                fail(path, 'value prohibited')
            return
        if not isinstance(sub, dict):
            raise ProviderError('Invalid output schema.', 'unsupported_schema')
        sub = _resolve(sub, schema if _root is None else _root)
        if set(sub) - supported:
            raise ProviderError('Unsupported schema keyword: ' + ', '.join(sorted(set(sub) - supported)), 'unsupported_schema')
        for child in sub.get('allOf', []):
            check(item, child, path, depth + 1)
        for key, count in [('anyOf', None), ('oneOf', 1)]:
            if key in sub:
                matches = sum(accepts(item, child, path, depth + 1) for child in sub[key])
                if (count is None and not matches) or (count is not None and matches != count):
                    fail(path, key + ' did not match')
        if 'not' in sub and accepts(item, sub['not'], path, depth + 1):
            fail(path, 'prohibited schema matched')
        if 'if' in sub:
            branch = 'then' if accepts(item, sub['if'], path, depth + 1) else 'else'
            if branch in sub:
                check(item, sub[branch], path, depth + 1)
        kinds = {'object': isinstance(item, dict), 'array': isinstance(item, list),
                 'string': isinstance(item, str), 'integer': type(item) is int,
                 'number': type(item) is int or (type(item) is float and math.isfinite(item)),
                 'boolean': type(item) is bool, 'null': item is None}
        if 'type' in sub:
            types = sub['type'] if isinstance(sub['type'], list) else [sub['type']]
            if any(kind not in kinds for kind in types):
                raise ProviderError('Unsupported schema type.', 'unsupported_schema')
            if not any(kinds[kind] for kind in types):
                fail(path, 'incorrect type')
        if 'enum' in sub and not any(type(item) is type(x) and item == x for x in sub['enum']):
            fail(path, 'outside allowed values')
        if 'const' in sub and (type(item) is not type(sub['const']) or item != sub['const']):
            fail(path, 'incorrect constant')
        if isinstance(item, dict):
            if any(key not in item for key in sub.get('required', [])):
                fail(path, 'required field missing')
            properties = sub.get('properties', {})
            for key, content in item.items():
                if key in properties:
                    check(content, properties[key], path + '.' + key, depth + 1)
                elif sub.get('additionalProperties') is False:
                    fail(path, 'unknown field ' + key)
                elif isinstance(sub.get('additionalProperties'), dict):
                    check(content, sub['additionalProperties'], path + '.' + key, depth + 1)
        if isinstance(item, list):
            if len(item) < sub.get('minItems', 0) or len(item) > sub.get('maxItems', float('inf')):
                fail(path, 'array length out of range')
            if sub.get('uniqueItems') and len({json.dumps(x, sort_keys=True) for x in item}) != len(item):
                fail(path, 'array items not unique')
            for index, content in enumerate(item):
                if 'items' in sub:
                    check(content, sub['items'], path + '[' + str(index) + ']', depth + 1)
        if isinstance(item, str):
            if len(item) < sub.get('minLength', 0) or len(item) > sub.get('maxLength', float('inf')):
                fail(path, 'string length out of range')
            if 'pattern' in sub and not re.search(sub['pattern'], item):
                fail(path, 'pattern did not match')
        if type(item) in (int, float):
            if type(item) is float and not math.isfinite(item):
                fail(path, 'non-finite number')
            for key, predicate in [('minimum', lambda x: item >= x), ('maximum', lambda x: item <= x),
                                   ('exclusiveMinimum', lambda x: item > x), ('exclusiveMaximum', lambda x: item < x)]:
                if key in sub and not predicate(sub[key]):
                    fail(path, 'number out of range')
            if 'multipleOf' in sub and not math.isclose(item / sub['multipleOf'], round(item / sub['multipleOf'])):
                fail(path, 'incorrect numeric multiple')

    check(value, schema)


def transport_schema(schema: dict) -> dict:
    """Convert optional fields to nullable strict transport; validate originals later."""
    def merge(base, extra):
        """Intersect the object refinements used by bundled conditionals."""
        result = copy.deepcopy(base)
        for key, value in extra.items():
            if key == 'properties':
                properties = result.setdefault('properties', {})
                for name, child in value.items():
                    properties[name] = merge(properties.get(name, {}), child)
            elif key == 'required':
                result[key] = list(dict.fromkeys(result.get(key, []) + value))
            elif key == 'type' and key in result:
                left = result[key] if isinstance(result[key], list) else [result[key]]
                right = value if isinstance(value, list) else [value]
                result[key] = [kind for kind in left if kind in right]
            elif key == 'enum' and key in result:
                result[key] = [item for item in result[key] if item in value]
            elif key == 'not':
                # The bundled action contract forbids this one optional field
                # outside its discriminator branch. Omit it from that branch's
                # strict properties, rather than asking the model to emit null.
                if (not isinstance(value, dict) or set(value) != {'required'}
                        or len(value['required']) != 1):
                    raise ValueError('unsupported negative refinement')
                name = value['required'][0]
                if name in result.get('required', []):
                    raise ValueError('inconsistent required refinement')
                result.get('properties', {}).pop(name, None)
            else:
                result[key] = copy.deepcopy(value)
        return result

    def variants(sub):
        directives = list(sub.get('allOf', []))
        if 'if' in sub:
            directives += [{key: sub[key] for key in ('if', 'then', 'else') if key in sub}]
        if not directives:
            return None
        selectors = {}
        for directive in directives:
            if (not isinstance(directive, dict) or 'if' not in directive
                    or set(directive) - {'if', 'then', 'else'}):
                return None
            condition = directive['if']
            if not isinstance(condition, dict) or set(condition) != {'properties'}:
                return None
            for name, restriction in condition['properties'].items():
                parent = sub.get('properties', {}).get(name, {})
                values = parent.get('enum')
                if (name not in sub.get('required', []) or not isinstance(values, list)
                        or not values or not isinstance(restriction, dict)
                        or not set(restriction).issubset({'const', 'enum'})):
                    return None
                selectors[name] = values
        if not selectors or math.prod(len(values) for values in selectors.values()) > 32:
            return None
        result = []
        for values in itertools.product(*selectors.values()):
            selected = dict(zip(selectors, values))
            branch = {key: copy.deepcopy(value) for key, value in sub.items()
                      if key not in {'allOf', 'if', 'then', 'else'}}
            for name, value in selected.items():
                branch['properties'][name]['enum'] = [value]
            try:
                for directive in directives:
                    try:
                        validate_output(selected, directive['if'])
                        consequence = directive.get('then', {})
                    except ProviderError as error:
                        if error.code != 'invalid_output':
                            raise
                        consequence = directive.get('else', {})
                    branch = merge(branch, consequence)
            except (ValueError, TypeError, KeyError):
                return None
            result.append(branch)
        return result

    def convert(sub, depth=0):
        if depth > 64:
            raise ProviderError('Schema nesting limit reached.', 'unsupported_schema')
        if isinstance(sub, bool):
            return {} if sub else {'not': {}}
        sub = _resolve(sub, schema)
        # Native structured APIs permit anyOf below the root. Compile finite
        # discriminator conditionals there instead of silently losing the
        # experiment-only and priority/basis constraints during generation.
        branches = variants(sub) if depth > 0 else None
        if branches is not None:
            return {'anyOf': [convert(branch, depth + 1) for branch in branches]}
        result = {key: copy.deepcopy(value) for key, value in sub.items()
                  if key not in {'$schema', '$id', '$defs', 'definitions', 'allOf', 'if', 'then', 'else', 'not'}}
        if 'const' in result:
            result['enum'] = [result.pop('const')]
        if 'properties' in sub:
            required = sub.get('required', [])
            properties = {}
            for name, child in sub['properties'].items():
                converted = convert(child, depth + 1)
                if name not in required:
                    converted = {'anyOf': [converted, {'type': 'null'}]}
                properties[name] = converted
            result.update(properties=properties, required=list(properties), additionalProperties=False)
        if 'items' in sub:
            result['items'] = convert(sub['items'], depth + 1)
        for key in ('anyOf', 'oneOf'):
            if key in sub:
                result['anyOf' if key == 'oneOf' else key] = [convert(x, depth + 1) for x in sub[key]]
                if key == 'oneOf':
                    result.pop('oneOf', None)
        return result
    return convert(schema)


def _restore_optional(value, schema: dict, root: dict | None = None):
    root = schema if root is None else root
    if isinstance(schema, bool):
        return value
    schema = _resolve(schema, root)
    if isinstance(value, dict):
        properties = schema.get('properties', {})
        required = schema.get('required', [])
        restored = {}
        for key, item in value.items():
            child = properties.get(key)
            if child is None:
                restored[key] = item
                continue
            if item is None and key not in required:
                try:
                    validate_output(None, child, _root=root)
                except ProviderError as error:
                    if error.code == 'invalid_output':
                        continue
                    raise
            restored[key] = _restore_optional(item, child, root)
        return restored
    if isinstance(value, list) and isinstance(schema.get('items'), dict):
        return [_restore_optional(item, schema['items'], root) for item in value]
    return value


def build_command(provider: str, binary: str, cwd: Path, schema_path: Path,
                  output_path: Path, *, model: str | None = None, timeout: int = 180) -> list[str]:
    if provider == 'codex':
        argv = [binary, 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
                '--sandbox', 'read-only', '--json', '--color', 'never', '--cd', str(cwd),
                '--output-schema', str(schema_path), '--output-last-message', str(output_path)]
        settings = {'web_search': 'disabled', 'project_doc_max_bytes': 0,
                    'skills.include_instructions': False, 'skills.bundled.enabled': False,
                    'features.shell_tool': False, 'features.apps': False,
                    'features.plugins': False, 'features.memories': False,
                    'features.hooks': False, 'features.multi_agent': False}
        for name, value in settings.items():
            argv += ['--config', name + '=' + json.dumps(value)]
        if model:
            argv += ['--model', model]
        return argv + ['-']
    if provider == 'claude':
        argv = [binary, '--print', '--safe-mode', '--restricted', '--tools', '',
                '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                '--disable-slash-commands', '--no-session-persistence',
                '--permission-prompts', 'none', '--output-format', 'json',
                '--json-schema', schema_path.read_text(encoding='utf-8')]
        if model:
            argv += ['--model', model]
        return argv
    if provider == 'antigravity':
        settings = {'agentMode': 'plan', 'toolPermission': 'strict',
                    'permissions': {'allow': [], 'ask': [], 'deny': [
                        'read_file(*)', 'write_file(*)', 'read_url(*)',
                        'execute_url(*)', 'command(*)', 'mcp(*)']},
                    'statusLine': {'enabled': False}, 'title': {'enabled': False}}
        # --print is a string flag, not a boolean. Streaming input keeps the
        # entire prompt on stdin and closing it ends this single-turn process.
        argv = [binary, '--input-format', 'stream-json', '--mode', 'plan',
                '--disable-slash-commands', '--output-format', 'stream-json',
                '--json-schema', str(schema_path),
                '--print-timeout', str(timeout) + 's', '--settings', json.dumps(settings)]
        if model:
            argv += ['--model', model]
        return argv
    raise ProviderError('Unknown provider.', 'unsupported_provider')


def _json(value: str):
    try:
        return json.loads(value, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    except (ValueError, TypeError):
        raise ProviderError('Provider returned malformed JSON.', 'invalid_output') from None


def _protocol_diagnostics(provider: str, stdout: str) -> dict:
    """Keep discriminator counts, never event text, arguments, paths or outputs."""
    known = {
        'event_types': {'init', 'step_update', 'result', 'thread.started', 'turn.started',
                        'turn.completed', 'turn.failed', 'item.started', 'item.updated',
                        'item.completed', 'error', 'system', 'assistant', 'user'},
        'step_types': {'user_input', 'agent_response', 'tool', 'finish', 'checkpoint', 'tool_call',
                       'command_execution', 'agent_message', 'reasoning', 'file_change',
                       'mcp_tool_call', 'web_search', 'todo_list'},
        'tool_names': {'finish', 'run_command', 'read_file', 'view_file', 'write_to_file',
                       'replace_file_content', 'multi_replace_file_content', 'list_dir',
                       'find_by_name', 'grep_search', 'code_search', 'search_web',
                       'read_url_content', 'view_webpage', 'invoke_subagent', 'ask_question',
                       'ask_permission', 'send_command_input', 'command_status'},
    }
    result = {'event_count': 0, 'malformed_lines': 0,
              'event_types': {}, 'step_types': {}, 'tool_names': {}}

    def record(group, value):
        if not isinstance(value, str):
            return
        # Unknown names are fingerprints: even a malicious "name" cannot copy
        # prompt text or credentials into an error receipt.
        label = value if value in known[group] else (
            'unrecognized:' + hashlib.sha256(value.encode()).hexdigest()[:12])
        counts = result[group]
        if label not in counts and len(counts) >= 24:
            result['labels_truncated'] = True
            return
        counts[label] = counts.get(label, 0) + 1

    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = _json(line)
        except ProviderError:
            result['malformed_lines'] += 1
            continue
        if not isinstance(event, dict):
            result['malformed_lines'] += 1
            continue
        result['event_count'] += 1
        record('event_types', event.get('event') if provider == 'antigravity' else event.get('type'))
        if provider == 'antigravity' and event.get('event') == 'step_update':
            step = event.get('step_update', {})
            if isinstance(step, dict):
                record('step_types', step.get('step_type'))
                if step.get('step_type') == 'tool':
                    record('tool_names', step.get('tool_name'))
                    info = step.get('tool_info')
                    if isinstance(info, dict) and info.get('name') != step.get('tool_name'):
                        record('tool_names', info.get('name'))
                    if step.get('tool_name') == 'finish':
                        samples = result.setdefault('finish_updates', [])
                        if len(samples) < 8:
                            samples.append({
                                'state': step.get('state') if step.get('state') in ('ACTIVE', 'DONE') else 'unrecognized',
                                'has_tool_info': isinstance(info, dict),
                                'has_info_name': isinstance(info, dict) and 'name' in info,
                                'info_name_matches': isinstance(info, dict) and info.get('name') == 'finish',
                                'has_error': isinstance(info, dict) and bool(info.get('error')),
                                'has_subagent_info': bool(step.get('subagent_info'))})
        if provider == 'antigravity' and event.get('event') == 'result':
            envelope = event.get('result')
            if isinstance(envelope, dict):
                result['result_summary'] = {
                    'status_success': envelope.get('status') == 'SUCCESS',
                    'has_structured_object': isinstance(envelope.get('structured_output'), dict)}
        if provider == 'codex':
            item = event.get('item')
            if isinstance(item, dict):
                record('step_types', item.get('type'))
    return result


def _parse(provider: str, stdout: str, output_path: Path) -> tuple[dict, dict]:
    native_serialization = []
    if provider == 'codex':
        events = [_json(line) for line in stdout.splitlines() if line.strip()]
        usage = None
        for event in events:
            if not isinstance(event, dict):
                raise ProviderError('Malformed Codex event.', 'protocol_error')
            if event.get('type') in ('error', 'turn.failed'):
                raise ProviderError('Codex reported a failed turn.', 'provider_failed')
            if event.get('type') == 'turn.completed':
                usage = event.get('usage')
            item = event.get('item', {})
            if isinstance(item, dict) and item.get('type') not in (None, 'agent_message', 'reasoning'):
                raise ProviderError('Provider attempted an out-of-scope tool action.', 'tool_use')
        if not any(event.get('type') == 'turn.completed' for event in events):
            raise ProviderError('Codex did not complete its turn.', 'protocol_error')
        if output_path.is_symlink() or not output_path.is_file() or output_path.stat().st_size > MAX_OUTPUT_BYTES:
            raise ProviderError('Codex final response is missing or oversized.', 'invalid_output')
        return _json(output_path.read_text(encoding='utf-8')), {'usage': usage, 'model_actual': None}
    if provider == 'antigravity':
        events = [_json(line) for line in stdout.splitlines() if line.strip()]
        if not all(isinstance(event, dict) for event in events):
            raise ProviderError('Malformed Antigravity event.', 'protocol_error')
        terminal = [event.get('result') for event in events if event.get('event') == 'result']
        if len(terminal) != 1:
            raise ProviderError('Antigravity did not return exactly one result.', 'protocol_error')
        envelope = terminal[0]
        for event in events:
            # Only the documented event discriminator identifies a tool step.
            # A similarly named field inside init/result metadata is not one.
            step = event.get('step_update', {}) if event.get('event') == 'step_update' else {}
            if isinstance(step, dict) and step.get('step_type') in ('tool', 'tool_call', 'command_execution'):
                info = step.get('tool_info')
                # Antigravity's native custom-schema completion is a finish
                # tool (FinishToolConfig.result_json_schema_string in 1.5.5).
                # This is only serialization, never permission for another tool.
                # run_job still validates the final object against the ORIGINAL
                # schema before accepting the job, including its conditionals.
                if (step.get('step_type') == 'tool' and step.get('tool_name') == 'finish'
                        and (info is None or (isinstance(info, dict)
                             and info.get('name', 'finish') == 'finish' and not info.get('error')))
                        and not step.get('subagent_info')):
                    # Canonical tool_name is sufficient: ACTIVE updates and
                    # native finish steps can omit tool_info or its duplicate
                    # name. Do not require a full DONE snapshot on each delta.
                    if step.get('state') not in ('ACTIVE', 'DONE'):
                        raise ProviderError('Malformed native finish state.', 'protocol_error')
                    if not isinstance(envelope, dict) or not isinstance(envelope.get('structured_output'), dict):
                        raise ProviderError('Native finish did not provide a structured result.', 'invalid_output')
                    native_serialization = ['finish']
                    continue
                raise ProviderError('Provider attempted an out-of-scope tool action.', 'tool_use')
    else:
        envelope = _json(stdout)
    if not isinstance(envelope, dict):
        raise ProviderError('Provider result envelope must be an object.', 'protocol_error')
    if provider == 'claude':
        if envelope.get('is_error') or envelope.get('subtype') != 'success':
            raise ProviderError('Claude reported a failed result: ' + _redact(str(envelope.get('error', envelope.get('subtype', 'unknown')))), 'provider_failed')
        text_key = 'result'
    else:
        if envelope.get('status') != 'SUCCESS':
            raise ProviderError('Antigravity reported a failed result: ' + _redact(str(envelope.get('error', envelope.get('status', 'unknown')))), 'provider_failed')
        text_key = 'response'
    value = envelope.get('structured_output')
    if value is None:
        value = _json(envelope.get(text_key, ''))
    models = list(envelope.get('modelUsage', {})) if isinstance(envelope.get('modelUsage'), dict) else []
    return value, {'usage': envelope.get('usage'),
                   'model_actual': models[0] if len(models) == 1 else None,
                   'cost_usd_reported': envelope.get('total_cost_usd'),
                   'native_serialization': native_serialization}


def run_job(provider: str, prompt: str, schema: dict, cwd: Path, *,
            model: str | None = None, timeout: int = 180, cancel_event=None) -> dict:
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt.encode()) > MAX_PROMPT_BYTES:
        raise ProviderError('Prompt is empty or exceeds the job input limit.', 'invalid_input')
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= MAX_JOB_SECONDS:
        raise ProviderError('Job timeout must be positive and bounded.', 'invalid_input')
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ProviderError('Model must be an explicit nonempty name or omitted.', 'invalid_input')
    cwd = Path(cwd).resolve()
    if not cwd.is_dir() or any(cwd.iterdir()):
        raise ProviderError('Provider jobs require a fresh empty working directory.', 'unsafe_context')
    if cancel_event is not None and cancel_event.is_set():
        raise ProviderError('Job cancelled before provider launch.', 'cancelled')
    description = describe(provider, cancel_event=cancel_event)
    started = time.monotonic()
    receipt = {**description, 'model_requested': model, 'model_actual': None,
               'scope': 'inline_text_only', 'tools_policy': 'disabled_or_denied',
               'elapsed_seconds': 0, 'usage': None,
               'limits': {'timeout_seconds': timeout, 'output_bytes': MAX_OUTPUT_BYTES}}
    output = None
    try:
        with tempfile.TemporaryDirectory(prefix='paper-provider-output-') as temporary:
            directory = Path(temporary)
            schema_path, output_path = directory / 'schema.json', directory / 'result.json'
            transport = transport_schema(schema)
            schema_path.write_text(json.dumps(transport, allow_nan=False), encoding='utf-8')
            argv = build_command(provider, description['binary'], cwd, schema_path, output_path,
                                 model=model, timeout=timeout)
            content = SYSTEM_SCOPE + '\n\n' + prompt
            data = ((json.dumps({'event': 'user', 'message': {'content': content}}) + '\n').encode()
                    if provider == 'antigravity' else content.encode())
            code, stdout, stderr = _process(argv, cwd, data, timeout, cancel_event)
            receipt['protocol'] = _protocol_diagnostics(provider, stdout)
            if code:
                raise ProviderError('Provider exited with code ' + str(code) + ': ' + _redact(stderr), 'provider_failed')
            output, metadata = _parse(provider, stdout, output_path)
            receipt.update(metadata)
            output = _restore_optional(output, schema)
            if not isinstance(output, dict):
                raise ProviderError('Provider output must be a JSON object.', 'invalid_output')
            validate_output(output, schema)
            receipt['elapsed_seconds'] = round(time.monotonic() - started, 3)
            return {'output': output, 'receipt': receipt}
    except ProviderError as error:
        if error.code == 'invalid_output' and isinstance(output, dict):
            if len(json.dumps(output, allow_nan=False).encode()) <= MAX_OUTPUT_BYTES:
                error.output = copy.deepcopy(output)
        receipt['elapsed_seconds'] = round(time.monotonic() - started, 3)
        error.receipt = receipt
        raise
    except (OSError, ValueError, TypeError, subprocess.SubprocessError) as error:
        receipt['elapsed_seconds'] = round(time.monotonic() - started, 3)
        raise ProviderError('Provider invocation failed: ' + _redact(str(error)), 'invocation_failed', receipt) from None
