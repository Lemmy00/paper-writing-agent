# Using the skill

## Start and resume

After the one-time personal installation, open your paper folder and choose Paper Writing Agent in chat. Ask it to set up the project and describe what you need. The agent inspects the folder, initializes missing state, asks questions when needed, and maintains the configuration and notes. You do not need to run a setup command.

For example:

> Help me revise the introduction. The current draft is in `main.tex`, and the results are in `results/`. Ask about anything the evidence does not establish.

To resume, open the same folder and invoke the skill again. It continues from saved questions and decisions. Project setup preserves an existing tool snapshot; compare and merge updates deliberately rather than treating initialization as an upgrade.

For an existing draft, the agent first maps the current manuscript and available evidence. It records inferred details without treating them as author approval, and asks only about information it cannot establish from the supplied materials.

## What setup creates

| Location | Purpose |
|---|---|
| `config/paper.yaml` | Agent-maintained project preferences. |
| `sources/` | References, extracted text, reading notes, and provenance. |
| `.paper/` | Questions, decisions, review outputs, and local reports. |
| `.paper-tools/research-paper/` | The project's copy of the skill and helpers. |

Keep manuscript source and results in their usual locations. Initialization does not create a manuscript or invent results. The global skill remains available in every project. Optional project entrypoints can be added for portability; they are not needed for ordinary use.

## Reviews

Reviews can happen at any stage. Development reviews distinguish missing evidence from an invalid result. Submission mocks use the complete supplied form. The bundled rubric is ICLR-style; its exact official venue/year has not been verified.

Three reviewer contexts examine the same manuscript, emphasizing methods, evidence, and significance. Each completes the selected rubrics, with shared ethics and confidence reporting. The coordinator saves initial reviews before combining findings. Reviewers need fresh contexts and appropriate access restrictions; where isolation cannot be verified, describe the result as a separate-role critique.

You can choose a different rubric or use several through chat:

> Use the review form in `rubrics/venue-review.md` together with `rubrics/reproducibility.md`. Show separate assessments and keep their original scales.

The agent reads the available forms, clarifies the selection if needed, and records it in your project's `reviews.rubrics` preference. An empty selection uses the bundled form. You do not need to edit configuration yourself. Each selected form is frozen into the review packet and listed in the approval plan; all three reviewers receive the same forms. Changing the selection prepares a new plan for approval. Rubrics do not authorize new tools, provider calls, or experiments.

Ask for a review plan in chat. The controller prepares the candidate and explains the proposed reviewer jobs, provider, limits, and data scope. You discuss and approve the work before any model call. After the reviews, it presents a task plan for your decision. Approved writing tasks produce a diff for review; application waits for your approval. Scientific questions and experiments remain explicit handoffs. The agent operates the commands and saves progress so you can pause or resume. See [the orchestration guide](../references/orchestration.md) for scope and recovery details.

The improvement plan distinguishes writing changes, existing evidence to check, questions for the author, and new research. Experiment requests identify the claim, comparison, controls, metric, possible outcomes, and stop condition. Missing proof obligations remain research work. Review scores are not acceptance probabilities.

## Local helpers

The agent normally runs these commands for you. From the paper folder:

```bash
# Build the manuscript within an authorized local build task.
python3 .paper-tools/research-paper/scripts/paperkit.py build . --main main.tex --allow-build

# Measure prose; the agent still needs to inspect and interpret the report.
python3 .paper-tools/research-paper/scripts/readability.py --tex main.tex --root . --output-dir .paper/readability/round-001

# Render pages; rendering does not mark them inspected.
python3 .paper-tools/research-paper/scripts/visual_audit.py render .paper/build/main.pdf --output .paper/visual

# Prepare a frozen manuscript packet without calling a provider.
python3 .paper-tools/research-paper/scripts/paperkit.py prepare-review --pdf .paper/build/main.pdf --output .paper/reviews/round-001/packet --mode development

# Check a completed review against the frozen packet.
python3 .paper-tools/research-paper/scripts/paperkit.py validate-review .paper/reviews/round-001/reviewer-1.json --packet .paper/reviews/round-001/packet

# Show remaining submission checks without submitting anything.
python3 .paper-tools/research-paper/scripts/paperkit.py preflight . --mode submission
```

Use the actual manuscript filename and fresh output directories. Without `--packet`, review validation checks structure only. Older review files may need deliberate migration; do not invent missing judgments to satisfy a schema.

For custom forms, the agent can repeat `--rubric` on `prepare-review` or the orchestrator's `plan` and `refresh` commands. Values are bundled names such as `user-supplied-iclr-form` or local Markdown paths; `plan` and `refresh` resolve relative paths from the paper project. Download a requested public form through the host's authorized source tools before selecting it; these helpers do not fetch URLs.

The skill references explain page inspection, readability interpretation, provisional text, and author signoff. Reports and recorded checks support judgment; they do not establish scientific validity. Local measurement/build helpers make no model-provider calls. The orchestration controller invokes the selected provider only for approved jobs and never executes experiment descriptions or publishes a paper.
