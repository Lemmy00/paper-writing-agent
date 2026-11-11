"""Synthetic controller trials: no real manuscripts or live model requests."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import orchestrator as oc
import paperkit as pk


def action(basis='writing', text='Split the opening sentence.'):
    category = {'writing': 'writing', 'existing_evidence': 'verification',
                'author_clarification': 'clarification', 'new_research': 'theory'}[basis]
    return {'category': category, 'priority': 'useful', 'claim': 'Synthetic claim.',
            'evidence': 'Synthetic paragraph.', 'action': text,
            'completion_criterion': 'Preserve the stated meaning.', 'resolution_basis': basis}


def fake_prepare(pdf, output, mode):
    output.mkdir(parents=True)
    shutil.copyfile(pdf, output / 'manuscript.pdf')
    (output / 'manuscript.txt').write_text('Synthetic manuscript. ' + pdf.read_text())
    for source, name in [('rubrics/user-supplied-iclr-form.md', 'rubric.md'),
                         ('prompts/scientific-reviewer.md', 'instructions.md'),
                         ('schemas/review.schema.json', 'review.schema.json')]:
        shutil.copyfile(ROOT / source, output / name)
    files = {p.name: pk.sha(p) for p in sorted(output.iterdir())}
    manifest = {'mode': mode, 'files': files,
                'packet_hash': pk.digest(json.dumps({'mode': mode, 'files': files}, sort_keys=True).encode())}
    pk.dump(output / 'packet.json', manifest)
    return manifest


class FakeRunner:
    def __init__(self, actions=None, questions=None):
        self.calls = []
        self.actions = [action()] if actions is None else actions
        self.questions = questions or []
        self.before = None
        self.writer = None

    def __call__(self, provider, prompt, schema, cwd, **kwargs):
        self.assert_empty(cwd)
        request = json.loads(prompt.split('\nREQUEST_JSON\n', 1)[1])
        self.calls.append((provider, request['job_type'], request))
        if self.before:
            self.before(provider, request, kwargs)
        if request['job_type'] == 'review':
            output = {'mode': request['mode'], 'packet_hash': request['packet_hash'],
                      'reviewer_id': request['reviewer_id'], 'reviewer_perspective': request['reviewer_perspective'],
                      'coverage': ['Synthetic text-only fixture; not visual or enforced blind coverage.'],
                      'summary': 'Synthetic reviewer assessment.',
                      **{field: {'score': 2, 'rationale': 'Synthetic AI basis, not human research experience.'}
                         for field in ('presentation', 'informativeness', 'soundness', 'rating', 'confidence')},
                      'critical_strengths': [], 'critical_weaknesses': [], 'questions_for_authors': [],
                      'ethics_review': {'answer': 'no', 'details': ''}, 'improvement_plan': []}
        elif request['job_type'] == 'synthesis':
            output = {'summary': 'Discuss this synthetic plan before executing tasks.',
                      'strengths_to_preserve': ['Preserve the supported synthetic observation.'],
                      'actions': copy.deepcopy(self.actions), 'questions': self.questions}
        else:
            if self.writer:
                output = self.writer(request)
            else:
                output = {'summary': 'A targeted sentence edit.', 'questions': [],
                          'edits': [{'path': 'main.tex', 'old_text': 'Original sentence.',
                                     'new_text': 'Clear sentence.',
                                     'action_ids': [request['approved_actions'][0]['id']]}]}
        return {'output': output, 'receipt': {'provider': provider, 'synthetic_test': True}}

    @staticmethod
    def assert_empty(cwd):
        if list(cwd.iterdir()):
            raise AssertionError('Provider workdir must start empty.')


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.project = Path(self.tmp.name).resolve() / 'paper'
        self.project.mkdir()
        (self.project / 'main.tex').write_text('Original sentence. Second sentence.\n')
        (self.project / 'main.pdf').write_text('%PDF-synthetic-v1')
        self.prepare = patch.object(pk, 'prepare_review', side_effect=fake_prepare)
        self.prepare.start()
        self.runner = FakeRunner()
        self.loop = None

    def tearDown(self):
        self.prepare.stop()
        self.tmp.cleanup()

    def create(self, **kwargs):
        self.loop = oc.ReviewLoop.create(self.project, kwargs.pop('pdf', 'main.pdf'), **kwargs)
        return self.loop

    def approve_plan(self, tasks=None):
        status = self.loop.status()
        ids = tasks or [task['id'] for task in status['pending_plan']['tasks']]
        return self.loop.approve(status['plan_hash'], ids, 'SYNTHETIC USER RESPONSE', 'Approve exactly these synthetic test tasks.')

    def reviewed(self, **kwargs):
        self.create(**kwargs)
        self.approve_plan()
        self.loop.advance(runner=self.runner)
        return self.loop

    def drafted(self, **kwargs):
        self.reviewed(**kwargs)
        self.approve_plan()
        self.loop.advance(runner=self.runner)
        return self.loop

    def fake_build(self, project, main, allow, cancel_event=None):
        self.assertTrue(allow)
        path = project / '.paper/build/revised.pdf'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('%PDF-' + pk.sha(project / main))
        return {'pdf': path.relative_to(project).as_posix()}

    def test_planning_and_unanswered_request_make_zero_calls_and_no_source_edits(self):
        self.create()
        before = (self.project / 'main.tex').read_bytes()
        for _ in range(3):
            self.assertEqual(self.loop.advance(runner=self.runner)['stage'], 'awaiting_review_approval')
        self.assertEqual(self.runner.calls, [])
        self.assertEqual((self.project / 'main.tex').read_bytes(), before)
        self.assertEqual(self.loop.status()['pending_plan']['capabilities']['scope'], 'inline_text_only')

    def test_source_only_plan_requires_separate_local_build_then_review_approval(self):
        self.create(pdf=None)
        self.assertEqual(self.loop.status()['stage'], 'awaiting_build_approval')
        with patch.object(pk, 'build', side_effect=self.fake_build) as builder:
            self.loop.advance(runner=self.runner)
            builder.assert_not_called()
            self.approve_plan()
            self.assertEqual(self.loop.advance(runner=self.runner)['stage'], 'awaiting_review_approval')
            self.assertEqual(builder.call_count, 1)
        self.assertEqual(self.runner.calls, [])

    def test_subset_approval_runs_only_selected_reviewer_and_requires_meta_approval(self):
        self.create()
        self.approve_plan(['review-' + oc.PERSPECTIVES[0]])
        self.loop.advance(runner=self.runner)
        self.assertEqual(len(self.runner.calls), 1)
        self.assertEqual(self.loop.status()['stage'], 'awaiting_review_approval')
        self.approve_plan(['review-' + name for name in oc.PERSPECTIVES[1:]])
        self.loop.advance(runner=self.runner)
        self.assertEqual(len(self.runner.calls), 3)
        self.assertEqual(self.loop.status()['stage'], 'awaiting_review_approval')
        self.approve_plan(['synthesis'])
        self.assertEqual(self.loop.advance(runner=self.runner)['stage'], 'awaiting_task_approval')
        self.assertEqual([call[1] for call in self.runner.calls], ['review'] * 3 + ['synthesis'])

    def test_model_or_budget_mutation_invalidates_grant_before_provider(self):
        for field, value in [('provider', 'claude'), ('model', 'different-model'), ('timeout', 999), ('max_rounds', 9)]:
            with self.subTest(field=field):
                self.create(run_id='case-' + field)
                self.approve_plan()
                state = self.loop._load();state['settings'][field] = value;self.loop._save(state)
                with self.assertRaisesRegex(oc.LoopError, 'settings changed'):
                    self.loop.advance(runner=self.runner)
                self.assertEqual(self.runner.calls, [])
                self.loop.stop('SYNTHETIC USER', 'Stop this synthetic case.')

    def test_missing_or_stale_user_decision_is_not_approval(self):
        self.create()
        status = self.loop.status();ids = [task['id'] for task in status['pending_plan']['tasks']]
        for reference, text in [('', 'Approve'), ('SYNTHETIC USER', ''), (None, None)]:
            with self.subTest(reference=reference):
                with self.assertRaises(oc.LoopError):
                    self.loop.approve(status['plan_hash'], ids, reference, text)
        with self.assertRaisesRegex(oc.LoopError, 'current concrete plan'):
            self.loop.approve('0' * 64, ids, 'SYNTHETIC USER', 'Approve old plan.')

    def test_source_or_packet_drift_stops_review_without_calls(self):
        self.create();self.approve_plan()
        (self.project / 'main.tex').write_text('Concurrent author revision.')
        with self.assertRaisesRegex(oc.LoopError, 'inputs changed'):
            self.loop.advance(runner=self.runner)
        self.assertEqual(self.loop.status()['stage'], 'stale')
        self.assertEqual(self.runner.calls, [])

    def test_packet_bytes_drift_rejected(self):
        self.create();self.approve_plan()
        packet = self.loop.directory / self.loop._load()['rounds'][-1]['packet']
        (packet / 'rubric.md').write_text('Changed rubric.')
        with self.assertRaisesRegex(oc.LoopError, 'packet file changed'):
            self.loop.advance(runner=self.runner)
        self.assertEqual(self.runner.calls, [])

    def test_failure_resume_preserves_valid_completed_jobs(self):
        self.create();self.approve_plan()
        def fail_once(provider, request, kwargs):
            if len(self.runner.calls) == 3:
                raise RuntimeError('Synthetic transient failure.')
        self.runner.before = fail_once
        with self.assertRaisesRegex(RuntimeError, 'transient'):
            self.loop.advance(runner=self.runner)
        self.runner.before = None
        self.loop.resume()
        self.loop.advance(runner=self.runner)
        self.assertEqual([call[1] for call in self.runner.calls], ['review', 'review', 'review', 'review', 'synthesis'])
        self.assertEqual(self.loop.status()['stage'], 'awaiting_task_approval')

    def test_interrupted_state_commit_recovers_saved_job_without_repeating_provider(self):
        self.create();self.approve_plan(['review-' + oc.PERSPECTIVES[0]])
        self.loop.advance(runner=self.runner)
        state = self.loop._load();state['stage'] = 'reviewing'
        state['rounds'][-1]['jobs'][oc.PERSPECTIVES[0]]['status'] = 'running'
        self.loop._save(state)
        self.loop.advance(runner=self.runner)
        self.assertEqual(len(self.runner.calls), 1)
        self.assertEqual(self.loop._load()['rounds'][-1]['jobs'][oc.PERSPECTIVES[0]]['status'], 'complete')

    def test_invalid_review_identity_fails_before_sealing(self):
        self.create();self.approve_plan()
        original = self.runner
        def wrong(*args, **kwargs):
            result = original(*args, **kwargs)
            result['output']['reviewer_id'] = 'other-reviewer'
            return result
        with self.assertRaisesRegex(oc.LoopError, 'identity'):
            self.loop.advance(runner=wrong)
        job = self.loop._load()['rounds'][0]['jobs'][oc.PERSPECTIVES[0]]
        self.assertEqual(job['status'], 'failed')
        self.assertIn('identity', job['last_error'])
        self.assertEqual(len(job['failures']), 1)
        self.assertTrue((self.loop.directory / 'round-001/jobs'/oc.PERSPECTIVES[0]/'invalid-output-attempt-1.json').is_file())

    def test_attempt_budget_stops_repeated_failure(self):
        self.create(max_attempts=1);self.approve_plan()
        def fail(*args, **kwargs):
            self.runner.calls.append('failed')
            raise RuntimeError('Synthetic failure.')
        with self.assertRaises(RuntimeError):self.loop.advance(runner=fail)
        self.loop.resume()
        with self.assertRaisesRegex(oc.LoopError, 'Attempt budget exhausted'):
            self.loop.advance(runner=fail)
        self.assertEqual(len(self.runner.calls), 1)

    def test_adapter_rejected_structured_output_is_preserved_privately(self):
        self.create();self.approve_plan()
        rejected = {'invalid': 'Synthetic rejected object; never a sealed review.'}
        def fail(*args, **kwargs):
            error = oc.providers.ProviderError('Synthetic schema failure.', 'invalid_output', {'synthetic_test': True})
            error.output = rejected
            raise error
        with self.assertRaisesRegex(oc.providers.ProviderError, 'schema failure'):
            self.loop.advance(runner=fail)
        directory = self.loop.directory / 'round-001/jobs' / oc.PERSPECTIVES[0]
        self.assertEqual(json.loads((directory / 'invalid-output-attempt-1.json').read_text()), rejected)
        self.assertFalse((directory / 'output.json').exists())
        self.assertEqual(self.loop._load()['rounds'][0]['jobs'][oc.PERSPECTIVES[0]]['status'], 'failed')

    def test_task_plan_requires_approval_then_draft_requires_diff_approval(self):
        self.reviewed();before = (self.project / 'main.tex').read_text()
        self.assertEqual(len(self.runner.calls), 4)
        self.loop.advance(runner=self.runner)
        self.assertEqual(len(self.runner.calls), 4)
        self.approve_plan()
        result = self.loop.advance(runner=self.runner)
        self.assertEqual(result['stage'], 'awaiting_patch_approval')
        self.assertTrue(Path(result['diff_file']).is_file())
        self.assertEqual((self.project / 'main.tex').read_text(), before)
        self.loop.advance(runner=self.runner)
        self.assertEqual((self.project / 'main.tex').read_text(), before)

    def test_approved_patch_applies_but_build_is_separately_gated(self):
        self.drafted();status = self.loop.status()
        (self.project / 'main.tex').chmod(0o664)
        self.loop.approve_patch(status['patch_hash'], 'SYNTHETIC USER', 'Apply this exact diff, without compiling.')
        with patch.object(pk, 'build', side_effect=self.fake_build) as builder:
            result = self.loop.advance(runner=self.runner)
            builder.assert_not_called()
        self.assertEqual(result['stage'], 'awaiting_build_approval')
        self.assertIn('Clear sentence.', (self.project / 'main.tex').read_text())
        self.assertEqual((self.project / 'main.tex').stat().st_mode & 0o777, 0o664)
        self.assertEqual(len(self.runner.calls), 5)

    def test_combined_apply_build_prepares_next_round_but_never_reviews_it_unapproved(self):
        self.drafted();status = self.loop.status()
        self.loop.approve_patch(status['patch_hash'], 'SYNTHETIC USER', 'Apply this diff and build it.', allow_build=True)
        with patch.object(pk, 'build', side_effect=self.fake_build):
            result = self.loop.advance(runner=self.runner)
        self.assertEqual(result['stage'], 'awaiting_review_approval')
        self.assertEqual(result['round'], 2)
        self.assertEqual(len(self.runner.calls), 5)
        self.loop.advance(runner=self.runner)
        self.assertEqual(len(self.runner.calls), 5)

    def test_round_limit_stops_further_reviews_after_author_approved_edit(self):
        self.drafted(max_rounds=1)
        self.loop.approve_patch(self.loop.status()['patch_hash'], 'SYNTHETIC USER', 'Apply and build.', allow_build=True)
        with patch.object(pk, 'build', side_effect=self.fake_build):
            result = self.loop.advance(runner=self.runner)
        self.assertEqual(result['stage'], 'stopped_limit')
        self.assertEqual(result['round'], 1)
        self.assertNotIn('final_ready', result)

    def test_plan_discussion_revises_ids_and_invalidates_old_approval(self):
        self.reviewed();old = self.loop.status()
        calls = len(self.runner.calls)
        updated = self.loop.propose_tasks([action(text='A revised concrete writing request.')], 'Discuss a different plan.')
        self.assertNotEqual(old['plan_hash'], updated['plan_hash'])
        self.assertNotEqual(old['pending_plan']['tasks'][0]['id'], updated['pending_plan']['tasks'][0]['id'])
        with self.assertRaises(oc.LoopError):
            self.loop.approve(old['plan_hash'], [old['pending_plan']['tasks'][0]['id']], 'SYNTHETIC USER', 'Approve stale action.')
        self.loop.advance(runner=self.runner)
        self.assertEqual(len(self.runner.calls), calls)

    def test_changed_approved_action_does_not_execute(self):
        self.reviewed();self.approve_plan()
        state = self.loop._load();state['rounds'][-1]['actions'][0]['action'] = 'Unapproved different task.';self.loop._save(state)
        with self.assertRaisesRegex(oc.LoopError, 'action content changed'):
            self.loop.advance(runner=self.runner)
        self.assertEqual(len(self.runner.calls), 4)

    def test_scope_and_fuzzy_patch_failures_are_retryable_within_budget(self):
        self.reviewed();self.approve_plan()
        self.runner.writer = lambda request: {'summary': 'Unsafe synthetic proposal.', 'questions': [],
              'edits': [{'path': '../outside.tex', 'old_text': 'Original sentence.', 'new_text': 'Changed.',
                         'action_ids': [request['approved_actions'][0]['id']]}]}
        with self.assertRaisesRegex(oc.LoopError, 'outside'):
            self.loop.advance(runner=self.runner)
        state = self.loop._load();key = state['rounds'][-1]['writer_job']
        self.assertEqual(state['rounds'][-1]['jobs'][key]['status'], 'failed')
        self.runner.writer = None;self.loop.resume()
        self.assertEqual(self.loop.advance(runner=self.runner)['stage'], 'awaiting_patch_approval')

    def test_patch_cannot_touch_unapproved_action(self):
        self.runner.actions = [action(), action(text='A second edit.')]
        self.reviewed();status = self.loop.status()
        first, second = [task['id'] for task in status['pending_plan']['tasks']]
        self.approve_plan([first])
        self.runner.writer = lambda request: {'summary': 'Wrong task.', 'questions': [],
             'edits': [{'path': 'main.tex', 'old_text': 'Original sentence.', 'new_text': 'Changed.', 'action_ids': [second]}]}
        with self.assertRaisesRegex(oc.LoopError, 'outside approved writing'):
            self.loop.advance(runner=self.runner)

    def test_questions_pause_only_affected_action_and_preserve_other_edits(self):
        self.runner.actions = [action(), action(text='Clarify an ambiguous scientific sentence.')]
        self.reviewed();self.approve_plan()
        ids = self.loop._load()['rounds'][-1]['approved_actions']
        self.runner.writer = lambda request: {'summary': 'One safe edit, one question.',
            'questions': [{'action_id': ids[1], 'question': 'What evidence supports the second claim?'}],
            'edits': [{'path': 'main.tex', 'old_text': 'Original sentence.', 'new_text': 'Clear sentence.', 'action_ids': [ids[0]]}]}
        result = self.loop.advance(runner=self.runner)
        self.assertEqual(result['stage'], 'awaiting_patch_approval')
        self.assertEqual(len(result['questions']), 1)
        self.loop.approve_patch(result['patch_hash'], 'SYNTHETIC USER', 'Apply only the safe edit.')
        self.loop.advance(runner=self.runner)
        statuses = {a['id']: a['status'] for a in self.loop._load()['rounds'][-1]['actions']}
        self.assertEqual(statuses[ids[0]], 'editorial_change_applied')
        self.assertEqual(statuses[ids[1]], 'awaiting_author_or_evidence')

    def test_diff_or_source_drift_rejects_application(self):
        self.drafted();status = self.loop.status()
        Path(status['diff_file']).write_text('Different human-review diff.')
        with self.assertRaisesRegex(oc.LoopError, 'diff changed'):
            self.loop.approve_patch(status['patch_hash'], 'SYNTHETIC USER', 'Approve old diff.')
        self.assertIn('Original sentence.', (self.project / 'main.tex').read_text())

    def test_author_source_change_after_patch_approval_is_never_overwritten(self):
        self.drafted();self.loop.approve_patch(self.loop.status()['patch_hash'], 'SYNTHETIC USER', 'Apply exact diff.')
        (self.project / 'main.tex').write_text('A later author change.')
        with self.assertRaises(oc.LoopError):self.loop.advance(runner=self.runner)
        self.assertEqual((self.project / 'main.tex').read_text(), 'A later author change.')

    def test_revised_plan_uses_fresh_writer_and_preserves_old_diff(self):
        self.drafted();old = self.loop.status();old_diff = Path(old['diff_file']).read_text()
        self.loop.propose_tasks([action(text='A changed writing task.')], 'Revised discussion.')
        self.approve_plan();new = self.loop.advance(runner=self.runner)
        self.assertNotEqual(new['diff_file'], old['diff_file'])
        self.assertEqual(Path(old['diff_file']).read_text(), old_diff)
        self.assertEqual([call[1] for call in self.runner.calls].count('writer'), 2)

    def test_pending_cancel_and_explicit_resume_are_live(self):
        self.create();self.loop.cancel('SYNTHETIC USER', 'Cancel this plan.')
        self.assertEqual(self.loop.advance(runner=self.runner)['stage'], 'cancelled')
        with self.assertRaises(oc.LoopError):self.loop.resume()
        self.assertEqual(self.loop.resume('SYNTHETIC USER', 'Resume discussion.')['stage'], 'awaiting_review_approval')
        self.assertFalse(self.loop.status()['cancel_requested'])

    def test_cancellation_during_provider_does_not_wait_for_lock_or_seal_result(self):
        self.create();self.approve_plan()
        def cancel(provider, request, kwargs):
            self.assertEqual(self.loop.status()['stage'], 'reviewing')
            self.loop.cancel('SYNTHETIC USER', 'Cancel while running.')
            self.assertTrue(kwargs['cancel_event'].is_set())
        self.runner.before = cancel
        result = self.loop.advance(runner=self.runner)
        self.assertEqual(result['stage'], 'cancelled')
        self.assertEqual(self.loop._load()['rounds'][-1]['jobs'][oc.PERSPECTIVES[0]]['status'], 'cancelled')

    def test_stop_during_provider_signals_immediately(self):
        self.create();self.approve_plan()
        def stop(provider, request, kwargs):
            result = self.loop.stop('SYNTHETIC USER', 'Stop this run now.')
            self.assertTrue(result['cancel_requested'])
        self.runner.before = stop
        self.assertEqual(self.loop.advance(runner=self.runner)['stage'], 'cancelled')
        self.assertEqual(len(self.runner.calls), 1)

    def test_cancel_during_build_does_not_prepare_next_packet(self):
        self.create(pdf=None);self.approve_plan()
        def cancel_build(*args, **kwargs):
            receipt = self.fake_build(*args, **kwargs)
            self.loop.cancel('SYNTHETIC USER', 'Cancel local compilation.')
            return receipt
        with patch.object(pk, 'build', side_effect=cancel_build):
            result = self.loop.advance(runner=self.runner)
        self.assertEqual(result['stage'], 'cancelled')
        self.assertEqual(result['round'], 0)

    def test_cancel_before_apply_preserves_author_file(self):
        self.drafted();self.loop.approve_patch(self.loop.status()['patch_hash'], 'SYNTHETIC USER', 'Apply diff.')
        self.loop.cancel('SYNTHETIC USER', 'Revoke before apply.')
        self.assertEqual(self.loop.advance(runner=self.runner)['stage'], 'cancelled')
        self.assertIn('Original sentence.', (self.project / 'main.tex').read_text())

    def test_cancel_mid_apply_rolls_back_known_changes_and_requires_new_diff_decision(self):
        self.drafted();self.loop.approve_patch(self.loop.status()['patch_hash'], 'SYNTHETIC USER', 'Apply diff.')
        original = oc._text
        def write_then_cancel(path, value):
            original(path, value)
            if path == self.project / 'main.tex' and 'Clear sentence.' in value:
                self.loop.cancel('SYNTHETIC USER', 'Cancel during apply.')
        with patch.object(oc, '_text', side_effect=write_then_cancel):
            result = self.loop.advance(runner=self.runner)
        self.assertEqual(result['stage'], 'cancelled')
        self.assertIn('Original sentence.', (self.project / 'main.tex').read_text())
        self.assertEqual(self.loop.resume('SYNTHETIC USER', 'Resume safely.')['stage'], 'awaiting_patch_approval')

    def test_interrupted_apply_journal_restores_only_known_changes(self):
        self.drafted();self.loop.approve_patch(self.loop.status()['patch_hash'], 'SYNTHETIC USER', 'Apply diff.')
        original = oc._text
        def interrupted(path, value):
            original(path, value)
            if path == self.project / 'main.tex' and 'Clear sentence.' in value:
                raise KeyboardInterrupt('Synthetic process interruption.')
        with patch.object(oc, '_text', side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self.loop.advance(runner=self.runner)
        self.assertIn('Clear sentence.', (self.project / 'main.tex').read_text())
        self.assertEqual(self.loop.advance(runner=self.runner)['stage'], 'awaiting_patch_approval')
        self.assertIn('Original sentence.', (self.project / 'main.tex').read_text())

    def test_write_failure_rolls_back_and_returns_to_diff_approval(self):
        self.drafted();self.loop.approve_patch(self.loop.status()['patch_hash'], 'SYNTHETIC USER', 'Apply diff.')
        original = oc._text
        def fail_source_write(path, value):
            if path == self.project / 'main.tex' and 'Clear sentence.' in value:
                raise OSError('Synthetic source-write failure.')
            return original(path, value)
        with patch.object(oc, '_text', side_effect=fail_source_write):
            with self.assertRaises(OSError):self.loop.advance(runner=self.runner)
        self.assertIn('Original sentence.', (self.project / 'main.tex').read_text())
        self.assertEqual(self.loop.resume()['stage'], 'awaiting_patch_approval')

    def test_reply_to_blocked_action_does_not_block_unrelated_diff_approval(self):
        self.runner.actions = [action(), action(text='An ambiguous second task.')]
        self.reviewed();self.approve_plan()
        ids = self.loop._load()['rounds'][-1]['approved_actions']
        self.runner.writer = lambda request: {'summary': 'Safe edit and question.',
             'questions': [{'action_id': ids[1], 'question': 'Which evidence applies?'}],
             'edits': [{'path': 'main.tex', 'old_text': 'Original sentence.', 'new_text': 'Clear sentence.', 'action_ids': [ids[0]]}]}
        status = self.loop.advance(runner=self.runner)
        self.loop.answer(status['questions'][0]['id'], 'SYNTHETIC USER', 'The original result table.')
        self.loop.approve_patch(status['patch_hash'], 'SYNTHETIC USER', 'Apply safe edit only.')
        self.assertEqual(self.loop.advance(runner=self.runner)['stage'], 'awaiting_build_approval')

    def test_build_failure_after_apply_resumes_build_without_applying_again(self):
        self.drafted();self.loop.approve_patch(self.loop.status()['patch_hash'], 'SYNTHETIC USER', 'Apply and build.', allow_build=True)
        with patch.object(pk, 'build', side_effect=ValueError('Synthetic build failure.')):
            with self.assertRaisesRegex(ValueError, 'build failure'):
                self.loop.advance(runner=self.runner)
        self.assertIn('Clear sentence.', (self.project / 'main.tex').read_text())
        self.assertEqual(self.loop.resume()['stage'], 'building_revision')
        with patch.object(pk, 'build', side_effect=self.fake_build):
            self.assertEqual(self.loop.advance(runner=self.runner)['stage'], 'awaiting_review_approval')

    def test_research_actions_are_handoffs_and_evidence_is_not_scientific_resolution(self):
        self.runner.actions = [action('new_research', 'Prove the missing synthetic lemma.')]
        self.reviewed();self.approve_plan();calls = len(self.runner.calls)
        self.assertEqual(self.loop.advance(runner=self.runner)['stage'], 'awaiting_evidence')
        self.assertEqual(len(self.runner.calls), calls)
        (self.project / 'proof-notes.txt').write_text('Author-supplied evidence, not verified by this helper.')
        identity = self.loop._load()['rounds'][-1]['actions'][0]['id']
        self.loop.record_evidence(identity, ['proof-notes.txt'], 'SYNTHETIC USER', 'Here is the artifact.')
        self.assertEqual(self.loop._load()['rounds'][-1]['actions'][0]['status'], 'evidence_supplied_unverified')
        self.assertEqual(len(self.runner.calls), calls)

    def test_evidence_registration_cannot_authorize_unrelated_manuscript_changes(self):
        self.runner.actions = [action('existing_evidence')]
        self.reviewed();self.approve_plan();self.loop.advance(runner=self.runner)
        identity = self.loop._load()['rounds'][-1]['actions'][0]['id']
        (self.project / 'results.txt').write_text('New supplied artifact.')
        (self.project / 'main.tex').write_text('Concurrent manuscript edits.')
        with self.assertRaisesRegex(oc.LoopError, 'Other project inputs changed'):
            self.loop.record_evidence(identity, ['results.txt'], 'SYNTHETIC USER', 'Only supply this artifact.')

    def test_separate_loop_ids_share_project_execution_lock(self):
        self.create()
        with self.loop._lock():
            other = oc.ReviewLoop(self.project, 'other-run')
            with self.assertRaisesRegex(oc.LoopError, 'already being advanced'):
                with other._lock():pass

    def test_question_only_plan_can_be_discussed_without_fake_task_approval(self):
        self.runner.actions = [];self.runner.questions = ['Which protocol produced the table?']
        self.reviewed();status = self.loop.status()
        self.assertEqual(status['stage'], 'awaiting_task_approval')
        question = status['questions'][0]
        self.loop.answer(question['id'], 'SYNTHETIC USER', 'The supplied protocol.')
        self.assertEqual(self.loop.status()['questions'][0]['status'], 'author_response_recorded')
        self.assertEqual(len(self.runner.calls), 4)

    def test_reject_or_defer_preserves_decision_without_running_tasks(self):
        self.runner.actions = [action(), action('new_research')]
        self.reviewed();ids = [task['id'] for task in self.loop.status()['pending_plan']['tasks']]
        self.loop.defer(ids[:1], 'SYNTHETIC USER', 'Defer this edit.')
        self.loop.defer(ids[1:], 'SYNTHETIC USER', 'Reject this research request.', reject=True)
        self.assertEqual(self.loop.status()['stage'], 'review_complete')
        self.assertEqual(len(self.runner.calls), 4)

    def test_refresh_requires_new_plan_approval_and_never_reuses_prior_review(self):
        self.reviewed()
        (self.project / 'main.tex').write_text('New author-provided manuscript.')
        (self.project / 'main.pdf').write_text('%PDF-synthetic-v2')
        result = self.loop.refresh('main.pdf', response_ref='SYNTHETIC USER', response_text='Review this updated candidate.')
        self.assertEqual(result['round'], 2)
        self.assertEqual(result['stage'], 'awaiting_review_approval')
        self.loop.advance(runner=self.runner)
        self.assertEqual(len(self.runner.calls), 4)

    def test_old_pdf_cannot_be_refreshed_as_new_after_manuscript_edit(self):
        self.reviewed()
        (self.project / 'main.tex').write_text('A changed manuscript with no updated PDF yet.')
        with self.assertRaisesRegex(oc.LoopError, 'previously reviewed PDF'):
            self.loop.refresh('main.pdf', response_ref='SYNTHETIC USER', response_text='Try this candidate.')
        self.assertEqual(self.loop.refresh(response_ref='SYNTHETIC USER', response_text='Prepare a build plan.')['stage'], 'awaiting_build_approval')

    def test_malformed_state_and_symlinked_editable_paths_are_rejected(self):
        (self.project / 'alias.tex').symlink_to(self.project / 'main.tex')
        with self.assertRaisesRegex(oc.LoopError, 'Symlinked'):
            self.create(editable=['alias.tex'])
        (self.project / 'alias.tex').unlink()
        self.create();pk.dump(self.loop.state_path, {'schema_version': 999})
        with self.assertRaisesRegex(oc.LoopError, 'Malformed'):
            self.loop.status()

    def test_concurrent_advance_lock_does_not_block_status_or_cancel(self):
        self.create()
        with self.loop._lock():
            self.assertEqual(self.loop.status()['stage'], 'awaiting_review_approval')
            self.loop.cancel('SYNTHETIC USER', 'Cancel despite busy controller.')
            with self.assertRaisesRegex(oc.LoopError, 'already being advanced'):
                self.loop.advance(runner=self.runner)


class LocalBuildCancellationTests(unittest.TestCase):
    def test_local_tool_cancel_terminates_bounded_process(self):
        event = threading.Event()
        timer = threading.Timer(0.15, event.set);timer.start()
        started = time.monotonic()
        try:
            with self.assertRaisesRegex(ValueError, 'cancelled'):
                pk.tool_run([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=10, cancel_event=event)
        finally:
            timer.cancel()
        self.assertLess(time.monotonic() - started, 3)

    def test_local_tool_timeout_is_explicit(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            pk.tool_run([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=0.15)


if __name__ == '__main__':
    unittest.main()
