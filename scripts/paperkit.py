#!/usr/bin/env python3
"""Local paper helpers. No network or model-provider calls. Python 3.10+."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import readability
import visual_audit

KIT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.paper', '.paper-tools', '.agents', '.claude', '.venv', 'venv',
        'node_modules', '__pycache__', 'sources'}
TEXT = {'.tex', '.bib', '.sty', '.cls', '.tikz', '.pgf', '.csv', '.tsv'}
TRACKED = TEXT | {'.pdf', '.png', '.jpg', '.jpeg', '.eps', '.svg', '.yaml', '.yml', '.json', '.py', '.r'}
MARKER = re.compile(r'\b(?:TODO|TBD|FIXME|XXX|PLACEHOLDER)\b|\blorem\s+ipsum\b|\?\?|\[INSERT\b|<INSERT\b', re.I)
WRAPPER = re.compile(r'\\PaperTODO\b|\\begin\s*\{PaperProvisional\}')
CHECKS = {'science', 'citations', 'terminology', 'relevance', 'readability', 'visual', 'venue', 'provisional'}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe(root: Path, name: str | Path) -> Path:
    root = root.resolve()
    p = (root / name).resolve()
    if not p.is_relative_to(root):
        raise ValueError(f'Path escapes workspace: {name}')
    return p


def dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.write-', delete=False) as f:
        json.dump(value, f, indent=2, ensure_ascii=False)
        f.write('\n')
        temp = Path(f.name)
    temp.replace(path)


def load_state(root: Path) -> dict[str, Any]:
    p = safe(root, '.paper/state.json')
    state = json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(state, dict) or state.get('schema_version') != 1:
        raise ValueError('Unsupported state schema; initialize or explicitly migrate.')
    for key in ('todos', 'questions', 'decisions', 'literal_exceptions'):
        if not isinstance(state.get(key, []), list):
            raise ValueError(f'Invalid state.{key}')
        if not all(isinstance(item, dict) for item in state.get(key, [])):
            raise ValueError(f'Invalid object in state.{key}')
    ids = []
    for item in state['todos']:
        if not isinstance(item, dict) or not re.fullmatch(r'T[0-9]{3,}', str(item.get('id', ''))):
            raise ValueError('Invalid TODO entry.')
        if item.get('status') not in ('open', 'resolved', 'removed'):
            raise ValueError('Invalid TODO status.')
        ids.append(item['id'])
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate TODO IDs in ledger.')
    return state


def source_files(root: Path, extensions: set[str] | None) -> list[Path]:
    result = []
    for p in root.rglob('*'):
        rel = p.relative_to(root)
        if any(part in SKIP for part in rel.parts):
            continue
        if extensions is not None and p.suffix.lower() not in extensions:
            continue
        if p.is_symlink() or any(parent.is_symlink() for parent in p.parents if parent != root and parent.is_relative_to(root)):
            raise ValueError(f'Symlinked manuscript input is not supported: {rel}')
        if p.is_file():
            result.append(p)
    return sorted(result)


def snapshot(root: Path) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha(p) for p in source_files(root, None)}


def group(text: str, position: int) -> tuple[str, int]:
    while position < len(text) and text[position].isspace():
        position += 1
    if position >= len(text) or text[position] != '{':
        raise ValueError('Missing braced argument')
    start = position + 1
    depth, i = 1, start
    while i < len(text):
        if text[i] == '\\':
            i += 2
            continue
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start:i], i + 1
        i += 1
    raise ValueError('Unclosed braced argument')


def body_hash(text: str) -> str:
    return digest(text.strip().encode('utf-8'))


def literal_allowed(state: dict, filename: str, line: int, text: str) -> bool:
    return any(isinstance(e, dict) and e.get('file') == filename and e.get('line') == line
               and e.get('sha256') == digest(text.encode('utf-8'))
               and str(e.get('approval_ref', '')).strip() and str(e.get('reason', '')).strip()
               for e in state.get('literal_exceptions', []))


def scan_sources(root: Path, state: dict, mode: str) -> tuple[list[str], list[str]]:
    errors, notes = [], []
    ledger = {t['id']: t for t in state['todos']}
    guard_sha = sha(KIT / 'assets/paper-todos.sty')
    seen = set()
    for p in source_files(root, TEXT):
        rel = p.relative_to(root).as_posix()
        if p.name == 'paper-todos.sty' and sha(p) == guard_sha:
            continue  # Only the exact unmodified guard implementation is exempt.
        text = p.read_text(encoding='utf-8')
        masked = list(text)
        for match in WRAPPER.finditer(text):
            line = text[:match.start()].count('\n') + 1
            try:
                identifier, end = group(text, match.end())
                if match.group().startswith('\\PaperTODO'):
                    body, end = group(text, end)
                else:
                    close = re.search(r'\\end\s*\{PaperProvisional\}', text[end:])
                    if close is None:
                        raise ValueError('Unclosed provisional environment')
                    body, end = text[end:end + close.start()], end + close.end()
                if not re.fullmatch(r'T[0-9]{3,}', identifier):
                    raise ValueError('Invalid TODO ID')
                item = ledger.get(identifier)
                if not item or not str(item.get('approval_ref', '')).strip():
                    errors.append(f'{rel}:{line}: unapproved TODO {identifier}')
                elif item.get('file') != rel or item.get('body_sha256') != body_hash(body):
                    errors.append(f'{rel}:{line}: TODO {identifier} differs from approved file/body')
                elif item['status'] != 'open':
                    errors.append(f'{rel}:{line}: closed TODO {identifier} is still in source')
                if identifier in seen:
                    errors.append(f'{rel}:{line}: duplicate TODO occurrence {identifier}')
                seen.add(identifier)
                if mode == 'submission':
                    errors.append(f'{rel}:{line}: provisional wrapper remains: {identifier}')
                for i in range(match.start(), end):
                    if masked[i] != '\n':
                        masked[i] = ' '
            except ValueError as exc:
                errors.append(f'{rel}:{line}: malformed provisional wrapper ({exc})')
        for line, content in enumerate(''.join(masked).splitlines(), 1):
            original_line = text.splitlines()[line - 1]
            if MARKER.search(content) and not literal_allowed(state, rel, line, original_line):
                errors.append(f'{rel}:{line}: unwrapped placeholder marker')
        if mode == 'submission' and re.search(r'\\usepackage\s*\[[^]]*\bdraft\b[^]]*\]\s*\{paper-todos\}', text):
            errors.append(f'{rel}: paper-todos is still explicitly in draft mode')
    for item in ledger.values():
        if item['status'] == 'open':
            message = f'Open author-approved TODO {item["id"]}: {item.get("file", "?")}'
            (errors if mode == 'submission' else notes).append(message)
    return errors, notes


def add_todo(root: Path, identifier: str, filename: str, text: str, approval_ref: str) -> str:
    if not re.fullmatch(r'T[0-9]{3,}', identifier) or not approval_ref.strip() or not text.strip():
        raise ValueError('Require an ID such as T001, nonempty body, and actual author approval reference.')
    p = safe(root, filename)
    if p.suffix not in {'.tex', '.tikz', '.pgf'}:
        raise ValueError('TODO target must be a manuscript TeX/figure source.')
    state = load_state(root)
    if any(t['id'] == identifier for t in state['todos']):
        raise ValueError('TODO ID already exists; do not overwrite approval history.')
    state['todos'].append({'id': identifier, 'file': p.relative_to(root.resolve()).as_posix(),
                           'body': text.strip(), 'body_sha256': body_hash(text),
                           'approval_ref': approval_ref.strip(), 'created_at': now(), 'status': 'open'})
    dump(safe(root, '.paper/state.json'), state)
    return '\\PaperTODO{' + identifier + '}{' + text.strip() + '}'


def close_todo(root: Path, identifier: str, disposition: str, approval_ref: str, note: str) -> None:
    if disposition not in ('resolved', 'removed') or not approval_ref.strip() or not note.strip():
        raise ValueError('Require resolved/removed disposition, approval reference, and explanatory note.')
    state = load_state(root)
    item = next((t for t in state['todos'] if t['id'] == identifier), None)
    if item is None or item['status'] != 'open':
        raise ValueError('No open TODO with that ID.')
    for p in source_files(root, TEXT):
        text = p.read_text(encoding='utf-8')
        if re.search(r'\\(?:PaperTODO\s*|begin\s*\{PaperProvisional\}\s*)\{' + re.escape(identifier) + r'\}', text):
            raise ValueError('Remove/resolve the actual wrapper before closing its ledger entry.')
    item.update(status=disposition, closed_at=now(), decision_ref=approval_ref, disposition_note=note)
    dump(safe(root, '.paper/state.json'), state)


def tool_run(argv: list[str], cwd: Path | None = None, timeout: int = 90,
             cancel_event=None) -> subprocess.CompletedProcess:
    """Run a local tool with bounded time and process-group cancellation."""
    if cancel_event is not None and cancel_event.is_set():
        raise ValueError('Local tool cancelled before launch.')
    process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True,
                               start_new_session=os.name == 'posix')
    deadline = time.monotonic() + timeout
    def stop():
        try:
            if os.name == 'posix': os.killpg(process.pid, signal.SIGTERM)
            else: process.terminate()
        except ProcessLookupError:
            pass
        try:
            return process.communicate(timeout=1)[0]
        except subprocess.TimeoutExpired:
            try:
                if os.name == 'posix': os.killpg(process.pid, signal.SIGKILL)
                else: process.kill()
            except ProcessLookupError:
                pass
            return process.communicate()[0]
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                stop()
                raise ValueError('Local tool cancelled.')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                output = stop()
                raise subprocess.TimeoutExpired(argv, timeout, output=output)
            try:
                output, _ = process.communicate(timeout=min(0.1, remaining))
                return subprocess.CompletedProcess(argv, process.returncode, output)
            except subprocess.TimeoutExpired:
                continue
    except BaseException:
        if process.poll() is None:
            stop()
        raise


def build(root: Path, main: str, allow: bool, cancel_event=None) -> dict:
    if not allow:
        raise ValueError('Building executes LaTeX; obtain permission and pass --allow-build.')
    root = root.resolve()
    binary = shutil.which('latexmk')
    if not binary:
        raise ValueError('latexmk is unavailable. Do not auto-install.')
    main_path = safe(root, main)
    if not main_path.is_file() or main_path.suffix != '.tex':
        raise ValueError('Main TeX source is missing.')
    before = snapshot(root)
    out = safe(root, '.paper/build')
    out.mkdir(parents=True, exist_ok=True)
    receipt_path = safe(root, '.paper/build-receipt.json')
    receipt_path.unlink(missing_ok=True)
    argv = [binary, '-norc', '-pdf', '-interaction=nonstopmode', '-halt-on-error',
            '-file-line-error', '-recorder', '-no-shell-escape', '-outdir=' + str(out), str(main_path)]
    completed = tool_run(argv, cwd=root, timeout=180, cancel_event=cancel_event)
    safe(root, '.paper/build-command.log').write_text(completed.stdout, encoding='utf-8')
    if completed.returncode:
        raise ValueError('LaTeX build failed; see .paper/build-command.log. No valid receipt was retained.')
    pdf, log = out / (main_path.stem + '.pdf'), out / (main_path.stem + '.log')
    if not pdf.is_file() or not log.is_file():
        raise ValueError('Build did not produce the expected PDF and log.')
    if before != snapshot(root):
        raise ValueError('Tracked inputs changed during build; rebuild a stable snapshot.')
    # Reject hidden/library inputs that would otherwise evade the content snapshot.
    fls = out / (main_path.stem + '.fls')
    if not fls.is_file():
        raise ValueError('Recorder output is missing.')
    recorded_inputs = {}
    for entry in fls.read_text(errors='replace').splitlines():
        if not entry.startswith('INPUT '):
            continue
        candidate = (root / entry[6:]).resolve()
        if candidate.is_file():
            recorded_inputs[str(candidate)] = sha(candidate)
        if candidate.is_relative_to(root) and not candidate.is_relative_to(out):
            parts = candidate.relative_to(root).parts
            if any(part in SKIP for part in parts):
                raise ValueError(f'Manuscript input in excluded state/tool/library folder: {candidate}')
    receipt = {'schema_version': 1, 'created_at': now(), 'main': main_path.relative_to(root).as_posix(),
               'inputs': before, 'recorded_inputs': recorded_inputs,
               'pdf': pdf.relative_to(root).as_posix(), 'pdf_sha256': sha(pdf),
               'log': log.relative_to(root).as_posix(), 'log_sha256': sha(log), 'argv': argv}
    dump(receipt_path, receipt)
    return receipt


def extract_pdf(pdf: Path) -> str:
    binary = shutil.which('pdftotext')
    if not binary:
        raise ValueError('pdftotext is unavailable; PDF text check cannot pass.')
    result = tool_run([binary, '-layout', str(pdf), '-'], timeout=90)
    if result.returncode:
        raise ValueError('PDF text extraction failed.')
    if not result.stdout.strip():
        raise ValueError('No PDF text extracted; require manual inspection, not a false pass.')
    return result.stdout


def release_fingerprint(root: Path) -> str:
    receipt = json.loads(safe(root, '.paper/build-receipt.json').read_text())
    value = {'inputs': snapshot(root), 'state': load_state(root), 'receipt': receipt,
             'pdf_sha256': sha(safe(root, receipt['pdf'])), 'log_sha256': sha(safe(root, receipt['log'])),
             'visual_audit_sha256': sha(safe(root, '.paper/visual/audit.json')),
             'readability_review_sha256': sha(safe(root, '.paper/readability-review.json'))}
    return digest(json.dumps(value, sort_keys=True).encode('utf-8'))


def candidate_fingerprint(root: Path) -> str:
    """Bind an editorial observation to the exact built candidate, not a score."""
    receipt_path = safe(root, '.paper/build-receipt.json')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt.get('inputs') != snapshot(root):
        raise ValueError('Manuscript/config/data changed since build; rebuild before recording the review.')
    for key in ('pdf', 'log'):
        path = safe(root, receipt[key])
        if not path.is_file() or sha(path) != receipt.get(key + '_sha256'):
            raise ValueError('Built ' + key + ' is missing or changed.')
    return digest(json.dumps({'inputs': snapshot(root), 'receipt': receipt}, sort_keys=True).encode())


def check_readability_review(root: Path) -> dict:
    errors, warnings = [], []
    try:
        entry = json.loads(safe(root, '.paper/readability-review.json').read_text(encoding='utf-8'))
        required = {'schema_version', 'created_at', 'report', 'report_sha256', 'candidate_fingerprint',
                    'observation_ref', 'coverage', 'disposition'}
        if not isinstance(entry, dict) or set(entry) != required or entry['schema_version'] != 1:
            raise ValueError('Unsupported readability-review record.')
        for key in ('observation_ref', 'coverage', 'disposition'):
            if not isinstance(entry[key], str) or not entry[key].strip():
                raise ValueError('Readability review lacks ' + key + '.')
        report = safe(root, entry['report'])
        result = readability.check_report(report, project=root)
        errors.extend(result['errors'])
        warnings.extend(result.get('warnings', []))
        if not report.is_file() or sha(report) != entry['report_sha256']:
            errors.append('Readability report changed since interpretation.')
        if entry['candidate_fingerprint'] != candidate_fingerprint(root):
            errors.append('Readability interpretation is stale for this manuscript candidate.')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.append('Readability review incomplete: ' + str(exc))
    return {'passed': not errors, 'errors': errors, 'warnings': warnings,
            'scope': 'Fresh measurements and recorded interpretation, never a score threshold or proof of comprehension.'}


def record_readability_review(root: Path, report: Path, observation_ref: str,
                             coverage: str, disposition: str) -> dict:
    if not observation_ref.strip() or len(coverage.strip()) < 24 or len(disposition.strip()) < 24:
        raise ValueError('Provide a real observation reference, specific extraction coverage, and a substantive disposition of flags.')
    report = safe(root, report)
    result = readability.check_report(report, project=root)
    if not result['passed']:
        raise ValueError('Readability review blocked: ' + '; '.join(result['errors']))
    entry = {'schema_version': 1, 'created_at': now(), 'report': report.relative_to(root.resolve()).as_posix(),
             'report_sha256': sha(report), 'candidate_fingerprint': candidate_fingerprint(root),
             'observation_ref': observation_ref.strip(), 'coverage': coverage.strip(),
             'disposition': disposition.strip()}
    dump(safe(root, '.paper/readability-review.json'), entry)
    return {'recorded': True, 'warnings': result.get('warnings', []),
            'scope': 'Editorial attestation only. No numerical threshold or automatic rewrite.'}


def preflight(root: Path, mode: str = 'draft', require_signoff: bool = True) -> dict:
    root = root.resolve()
    state = load_state(root)
    errors, notes = scan_sources(root, state, mode)
    if not any(p.suffix == '.tex' and p.name != 'paper-todos.sty' for p in source_files(root, TEXT)):
        errors.append('No manuscript TeX sources found.')
    if mode == 'submission':
        for item in state.get('questions', []) + state.get('decisions', []):
            if item.get('blocking') is True and item.get('status', 'open') == 'open':
                errors.append('Unresolved scientific/author decision: ' + str(item.get('id', '?')))
        receipt_file = safe(root, '.paper/build-receipt.json')
        if not receipt_file.is_file():
            errors.append('Managed build receipt missing.')
        else:
            receipt = json.loads(receipt_file.read_text())
            for path, expected in receipt.get('recorded_inputs', {}).items():
                recorded = Path(path)
                if not recorded.is_file() or sha(recorded) != expected:
                    errors.append(f'Recorded LaTeX input missing or changed: {path}')
            if receipt.get('inputs') != snapshot(root):
                errors.append('Manuscript/config/data snapshot changed since build.')
            for key in ('pdf', 'log'):
                p = safe(root, receipt[key])
                if not p.is_file() or sha(p) != receipt.get(key + '_sha256'):
                    errors.append(f'{key.upper()} missing or changed since managed build.')
            pdf = safe(root, receipt['pdf'])
            if pdf.is_file():
                visual = visual_audit.check_audit(pdf, safe(root, '.paper/visual/audit.json'))
                errors.extend('Visual audit: ' + e for e in visual['errors'])
                try:
                    for number, line in enumerate(extract_pdf(pdf).splitlines(), 1):
                        if MARKER.search(line) and not literal_allowed(state, '@pdf', number, line):
                            errors.append(f'PDF text line {number}: placeholder/unresolved marker')
                except ValueError as exc:
                    errors.append(str(exc))
            log = safe(root, receipt['log'])
            if log.is_file():
                log_text = log.read_text(errors='replace')
                if re.search(r'(?:Citation|Reference)[^\n]*undefined|There were undefined|LaTeX Error|Package [^\n]* Error|^!', log_text, re.I | re.M):
                    errors.append('Build log contains undefined references/citations or TeX errors.')
                if re.search(r'Overfull \\[hv]box', log_text):
                    notes.append('Overfull boxes reported: verify actual layout, do not assume harmless.')
        readability_result = check_readability_review(root)
        errors.extend(readability_result['errors'])
        notes.extend(readability_result['warnings'])
        if require_signoff:
            approval_path = safe(root, '.paper/release-approval.json')
            if not approval_path.is_file():
                errors.append('Exact-artifact author release signoff missing.')
            elif receipt_file.is_file():
                approval = json.loads(approval_path.read_text())
                if set(approval.get('checks', [])) != CHECKS or not approval.get('approval_ref'):
                    errors.append('Release signoff does not attest all required checks.')
                try:
                    if approval.get('fingerprint') != release_fingerprint(root):
                        errors.append('Release signoff is stale; inspect and approve the changed candidate.')
                except (KeyError, OSError, ValueError) as exc:
                    errors.append(f'Cannot validate release fingerprint: {exc}')
    return {'mode': mode, 'passed': not errors, 'errors': errors, 'notes': notes,
            'scope': 'Implemented hygiene checks, not proof of scientific or visual correctness.'}


def approve_release(root: Path, approval_ref: str, checks: set[str]) -> None:
    if not approval_ref.strip() or checks != CHECKS:
        raise ValueError('Require a real author approval reference and all eight actual inspections.')
    result = preflight(root, 'submission', require_signoff=False)
    if not result['passed']:
        raise ValueError('Release blocked: ' + '; '.join(result['errors']))
    dump(safe(root, '.paper/release-approval.json'), {'approval_ref': approval_ref,
         'created_at': now(), 'checks': sorted(checks), 'fingerprint': release_fingerprint(root)})


def ingest(root: Path, pdf: Path, title: str, url: str, role: str) -> dict:
    pdf = pdf.resolve()
    if not pdf.is_file() or pdf.read_bytes()[:5] != b'%PDF-':
        raise ValueError('Input is not a local PDF.')
    identifier = sha(pdf)
    index_path = safe(root, 'sources/index.json')
    index = json.loads(index_path.read_text()) if index_path.exists() else {'schema_version': 1, 'papers': []}
    existing = next((p for p in index['papers'] if p['sha256'] == identifier), None)
    if existing:
        return existing
    destination = safe(root, f'sources/pdfs/{identifier[:16]}.pdf')
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf, destination)
    item = {'sha256': identifier, 'title': title or pdf.stem, 'metadata_verified': False,
            'provided_url': url or None, 'role': role, 'acquired_at': now(),
            'pdf': destination.relative_to(root).as_posix(), 'read_status': 'unread',
            'reading_coverage': [], 'visual_inspection': False}
    try:
        text = extract_pdf(destination)
        target = safe(root, f'sources/text/{identifier[:16]}.txt')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
        item.update(extraction='complete', text=target.relative_to(root).as_posix())
    except ValueError as exc:
        item.update(extraction='unavailable', extraction_note=str(exc))
    index['papers'].append(item)
    dump(index_path, index)
    return item


def prepare_review(pdf: Path, output: Path, mode: str) -> dict:
    if mode not in ('development', 'submission_mock'):
        raise ValueError('Unsupported review mode.')
    pdf = pdf.resolve()
    if not pdf.is_file() or pdf.read_bytes()[:5] != b'%PDF-':
        raise ValueError('Supply a valid manuscript PDF.')
    if output.exists():
        raise ValueError('Choose a new packet directory; never overwrite a frozen review.')
    # Prepare in a temporary sibling to avoid publishing a partial packet.
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='.packet-', dir=output.parent))
    try:
        shutil.copyfile(pdf, tmp / 'manuscript.pdf')
        (tmp / 'manuscript.txt').write_text(extract_pdf(pdf), encoding='utf-8')
        shutil.copyfile(KIT / 'rubrics/user-supplied-iclr-form.md', tmp / 'rubric.md')
        shutil.copyfile(KIT / 'prompts/scientific-reviewer.md', tmp / 'instructions.md')
        shutil.copyfile(KIT / 'schemas/review.schema.json', tmp / 'review.schema.json')
        files = {p.name: sha(p) for p in sorted(tmp.iterdir())}
        packet_hash = digest(json.dumps({'mode': mode, 'files': files}, sort_keys=True).encode())
        manifest = {'mode': mode, 'packet_hash': packet_hash, 'files': files,
                    'rubric_provenance': 'user_supplied_exact_official_year_unverified',
                    'visual_access': 'PDF included; receiver must actually inspect rendered pages.',
                    'isolation': 'Content minimized; runtime/context isolation is the host responsibility.'}
        dump(tmp / 'packet.json', manifest)
        tmp.rename(output)
        return manifest
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise


def validate_review_packet(value: dict, packet: Path) -> list[str]:
    """Check review structure, frozen packet bytes, and review-to-packet identity."""
    errors = validate_review(value)
    try:
        packet = packet.resolve()
        manifest = json.loads((packet / 'packet.json').read_text(encoding='utf-8'))
        expected = {'manuscript.pdf', 'manuscript.txt', 'rubric.md',
                    'instructions.md', 'review.schema.json'}
        files = manifest.get('files')
        mode = manifest.get('mode')
        if mode not in ('development', 'submission_mock') or not isinstance(files, dict) or set(files) != expected:
            return errors + ['Invalid frozen packet manifest.']
        for name, recorded_hash in files.items():
            path = packet / name
            if path.is_symlink() or not path.is_file() or sha(path) != recorded_hash:
                errors.append(f'Frozen packet file missing or changed: {name}')
        computed = digest(json.dumps({'mode': mode, 'files': files}, sort_keys=True).encode())
        if manifest.get('packet_hash') != computed:
            errors.append('Frozen packet manifest hash does not match its contents.')
        if isinstance(value, dict):
            if value.get('packet_hash') != computed:
                errors.append('Review belongs to a different frozen packet.')
            if value.get('mode') != mode:
                errors.append('Review mode differs from the frozen packet.')
    except (OSError, ValueError, TypeError, AttributeError):
        errors.append('Frozen packet is unreadable or malformed.')
    return errors


def validate_review(value: dict) -> list[str]:
    errors = []
    required = {'mode', 'packet_hash', 'reviewer_id', 'coverage', 'summary', 'presentation',
                'informativeness', 'soundness', 'critical_strengths', 'critical_weaknesses',
                'questions_for_authors', 'rating', 'improvement_plan', 'reviewer_perspective',
                'ethics_review', 'confidence'}
    if not isinstance(value, dict):
        return ['Review must be an object.']
    if set(value) != required:
        errors.append('Review keys must exactly match the schema.')
    mode = value.get('mode')
    if mode not in ('development', 'submission_mock'):
        errors.append('Invalid review mode.')
    if not re.fullmatch(r'[0-9a-f]{64}', str(value.get('packet_hash', ''))):
        errors.append('Invalid packet hash.')
    def nonempty(x):
        return isinstance(x, str) and bool(x.strip())
    for field in ('summary', 'reviewer_id'):
        if not nonempty(value.get(field)):
            errors.append(f'{field} is required.')
    if value.get('reviewer_perspective') not in ('soundness_methods', 'evidence_evaluation', 'significance_positioning', 'general'):
        errors.append('Unknown reviewer perspective.')
    ethics = value.get('ethics_review')
    if not isinstance(ethics, dict) or set(ethics) != {'answer', 'details'}:
        errors.append('Ethics review needs answer and details.')
    elif ethics['answer'] not in ('yes', 'no') or not isinstance(ethics['details'], str):
        errors.append('Ethics review needs a yes/no answer and text details.')
    elif ethics['answer'] == 'yes' and not nonempty(ethics['details']):
        errors.append('Ethics concerns require details.')
    coverage = value.get('coverage')
    if not isinstance(coverage, list) or not coverage or not all(nonempty(x) for x in coverage):
        errors.append('Coverage must explicitly list examined material/capability limitations.')
    for field, high in [('presentation', 3), ('informativeness', 3), ('soundness', 3), ('rating', 4), ('confidence', 4)]:
        item = value.get(field)
        if not isinstance(item, dict) or set(item) != {'score', 'rationale'}:
            errors.append(f'{field} needs score and rationale.')
            continue
        score = item['score']
        if not (mode == 'development' and score is None) and not (type(score) is int and 1 <= score <= high):
            errors.append(f'{field} score out of range or not assessable in this mode.')
        if not nonempty(item['rationale']):
            errors.append(f'{field} rationale missing.')
    for field in ('critical_strengths', 'critical_weaknesses'):
        items = value.get(field)
        if not isinstance(items, list) or len(items) > 2:
            errors.append(f'{field} must contain zero to two consequential findings.')
            continue
        for item in items:
            if not isinstance(item, dict) or set(item) != {'claim', 'location', 'why_consequential'} or not all(nonempty(v) for v in item.values()):
                errors.append(f'{field} finding needs claim, location, and consequential rationale.')
    questions = value.get('questions_for_authors')
    if not isinstance(questions, list):
        errors.append('Questions must be an array.')
    else:
        for q in questions:
            if not isinstance(q, dict) or set(q) != {'question', 'location', 'assessment_effect'} or not all(nonempty(v) for v in q.values()):
                errors.append('Each question needs location and material assessment effect.')
    plan = value.get('improvement_plan')
    if not isinstance(plan, list):
        errors.append('Improvement plan must be an array.')
    else:
        for action in plan:
            keys = {'category', 'priority', 'claim', 'evidence', 'action', 'completion_criterion', 'resolution_basis'}
            if not isinstance(action, dict) or not keys <= set(action) or set(action) - keys - {'experiment_design'}:
                errors.append('Improvement action has invalid fields.')
                continue
            if not all(nonempty(action[k]) for k in keys):
                errors.append('Improvement action fields must be nonempty strings.')
            if action['category'] not in ('clarification', 'writing', 'verification', 'experiment', 'theory', 'positioning', 'optional_extension'):
                errors.append('Unknown action category.')
            if action['resolution_basis'] not in ('writing', 'existing_evidence', 'new_research', 'author_clarification'):
                errors.append('Unknown action resolution basis.')
            if action['category'] in ('experiment', 'theory') and action['resolution_basis'] != 'new_research':
                errors.append('Experiments and missing theory require new research, not a writing fix.')
            if action['priority'] not in ('decision_critical', 'useful', 'optional'):
                errors.append('Unknown action priority.')
            if action['category'] == 'optional_extension' and action['priority'] != 'optional':
                errors.append('An optional extension cannot be a decision-critical requirement.')
            if action['category'] == 'experiment':
                exp = action.get('experiment_design')
                if not isinstance(exp, dict) or set(exp) != {'hypothesis', 'comparison', 'controls', 'metric', 'possible_outcomes', 'stop_condition'} or not all(nonempty(v) for v in exp.values()):
                    errors.append('Experiment needs hypothesis, comparison, controls, metric, possible outcomes, and stop condition.')
            elif 'experiment_design' in action:
                errors.append('Experiment design belongs only to experiment actions.')
    return errors


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    for name in ('preflight', 'build', 'approve-release', 'readability-review', 'todo-add', 'todo-close', 'ingest'):
        s = sub.add_parser(name)
        s.add_argument('project', type=Path)
        if name == 'preflight':
            s.add_argument('--mode', choices=['draft', 'submission'], default='draft')
        elif name == 'build':
            s.add_argument('--main', default='main.tex')
            s.add_argument('--allow-build', action='store_true')
        elif name == 'approve-release':
            s.add_argument('--approval-ref', required=True)
            s.add_argument('--checks', required=True, help=','.join(sorted(CHECKS)))
        elif name == 'readability-review':
            s.add_argument('--report', required=True, type=Path)
            s.add_argument('--observation-ref', required=True)
            s.add_argument('--coverage', required=True)
            s.add_argument('--disposition', required=True)
        elif name == 'todo-add':
            s.add_argument('--id', required=True)
            s.add_argument('--file', required=True)
            s.add_argument('--text', required=True)
            s.add_argument('--approval-ref', required=True)
        elif name == 'todo-close':
            s.add_argument('--id', required=True)
            s.add_argument('--disposition', choices=['resolved', 'removed'], required=True)
            s.add_argument('--approval-ref', required=True)
            s.add_argument('--note', required=True)
        elif name == 'ingest':
            s.add_argument('--pdf', required=True, type=Path)
            s.add_argument('--title', default='')
            s.add_argument('--url', default='')
            s.add_argument('--role', choices=['style', 'background', 'both'], default='background')
    s = sub.add_parser('prepare-review')
    s.add_argument('--pdf', required=True, type=Path)
    s.add_argument('--output', required=True, type=Path)
    s.add_argument('--mode', choices=['development', 'submission_mock'], default='development')
    s = sub.add_parser('validate-review')
    s.add_argument('review', type=Path)
    s.add_argument('--packet', type=Path, help='Verify frozen bytes and bind this review to its packet.')
    args = p.parse_args()
    try:
        root = args.project.resolve() if hasattr(args, 'project') else None
        if args.command == 'preflight':
            result = preflight(root, args.mode)
        elif args.command == 'build':
            result = build(root, args.main, args.allow_build)
        elif args.command == 'approve-release':
            approve_release(root, args.approval_ref, set(args.checks.split(',')))
            result = {'recorded': True, 'note': 'Attestation recorded; not an automated science/visual audit.'}
        elif args.command == 'readability-review':
            result = record_readability_review(root, args.report, args.observation_ref, args.coverage, args.disposition)
        elif args.command == 'todo-add':
            result = {'wrapper_to_insert_after_approval': add_todo(root, args.id, args.file, args.text, args.approval_ref)}
        elif args.command == 'todo-close':
            close_todo(root, args.id, args.disposition, args.approval_ref, args.note)
            result = {'closed': args.id, 'disposition': args.disposition}
        elif args.command == 'ingest':
            result = ingest(root, args.pdf, args.title, args.url, args.role)
        elif args.command == 'prepare-review':
            result = prepare_review(args.pdf, args.output, args.mode)
        else:
            review = json.loads(args.review.read_text())
            errors = (validate_review_packet(review, args.packet) if args.packet
                      else validate_review(review))
            result = {'passed': not errors, 'errors': errors,
                      'validation_scope': 'packet_and_structure' if args.packet else 'structure_only'}
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if result.get('passed') is False else 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
