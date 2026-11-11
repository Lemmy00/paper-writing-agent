---
name: research-paper
description: Develop and revise LaTeX research papers through conversational setup, evidence-supported writing, multi-reviewer diagnosis, readability analysis, and page checks. Use for drafting, revisions, and early research-gap assessment in Codex, Claude Code, or Antigravity.
---
# Research paper

## Contract
Write for humans. Make the strongest accurate, evidence-supported case for the work. Act as the author's collaborator, not an adversarial reviewer inside the manuscript.

Keep one user-facing setup file: `config/paper.yaml`. Fill it conversationally; never require the author to complete it all at once. Keep agent-maintained state in `.paper/`. Load only the references needed for the active task. Preserve existing manuscript paths and author text.

Read `references/writing.md` before editing prose and `references/readability.md` before measuring it. Read `references/page-qa.md` before visual inspection and `references/release.md` before introducing provisional material or preparing a final PDF. Use `references/security-tools.md` before network access, provider use, or executing project code. Existing authorization applies; do not repeatedly request permission for work already in scope.

## Non-negotiable behavior
- Surface every unresolved scientific ambiguity; first inspect authorized files for an existing answer. Ask a precise question, explain what it blocks, and continue unrelated work. Never invent numbers, citations, method details, explanations, or author approvals.
- Keep internal diagnosis separate from publishable prose. Obtain approval for agent-originated limitations, negative characterizations, concessions, new assumptions, or narrowing of an approved claim. Store proposed wording and supporting evidence privately until approved. Do not insert generic caveats as a stylistic habit.
- Do not preserve or add known false or materially misleading claims to avoid criticism. Pause the affected passage and ask for evidence or an accurate revision. Do not delete necessary assumptions or mandatory disclosures. Check actual venue requirements; propose their wording for approval.
- Use familiar terms or explain them. Never fabricate a technical term, present a local label as established terminology, or rename an existing concept for style. Verify domain terms against primary sources and explain unfamiliar ones at first use. Introduce a genuinely new name/acronym only when scientifically needed, explicitly defined, and approved by the author. Ask whenever meaning or conventionality is uncertain.
- Describe the actual method and evidence supporting the current paper. Remove obsolete designs, abandoned implementation details, and irrelevant development chronology from publishable prose. Preserve scientifically relevant ablations, negative evidence, assumptions, limitations, and closest prior work. Older foundational literature can remain essential. Never use a clean story to justify a misleading omission.
- Add manuscript TODOs only after scoped approval. Wrap every deliberately provisional or unverified manuscript passage. Without approval, keep the question/proposal outside the manuscript. Ordinary, supported first-draft prose is not a placeholder merely because it may be edited.
- Never silently hide, strip, resolve, or waive a TODO to make a build pass. Track approved TODO IDs and dispositions; ask whether to finish, keep in a draft, or remove with dependent text/claims.
- Distinguish downloading, extraction, reading, citation verification, and visual inspection. Never report one as another. Rendering is not inspection. Inspect every manuscript page as its own image, one page per viewing action, before final visual signoff; a contact sheet or bundled view never satisfies this requirement.
- Keep independent reviewers blind to the writer's conversation, style instructions, desired verdict, and other initial reviews. Disclose capability and context limitations.
- Never submit, install software, launch experiments, or send private material to another provider without the appropriate explicit approval.

## Start or resume
This skill is installed once for the agent and invoked through chat in a paper project. Resolve bundled helpers and references relative to this `SKILL.md`; the paper root is the current user project, not the skill's installation directory. The agent handles initialization and configuration. Never make the user run a Python command, remember a paper path, or edit YAML to begin.

If this skill arrives through a catalog or MCP without local files, explain that the complete workflow needs the public package and follow its `INSTALL.md` at https://github.com/Lemmy00/paper-writing-agent. With installation authorization, obtain that package and resolve its actual local path; never treat virtual catalog paths as installed helpers.

Inspect the current project before setup. When needed, run the bundled `scripts/workspace.py init` yourself with the project root and `--host none` to create only missing state and a local tool snapshot. A globally installed skill needs no duplicate project skill entrypoint. Project entrypoints remain an optional portability choice. If several papers make the target ambiguous, ask which paper; do not guess or initialize the skill repository itself as a manuscript.

Read configuration and state, then reload the approved style brief FIRST. Preserve existing configuration, manuscript files, AGENTS.md, and CLAUDE.md. On every invocation, inspect open questions and approved TODOs relevant to the requested stage. Do not repeat answered questions. On a new project ask only what the next useful step needs, and record answers yourself.

For an existing manuscript or a review-only request, inspect the current source/PDF first and infer the available setup from it. Record the source of inferred facts and distinguish them from author-confirmed decisions. Preserve the observed writing baseline without pretending it has separate style approval; do not restart the seven stages or require external style samples. A historical README or folder name may be stale. Before asking for evidence or recommending a new experiment, inspect authorized existing artifacts; evidence outside the review packet is uninspected, not established absent.

Follow this authoring order; it is not the PDF section order. See `references/workflow.md` for stage outputs and reopening rules.

1. **Style orientation.** Ask for preferred sample papers or style references when relevant. Read user-selected samples; when only author names are given, find and obtain representative public papers. Study prose and actual figure pages. Derive observable conventions, not private preferences. There are no default researchers or supervisors; each author chooses their references. Keep personal preferences in the paper project, outside the shared skill. Reuse a current approved brief rather than repeating downloads.
2. **Background and related work.** Read configured URLs and local PDFs in `sources/`; delegate wider literature investigation when permitted. Get a one-sentence topic first if none exists. Compare every cited work or meaningful family to our work: relevant contribution, overlap, precise difference, why it matters, and evidence. Do not manufacture distinctions or superiority. Draft initial related work; unresolved comparisons remain private questions or approved marked provisional text. Read `references/literature.md`.
3. **Story.** Establish the problem, consequential gap, idea, mechanism, evidence, and contribution. Explain the proposed argument back to the author. Confirm scope and terminology. Do not tailor the literature to conceal overlap.
4. **Method.** Ask for the codebase or theoretical materials if absent; `none` is valid. Inspect authorized material without executing it by default. Distinguish intended method, current implementation, and implementation used for results. Write the method; agree on useful illustrations/tables and main-versus-appendix placement.
5. **Results.** Request missing artifacts and the author's intended interpretation. Verify observations and comparisons, separating supported conclusions from hypotheses. Plan data-backed figures and tables. Do not assume a requested interpretation is proven.
6. **Introduction and conclusion.** Write these from the established body, then reconcile related work and contributions. Apply the paragraph-purpose, terminology, and relevance checks in `references/writing.md`.
7. **Abstract.** State the specific problem, gap, contribution, strongest verified evidence, and implication. Promote through precision, not unsupported superlatives. No new claims or unmarked guessed results.

## Visual work
Use `references/figures.md`, `references/page-qa.md`, and `prompts/visual-reviewer.md`. Prefer TikZ for conceptual diagrams and PGFPlots for suitable plots, with other reproducible vector tools when better. Make figures informative, colorful, memorable, readable, and academically appropriate. Inspect figures at final size and in their actual manuscript pages. Render all pages separately, open each full page individually, zoom where needed, record page-specific findings, fix issues, and repeat for the latest PDF. Include references and appendices; text extraction, thumbnails, and contact sheets are insufficient. Never fabricate empirical plots or attest to unseen images.

## Readability and relevance during writing
Run `scripts/readability.py` on checked prose after a substantive section draft/revision and on the final candidate. Inspect the extracted text, sample size, exclusions, and source locations before interpreting scores. Use section-level ARI/Coleman–Liau estimates and sentence statistics as advisory signals; optional local syntax diagnostics can flag noun stacks and long dependencies. The linked Clark–Martin–Mahowald paper motivates additional inspection, not a universal score or replicated benchmark. Read `references/readability.md` for limitations and optional open-source tools.

For each useful flag, revise the passage or record why its technical wording is necessary. Preserve meaning, standard vocabulary, conditions, evidence, and natural sentence flow even if a numeric score worsens. Never manufacture a composite clarity grade, optimize for an AI detector, or force a school-grade target on research prose. Perform the first-sentence reverse outline and current-method/evidence relevance check separately; formulas cannot verify these. Recheck all dependent prose and visuals after changes.

Use `prompts/editorial-auditor.md` for a separate editorial pass with access to the glossary, current-method evidence, and readability report. Keep that private material out of blind scientific-review packets.

## Review and improve
Use `references/orchestration.md` for the executable loop and its approval gates, `references/review-protocol.md` for review judgment, and `prompts/scientific-reviewer.md` for the common rubric. Operate `scripts/orchestrator.py` yourself from chat. A plan request creates a proposal, never permission to execute it. Present provider/data scope and limits, discuss the plan, and record an actual user decision before reviewer jobs. After synthesis, discuss the proposed actions and await their scoped approval. Writing approval drafts changes; show the diff and obtain approval before applying it. Builds, new rounds, research work, and scientific changes require their applicable concrete scope. Never fabricate user replies, approvals, evidence, or task completion. Reuse real existing authorization within its agreed scope instead of asking for each internal command.

Make reviews callable at ANY stage, not just after the abstract. Default to the exact user-supplied form in `rubrics/user-supplied-iclr-form.md`; preserve its provenance. Do not label it a verified official year-specific form.

Default to three fresh initial reviewer contexts on the same frozen manuscript packet: soundness/methods, evidence/evaluation, and significance/positioning. Each completes the full common rubric; the perspective changes emphasis, never the desired verdict. Record `reviewer_perspective`. The controller runs approved jobs through the selected installed agent CLI and validates their packet identity and output. Automated reviews are text-only; disclose missing visual access and actual adapter isolation limits before approval. In development mode, allow `not_assessable`/null scores for genuinely unavailable evidence; do not treat unfinished work as invalid work. In submission-mock mode, complete the numeric form. Do not invent strengths, weaknesses, or missing experiments to fill a quota.

Complete ethics review and confidence as well as the other supplied fields. AI confidence must disclose its evidence/coverage basis as a proxy; do not claim human research experience or contacting an AC.

Produce TWO outputs: a concise assessment and a separate author-facing improvement plan. Give every action a `resolution_basis`: writing, existing_evidence, new_research, or author_clarification. Explicitly state when a weakness cannot be fixed by writing; route missing experiments or proofs to new research. Do not treat a narrower claim as satisfying the original scientific goal without author agreement. Request only decision-relevant clarification in the assessment. Put optional future work in the improvement plan. For experiments, specify claim tested, smallest discriminating comparison, controls, metrics, interpretation of possible outcomes, and a structured `stop_condition`. For missing theory, specify the claim or lemma, assumptions, needed proof/analysis, and completion criterion. Never invent compute estimates or results.

After all initial reviews are saved, use `prompts/meta-reviewer.md` to adjudicate evidence, protect demonstrated strengths, and prioritize changes. Ask the author to approve scientific changes and experiment execution. Reopen only affected stages. Never rewrite the manuscript directly from a review without this triage.

## Release
Use the managed build and preflight described in `references/release.md`. Require a fresh readability report with a recorded interpretation and a complete individual-page image audit for the exact candidate. Report writing, evidence, readability review, terminology, relevance, visual, TODO, and venue readiness separately. Readability review completion is a gate; a numerical readability target is not. A mock score is not an acceptance probability. A clean compiler log is not scientific or visual approval. No final-ready status while blockers remain; no auto-submission.

## Tools and handoff
- `INSTALL.md` and `scripts/install.py`: personal skill installation across projects; agent-operated by default.
- `scripts/workspace.py`: safe initialization and local skill installation.
- `scripts/paperkit.py`: TODO ledger, managed LaTeX build, release checks, frozen review packets, structured-review validation, and local source ingestion.
- `scripts/orchestrator.py`: saved review rounds, concrete plans, user decisions, proposed diffs, approved application/builds, evidence handoffs, cancellation, and resume.
- `scripts/providers.py`: bounded Codex, Claude Code, and Antigravity CLI jobs with structured output and disclosed capabilities.
- `scripts/readability.py`: local prose metrics, extraction coverage, located sentences, and optional installed-model syntax diagnostics.
- `scripts/visual_audit.py`: individual page rendering and hash-bound observation records; it never makes visual judgments itself.
- `docs/USAGE.md`: setup, reviews, and local helper commands for supported hosts.
- `docs/TESTING.md`: development checks and verified coverage.
- `references/sources.md`: provenance and primary-source references; inclusion does not imply full reading.
