# Readability and local language tools

## Purpose

Measure prose to find passages worth inspecting. Require the agent to run the tool, examine what it measured, and record an interpretation. Do not require the paper to reach a numerical target. Clarity, scientific accuracy, the paragraph's purpose, and suitability for the intended reader remain judgments.

Use the bundled local helper first; add an existing open-source grammar or style tool only when it solves a real need. The default helper needs Python 3.10+ and never sends text or downloads resources. It is supplied under the MIT license in `LICENSE-QUALITY-TOOLS.txt`.

## What the linked research supports

Thomas Hikaru Clark, Matias B. Martin, and Kyle Mahowald, *Why is AI-generated language so hard to understand?*, arXiv:2610.29162v1, 21 October 2026: https://arxiv.org/abs/2610.29162 and https://arxiv.org/pdf/2610.29162 . Read Sections 3.1 and 7 and Appendix B for scope and measurement details.

The paper examines linguistic features associated with comprehension difficulty, including dependency length, object-relative clauses, stacked noun compounds, and unusual n-grams. Its analysis uses dependency parses and additional resources; some semantic features use a classifier. The dependency measure is standardized against a reference distribution by sentence length. The study does not provide a universal paper-readability score, an ICLR/ICML threshold, or a ready-made scientific-prose grader.

Use this as motivation to inspect dense phrasing. The optional local noun-stack and raw dependency diagnostics below are **inspired by the paper, not a replication**. They do not implement all of its measures, reference corpora, standardization, or classifiers. Neither conventional formula scores nor these diagnostics are an AI detector.

## Included measurements

| Measurement | What it supplies | How to interpret it |
|---|---|---|
| Automated Readability Index (ARI) | Character/word/sentence-based grade estimate | A rough English surface-complexity signal, not a reader's actual education requirement. |
| Coleman–Liau index | Letter/word/sentence-based grade estimate | Another rough signal with different assumptions; do not average into a new quality score. |
| Words, sentences, paragraphs | Explicit sample size | Check coverage and whether a small abstract is being compared to a full paper. |
| Mean, median, p90 sentence length | Distribution of sentence lengths | Inspect long or crowded sentences; short choppy prose can also be hard to read. |
| Located longest sentences | Section, source file and paragraph-start line | Find actionable passages. Report that the line is approximate, not an exact token map. |
| Optional local spaCy | Noun compounds containing at least three nouns; raw dependency lengths | Candidate constructions to inspect. Standard technical noun phrases are not automatically wrong. |

The default implementation uses documented, deterministic English tokenization and standard ARI/Coleman–Liau formulas; it does not claim byte-for-byte parity with textstat. It does not fabricate Flesch scores through a guessed syllable counter. Warnings for fewer than 100 words or five sentences are practical caution settings, not validated publication cutoffs. Never clip a negative or unusually high score into a misleading 0–100 scale.

## Measure actual prose

Run after a substantive section draft, a major prose revision, before a review round, and on the final candidate. Do not rerun after every keystroke.

```bash
python3 .paper-tools/research-paper/scripts/readability.py \
  --tex main.tex --root . --output-dir .paper/readability/round-001
```

The tool writes `report.json`, `report.md`, and `cleaned.txt`. It follows bounded local `\input`/`\include` files relative to the configured project/build root, without executing TeX. Preamble `\includeonly` is marked unsupported rather than silently measuring excluded sections as current prose. It keeps abstract/body/appendix section labels when recognized and reports sections separately. The overall score is for all included prose, so compare section-level values when their roles differ.

For the main score it excludes TeX preamble, heading labels, citation/reference keys, bibliography entries, equations, math, tables, figures, captions, footnotes, and code. These exclusions are recorded; they are **not permission to skip editorial or visual review** of those elements. Inspect captions separately; a caption can be measured as its own vetted prose sample if useful.

Inspect `cleaned.txt` against the manuscript, including a paragraph containing notation or a custom macro. Unsupported macros, conditionals, or environments produce `needs_review`; they must not silently count as complete extraction. This is a conservative reader, not a TeX interpreter. If it cannot extract a project faithfully, save inspected prose under `.paper/` and run:

```bash
python3 .paper-tools/research-paper/scripts/readability.py \
  --text .paper/prose-for-review.txt --output-dir .paper/readability/round-002
```

State which sections this text covers and which elements were reviewed separately. Never submit only easy paragraphs and claim the entire paper was assessed. The tool cannot prove the supplied text represents the manuscript; the agent must check this.

Keep old report directories for comparison. The helper refuses to overwrite a nonempty report directory. Check a saved report with `--check PATH/report.json --root PROJECT`.

## Act on the results

1. Confirm extraction, sample size, language, exclusions, and current input hashes.
2. Read each useful flagged passage in context. Look for multiple unrelated jobs, missing subjects/actions, an overloaded sentence, an unexplained term, or a chain of compressed noun modifiers.
3. Make an edit only when it improves the explanation while preserving meaning, assumptions, conditions, citations, numerical values, and standard vocabulary.
4. Read the revision naturally and inspect paragraph openings as a reverse outline. A better formula score cannot establish coherence.
5. Record what changed, what was retained and why, and what remains unresolved. A legitimate mathematical definition or standard term can remain difficult.

Do not game measurements by deleting qualifications, definitions, necessary citations, long method names, or scientifically meaningful clauses. Do not rewrite to many fragments. Never transform terminology merely to lower grade estimates. The intended audience is the actual research community.

## Compare revisions and style samples

Use `--baseline OLD/report.json` for matched before/after diagnostics. Mismatched settings, section coverage, extraction status, or optional parser versions are reported as incomparable. Matching settings still cannot prove that two passages cover the same scientific content; inspect that separately.

Use the user's chosen professor papers as descriptive style references only after extracting comparable prose and checking it. An abstract should be compared with abstracts, not a methods section or references page. Do not impose one professor's numeric score as a target, infer their preferences from scores, or penalize a paper for necessary notation.

## Optional open-source integrations

These tools remain optional. The supplied helper implements the standard-library measurements and optional spaCy path; it does not bundle the other packages or promise that their integrations have been executed.

| Tool | Use | Setup and boundary |
|---|---|---|
| textstat | Established implementation of Flesch, Flesch–Kincaid, Fog, ARI, Coleman–Liau, and other formulas | MIT license. Pin and record version and language resources. Its release history includes automatic dictionary downloads; verify local assets first and never use a hidden download or cloud fallback. Different tokenizers cannot be mixed silently with the bundled scores. |
| LanguageTool | Grammar/spelling suggestions from a locally running server | The local open-source server has fewer features than its hosted AI service. Confirm the endpoint is local. Preserve a project dictionary for technical vocabulary; accept fixes individually. |
| LTeX+ | LaTeX-aware LanguageTool checking inside VS Code | Prefer this existing interface over rebuilding a grammar checker. Checking can be offline, but initial installation may download a language server; offline installation packages exist. External-server settings can change where text goes. |
| Vale | Deterministic style and terminology rules | Apply to inspected prose using documented formats; do not assume native LaTeX parsing. Flag ambiguous terms for explanation, not automatic renaming. |
| spaCy | Optional local syntactic diagnostics | Use `--spacy-model NAME_OR_LOCAL_PATH` only for an already installed trusted English model with a dependency parser. Record library/model versions. No automatic download. |
| pylatexenc | A richer configurable LaTeX-to-text option for a future adapter | Still a heuristic conversion, not a TeX engine. Record macro handling and check output against the PDF. It is not required or invoked by the current helper. |

Grammar checking, readability metrics, terminology validation, and scientific review answer different questions. Do not describe a local grammar warning as evidence that a claim is scientifically false, or a high readability score as proof of correctness.

## Final-candidate record

After measurements and editorial inspection, record a real observation of the current built manuscript using `paperkit.py readability-review`. Supply the report path, observation reference, a coverage note, and a substantive disposition of flags. The record is bound to current source/build/report hashes. It records agent editorial work, not author approval for a scientific change. Follow `references/release.md` for the final author signoff.

The managed release check fails if the report or interpretation is absent/stale, inputs changed, or extraction is unresolved. A missing optional parser or a short sample is reported; neither invents a replacement score. No score threshold controls release. The tool does not authenticate the observer or prove comprehension.

## Primary sources

Checked 10 November 2026. Recheck installed-version details when enabling an optional integration.

- Paper: https://arxiv.org/abs/2610.29162 ; https://arxiv.org/pdf/2610.29162 .
- textstat code, metrics, license: https://github.com/textstat/textstat ; resource-download history: https://github.com/textstat/textstat/releases .
- LanguageTool local server: https://dev.languagetool.org/http-server ; license: https://github.com/languagetool-org/languagetool/blob/master/README.md .
- LTeX+: https://github.com/ltex-plus/vscode-ltex-plus ; installation: https://ltex-plus.github.io/ltex-plus/vscode-ltex-plus/installation-usage-vscode-ltex-plus.html .
- Vale: https://github.com/vale-cli/vale ; formats: https://docs.vale.sh/formats ; readability rules: https://docs.vale.sh/checks/readability .
- spaCy: https://spacy.io/usage/linguistic-features#dependency-parse ; models: https://spacy.io/usage/models .
- pylatexenc: https://github.com/phfaist/pylatexenc ; https://pylatexenc.readthedocs.io/en/v2.10/latex2text/ .
