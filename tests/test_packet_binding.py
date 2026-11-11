"""Packet integrity tests use synthetic bytes, not a reviewer or a real paper."""
import json
import tempfile
import unittest
from pathlib import Path

from test_paperkit import pk, review


class PacketBindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.packet = Path(self.tmp.name).resolve()
        files = {}
        for name in ('manuscript.pdf', 'manuscript.txt', 'rubric.md',
                     'instructions.md', 'review.schema.json'):
            target = self.packet / name
            target.write_text('Synthetic fixture: ' + name)
            files[name] = pk.sha(target)
        self.manifest = {'mode': 'development', 'files': files}
        self.manifest['packet_hash'] = pk.digest(json.dumps(self.manifest, sort_keys=True).encode())
        self.write_manifest()
        self.value = review()
        self.value['packet_hash'] = self.manifest['packet_hash']

    def tearDown(self):
        self.tmp.cleanup()

    def write_manifest(self):
        pk.dump(self.packet / 'packet.json', self.manifest)

    def test_matching_review_passes(self):
        self.assertEqual(pk.validate_review_packet(self.value, self.packet), [])

    def test_other_packet_review_rejected(self):
        self.value['packet_hash'] = 'b' * 64
        self.assertTrue(any('different frozen packet' in e for e in pk.validate_review_packet(self.value, self.packet)))

    def test_changed_and_missing_packet_files_rejected(self):
        for name in self.manifest['files']:
            with self.subTest(name=name):
                path = self.packet / name
                original = path.read_bytes()
                path.write_text('Changed packet content')
                self.assertTrue(pk.validate_review_packet(self.value, self.packet))
                path.unlink()
                self.assertTrue(pk.validate_review_packet(self.value, self.packet))
                path.write_bytes(original)

    def test_manifest_hash_tampering_rejected(self):
        self.manifest['packet_hash'] = '0' * 64
        self.write_manifest()
        self.assertTrue(pk.validate_review_packet(self.value, self.packet))

    def test_review_mode_must_match(self):
        self.value['mode'] = 'submission_mock'
        self.value['rating']['score'] = 3
        self.assertTrue(any('mode differs' in e for e in pk.validate_review_packet(self.value, self.packet)))

    def test_unsafe_or_malformed_manifest_rejected(self):
        self.manifest['files']['../outside'] = 'a' * 64
        self.write_manifest()
        self.assertTrue(pk.validate_review_packet(self.value, self.packet))
        (self.packet / 'packet.json').write_text('[]')
        self.assertTrue(pk.validate_review_packet(self.value, self.packet))

    def test_symlinked_packet_member_rejected(self):
        target = self.packet / 'manuscript.txt'
        target.unlink()
        source = self.packet / 'alternate.txt'
        source.write_text('Synthetic fixture: manuscript.txt')
        target.symlink_to(source)
        self.assertTrue(pk.validate_review_packet(self.value, self.packet))
