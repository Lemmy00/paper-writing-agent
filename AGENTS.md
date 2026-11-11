# Paper Writing Agent repository

This repository distributes the `research-paper` skill. It is not a manuscript workspace.

## Installing the skill

When asked to install this skill, follow `INSTALL.md`. Default to a personal installation for the current agent, available across projects. Let the agent run any necessary helper commands; do not require the user to supply a paper path or run Python. Install all hosts only when requested. Preserve existing installations and author modifications.

Project initialization belongs to the installed skill when it is invoked in a paper project. Do not initialize this repository as a paper merely because it is open during installation.

## Maintaining the package

Keep the README short: what the skill does, installation through chat, and use through chat. Keep manual commands in the installation or usage guides. Runtime resources referenced by `SKILL.md` must remain part of the installable package.

Keep manuscript trials, reviews, local setup records, and logs outside the public package. Use synthetic fixtures for public regression tests. Remove temporary test projects, logs, and environments after validation unless the user asks to retain them; preserve author-owned project records. Run the relevant tests in `docs/TESTING.md`; distinguish file installation, host discovery, helper checks, and a real writing trial in reports.

Keep personal supervisor, researcher, and style preferences out of the public package. Authors choose their own references during setup; record those choices only in their private project configuration.
