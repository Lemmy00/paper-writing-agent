# Stage workflow

Keep the visible experience simple: one conversation and one configuration. Maintain style notes, questions, claims, terminology, reviews, and decisions under `.paper/`; do not ask the author to maintain these manually. Record state after meaningful decisions. Keep stage outputs compact and useful.

## Stage outputs and checkpoints

| Stage | Output | Author checkpoint |
|---|---|---|
| Style | Sample-backed conventions, short sample rewrite, visual references | Approve usable conventions; do not infer supervisors' private tastes |
| Background | Source library, comparison notes, close-work alerts, early related work | Resolve uncertain distinctions |
| Story | One-sentence contribution plus argument and section outline | Confirm the scientific message, scope, and terms |
| Method | Accurate method text and proposed visuals/placement | Confirm method understanding and unresolved implementation choices |
| Results | Evidence-linked text, plots, tables, interpretation | Confirm uncertain provenance, interpretation, and experiment requests |
| Introduction/conclusion | Motivation and synthesis aligned with body | Approve substantive changes to contribution or scope |
| Abstract | Natural, specific, compelling summary | Check every result and claim against final body |

A checkpoint is a short question or confirmation of meaningful decisions, not a request to approve every grammar fix. Do not demand results during style orientation. Ask before committing scientific guesses even when config is filled.

At each writing checkpoint also check terminology and relevance, then run and interpret the available readability measurements. Keep draft reports in `.paper/`; the author need not operate the tools. When layout changes, inspect affected pages individually, including pages changed by reflow. Before final handoff inspect every page of the current PDF separately, including references and appendices, and bind the visual records and readability interpretation to that candidate. See `references/page-qa.md`, `references/readability.md`, and `references/release.md`.

## Reopen only what changed

New close prior work may reopen background and story. A method change may affect method, experiments, figures, and claims. New results may affect results, contribution, introduction, conclusion, and abstract. A figure layout fix needs new visual inspection, not new experiments. Recheck all dependent claims and stale approvals after substantive changes.

An updated build invalidates observations of changed pages; final release requires a complete audit of the latest PDF. A prose edit requires refreshed readability extraction/metrics and interpretation. A renamed concept requires checking every occurrence and definition, not just the edited paragraph. Remove stale method descriptions and results instead of maintaining a public history of versions.

## Incomplete projects

An author may request a readiness review after any stage. Explicitly list what the reviewer actually received. Missing results mean a claim is not yet assessable; they do not establish the method is wrong. Keep research questions and experiment requests separate from the manuscript. Never fill gaps with fictional results. Do not present a submission recommendation as calibrated for a partially supplied project.

## Source library

Use `sources/pdfs/`, `sources/text/`, `sources/notes/`, and `sources/index.json`. Preserve original PDFs and record canonical URL/DOI, title, authors, version, retrieval time, hash, role (style/background/both), extraction status, and actual reading coverage. Download only permitted accessible copies; ask for missing authorized PDFs. Do not bypass paywalls or access restrictions. Update `config/paper.yaml` conversationally while leaving detailed provenance agent-managed.
