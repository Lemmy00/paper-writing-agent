from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import providers

SCHEMA = {'type': 'object', 'additionalProperties': False,
          'required': ['answer'], 'properties': {
              'answer': {'type': 'string', 'minLength': 1},
              'extra': {'type': 'string'}}}

FAKE = r'''
import json, os, pathlib, subprocess, sys, time
args=sys.argv[1:]
if '--version' in args:
    print('test-cli 9.0');sys.exit(0)
if '--help' in args:
    print('--ignore-user-config --ephemeral --json --output-schema --sandbox --safe-mode '
          '--restricted --tools --strict-mcp-config --json-schema --no-session-persistence '
          '--permission-prompts --settings --print-timeout --output-format --input-format --mode',
          file=sys.stderr if os.environ.get('FAKE_HELP_STDERR') else sys.stdout)
    sys.exit(0)
stdin=sys.stdin.read()
pathlib.Path(os.environ['FAKE_TRACE']).write_text(json.dumps({'args':args,'stdin':stdin,'cwd':os.getcwd()}))
mode=os.environ.get('FAKE_MODE','ok')
if mode=='sleep':
    marker=os.environ['FAKE_CHILD_MARKER']
    subprocess.Popen([sys.executable,'-c',
        'import pathlib,time,sys;time.sleep(.4);pathlib.Path(sys.argv[1]).write_text("survived")',marker])
    time.sleep(30)
if mode=='flood':
    sys.stdout.write('x'*(4*1024*1024));sys.stdout.flush();sys.exit(0)
if mode=='exit':
    sys.stderr.write('API_KEY=sk-super-secret-fake-value');sys.exit(7)
if mode=='invalid':
    print('not json');sys.exit(0)
name=pathlib.Path(sys.argv[0]).name
value={'answer':True} if mode=='badshape' else {'answer':'ok'}
if name=='codex':
    if mode=='auth':
        print(json.dumps({'type':'turn.failed','error':{'message':'login required'}}));sys.exit(0)
    if mode=='tool':
        print(json.dumps({'type':'item.completed','item':{'type':'command_execution'}}))
    value['extra']=None
    pathlib.Path(args[args.index('--output-last-message')+1]).write_text(json.dumps(value))
    print(json.dumps({'type':'thread.started','thread_id':'fresh'}))
    print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':json.dumps(value)}}))
    print(json.dumps({'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':3}}))
elif name=='claude':
    print(json.dumps({'type':'result','subtype':'error_auth' if mode=='auth' else 'success',
      'is_error':mode=='auth','structured_output':value,'usage':{'input_tokens':10},
      'modelUsage':{'test-model':{}},'total_cost_usd':0.01}))
else:
    print(json.dumps({'event':'init','init':{'tools':[]}}))
    if mode=='metadata_tool':
        print(json.dumps({'event':'init','step_update':{'step_type':'tool','tool_name':'run_command'},
                         'init':{'tools':['run_command']}}))
    if mode in ('finish','finish_invalid','finish_error','finish_impersonation','finish_deltas',
                'finish_missing_output','finish_partial_error','tool','secret_tool'):
        name='finish' if mode.startswith('finish') else 'run_command'
        if mode=='secret_tool': name='API_KEY=sk-must-not-appear-in-receipt'
        info={'name':'run_command' if mode=='finish_impersonation' else name,
              'parameters':{'private':'SECRET_INLINE_PACKET'},'output':'SECRET_TOOL_OUTPUT'}
        if mode=='finish_error': info['error']={'message':'SECRET_ERROR'}
        if mode in ('finish_deltas','finish_partial_error'):
            for detail in [None, {}, {'name':'finish'}]:
                step={'step_type':'tool','tool_name':'finish','state':'ACTIVE'}
                if detail is not None: step['tool_info']=detail
                if mode=='finish_partial_error' and detail is None:
                    step['tool_info']={'error':{'message':'SECRET_ERROR'}}
                print(json.dumps({'event':'step_update','step_update':step}))
            print(json.dumps({'event':'step_update','step_update':{'step_type':'finish','state':'DONE'}}))
        else:
            print(json.dumps({'event':'step_update','step_update':{
                'step_type':'tool','tool_name':name,'state':'DONE','tool_info':info}}))
        if mode=='finish_invalid': value={'answer':False}
    result={'status':'ERROR' if mode=='auth' else 'SUCCESS',
      'error':'login required' if mode=='auth' else '', 'structured_output':value,
      'usage':{'input_tokens':10}}
    if mode=='finish_missing_output': result.pop('structured_output')
    print(json.dumps({'event':'result','result':result}))
    if mode=='two_turns': print(json.dumps({'event':'result','result':result}))
'''


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.bin = self.root / 'bin'; self.bin.mkdir()
        self.cwd = self.root / 'job'; self.cwd.mkdir()
        self.trace = self.root / 'trace.json'
        self.marker = self.root / 'child-survived'
        for name in providers.BINARIES.values():
            path = self.bin / name
            path.write_text('#!' + sys.executable + '\n' + FAKE)
            path.chmod(0o755)
        self.environment = patch.dict(os.environ, {
            'PATH': str(self.bin) + os.pathsep + os.environ.get('PATH', ''),
            'FAKE_TRACE': str(self.trace), 'FAKE_MODE': 'ok',
            'FAKE_CHILD_MARKER': str(self.marker)})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.tmp.cleanup()

    def run_provider(self, provider='codex', **kwargs):
        return providers.run_job(provider, 'Synthetic review fixture only.', SCHEMA, self.cwd, **kwargs)

    def test_all_provider_envelopes_and_native_commands(self):
        for name in providers.BINARIES:
            with self.subTest(provider=name):
                result = self.run_provider(name, model='explicit-model')
                self.assertEqual(result['output'], {'answer': 'ok'})
                self.assertEqual(result['receipt']['provider'], name)
                self.assertEqual(result['receipt']['model_requested'], 'explicit-model')
                self.assertEqual(result['receipt']['usage']['input_tokens'], 10)
                trace = json.loads(self.trace.read_text())
                self.assertIn('Synthetic review fixture only.', trace['stdin'])
                self.assertNotIn('Synthetic review fixture only.', ' '.join(trace['args']))
                self.assertEqual(Path(trace['cwd']), self.cwd)
                self.assertFalse(any('dangerous' in part for part in trace['args']))
                self.assertNotIn('--continue', trace['args'])
                self.assertNotIn('--resume', trace['args'])
                if name == 'codex':
                    self.assertIn('features.shell_tool=false', trace['args'])
                    path = Path(trace['args'][trace['args'].index('--output-schema')+1])
                    self.assertFalse(path.parent.exists())
                elif name == 'claude':
                    self.assertIn('--safe-mode', trace['args'])
                    self.assertEqual(trace['args'][trace['args'].index('--tools')+1], '')
                else:
                    self.assertNotIn('--print', trace['args'])
                    self.assertEqual(trace['args'][trace['args'].index('--input-format')+1], 'stream-json')
                    message = json.loads(trace['stdin'])
                    self.assertEqual(message['event'], 'user')
                    self.assertIn('Synthetic review fixture only.', message['message']['content'])
                    settings = json.loads(trace['args'][trace['args'].index('--settings')+1])
                    self.assertIn('command(*)', settings['permissions']['deny'])
                    self.assertTrue(any('persistence' in x for x in result['receipt']['limitations']))

    def test_errors_inside_successful_process_are_not_success(self):
        for mode, code in [('auth', 'provider_failed'), ('invalid', 'invalid_output'),
                           ('badshape', 'invalid_output')]:
            for provider in providers.BINARIES:
                with self.subTest(mode=mode, provider=provider), patch.dict(os.environ, {'FAKE_MODE': mode}):
                    with self.assertRaises(providers.ProviderError) as caught:
                        self.run_provider(provider)
                    self.assertEqual(caught.exception.code, code)

    def test_nonzero_exit_redacts_diagnostic_secrets(self):
        with patch.dict(os.environ, {'FAKE_MODE': 'exit'}):
            with self.assertRaises(providers.ProviderError) as caught:
                self.run_provider()
        self.assertEqual(caught.exception.code, 'provider_failed')
        self.assertNotIn('super-secret', str(caught.exception))
        self.assertEqual(caught.exception.receipt['provider'], 'codex')

    def test_invalid_parsed_output_is_transient_and_receipt_keeps_usage(self):
        with patch.dict(os.environ, {'FAKE_MODE': 'badshape'}):
            with self.assertRaises(providers.ProviderError) as caught:
                self.run_provider('claude')
        self.assertEqual(caught.exception.output, {'answer': True})
        self.assertEqual(caught.exception.receipt['usage'], {'input_tokens': 10})
        self.assertNotIn('answer', json.dumps(caught.exception.receipt))

    def test_unexpected_codex_tool_event_is_rejected(self):
        with patch.dict(os.environ, {'FAKE_MODE': 'tool'}):
            with self.assertRaises(providers.ProviderError) as caught:
                self.run_provider()
        self.assertEqual(caught.exception.code, 'tool_use')

    def test_antigravity_rejects_multiple_turns_in_one_fresh_job(self):
        with patch.dict(os.environ, {'FAKE_MODE': 'two_turns'}):
            with self.assertRaises(providers.ProviderError) as caught:
                self.run_provider('antigravity')
        self.assertEqual(caught.exception.code, 'protocol_error')

    def test_antigravity_native_finish_still_validates_original_schema(self):
        with patch.dict(os.environ, {'FAKE_MODE': 'finish'}):
            result = self.run_provider('antigravity')
        self.assertEqual(result['output'], {'answer': 'ok'})
        self.assertEqual(result['receipt']['native_serialization'], ['finish'])
        self.assertEqual(result['receipt']['protocol']['tool_names'], {'finish': 1})
        for mode, code in [('finish_invalid', 'invalid_output'), ('finish_error', 'tool_use'),
                           ('finish_impersonation', 'tool_use'), ('tool', 'tool_use'),
                           ('finish_missing_output', 'invalid_output'), ('finish_partial_error', 'tool_use')]:
            with self.subTest(mode=mode), patch.dict(os.environ, {'FAKE_MODE': mode}):
                with self.assertRaises(providers.ProviderError) as caught:
                    self.run_provider('antigravity')
                self.assertEqual(caught.exception.code, code)

    def test_antigravity_native_finish_accepts_partial_stream_updates(self):
        # Compatibility fixture, not a claim of a successful live provider run:
        # the live diagnostic established finish events, but discarded details.
        with patch.dict(os.environ, {'FAKE_MODE': 'finish_deltas'}):
            result = self.run_provider('antigravity')
        protocol = result['receipt']['protocol']
        self.assertEqual(protocol['step_types'], {'tool': 3, 'finish': 1})
        self.assertEqual(protocol['tool_names'], {'finish': 3})
        self.assertEqual([step['has_tool_info'] for step in protocol['finish_updates']], [False, True, True])
        self.assertEqual(protocol['result_summary'], {'status_success': True, 'has_structured_object': True})

    def test_antigravity_discriminators_do_not_inspect_metadata_or_leak_payloads(self):
        with patch.dict(os.environ, {'FAKE_MODE': 'metadata_tool'}):
            result = self.run_provider('antigravity')
        self.assertEqual(result['receipt']['protocol']['tool_names'], {})
        with patch.dict(os.environ, {'FAKE_MODE': 'secret_tool'}):
            with self.assertRaises(providers.ProviderError) as caught:
                self.run_provider('antigravity')
        diagnostic = caught.exception.receipt['protocol']
        self.assertEqual(diagnostic['event_types'], {'init': 1, 'step_update': 1, 'result': 1})
        names = diagnostic['tool_names']
        self.assertEqual(len(names), 1)
        self.assertTrue(next(iter(names)).startswith('unrecognized:'))
        receipt = json.dumps(caught.exception.receipt)
        self.assertNotIn('SECRET', receipt)
        self.assertNotIn('must-not-appear', receipt)

    def test_protocol_diagnostic_names_and_size_are_bounded(self):
        stream = '\n'.join(json.dumps({'event':'secret ' + str(i),
            'step_update': {'step_type':'tool', 'tool_name':'SECRET_TOOL'}}) for i in range(100))
        diagnostic = providers._protocol_diagnostics('antigravity', stream)
        self.assertEqual(diagnostic['event_count'], 100)
        self.assertEqual(len(diagnostic['event_types']), 24)
        self.assertTrue(diagnostic['labels_truncated'])
        self.assertEqual(diagnostic['tool_names'], {})
        self.assertNotIn('secret', json.dumps(diagnostic))

    def test_large_output_is_bounded(self):
        with patch.dict(os.environ, {'FAKE_MODE': 'flood'}):
            with self.assertRaises(providers.ProviderError) as caught:
                self.run_provider()
        self.assertEqual(caught.exception.code, 'output_limit')

    @unittest.skipUnless(os.name == 'posix', 'POSIX process group regression')
    def test_timeout_stops_descendant_process(self):
        with patch.dict(os.environ, {'FAKE_MODE': 'sleep'}):
            with self.assertRaises(providers.ProviderError) as caught:
                self.run_provider(timeout=0.15)
        self.assertEqual(caught.exception.code, 'timeout')
        time.sleep(0.5)
        self.assertFalse(self.marker.exists())

    def test_cancel_before_launch_and_during_job(self):
        event = threading.Event(); event.set()
        with self.assertRaises(providers.ProviderError) as caught:
            self.run_provider(cancel_event=event)
        self.assertEqual(caught.exception.code, 'cancelled')
        self.assertFalse(self.trace.exists())
        event.clear(); timer = threading.Timer(0.35, event.set); timer.start()
        try:
            with patch.dict(os.environ, {'FAKE_MODE': 'sleep'}):
                with self.assertRaises(providers.ProviderError) as caught:
                    self.run_provider(cancel_event=event)
            self.assertEqual(caught.exception.code, 'cancelled')
        finally:
            timer.cancel()

    def test_missing_binary_and_unsafe_context_do_not_launch(self):
        with patch.object(providers.shutil, 'which', return_value=None):
            with self.assertRaises(providers.ProviderError) as caught:
                self.run_provider()
        self.assertEqual(caught.exception.code, 'missing_binary')
        (self.cwd / 'writer-notes.md').write_text('Do not inherit this.')
        with self.assertRaises(providers.ProviderError) as caught:
            self.run_provider()
        self.assertEqual(caught.exception.code, 'unsafe_context')
        self.assertFalse(self.trace.exists())

    def test_schema_transport_restores_optional_fields_and_keeps_required_null(self):
        schema = {'type': 'object', 'additionalProperties': False,
                  'required': ['nullable'], 'properties': {
                      'nullable': {'type': ['integer', 'null']},
                      'optional': {'type': 'string'}}}
        transport = providers.transport_schema(schema)
        self.assertEqual(set(transport['required']), {'nullable', 'optional'})
        restored = providers._restore_optional({'nullable': None, 'optional': None}, schema)
        self.assertEqual(restored, {'nullable': None})
        providers.validate_output(restored, schema)

    def test_action_transport_preserves_discriminator_constraints(self):
        schema = json.loads((ROOT / 'schemas/review.schema.json').read_text())
        transport = providers.transport_schema(schema)
        original = schema['properties']['improvement_plan']['items']
        native = transport['properties']['improvement_plan']['items']
        self.assertEqual(len(native['anyOf']), 7)
        bases = {'category':'writing', 'priority':'decision_critical', 'claim':'claim',
                 'evidence':'evidence', 'action':'action', 'completion_criterion':'done',
                 'resolution_basis':'writing'}
        providers.validate_output(bases, native)
        for category in ('writing', 'verification', 'positioning', 'clarification'):
            action = {**bases, 'category': category, 'experiment_design': {
                key:'planned' for key in original['properties']['experiment_design']['required']}}
            with self.subTest(category=category), self.assertRaises(providers.ProviderError):
                providers.validate_output(action, native)
        for action in [{**bases, 'category':'experiment'},
                       {**bases, 'category':'theory'},
                       {**bases, 'category':'optional_extension'}]:
            with self.subTest(action=action), self.assertRaises(providers.ProviderError):
                providers.validate_output(action, native)
        experiment = {**bases, 'category':'experiment', 'resolution_basis':'new_research',
                      'experiment_design': {key:'planned' for key in original['properties']['experiment_design']['required']}}
        providers.validate_output(experiment, native)
        providers.validate_output(experiment, original)

    def test_validator_original_review_conditionals_and_boolean_scores(self):
        from test_paperkit import review
        schema = json.loads((ROOT / 'schemas/review.schema.json').read_text())
        valid = review(); providers.validate_output(valid, schema)
        for mutate in [lambda v: v['confidence'].update(score=True),
                       lambda v: v['ethics_review'].update(answer='yes', details=''),
                       lambda v: v.update(unexpected='field')]:
            value = review(); mutate(value)
            with self.assertRaises(providers.ProviderError):
                providers.validate_output(value, schema)

    def test_local_refs_combinators_and_nonstandard_json_are_checked(self):
        schema = {'$defs': {'text': {'type': 'string', 'minLength': 1}},
                  'type': 'object', 'required': ['name'], 'additionalProperties': False,
                  'properties': {'name': {'$ref': '#/$defs/text'}}}
        providers.validate_output({'name': 'test'}, schema)
        with self.assertRaises(providers.ProviderError):
            providers.validate_output({'name': ''}, schema)
        for text in ['{"value":NaN}', '```json\n{}\n```']:
            with self.assertRaises(providers.ProviderError):
                providers._json(text)

    def test_limits_are_explicit_and_do_not_launch(self):
        for timeout in [0, True, float('nan'), providers.MAX_JOB_SECONDS + 1]:
            with self.subTest(timeout=timeout), self.assertRaises(providers.ProviderError):
                self.run_provider(timeout=timeout)
        self.assertFalse(self.trace.exists())

    def test_approval_metadata_probes_no_model_and_discloses_limits(self):
        description = providers.describe('antigravity')
        self.assertEqual(description['scope'], 'inline_text_only')
        self.assertTrue(any('hooks' in text for text in description['limitations']))
        self.assertIn('not inherited', description['model_policy'])
        self.assertFalse(self.trace.exists())

    def test_successful_help_on_stderr_is_accepted(self):
        with patch.dict(os.environ, {'FAKE_HELP_STDERR': '1'}):
            self.assertEqual(providers.detect('antigravity')['provider'], 'antigravity')
        self.assertFalse(self.trace.exists())


if __name__ == '__main__':
    unittest.main()
