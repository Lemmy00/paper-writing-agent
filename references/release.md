# Provisional text and managed release

## Author-controlled TODO lifecycle
Ask before inserting any manuscript TODO or deliberate provisional content. Approval is scoped to the ID, file, and exact provisional body; changes need renewed approval. Without approval, put the question in `.paper/`, not the manuscript. Register with `paperkit.py todo-add` using a real approval reference. The helper prints, but does not insert, a wrapper.

Use `\PaperTODO{T001}{Confirm the measured inference budget.}` for inline/block prose, or `\begin{PaperProvisional}{T001}...\end{PaperProvisional}` for a whole provisional block. Use the bundled `paper-todos.sty`; default mode is final and raises an error on either marker. `[draft]` mode visibly displays them. Never redefine the commands to erase text. Compile with halt-on-error.

Each return to the project surfaces relevant open TODOs. Before review freeze and before release ask whether to resolve, keep for internal draft, or remove with dependent content/claims. Removal is a scientific/editorial decision, not a global search-and-delete. Record the real author decision, update the content, then close the ledger entry. Keep resolved history. Do not close an item while its wrapper remains.

## Two defenses
1. **Compilation:** final-mode wrapper use errors. A draft mode is allowed for internal work, but is not a submission mode.
2. **Managed preflight:** inspect source, comments, captions, bibliography/table/figure sources, ledger, build log, and extracted final PDF text. Block unknown/unapproved markers, unresolved tasks, common TODO/TBD/FIXME/XXX/placeholder markers, unresolved references/citations, stale build receipts, and missing signoff.

The scanner is conservative and not a full TeX interpreter. It may flag a literal acronym as a placeholder and cannot recognize every semantically provisional sentence or obfuscated macro. No silent blanket exclusions: ask about false positives. Final visual and semantic inspection remains mandatory. The tool does not intercept arbitrary manual compilation or upload.

## Managed build and release check
Run `paperkit.py build PROJECT --main main.tex --allow-build` only after permission to execute local LaTeX. It disables latexmk rc loading and TeX shell escape, uses a dedicated build directory, records a content snapshot and PDF/log hashes, and refuses a build that changes tracked inputs. This reduces accidental execution risk but is not an OS sandbox; untrusted TeX still requires isolation.

After the candidate is complete, actually inspect it. Confirm scientific claims, citation support, familiar or explained terminology, relevance to the current evaluated work, interpreted readability diagnostics, visual quality of every page, mandatory venue rules/disclosures, and absence of provisional material. Preserve the seven-stage writing sequence; these are checks around that sequence, not new user setup steps.

1. Build the current candidate using existing authorization. Do not ask repeatedly for routine compilation already in scope.
2. Run `scripts/readability.py`, inspect `cleaned.txt`, and resolve unsupported extraction or provide vetted prose. Read flagged passages, revise when useful, and preserve technically necessary wording. Record a final editorial interpretation with `paperkit.py readability-review PROJECT --report .paper/readability/round-001/report.json --observation-ref 'actual editorial observation reference' --coverage 'specific sections and exclusions checked against the current candidate' --disposition 'specific changes and justified retained constructions'`. This is the agent's observation, not invented author approval. The source/build/report hashes bind it to the candidate. Any edits needed after the measurement require a fresh report and candidate record.
3. Follow `references/page-qa.md`: render the final PDF to `.paper/visual/`, open **each page separately as an image**, zoom as necessary, and record individual observations. All pages, including references and appendices, must pass. A montage, batch of thumbnails, extracted text, or rendering itself never suffices. Archive the old audit before rerendering a changed candidate; never copy old pass records into the new one.
4. Obtain the real author's final signoff when needed and use `paperkit.py approve-release PROJECT --approval-ref 'real conversation reference' --checks science,citations,terminology,relevance,readability,visual,venue,provisional`. This is a recorded attestation, not automated scientific or visual understanding. It binds source/PDF/log hashes, the visual manifest, and the readability interpretation. Never invoke it without the actual inspections and approval.

Readability review completion is required; no ARI, Coleman–Liau, grammar-warning count, or synthetic score threshold determines submission readiness. A short sample or an unavailable optional parser is disclosed. Unresolved extraction coverage, a stale report, an unseen page, or a page requiring repair prevents a false completion claim.

Run `paperkit.py preflight PROJECT --mode submission`. Any changed source, media, bibliography, configuration, PDF, or log invalidates the receipt/signoff. `.paper/` and tool directories are not submission sources; do not put manuscript inputs there except managed build artifacts. Symlinked manuscript inputs are rejected. Report checks that are unavailable rather than mark them passed.

A successful preflight does not upload the paper or guarantee scientific correctness. It means the implemented checks passed on the approved artifact. The record checks cannot prove that an observer actually viewed an image or comprehended a passage; that remains an explicit agent responsibility. Never promise that regex checks alone can detect all unfinished prose. Keep writing completeness, evidence sufficiency, terminology/relevance, readability interpretation, visual coverage, review status, and release hygiene separate.

## Literal marker exceptions
For a genuinely final, literal occurrence of a marker word (for example a cited acronym), the agent may record an author-approved, exact-line exception in `state.literal_exceptions`: `file`, `line` (1-based), `sha256` of that exact UTF-8 line without newline, `approval_ref`, and `reason`. For extracted PDF lines use `file: "@pdf"`. No wildcard or folder exemption exists. This cannot exempt a provisional wrapper, an open ledger item, or a build error. Never use exceptions to conceal unfinished text. Both source and PDF occurrences must be inspected; changed lines invalidate the exception.
