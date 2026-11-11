# Running the review loop through chat

The host agent operates `scripts/orchestrator.py`; the author uses conversation. Read the controller's current status before every transition. Keep the current project, actual provider, candidate, plan, and decision scope explicit. Installing the skill does not authorize reviewer calls or manuscript changes.

## Plan, discuss, approve

1. Inspect the existing manuscript and available artifacts. Create a loop plan with the main source, optional current PDF, editable manuscript files, provider/model, round limit, attempt limit, and per-job deadline. Creating a plan makes no model call and changes no manuscript. Without a PDF, the first plan requests a local build; it cannot build until approved.
2. Present the concrete review plan in chat. It names three reviewer perspectives and a synthesis job, the supplied candidate, data sent, provider/model choice, request limits, and adapter limitations. An omitted model means the CLI/provider default, not necessarily the model in the current chat. The automated reviewers receive text; PDF pixels and figure layout remain unassessed. Antigravity may load its configured customizations and retain conversation metadata; display its returned limits before requesting approval.
3. Discuss and revise the plan. A request to review a plan, a positive comment, silence, or elapsed time is not an execution decision. Ask a precise question if the intended authorization is ambiguous. Approve only the tasks the user actually selected, using the exact current plan hash and a reference and text from that user response. Never invent an approval reference or turn an agent's recommendation into the author's decision.
4. Advance only approved jobs. Completed validated reviews are retained; synthesis waits for the three sealed initial outputs and its own approved scope. The result is a prioritized proposal, not permission to execute it.
5. Explain the proposed actions and their dependencies. Separate writing, checking existing evidence, author questions, and new research. Use `propose` to revise the action plan during discussion; changed content invalidates the former grant. Users can select a batch, reject or defer actions, or supply answers and evidence. Do not impose all reviewer suggestions as acceptance requirements.
6. Approved writing tasks produce a proposed patch in isolation. Show its exact diff and affected files. A separate decision tied to that patch and source snapshot is required before application. Local compilation also needs scoped authorization; it can be approved with the concrete patch. Edits outside the approved actions or file scope are rejected.
7. After approved edits and build, present the new candidate's review plan. The configured round budget is a ceiling, not standing permission for further calls. Stop when the user decides to stop, the budget is reached, no material work is proposed, or unresolved research/decisions require a handoff.

Reuse an existing explicit user authorization when it covers the concrete action and current scope. Do not ask again for every command within an approved batch. A general request to improve a paper does not grant blanket permission to execute subsequent research proposals.

## Evidence and research handoffs

The controller does not execute experiment descriptions, arbitrary shell commands, or publication actions. It records approved research/evidence tasks and the supplied artifact or author response. The host agent discusses the actual execution plan, resources, and permissions before using research tools. New results can be registered and a new candidate prepared for review. A recorded file or answer is not automatically a verified result or a resolved scientific concern.

When a writing action needs a scientific decision, retain its question and continue unrelated approved work where possible. Preserve original claims until the author approves a substantive change; do not substitute narrower wording for missing evidence. The loop's completion status is separate from final scientific, readability, visual, venue, and author release checks.

## Agent-operated interface

From the project, use the bundled helper path. The commands below are for agents and optional manual operation; do not make authors remember them.

```bash
python3 .paper-tools/research-paper/scripts/orchestrator.py plan . --main main.tex --pdf main.pdf --provider codex
python3 .paper-tools/research-paper/scripts/orchestrator.py status .
python3 .paper-tools/research-paper/scripts/orchestrator.py advance .
```

Use `--provider claude` or `--provider antigravity` only within the user's selected provider scope. `--model` is optional; preserve an explicitly requested model. Use `--editable` for each authorized manuscript file, and omit `--pdf` when a build plan is needed. Prefer the current host; never switch providers silently after a failure.

The `approve`, `approve-patch`, `propose`, `answer`, `evidence`, `defer`, `reject`, `refresh`, `resume`, `cancel`, and `stop` commands expose the corresponding transitions. Inspect their `--help` output for arguments. Approval commands record a host attestation from a real user reply; the program cannot authenticate that the caller truthfully represents the user. That boundary must never be described as authenticated human identity.

## State and recovery

The current loop is identified by `.paper/active-loop.json`. Its history, plans, decisions, packets, reviews, diffs, provider receipts, and human-readable `status.md` live under `.paper/loops/<run-id>/`. Keep this author-owned record when resuming; it is not disposable test data.

The controller uses atomic state writes and an exclusive execution lock. Status remains readable during work. Cancellation signals a running job without waiting for that lock. Resume revalidates source, packet, job, and approval identities before continuing. It reuses valid completed jobs and preserves interrupted/failed attempts; it does not turn partial output into completion or retry indefinitely. Changed manuscript, plan, diff, or execution scope requires a fresh decision where applicable.

Provider processes have time and output limits and are terminated on cancellation or timeout. These limits are not universal billing caps, and stopping a local client cannot prove that an in-flight remote request stopped. Missing binaries, authentication problems, incompatible outputs, and unresolved questions remain explicit states for the author and agent to address.
