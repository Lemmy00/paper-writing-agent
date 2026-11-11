"""Synthetic custom forms; no live providers or private manuscripts."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_paperkit import pk, review
import review_rubrics as rr
import providers


class ReviewRubricTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.pdf = self.root / 'draft.pdf'
        self.pdf.write_bytes(b'%PDF-synthetic')
        self.venue = self.root / 'venue.md'
        self.venue.write_text('# Synthetic venue form\n\n## Recommendation\n\nUse 1–7; 7 means acceptance.\n')
        self.checklist = self.root / 'checklist.md'
        self.checklist.write_text('# Reproducibility checklist\n\nAre the inputs available? Answer Yes / No / Not applicable.\n')
        self.extract = patch.object(pk, 'extract_pdf', return_value='Synthetic manuscript text.')
        self.extract.start()

    def tearDown(self):
        self.extract.stop()
        self.tmp.cleanup()

    def packet(self, selected=None, *, name='packet', mode='development'):
        packet = self.root / name
        manifest = pk.prepare_review(self.pdf, packet, mode, rubrics=selected)
        return packet, manifest

    def native_review(self, packet, manifest):
        value = review()
        value['packet_hash'] = manifest['packet_hash']
        value['mode'] = manifest['mode']
        for field in ('presentation', 'informativeness', 'soundness', 'rating'):
            del value[field]
        value['rubric_assessments'] = {
            rubric['id']: '## Recommendation\n\n7 on the native 1–7 scale.\n\nChecklist: Not applicable.'
            for rubric in rr.packet_rubrics(packet)}
        return value

    def test_default_form_keeps_legacy_contract(self):
        packet, manifest = self.packet()
        self.assertFalse((packet / 'rubrics.json').exists())
        self.assertEqual((packet / 'rubric.md').read_bytes(), rr.DEFAULT_PATH.read_bytes())
        value = review()
        value['packet_hash'] = manifest['packet_hash']
        self.assertEqual(pk.validate_review_packet(value, packet), [])
        value['rating']['score'] = 7
        self.assertTrue(pk.validate_review_packet(value, packet))

    def test_one_custom_form_preserves_native_scale_without_default_rating(self):
        packet, manifest = self.packet([self.venue])
        value = self.native_review(packet, manifest)
        self.assertIn('Use 1–7; 7 means acceptance.', (packet / 'rubric.md').read_text())
        self.assertNotIn('rating', rr.packet_schema(packet)['properties'])
        self.assertEqual(pk.validate_review_packet(value, packet), [])

    def test_multiple_forms_require_each_assessment(self):
        packet, manifest = self.packet([self.venue, self.checklist])
        value = self.native_review(packet, manifest)
        self.assertEqual(pk.validate_review_packet(value, packet), [])
        for rubric_id in list(value['rubric_assessments']):
            missing = copy.deepcopy(value)
            del missing['rubric_assessments'][rubric_id]
            self.assertTrue(pk.validate_review_packet(missing, packet))
        extra = copy.deepcopy(value)
        extra['rubric_assessments']['unselected'] = 'An unrelated form.'
        self.assertTrue(pk.validate_review_packet(extra, packet))
        value['rubric_assessments']['rubric-002'] = ' \n'
        self.assertTrue(pk.validate_review_packet(value, packet))

    def test_bundled_and_custom_forms_can_be_selected_together(self):
        packet, manifest = self.packet([rr.DEFAULT_ID, self.checklist])
        self.assertEqual(len(rr.packet_rubrics(packet)), 2)
        self.assertIn('Critical Strengths', (packet / 'rubric.md').read_text())
        self.assertIn('Reproducibility checklist', (packet / 'rubric.md').read_text())
        self.assertEqual(pk.validate_review_packet(self.native_review(packet, manifest), packet), [])

    def test_selected_order_and_content_are_bound_to_packet_hash(self):
        packet, first = self.packet([self.venue, self.checklist])
        _, second = self.packet([self.checklist, self.venue], name='reversed')
        self.assertNotEqual(first['packet_hash'], second['packet_hash'])
        self.venue.write_text('# Updated form\n\nAnswer a different question.\n')
        _, third = self.packet([self.venue, self.checklist], name='updated')
        self.assertNotEqual(first['packet_hash'], third['packet_hash'])
        self.assertNotIn('Updated form', (packet / 'rubric.md').read_text())
        self.assertEqual(pk.validate_review_packet(self.native_review(packet, first), packet), [])

    def test_shared_ethics_task_basis_and_confidence_are_still_enforced(self):
        packet, manifest = self.packet([self.venue], mode='submission_mock')
        good = self.native_review(packet, manifest)
        for field, invalid in [
                ('ethics_review', {'answer': 'yes', 'details': ''}),
                ('confidence', {'score': None, 'rationale': 'Missing topic coverage.'}),
                ('improvement_plan', [{'category': 'experiment', 'priority': 'useful',
                                       'claim': 'A claim.', 'evidence': 'No evidence.', 'action': 'Compare.',
                                       'completion_criterion': 'Known.', 'resolution_basis': 'writing'}])]:
            value = copy.deepcopy(good)
            value[field] = invalid
            self.assertTrue(pk.validate_review_packet(value, packet), field)

    def test_native_schema_matches_optional_full_validator_and_provider_transport(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest('Optional jsonschema is not installed.')
        packet, manifest = self.packet([self.venue, self.checklist])
        schema = rr.packet_schema(packet)
        jsonschema.Draft202012Validator.check_schema(schema)
        value = self.native_review(packet, manifest)
        jsonschema.validate(value, schema)
        providers.validate_output(value, schema)
        providers.validate_output(value, providers.transport_schema(schema))

    def test_weakened_custom_schema_is_rejected_even_with_updated_file_hash(self):
        packet, manifest = self.packet([self.venue])
        (packet / 'review.schema.json').write_text('{}')
        manifest['files']['review.schema.json'] = pk.sha(packet / 'review.schema.json')
        manifest['packet_hash'] = pk.digest(json.dumps({'mode': manifest['mode'], 'files': manifest['files']}, sort_keys=True).encode())
        pk.dump(packet / 'packet.json', manifest)
        self.assertTrue(pk.validate_review_packet(self.native_review(packet, manifest), packet))

    def test_unlisted_metadata_cannot_change_default_review_contract(self):
        packet, manifest = self.packet()
        (packet / 'rubrics.json').write_text('{"version":1,"rubrics":[]}')
        value = review()
        value['packet_hash'] = manifest['packet_hash']
        self.assertTrue(pk.validate_review_packet(value, packet))
        with self.assertRaises(ValueError):
            rr.packet_schema(packet)

    def test_invalid_and_duplicate_selections_leave_no_partial_packet(self):
        empty = self.root / 'empty.md'
        empty.write_text(' \n')
        linked = self.root / 'linked.md'
        linked.symlink_to(self.venue)
        for index, selection in enumerate(([self.venue, self.venue], [empty], [linked],
                                            ['missing.md'], ['https://example.org/form.md'],
                                            [self.root], [self.venue] * (rr.MAX_RUBRICS + 1))):
            with self.subTest(selection=selection):
                packet = self.root / ('invalid-' + str(index))
                with self.assertRaises(ValueError):
                    pk.prepare_review(self.pdf, packet, 'development', rubrics=selection)
                self.assertFalse(packet.exists())

    def test_relative_paths_resolve_from_selected_project(self):
        self.assertEqual(rr.resolve_rubrics(['venue.md'], base=self.root), [self.venue])
        self.assertEqual(rr.resolve_rubrics([], base=self.root), [rr.DEFAULT_PATH.resolve()])


@unittest.skipUnless(all(shutil.which(tool) for tool in ('latexmk', 'pdflatex', 'pdftotext')),
                     'Local LaTeX and PDF extraction tools are required.')
class RubricCLIIntegrationTests(unittest.TestCase):
    def test_custom_forms_through_real_pdf_and_cli_from_another_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            project = root / 'paper with spaces'
            (project / 'rubrics').mkdir(parents=True)
            (project / 'main.tex').write_text(r'\documentclass{article}\begin{document}Synthetic draft.\end{document}')
            (project / 'rubrics/venue.md').write_text('# Synthetic venue\n\nUse 1–7.\n')
            (project / 'rubrics/artifacts.md').write_text('# Artifact checklist\n\nAre the inputs available?\n')
            receipt = pk.build(project, 'main.tex', True)
            pdf = project / receipt['pdf']
            command = [sys.executable, str(pk.KIT / 'scripts/orchestrator.py'), 'plan', str(project),
                       '--pdf', str(pdf), '--rubric', 'rubrics/venue.md', '--rubric', 'rubrics/artifacts.md']
            completed = subprocess.run(command, cwd=root, check=True, capture_output=True, text=True)
            status = json.loads(completed.stdout)
            self.assertEqual(status['stage'], 'awaiting_review_approval')
            self.assertEqual(len(status['pending_plan']['rubrics']), 2)
            packet = next((project / '.paper/loops').glob('*/round-001/packet'))
            manifest = json.loads((packet / 'packet.json').read_text())
            self.assertIn('Synthetic draft.', (packet / 'manuscript.txt').read_text())
            value = review()
            value['packet_hash'] = manifest['packet_hash']
            for field in ('presentation', 'informativeness', 'soundness', 'rating'):
                del value[field]
            value['rubric_assessments'] = {'rubric-001': '## Native rating\n\n7 of 7.',
                                           'rubric-002': '## Inputs\n\nNot applicable to this synthetic fixture.'}
            review_file = root / 'review.json'
            pk.dump(review_file, value)
            checked = subprocess.run([sys.executable, str(pk.KIT / 'scripts/paperkit.py'),
                                      'validate-review', str(review_file), '--packet', str(packet)],
                                     cwd=root, check=True, capture_output=True, text=True)
            self.assertTrue(json.loads(checked.stdout)['passed'])
            state = json.loads(next((project / '.paper/loops').glob('*/state.json')).read_text())
            self.assertTrue(all(job['status'] == 'pending' for job in state['rounds'][0]['jobs'].values()))


if __name__ == '__main__':
    unittest.main()
