# Individual page-image inspection

## Completion rule

Inspect **every page of the current compiled manuscript as a separate full-page image**. This includes the title/abstract page, pages without figures, references, and appendices. Open one page image at a time. A contact sheet, tiled montage, multi-page image bundle, extracted text, successful rendering, or clean compiler log does not satisfy this requirement. A crop may supplement a full-page view but cannot replace it.

Use the host's actual image-viewing tool. Inspect page composition at intended publication scale, then zoom or crop small details as necessary. If the host cannot display images, mark visual inspection unavailable and leave the gate incomplete; do not infer layout quality from text or source code.

## What to examine on each page

- Check reading order, columns, margins, whitespace, headers, footers, page numbers, section breaks, and stranded headings or lines.
- Check text, equations, tables, captions, and footnotes for clipping, overlap, collisions, tiny type, awkward breaks, and inconsistent formatting.
- Check each figure's labels, legends, axes, arrows, colors, and caption at the scale used in the manuscript. Cross-check what it claims against the evidence separately.
- Check references and appendix pages with the same care. Empty or unusually sparse pages need a deliberate explanation.
- Record a few page-specific observations and the locations of actual defects. A generic "looks good" or copied note does not count as a close inspection.

Visual review remains separate from the independent scientific reviews. A scientific reviewer with only text access cannot approve page layout.

## Local helper

The bundled `scripts/visual_audit.py` uses local Poppler (`pdfinfo` and `pdftoppm`). It does not install software or call a provider. From a project, substitute the installed helper path:

```bash
python3 .paper-tools/research-paper/scripts/visual_audit.py render \
  .paper/build/main.pdf --output .paper/visual
```

The output contains `page-001.png`, `page-002.png`, and so forth, plus `audit.json`. Every page starts pending. Rendering may process the PDF in one command; **inspection must still happen one image at a time**. The manifest records the exact PDF hash, actual page count, image hashes/dimensions, render settings, and individual observations.

After actually viewing a page, record its result:

```bash
python3 .paper-tools/research-paper/scripts/visual_audit.py record \
  .paper/build/main.pdf --manifest .paper/visual/audit.json \
  --page 1 --reviewer visual-reviewer \
  --observation-ref 'actual session and individual-image observation reference' \
  --findings 'Specific observations about the elements visible on this page.' \
  --status pass
```

Use `needs_fix` for an unresolved defect. The example observation reference is a template, not evidence; replace it with the real view event or a real human inspection record. Never record an inspection merely because an image exists. Use a distinct observation reference and specific findings for every page.

```bash
python3 .paper-tools/research-paper/scripts/visual_audit.py check \
  .paper/build/main.pdf --manifest .paper/visual/audit.json
```

The check fails if any page is pending, has an unresolved defect, is missing, has changed, or lacks an appropriate record. It also checks the PDF's actual page count, so omitting references or appendices cannot make coverage complete. Unknown or malformed manifests fail closed. Existing unchanged renders can be reused without erasing their observations. A nonempty unrelated directory is never overwritten.

## Revisions and final review

During drafting, inspect affected pages after changes and include neighboring pages when floats, pagination, or text flow may have shifted. This helps locate defects early; it does not establish final coverage for another PDF.

After the final content or layout change, compile the candidate, render it, and inspect **every page of that exact PDF individually**. Any change to PDF bytes invalidates the previous candidate's audit. Preserve the old audit as history outside the active gate, then use a new empty `.paper/visual/` directory for the current candidate. Do not copy earlier pass records into the new audit. Reopening the same unchanged candidate reuses its valid records.

The managed release check requires the active audit at `.paper/visual/audit.json`; the signoff also binds that manifest. A later change to observations requires renewed final signoff. Keep the author-facing status clear: "12 of 14 pages inspected; pages 13 and 14 pending" or "page 6 needs a caption repair."

## Limits of enforcement

The tool verifies artifact identity and completeness of recorded coverage. It cannot authenticate a person's identity, prove that an agent actually used an image viewer, or judge whether observations are scientifically correct. Those remain agent and author responsibilities. A passed coverage check must never be described as automatic visual understanding.
