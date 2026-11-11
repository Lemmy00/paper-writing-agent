# Independent review for diagnosis and improvement

## Modes
**Development (default):** callable at any stage, including idea/method/partial results. Record supplied and missing material. Score what is assessable; use null with a reason for missing evidence. Distinguish 'not demonstrated yet', 'not included in packet', 'unclear', and 'contradicted'. Do not assign rejection just because a requested early-stage packet is incomplete. An optional counterfactual 'as submitted today' assessment must be labeled separately.

**Submission mock:** use a frozen complete candidate and the exact selected rubric. Require all numeric fields. Read relevant appendices before claiming something is missing. Evaluate only manuscript-visible evidence in the blind assessment.

The bundled form was supplied by the user. It has presentation/informativeness/soundness scores 1-3 and overall rating/confidence scores 1-4, plus ethics review and details. AI confidence must explain its actual evidence and topic coverage as a proxy; it must not claim human research experience or that an AC was contacted. Its exact official venue-year provenance has not been independently verified. Store that fact; do not map it to an old ICLR or ICML scale. Verify the target year/track/stage before an official-form simulation. The public ICLR 2027 reviewer guide supports concise, consequential, constructive reviewing but is not proof of this exact form.

## Requests from any agent
Any writer, literature, method, results, or figure agent may request a specialist review. Send the coordinator the artifact/version, mode, and scope, not the worker's desired conclusion. The coordinator prepares a neutral packet and starts fresh authorized reviewer contexts. A scoped diagnostic may ask a specific scientific question, but label that scope rather than present it as a completely unprompted general review. Never forward the writer's conversation as the independent review context.

## Default reviewer perspectives
Use three fresh initial contexts by default, each completing the full common form:
- `soundness_methods`: correctness, assumptions, derivations, method validity.
- `evidence_evaluation`: controls, comparisons, uncertainty, and evidence for claims.
- `significance_positioning`: consequential contribution and distinctions from closest work.

These are fair emphases, not prescribed verdicts. A `general` perspective is available for an explicitly scoped additional critique. The coordinator reads the agent-maintained roster and round budget from configuration and uses the controller described in `references/orchestration.md`. Preferences and budgets do not themselves authorize provider execution. Discuss the concrete reviewer plan before approval, then discuss the resulting task plan before approving its actions. If three independent contexts are unavailable, disclose the actual number and isolation limits.

## Independence
Prepare identical packet contents and hashes for each initial reviewer: manuscript PDF, extracted text, selected rubric, neutral task, and review schema. Include approved supplemental evidence consistently when simulating the selected process. Do NOT include story notes, professor preferences, author identity hints, private TODO ledger, approvals, desired rating, writer conversation, or other reviews. A PDF can itself reveal identities; do not promise anonymity without inspecting it.

Use fresh sessions and separate output directories. Model diversity is optional and requires provider disclosure/cost approval. A different persona inside the writer's conversation is not independent. Native subagents may inherit instructions or workspace access: configure and inspect actual context isolation. If isolation cannot be verified, label the result 'separate-role critique', not blind independent review. Frozen packets do not by themselves enforce filesystem or network isolation.

A separate artifact auditor may inspect code/results/private provenance; keep its findings separate from the blind-review score until author triage. Web lookup during blind review can unblind a submission: agree on lookup policy and log sources.

Keep the writer's readability reports, glossary, and page-QA decisions out of the initial blind-review packet. They belong to a separate editorial/visual audit and must not anchor scientific reviewers. A reviewer may use its own authorized diagnostics, but numerical readability is not scientific soundness or an acceptance score. The final visual auditor must actually open every page individually; merely receiving the PDF is not visual coverage.

## Output A: concise assessment
Use the supplied form headings and anchors. Identify at most one or two critical strengths and at most one or two critical weaknesses. Empty arrays render as 'None'; do not force a negative or positive point. Explain why each is consequential and cite a section/figure/equation or checkable observation. Questions must be able to materially change the assessment. Optional future-work suggestions belong in Output B, not as artificial acceptance requirements.

## Output B: author-facing improvement plan
For each proposed action record:
- Exact affected claim and observed evidence or missing information.
- Category: clarification, writing, verification, experiment, theory, positioning, or optional extension. Required `resolution_basis`: writing, existing_evidence, new_research, or author_clarification. Experiments and missing theory require new_research.
- Priority: decision-critical, useful, or optional; separate confidence from severity.
- Smallest useful action, dependency/owner, and completion criterion.
- For experiments: hypothesis, discriminating comparison, controls, data/metric, possible outcomes and how each changes interpretation, and an explicit `stop_condition`. Ask for compute budget rather than invent it.
- For missing theory: identify the claim/lemma, assumptions, required proof/analysis, and completion criterion. State that it cannot be supplied through prose alone.
- Non-experimental alternative when legitimate: locate existing evidence, repair explanation, verify source, or author-approved narrowing. Do not suggest hiding unfavorable results.

Explicitly distinguish “the writing can improve now” from “these scientific weaknesses require new research.” Author-approved narrowing is an alternative scientific decision, not evidence that the original claim was validated.

This plan is an aid to the author, not manuscript text and not a promise that the work will be accepted. Protect demonstrated strengths during revision. Do not add tests merely to satisfy imagined reviewers. Recommend new research only when it tests an actual claim or the author explicitly wants an extension.

## Aggregate only after initial reviews are sealed
Use the meta-reviewer to reconcile duplicate concerns and disagreements by evidence. Do not average scores into a verdict or acceptance probability. Confirm that alleged missing material is genuinely absent. Present highest-leverage actions and their rationale to the author. Preserve dissent rather than laundering a weak claim into consensus.

After approval, route writing fixes to the writer; scientific questions to the author; evidence checks to the auditor; experiments to the author until explicitly authorized. Never let a review automatically insert limitations or new terminology. Re-review changed claims on a new snapshot; retain original reviews and distinguish rebuttal-informed review from fresh review. Stop after a configured budget (suggest three rounds) or when no decision-relevant improvement remains. Report remaining research work explicitly.

Include terminology/relevance and readability findings in author-facing triage: an invented label needs an established equivalent or an approved definition; an obsolete pipeline needs alignment with the evaluated method; a difficult sentence needs a meaning-preserving edit or a justified retention. Neither jargon counts nor formula scores override scientifically required evidence. Rebuild after edits and refresh individual-page inspection of the final candidate.
