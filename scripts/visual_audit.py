#!/usr/bin/env python3
"""Render individual PDF pages and check recorded visual-inspection coverage.

Records are attestations: this helper cannot verify that a human or model actually
viewed an image. It does verify artifact identity, one record per page, and stale
or incomplete coverage. No provider calls or dependency installation occur.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
KIND = "individual-page-visual-audit"
HASH = re.compile(r"^[0-9a-f]{64}$")
TOP_KEYS = {"schema_version", "kind", "created_at", "pdf_sha256", "pdf_pages", "render", "pages"}
PAGE_KEYS = {"page", "image", "image_sha256", "width_px", "height_px", "inspection"}
RENDER_KEYS = {"dpi", "format", "renderer", "renderer_version"}
INSPECTION_KEYS = {"reviewer", "observation_ref", "inspected_at", "findings", "status",
                   "view_kind", "pdf_sha256", "image_sha256"}


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else _legacy_hash(stream)


def _legacy_hash(stream) -> str:
    value = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(block)
    return value.hexdigest()


def _regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular, existing file: {path}")


def _run(argv: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=timeout, env={**os.environ, "LC_ALL": "C"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"Cannot run {Path(argv[0]).name}: {exc}") from exc
    if result.returncode:
        raise ValueError(f"{Path(argv[0]).name} failed: {result.stderr.strip()[:500]}")
    return result


def _binary(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise ValueError(f"{name} is unavailable; visual audit cannot pass. Do not auto-install.")
    return found


def pdf_page_count(pdf: Path) -> int:
    _regular_file(pdf, "PDF")
    result = _run([_binary("pdfinfo"), str(pdf)])
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
    if not match or int(match.group(1)) < 1:
        raise ValueError("Cannot determine the complete PDF page count.")
    return int(match.group(1))


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"Invalid PNG header: {path.name}")
    width, height = struct.unpack(">II", header[16:24])
    if width < 1 or height < 1:
        raise ValueError(f"Invalid PNG dimensions: {path.name}")
    return width, height


def _write_json(path: Path, data: dict) -> None:
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlinked audit manifest.")
    descriptor, temporary = tempfile.mkstemp(prefix=".audit-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _read_manifest(manifest: Path) -> dict:
    _regular_file(manifest, "Audit manifest")
    if manifest.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("Audit manifest is unexpectedly large.")
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Unreadable audit manifest: {exc}") from exc
    if not isinstance(data, dict) or set(data) != TOP_KEYS:
        raise ValueError("Unknown or incomplete audit manifest structure.")
    if type(data["schema_version"]) is not int or data["schema_version"] != SCHEMA_VERSION or data["kind"] != KIND:
        raise ValueError("Unknown visual audit schema or kind.")
    return data


def _valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return datetime.fromisoformat(value).tzinfo is not None
    except ValueError:
        return False


def _specific_findings(value: Any) -> bool:
    if not isinstance(value, str) or len(value.strip()) < 24:
        return False
    return value.strip().lower() not in {"all pages look fine and readable", "everything looks good on this page"}


def _validate(pdf: Path, manifest: Path, require_inspection: bool) -> tuple[dict, list[str], int]:
    data = _read_manifest(manifest)
    _regular_file(pdf, "PDF")
    errors: list[str] = []
    current_hash = sha256(pdf)
    count = pdf_page_count(pdf)
    if not isinstance(data["pdf_sha256"], str) or not HASH.fullmatch(data["pdf_sha256"]) or data["pdf_sha256"] != current_hash:
        errors.append("PDF hash changed or is invalid; render and inspect the current candidate.")
    if type(data["pdf_pages"]) is not int or data["pdf_pages"] != count:
        errors.append("Manifest page count does not match the complete current PDF.")
    if not _valid_timestamp(data["created_at"]):
        errors.append("Invalid audit creation timestamp.")
    settings = data["render"]
    if (not isinstance(settings, dict) or set(settings) != RENDER_KEYS or
            settings.get("format") != "png" or settings.get("renderer") != "pdftoppm" or
            type(settings.get("dpi")) is not int or not 100 <= settings.get("dpi", 0) <= 600 or
            not isinstance(settings.get("renderer_version"), str) or not settings.get("renderer_version", "").strip()):
        errors.append("Unknown or incomplete individual-page render settings.")
    pages = data["pages"]
    if not isinstance(pages, list) or len(pages) != count:
        errors.append("Every PDF page requires its own full-page image and audit entry.")
        return data, errors, 0
    seen_notes: set[str] = set()
    seen_refs: set[str] = set()
    reviewed = 0
    for number, entry in enumerate(pages, 1):
        prefix = f"Page {number}: "
        if not isinstance(entry, dict) or set(entry) != PAGE_KEYS:
            errors.append(prefix + "unknown or incomplete page entry.")
            continue
        if type(entry["page"]) is not int or entry["page"] != number:
            errors.append(prefix + "page numbers must be unique, complete, and in PDF order.")
        filename = f"page-{number:03d}.png"
        if entry["image"] != filename:
            errors.append(prefix + "requires its own named full-page image, not a bundle or crop.")
            continue
        image = manifest.parent / filename
        try:
            _regular_file(image, "Page image")
            if not isinstance(entry["image_sha256"], str) or not HASH.fullmatch(entry["image_sha256"]) or sha256(image) != entry["image_sha256"]:
                errors.append(prefix + "image missing, changed, or not bound to the audit.")
            width, height = _png_size(image)
            if type(entry["width_px"]) is not int or type(entry["height_px"]) is not int or (entry["width_px"], entry["height_px"]) != (width, height):
                errors.append(prefix + "image dimensions changed or are invalid.")
        except (OSError, ValueError) as exc:
            errors.append(prefix + str(exc))
        inspection = entry["inspection"]
        if inspection is None:
            if require_inspection:
                errors.append(prefix + "individual image inspection is pending.")
            continue
        if not isinstance(inspection, dict) or set(inspection) != INSPECTION_KEYS:
            errors.append(prefix + "unknown or incomplete inspection record.")
            continue
        for key in ("reviewer", "observation_ref"):
            if not isinstance(inspection[key], str) or not inspection[key].strip():
                errors.append(prefix + f"missing {key}.")
        observation = str(inspection["observation_ref"]).strip()
        if observation in seen_refs:
            errors.append(prefix + "inspection reference was reused for another page; inspect each image separately.")
        seen_refs.add(observation)
        notes = inspection["findings"]
        if not _specific_findings(notes):
            errors.append(prefix + "requires specific observations, not an empty or generic pass.")
        normalized = " ".join(str(notes).casefold().split())
        if normalized in seen_notes:
            errors.append(prefix + "findings were copied from another page; record page-specific observations.")
        seen_notes.add(normalized)
        if not _valid_timestamp(inspection["inspected_at"]):
            errors.append(prefix + "invalid inspection timestamp.")
        if inspection["view_kind"] != "individual_full_page":
            errors.append(prefix + "bundle, contact-sheet, crop-only, or text-only inspection does not count.")
        if inspection["pdf_sha256"] != data["pdf_sha256"] or inspection["image_sha256"] != entry["image_sha256"]:
            errors.append(prefix + "inspection is stale for this PDF or page image.")
        if inspection["status"] not in {"pass", "needs_fix"}:
            errors.append(prefix + "unknown inspection status.")
        elif inspection["status"] == "needs_fix":
            reviewed += 1
            if require_inspection:
                errors.append(prefix + "visual defect remains unresolved.")
        else:
            reviewed += 1
    return data, errors, reviewed


def render_pdf(pdf: Path, output_dir: Path, dpi: int = 160) -> dict:
    """Create individual page PNGs and a pending audit; reuse an intact identical audit."""
    pdf, output_dir = Path(pdf).absolute(), Path(output_dir).absolute()
    _regular_file(pdf, "PDF")
    if type(dpi) is not int or not 100 <= dpi <= 600:
        raise ValueError("DPI must be an integer between 100 and 600.")
    if output_dir.is_symlink() or (output_dir.exists() and not output_dir.is_dir()):
        raise ValueError("Output must be a normal directory, not a symlink or file.")
    manifest = output_dir / "audit.json"
    if output_dir.exists() and any(output_dir.iterdir()):
        if not manifest.is_file():
            raise ValueError("Refusing to overwrite a nonempty directory without a valid audit.")
        data, errors, _ = _validate(pdf, manifest, require_inspection=False)
        if isinstance(data["render"], dict) and data["render"].get("dpi") != dpi:
            errors.append("Render resolution changed.")
        if errors:
            raise ValueError("Existing audit cannot be reused; use a new output directory: " + "; ".join(errors))
        return data
    count = pdf_page_count(pdf)
    source_hash = sha256(pdf)
    binary = _binary("pdftoppm")
    version_result = _run([binary, "-v"])
    version = (version_result.stderr or version_result.stdout).splitlines()[0]
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".pageqa-", dir=output_dir.parent) as temporary:
        staging = Path(temporary)
        _run([binary, "-png", "-r", str(dpi), str(pdf), str(staging / "render")], timeout=300)
        raw = list(staging.glob("render-*.png"))
        if len(raw) != count or sha256(pdf) != source_hash:
            raise ValueError("Rendering did not produce every page, or PDF changed while rendering.")
        numbered = {}
        for image in raw:
            match = re.fullmatch(r"render-(\d+)\.png", image.name)
            if not match or int(match.group(1)) in numbered:
                raise ValueError("Unexpected page-render output.")
            numbered[int(match.group(1))] = image
        if set(numbered) != set(range(1, count + 1)):
            raise ValueError("Rendering has missing or extra PDF pages.")
        pages = []
        for number in range(1, count + 1):
            image = staging / f"page-{number:03d}.png"
            numbered[number].rename(image)
            width, height = _png_size(image)
            pages.append({"page": number, "image": image.name, "image_sha256": sha256(image),
                          "width_px": width, "height_px": height, "inspection": None})
        data = {"schema_version": SCHEMA_VERSION, "kind": KIND, "created_at": timestamp(),
                "pdf_sha256": source_hash, "pdf_pages": count,
                "render": {"dpi": dpi, "format": "png", "renderer": "pdftoppm", "renderer_version": version},
                "pages": pages}
        _write_json(staging / "audit.json", data)
        output_dir.mkdir(parents=True, exist_ok=True)
        if any(output_dir.iterdir()):
            raise ValueError("Output directory changed during render; refusing to overwrite its content.")
        # The manifest is moved last; partial transfers cannot appear as complete.
        for entry in pages:
            shutil.move(str(staging / entry["image"]), str(output_dir / entry["image"]))
        shutil.move(str(staging / "audit.json"), str(manifest))
    return data


def record_page(pdf: Path, manifest: Path, page: int, reviewer: str,
                observation_ref: str, findings: str, status: str = "pass") -> dict:
    """Record a real inspection already performed; never call merely because rendering succeeded."""
    pdf, manifest = Path(pdf).absolute(), Path(manifest).absolute()
    data, errors, _ = _validate(pdf, manifest, require_inspection=False)
    if errors:
        raise ValueError("Cannot record against an invalid audit: " + "; ".join(errors))
    if type(page) is not int or not 1 <= page <= data["pdf_pages"]:
        raise ValueError("Page must identify exactly one existing PDF page.")
    if not reviewer.strip() or not observation_ref.strip() or not _specific_findings(findings):
        raise ValueError("Require reviewer, real observation reference, and page-specific findings of at least 24 characters.")
    if status not in {"pass", "needs_fix"}:
        raise ValueError("Status must be pass or needs_fix.")
    normalized = " ".join(findings.casefold().split())
    for entry in data["pages"]:
        prior = entry["inspection"]
        if entry["page"] != page and prior:
            if prior["observation_ref"].strip() == observation_ref.strip():
                raise ValueError("Each page requires a distinct individual-image observation reference.")
            if " ".join(prior["findings"].casefold().split()) == normalized:
                raise ValueError("Do not copy another page's findings; inspect and describe this page individually.")
    target = data["pages"][page - 1]
    target["inspection"] = {"reviewer": reviewer.strip(), "observation_ref": observation_ref.strip(),
                            "inspected_at": timestamp(), "findings": findings.strip(), "status": status,
                            "view_kind": "individual_full_page", "pdf_sha256": data["pdf_sha256"],
                            "image_sha256": target["image_sha256"]}
    _write_json(manifest, data)
    return target


def check_audit(pdf: Path, manifest: Path) -> dict:
    """Return fail-closed artifact/coverage checks; this is not visual perception."""
    pdf, manifest = Path(pdf).absolute(), Path(manifest).absolute()
    result = {"passed": False, "errors": [], "page_count": None, "reviewed_pages": 0,
              "pdf_sha256": None, "manifest_sha256": None,
              "scope": "Artifact integrity and per-page recorded coverage; does not authenticate actual image viewing or visual judgment."}
    try:
        data, errors, reviewed = _validate(pdf, manifest, require_inspection=True)
        result.update(errors=errors, page_count=data["pdf_pages"], reviewed_pages=reviewed,
                      pdf_sha256=data["pdf_sha256"], manifest_sha256=sha256(manifest), passed=not errors)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result["errors"] = [str(exc)]
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    render = commands.add_parser("render")
    render.add_argument("pdf", type=Path)
    render.add_argument("--output", required=True, type=Path)
    render.add_argument("--dpi", type=int, default=160)
    record = commands.add_parser("record")
    record.add_argument("pdf", type=Path)
    record.add_argument("--manifest", required=True, type=Path)
    record.add_argument("--page", required=True, type=int)
    record.add_argument("--reviewer", required=True)
    record.add_argument("--observation-ref", required=True)
    record.add_argument("--findings", required=True)
    record.add_argument("--status", required=True, choices=("pass", "needs_fix"))
    check = commands.add_parser("check")
    check.add_argument("pdf", type=Path)
    check.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "render":
            result = render_pdf(args.pdf, args.output, args.dpi)
        elif args.command == "record":
            result = record_page(args.pdf, args.manifest, args.page, args.reviewer,
                                 args.observation_ref, args.findings, args.status)
        else:
            result = check_audit(args.pdf, args.manifest)
        print(json.dumps(result, indent=2))
        return 1 if args.command == "check" and not result["passed"] else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
