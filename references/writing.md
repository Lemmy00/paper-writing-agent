# Writing policy

## Advocate in the manuscript, investigate in private

Present the strongest accurate interpretation supported by the evidence. Do not insert defensive phrases, imagined generalization failures, generic limitations, or claims that the method is preliminary merely because they sound balanced. Do not transform absence of supplied evidence into proof of a weakness.

Put agent-originated concerns in `.paper/decisions.md` or the state ledger. Record the concern, exact location, evidence, whether it is confirmed/suspected/unknown, proposed wording, and requested author decision. Only incorporate a new limitation, negative characterization, concession, claim narrowing, or altered assumption after approval of its meaning and wording. Approval must have a real conversation reference; never generate approval on the author's behalf. Existing approved scope conditions should remain accurate and consistent.

Necessary technical truth is not optional: if an existing claim is false or materially misleading, stop that edit and ask for evidence or correction. Do not conceal the issue or silently publish it. Check mandatory venue disclosures; draft their precise wording for approval rather than omit them or pad them with speculative weaknesses. Internal reviewers may report evidence-backed problems without asking permission first; publishing their wording requires author triage.

## Paragraph purpose

Before accepting a paragraph, answer privately:
1. Why is it here? What question or claim does it address?
2. What does it explain, and what should the reader understand afterward?
3. How does it advance the paper's argument rather than merely repeat context?
4. Does its first sentence make that purpose clear?
5. Do the remaining sentences support that same purpose with evidence, reasoning, or an example?

Use one main job per paragraph. Split mixed purposes; remove redundant ones. Read the first sentence of every paragraph as a reverse outline: it should form an intelligible argument. Do not force identical sentence templates, paragraph lengths, canned transitions, or keyword-rich openings. A transition can be natural while still conveying the point. Preserve accurate technical terms and necessary notation. Replace vague adjectives with specific evidence, not stilted synonyms. Do not optimize for AI-detector scores.

## Background and related work

Apply `references/literature.md`: each cited work or coherent family needs a clear relationship to this paper. A factual definition may establish shared vocabulary without a contrived contrast in its own paragraph; its enclosing discussion must make the relevance clear. Difference is not automatically superiority, novelty, or a defect in the prior work.

## Abstract and conclusion

Write the abstract last, but allow marked planning notes outside the manuscript earlier. State a specific problem and gap, the actual contribution, strongest verified evidence with necessary conditions, and its implication. Prefer natural connected prose over a rigid five-sentence formula. Never invent a result to complete the abstract. Avoid unsupported 'first', 'novel', 'state-of-the-art', 'robust', 'general', and 'significant'. The conclusion synthesizes demonstrated value; do not append unsolicited shortcomings or speculative future work.

## Style calibration

Use the author's chosen reference papers. Derive conventions by reading representative coauthored papers; never attribute every sentence to an individual author or claim their personal preferences. No researchers or supervisors are selected by default; keep individual choices in the paper project. Inspect figure pages before making visual-style observations. Distinguish metadata inspection from full-paper reading.

For explanatory visuals, ask whether the author has additional examples they want to use. Translate useful ideas to static, page-limited conference PDFs. Record sample locations supporting approved conventions; user feedback takes precedence.

## Terminology

Every term must be familiar to the intended audience or explained. Maintain an agent-managed glossary with preferred term, exact meaning, supporting source or author approval, acronym, first-use location, and confusing aliases. A glossary entry does not replace an explanation in the paper.

| Kind of language | Required treatment |
|---|---|
| Ordinary language and audience-familiar vocabulary | Use naturally; do not ask about every word or add dictionary definitions. |
| Established but specialized term | Check its meaning in appropriate primary sources; define or explain at first substantive use and cite when needed. |
| Acronym or unfamiliar symbol | Expand/define at first use. Check abstract and main text separately, and make captions understandable when read alone. |
| Truly new scientific concept or name | First check for an established equivalent. Propose a descriptive name privately with its exact definition, purpose, and relationship to existing concepts; obtain author approval before use. Explicitly introduce it as new here. |
| Code identifier, experiment nickname, or development label | Translate to ordinary descriptive language unless the identifier is necessary for reproducibility. Do not promote it into a scientific concept by capitalization. |

Never invent terminology to make an ordinary mechanism sound novel. Never present an unexplained compound phrase as a recognized technical category. Do not rename established concepts or rotate synonyms simply to avoid repetition. Preserve mathematical and domain vocabulary even when a readability score penalizes it. Approval does not make an established concept novel or license an inaccurate definition.

Ask concretely: 'The code calls this Y, while the draft says X. Do these mean the same operation? May I use X with this definition throughout?' Keep unresolved names and meanings outside manuscript text. During each consistency pass check headings, abstract, main prose, captions, algorithms, tables, notation, and appendices for mismatched terms and definitions used before introduction.

## Current work and relevance

Describe the scientific object supported by the paper's evidence, rather than the chronology of building it. Keep a compact record of the evaluated implementation/data version and the agreed contribution. The latest code is not automatically the code used for the reported results: ask about a mismatch before updating the method description.

For every paragraph, figure, table, example, and appendix item ask whether it helps explain, reproduce, assess, or qualify an actual claim. Remove obsolete design descriptions, abandoned prompt variants, old file names, debugging stories, and intermediate attempts that serve none of these purposes. Keep them in private development notes when useful. If a historical change explains a controlled ablation or a central research finding, describe that comparison directly rather than narrating the work diary.

Retain negative results, relevant failed alternatives, controls, boundary cases, necessary assumptions, and required disclosures when omitting them would distort the evidence. Presenting a compelling story never licenses cherry-picking. Ask the author before substantive removal or claim changes. Do not equate recent with relevant: retain foundational work and the closest prior art regardless of age, and verify time-sensitive claims such as 'best', 'latest', and 'first' against current sources.

When the method, data, results, or related work changes, update dependent claims, notation, diagrams, captions, tables, appendix references, introduction, conclusion, and abstract. Do not leave an old pipeline figure describing a superseded implementation. The private relevance audit should distinguish 'obsolete', 'unrelated', 'necessary context', 'necessary evidence', and 'unresolved' rather than blindly deleting negative statements.

## Readability measurements

Follow `references/readability.md`. Measure checked prose at useful checkpoints, review located difficult passages, and compare revisions only under the same extraction and measurement settings. A better numerical score is not evidence that a paragraph is true, coherent, natural, or useful. Do not shorten text by deleting definitions, logical links, conditions, or necessary repetition. Keep captions and mathematical explanations in human review even when excluded from a prose formula.

## Provisional content

Supported first-draft prose may be revised normally. Deliberately temporary paragraphs, speculative result interpretations presented as placeholders, example numbers, fake citation keys, and insert-later figures are not ordinary prose. Keep them outside the manuscript unless approved, then use a tracked TODO wrapper. Never leave realistic dummy results that can be mistaken for observations.
