# Testing

From a source checkout, use Python 3.10+ and install the optional validation dependencies. The example uses a virtual environment to keep these development dependencies separate; it is not part of normal skill use. Personal skill installations contain the runtime resources rather than the development test suite.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
```

Full integration coverage needs `latexmk`, `pdflatex`, `pdftotext`, `pdfinfo`, and `pdftoppm`. Tests requiring missing tools are skipped, so inspect the final count.

## Verified on 11 November 2026

| Platform | Environment | Result |
|---|---|---|
| macOS | Python 3.11.15, local LaTeX and Poppler | 178 passed, none skipped |
| Linux | Python 3.13.9, TeX Live 2023, latexmk 4.89, Poppler | 178 passed, none skipped |

These runs included actual LaTeX builds, PDF extraction, page rendering, review-schema parity, packet integrity, preservation of existing project files, and stale-record checks. The Codex skill validator also passed.

Installation tests cover all three personal locations, self-contained copies, existing-file preservation, generated-cache handling, and project initialization after deleting the source checkout. A separate bounded onboarding trial confirmed that an agent could set up an existing draft from a personal installation through chat.

Readability regressions cover literal inline code, percent signs inside code, comment boundaries, layout commands, and malformed verbatim delimiters. Unknown custom macros still require inspected extraction rather than an automatic pass.

Orchestration regressions cover approval before calls, partial grants, sealed initial reviews before synthesis, plan and source changes, exact diff approval, safe application and rollback, build cancellation, bounded retries, saved progress, and evidence/author handoffs. Provider checks cover CLI construction, schema validation, restricted tools, deadlines, cancellation, and compatibility failures.

Live integration checks used a disposable one-page synthetic draft and the installed agent logins, within separately approved request limits. Codex and Claude returned valid structured reviews. Antigravity's two live responses were rejected by the tool parser; compatibility fixes pass offline checks, but a successful live Antigravity review has not been established. No real paper was used in these provider checks. The Codex trial used 12 requests total and exercised three review perspectives, synthesis, an approved writing task, a proposed diff, separately approved application/build, and a fresh review round. Initial schema failures led to fixes; an explicit temporary test-state migration preserved the sealed pre-fix reviews. The writing phase and complete second review round used the final controller. Approval decisions were simulated only inside that disposable fixture.

The suite checks workflow behavior and record integrity. It does not validate scientific claims, prove that a page was visually inspected, or establish acceptance readiness. Interactive skill discovery has not been tested in every host. A VS Code extension is not implemented.
