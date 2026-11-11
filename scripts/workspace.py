#!/usr/bin/env python3
"""Initialize a paper workspace without overwriting author files."""
from __future__ import annotations
import argparse
import json
import shutil
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
HOSTS = ('both', 'all', 'codex', 'claude', 'antigravity', 'none')


def initialize(project: Path, host: str = 'both') -> list[str]:
    if host not in HOSTS:
        raise ValueError(f'Unsupported host: {host}')
    project = project.resolve()
    if project == KIT or KIT in project.parents:
        raise ValueError('Choose a paper workspace outside this skill directory.')
    project.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    def write_missing(relative: str, text: str) -> None:
        p = project / relative
        if not p.resolve().is_relative_to(project):
            raise ValueError(f'Path escapes workspace: {relative}')
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(text, encoding='utf-8')
            created.append(relative)
    for directory in ['config', 'sources/pdfs', 'sources/text', 'sources/notes', '.paper']:
        p = project / directory
        if not p.resolve().is_relative_to(project):
            raise ValueError(f'Unsafe workspace directory: {directory}')
        p.mkdir(parents=True, exist_ok=True)
    canonical = project / '.paper-tools/research-paper'
    if not canonical.resolve().is_relative_to(project):
        raise ValueError('Canonical kit path escapes workspace.')
    if not canonical.exists():
        shutil.copytree(KIT, canonical, ignore=shutil.ignore_patterns(
            '.git', '__pycache__', '*.pyc', '.venv', 'venv', 'node_modules', '.local-tests'))
        created.append('.paper-tools/research-paper')
    write_missing('config/paper.yaml', (KIT / 'config/paper.yaml').read_text())
    write_missing('paper-todos.sty', (KIT / 'assets/paper-todos.sty').read_text())
    write_missing('sources/index.json', '{"schema_version": 1, "papers": []}\n')
    state = {'schema_version': 1, 'stage': 'style', 'todos': [], 'questions': [],
             'decisions': [], 'glossary': {}, 'literal_exceptions': []}
    write_missing('.paper/state.json', json.dumps(state, indent=2) + '\n')
    wrapper = '''---
name: research-paper
description: Guide author-approved research paper development, LaTeX writing, and independent readiness review.
---
Read `.paper-tools/research-paper/SKILL.md` from the project root and follow it.
Load its references relative to that canonical directory. Keep the user's setup
in `config/paper.yaml`. Do not expose writer instructions to blind reviewers.
'''
    # Codex and Antigravity share the standard project skill location.
    if host in ('both', 'all', 'codex', 'antigravity'):
        write_missing('.agents/skills/research-paper/SKILL.md', wrapper)
    if host in ('both', 'all', 'claude'):
        write_missing('.claude/skills/research-paper/SKILL.md', wrapper)
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init')
    init.add_argument('project', type=Path)
    init.add_argument('--host', choices=HOSTS, default='both',
                      help='both/all create shared Codex–Antigravity and Claude entrypoints')
    args = parser.parse_args()
    try:
        print(json.dumps({'created': initialize(args.project, args.host),
                          'note': 'Existing files were preserved; no provider or network calls.'}, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
