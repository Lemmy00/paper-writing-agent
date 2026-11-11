# Paper Writing Agent

A research paper writing skill for **Codex, Claude Code, and Antigravity**.

Work on your paper through conversation. The agent helps with structure, writing, figures, and reviews. It asks for missing information and distinguishes writing improvements from weaknesses that need experiments or proof.

## Install once

Ask your agent:

> Install the research-paper skill from https://github.com/Lemmy00/paper-writing-agent for my agent, so I can use it in any project.

The agent can follow the [installation guide](INSTALL.md). Installation is personal to your agent; you do it once, rather than for every paper. A terminal option is also available in the guide.

## Use

Open your paper folder and select **Paper Writing Agent** from your agent's skills, or use its chat command:

| Agent | Command |
|---|---|
| Codex | `$research-paper` |
| Claude Code | `/research-paper` |
| Antigravity | `/research-paper` |

Then describe what you need:

> Set up this project for paper writing. Use the draft and materials already here, ask for anything missing, and help me improve it.

The agent initializes the current project, preserves existing files, and handles configuration. You do not need to run Python commands or edit YAML. Share drafts, notes, references, and results through chat as you go.

The review loop uses three perspectives: methods, evidence, and significance. It presents a plan, waits for your approval, and combines reviews into proposed writing changes, questions, and research tasks. You review proposed edits before they are applied. The loop saves progress and can pause or resume.

[Usage guide](docs/USAGE.md) · [Testing](docs/TESTING.md) · [MIT license](LICENSE)
