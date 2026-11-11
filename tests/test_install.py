from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import install as installer


class PersonalInstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.home = self.root / 'home'
        self.source = self.root / 'checkout'
        self.home.mkdir()
        self.source.mkdir()
        for relative, source in installer.package_files(ROOT).items():
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def tearDown(self):
        self.tmp.cleanup()

    def test_all_hosts_receive_self_contained_runtime(self):
        result = installer.install('all', home=self.home, source=self.source)
        self.assertEqual({item['host'] for item in result}, set(installer.HOST_PATHS))
        for item in result:
            destination = Path(item['path'])
            self.assertEqual(item['status'], 'installed')
            self.assertFalse(destination.is_symlink())
            self.assertTrue((destination / 'SKILL.md').is_file())
            self.assertTrue((destination / 'scripts/install.py').is_file())
            self.assertTrue((destination / 'rubrics/user-supplied-iclr-form.md').is_file())

    def test_copy_survives_deleted_checkout_and_initializes_existing_paper(self):
        destination = Path(installer.install('codex', home=self.home, source=self.source)[0]['path'])
        shutil.rmtree(self.source)
        paper = self.root / 'paper'
        paper.mkdir()
        manuscript = paper / 'main.tex'
        manuscript.write_text('Existing author manuscript.\n')
        command = [sys.executable, str(destination / 'scripts/workspace.py'),
                   'init', str(paper), '--host', 'none']
        subprocess.run(command, check=True, capture_output=True, text=True)
        again = subprocess.run(command, check=True, capture_output=True, text=True)
        self.assertIn('"created": []', again.stdout)
        self.assertEqual(manuscript.read_text(), 'Existing author manuscript.\n')
        self.assertTrue((paper / 'config/paper.yaml').is_file())
        self.assertTrue((paper / '.paper-tools/research-paper/scripts/paperkit.py').is_file())
        self.assertFalse((paper / '.agents').exists())
        self.assertFalse((paper / '.claude').exists())

    def test_identical_copy_and_install_from_itself_are_unchanged(self):
        destination = Path(installer.install('claude', home=self.home, source=self.source)[0]['path'])
        environment = dict(os.environ)
        environment.pop('PYTHONPYCACHEPREFIX', None)
        environment.pop('PYTHONDONTWRITEBYTECODE', None)
        subprocess.run([sys.executable, str(destination / 'scripts/paperkit.py'), '--help'],
                       check=True, capture_output=True, text=True, env=environment)
        self.assertTrue((destination / 'scripts/__pycache__').is_dir())
        (destination / '.DS_Store').write_bytes(b'Finder metadata')
        self.assertEqual(installer.install('claude', home=self.home, source=self.source)[0]['status'], 'unchanged')
        self.assertEqual(installer.install('claude', home=self.home, source=destination)[0]['status'], 'unchanged')

    def test_existing_custom_install_is_preserved_before_any_host_is_created(self):
        destination = self.home / installer.HOST_PATHS['claude']
        destination.mkdir(parents=True)
        (destination / 'SKILL.md').write_text('Personal changes')
        with self.assertRaisesRegex(ValueError, 'Existing skill preserved'):
            installer.install('all', home=self.home, source=self.source)
        self.assertEqual((destination / 'SKILL.md').read_text(), 'Personal changes')
        self.assertFalse((self.home / installer.HOST_PATHS['codex']).exists())

    def test_changed_source_or_installed_content_requires_deliberate_update(self):
        destination = Path(installer.install('codex', home=self.home, source=self.source)[0]['path'])
        original = (destination / 'SKILL.md').read_bytes()
        (self.source / 'SKILL.md').write_text('New source version')
        with self.assertRaisesRegex(ValueError, 'Compare and merge'):
            installer.install('codex', home=self.home, source=self.source)
        self.assertEqual((destination / 'SKILL.md').read_bytes(), original)
        (self.source / 'SKILL.md').write_bytes(original)
        (destination / 'personal-note.md').write_text('Keep this note')
        with self.assertRaises(ValueError):
            installer.install('codex', home=self.home, source=self.source)
        self.assertEqual((destination / 'personal-note.md').read_text(), 'Keep this note')

    def test_development_link_is_explicit_and_idempotent(self):
        destination = Path(installer.install('antigravity', home=self.home, source=self.source, link=True)[0]['path'])
        self.assertTrue(destination.is_symlink())
        self.assertEqual(destination.resolve(), self.source)
        self.assertEqual(installer.install('antigravity', home=self.home, source=self.source, link=True)[0]['status'], 'unchanged')
        with self.assertRaisesRegex(ValueError, 'Existing skill link preserved'):
            installer.install('antigravity', home=self.home, source=self.source)

    def test_repository_environment_logs_and_manuscripts_are_not_packaged(self):
        for relative in ('.git/config', '.venv/secret.py', '.local-tests/paper.pdf',
                         'tests/test_private.py', 'main.tex', 'main.pdf', 'AGENTS.md',
                         'docs/session.log', 'assets/paper.pdf', 'scripts/__pycache__/cache.pyc',
                         'scripts/.env.private', 'docs/private-review.md',
                         'assets/private-manuscript-figure.png', 'references/notes/.secrets.md'):
            path = self.source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('Not runtime content')
        destination = Path(installer.install('codex', home=self.home, source=self.source)[0]['path'])
        for relative in ('.git', '.venv', '.local-tests', 'tests', 'main.tex', 'main.pdf',
                         'AGENTS.md', 'docs/session.log', 'assets/paper.pdf',
                         'scripts/__pycache__', 'scripts/.env.private', 'docs/private-review.md',
                         'assets/private-manuscript-figure.png', 'references/notes/.secrets.md'):
            self.assertFalse((destination / relative).exists(), relative)

    def test_nested_destination_and_symlinked_home_parent_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'must not contain'):
            installer.install('codex', home=self.source, source=self.source)
        outside = self.root / 'outside'
        outside.mkdir()
        (self.home / '.agents').symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'escapes the home'):
            installer.install('codex', home=self.home, source=self.source)
        self.assertEqual(list(outside.iterdir()), [])

    def test_nested_destination_through_internal_home_alias_is_rejected(self):
        source = self.home / 'shared'
        shutil.copytree(self.source, source)
        (self.home / '.agents').symlink_to(source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'must not contain'):
            installer.install('codex', home=self.home, source=source)
        self.assertFalse((source / 'skills/research-paper').exists())

    def test_runtime_symlink_and_incomplete_source_are_rejected(self):
        outside = self.root / 'external.md'
        outside.write_text('Private material')
        writing = self.source / 'references/writing.md'
        original = writing.read_bytes()
        writing.unlink()
        writing.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'contains a symlink'):
            installer.install('codex', home=self.home, source=self.source)
        writing.unlink()
        writing.write_bytes(original)
        for relative in ('scripts/workspace.py', 'rubrics/user-supplied-iclr-form.md',
                         'schemas/review.schema.json', 'prompts/scientific-reviewer.md',
                         'references/review-protocol.md'):
            with self.subTest(relative=relative):
                path = self.source / relative
                original = path.read_bytes()
                path.unlink()
                with self.assertRaisesRegex(ValueError, 'Incomplete skill package'):
                    installer.install('codex', home=self.home, source=self.source)
                path.write_bytes(original)
        self.assertFalse((self.home / '.agents').exists())

    def test_unknown_host_is_rejected_without_writes(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported host'):
            installer.install('unknown', home=self.home, source=self.source)
        self.assertEqual(list(self.home.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
