# Install for your agent

Ask your agent to install this repository's `research-paper` skill for personal use. It should be available across projects. Installing the skill and setting up a paper are separate steps: project setup happens later, when you invoke the skill in that project.

## Instructions for the installing agent

1. Use the current host unless the user requests another host or all hosts. The skill lives at this repository's root, and its installed name is `research-paper`.
2. Use an available native GitHub skill installer when it supports a complete root-level skill. Otherwise retrieve this repository to a local temporary checkout and run the included installer using Python 3.10+.
3. Keep the complete runtime package together. A lone `SKILL.md` is insufficient: its scripts, references, prompts, rubric, schema, configuration template, and assets are required.
4. Install in the host's personal skill directory. Preserve existing installations; compare and merge an update deliberately if the installer reports a difference. Do not replace an author's local changes automatically.
5. Report the installed name and host. The skill will be available on the next turn; refresh discovery or start a new session if the host requires it. Do not claim a live discovery check unless it was performed.

| Host | Personal location |
|---|---|
| Codex | `~/.agents/skills/research-paper/` |
| Claude Code | `~/.claude/skills/research-paper/` |
| Antigravity App and CLI | `~/.gemini/config/skills/research-paper/` |

The included installer creates a self-contained copy, so a temporary checkout can be removed afterward. It makes no network or provider calls and does not initialize a paper, install dependencies, or change agent authentication. A deliberate development checkout can use `--link` instead; that checkout must remain available.

## Optional terminal installation

You can also install manually with Python 3.10+:

```bash
git clone https://github.com/Lemmy00/paper-writing-agent.git
cd paper-writing-agent
python3 scripts/install.py --host codex
```

Choose `claude`, `antigravity`, or `all` as needed. Then open your paper folder, select the skill in chat, and ask it to set up the project. The agent finds the manuscript and manages setup; no paper-path command is required.

The local writing helpers need Python 3.10+. Building PDFs also needs LaTeX; PDF extraction and rendering need Poppler. The agent should check what is available when an operation needs it, rather than require every optional tool before starting.

Automated review jobs use the selected agent's installed, signed-in CLI. The agent checks availability and presents the provider, data scope, limits, and tasks before requesting execution approval. Installing this skill does not authorize model calls or task execution.
