from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import visual_audit as va


def write_pdf(path: Path) -> None:
    """Two readable pages using only the PDF core font; no extra dependency."""
    pages = ["Synthetic fixture: page one.", "Synthetic fixture: appendix page two."]
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [4 0 R 6 0 R] /Count 2 >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    for index, text in enumerate(pages):
        contents_number = 5 + 2 * index
        objects.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 500] "
                        "/Resources << /Font << /F1 3 0 R >> >> "
                        f"/Contents {contents_number} 0 R >>").encode())
        stream = f"BT /F1 14 Tf 30 450 Td ({text}) Tj ET\n".encode()
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream")
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, value in enumerate(objects, 1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + value + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        output += f"{offset:010d} 00000 n \n".encode()
    output += f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(output)


@unittest.skipUnless(shutil.which("pdftoppm") and shutil.which("pdfinfo"), "Poppler is unavailable")
class VisualAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.pdf = self.root / "fixture.pdf"
        write_pdf(self.pdf)
        self.output = self.root / "visual"
        va.render_pdf(self.pdf, self.output, dpi=100)
        self.manifest = self.output / "audit.json"

    def tearDown(self):
        self.temporary.cleanup()

    def record(self, page, status="pass"):
        # Deliberately synthetic records test coverage logic, not visual perception.
        return va.record_page(self.pdf, self.manifest, page, "SYNTHETIC UNIT TEST",
                              f"synthetic-test-only-page-{page}",
                              f"Synthetic observation for page {page}: fixture label and margins are recorded for test purposes.", status)

    def test_real_render_creates_all_pages_and_no_inspections(self):
        data = json.loads(self.manifest.read_text())
        self.assertEqual(data["pdf_pages"], 2)
        self.assertEqual(sorted(p.name for p in self.output.glob("*.png")), ["page-001.png", "page-002.png"])
        self.assertTrue(all(entry["inspection"] is None for entry in data["pages"]))
        result = va.check_audit(self.pdf, self.manifest)
        self.assertFalse(result["passed"])
        self.assertEqual(result["reviewed_pages"], 0)

    def test_one_page_is_insufficient_and_complete_attestations_pass(self):
        self.record(1)
        result = va.check_audit(self.pdf, self.manifest)
        self.assertFalse(result["passed"])
        self.assertEqual(result["reviewed_pages"], 1)
        self.record(2)
        self.assertTrue(va.check_audit(self.pdf, self.manifest)["passed"])

    def test_needs_fix_blocks_coverage(self):
        self.record(1)
        self.record(2, "needs_fix")
        result = va.check_audit(self.pdf, self.manifest)
        self.assertEqual(result["reviewed_pages"], 2)
        self.assertTrue(any("unresolved" in error for error in result["errors"]))

    def test_image_mutation_invalidates_record(self):
        self.record(1)
        self.record(2)
        with (self.output / "page-002.png").open("ab") as stream:
            stream.write(b"changed")
        self.assertFalse(va.check_audit(self.pdf, self.manifest)["passed"])
        with self.assertRaises(ValueError):
            self.record(2)

    def test_new_pdf_requires_new_render_and_records(self):
        self.record(1)
        self.record(2)
        with self.pdf.open("ab") as stream:
            stream.write(b"\nchanged PDF bytes\n")
        self.assertFalse(va.check_audit(self.pdf, self.manifest)["passed"])
        with self.assertRaises(ValueError):
            va.render_pdf(self.pdf, self.output, dpi=100)

    def test_missing_appendix_page_cannot_pass(self):
        self.record(1)
        self.record(2)
        data = json.loads(self.manifest.read_text())
        data["pages"].pop()
        data["pdf_pages"] = 1
        self.manifest.write_text(json.dumps(data))
        result = va.check_audit(self.pdf, self.manifest)
        self.assertFalse(result["passed"])
        self.assertTrue(any("page count" in error for error in result["errors"]))

    def test_missing_image_cannot_pass(self):
        self.record(1)
        self.record(2)
        (self.output / "page-002.png").unlink()
        self.assertFalse(va.check_audit(self.pdf, self.manifest)["passed"])

    def test_copied_findings_and_bundle_reference_rejected(self):
        entry = self.record(1)["inspection"]
        with self.assertRaises(ValueError):
            va.record_page(self.pdf, self.manifest, 2, "SYNTHETIC TEST", "different-ref", entry["findings"])
        with self.assertRaises(ValueError):
            va.record_page(self.pdf, self.manifest, 2, "SYNTHETIC TEST", entry["observation_ref"],
                           "Page two has distinct synthetic notes but reuses a bundled observation.")
        with self.assertRaises(ValueError):
            va.record_page(self.pdf, self.manifest, 2, "SYNTHETIC TEST", "new-ref", "looks good")

    def test_unknown_and_malformed_manifest_fail_closed(self):
        data = json.loads(self.manifest.read_text())
        data["schema_version"] = 99
        self.manifest.write_text(json.dumps(data))
        self.assertFalse(va.check_audit(self.pdf, self.manifest)["passed"])
        self.manifest.write_text("{not valid JSON")
        self.assertFalse(va.check_audit(self.pdf, self.manifest)["passed"])

    def test_idempotent_render_preserves_records(self):
        self.record(1)
        before = self.manifest.read_bytes()
        va.render_pdf(self.pdf, self.output, dpi=100)
        self.assertEqual(before, self.manifest.read_bytes())

    def test_unrelated_output_and_symlink_images_refused(self):
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        (unrelated / "author-note.txt").write_text("Keep this file.")
        with self.assertRaises(ValueError):
            va.render_pdf(self.pdf, unrelated)
        image = self.output / "page-001.png"
        saved = self.root / "saved.png"
        image.rename(saved)
        image.symlink_to(saved)
        self.assertFalse(va.check_audit(self.pdf, self.manifest)["passed"])


if __name__ == "__main__":
    unittest.main()
