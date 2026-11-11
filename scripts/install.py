#!/usr/bin/env python3
"""Install the research-paper skill for a personal agent, without replacing files."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1]
HOST_PATHS = {
    'codex': Path('.agents/skills/research-paper'),
    'claude': Path('.claude/skills/research-paper'),
    'antigravity': Path('.gemini/config/skills/research-paper'),
}
ROOT_FILES = ('SKILL.md', 'README.md', 'INSTALL.md', 'LICENSE', 'LICENSE-QUALITY-TOOLS.txt')
# Deliberately enumerate package contents instead of copying checkout debris.
# Add a path here when a new resource becomes part of the distributed skill.
RUNTIME_FILES = (
    'agents/openai.yaml', 'assets/icon.svg', 'assets/paper-todos.sty',
    'config/paper.yaml', 'docs/USAGE.md', 'docs/TESTING.md',
    'prompts/editorial-auditor.md', 'prompts/literature-researcher.md',
    'prompts/meta-reviewer.md', 'prompts/scientific-reviewer.md',
    'prompts/visual-reviewer.md', 'prompts/writer.md',
    'references/figures.md', 'references/literature.md', 'references/page-qa.md',
    'references/orchestration.md',
    'references/readability.md', 'references/release.md',
    'references/review-protocol.md', 'references/security-tools.md',
    'references/sources.md', 'references/workflow.md', 'references/writing.md',
    'rubrics/user-supplied-iclr-form.md', 'schemas/review.schema.json',
    'scripts/install.py', 'scripts/paperkit.py', 'scripts/readability.py',
    'scripts/orchestrator.py', 'scripts/providers.py',
    'scripts/visual_audit.py', 'scripts/workspace.py',
)


def package_files(source: Path) -> dict[str, Path]:
    """Select runtime files, never repository state or unrelated top-level material."""
    files: dict[str, Path] = {}
    for name in (*ROOT_FILES, *RUNTIME_FILES):
        path = source / name
        if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != source and p.is_relative_to(source)):
            raise ValueError(f'Runtime package contains a symlink: {name}')
        if path.is_file():
            files[name] = path
    missing = [name for name in (*ROOT_FILES, *RUNTIME_FILES) if name not in files]
    if missing:
        raise ValueError('Incomplete skill package; missing: ' + ', '.join(missing))
    return files


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def same_install(destination: Path, files: dict[str, Path]) -> bool:
    actual: dict[str, Path] = {}
    for path in destination.rglob('*'):
        relative = path.relative_to(destination)
        if '__pycache__' in relative.parts or path.suffix == '.pyc' or path.name == '.DS_Store':
            continue
        if path.is_symlink():
            return False
        if path.is_file():
            actual[relative.as_posix()] = path
    return set(actual) == set(files) and all(file_hash(actual[name]) == file_hash(path)
                                           for name, path in files.items())


def install(host: str, *, home: Path | None = None, source: Path | None = None,
            link: bool = False) -> list[dict[str, str]]:
    """Install into personal discovery folders; existing differing content is preserved."""
    if host not in (*HOST_PATHS, 'all'):
        raise ValueError(f'Unsupported host: {host}')
    home = (Path.home() if home is None else Path(home)).resolve()
    source = (KIT if source is None else Path(source)).resolve()
    files = package_files(source)
    hosts = list(HOST_PATHS) if host == 'all' else [host]
    plans = []
    for name in hosts:
        destination = home / HOST_PATHS[name]
        resolved_parent = destination.parent.resolve()
        if not resolved_parent.is_relative_to(home):
            raise ValueError(f'Personal skill location escapes the home directory: {destination}')
        actual_destination = resolved_parent / destination.name
        if actual_destination == source and not destination.is_symlink():
            state = 'unchanged'
        elif actual_destination.is_relative_to(source) or source.is_relative_to(actual_destination):
            raise ValueError('Installation source and destination must not contain each other.')
        elif destination.is_symlink():
            if link and destination.resolve() == source:
                state = 'unchanged'
            else:
                raise ValueError(f'Existing skill link preserved: {destination}. Use --link for this development checkout, or compare and merge the installation explicitly.')
        elif destination.exists():
            if destination.is_dir() and not link and same_install(destination, files):
                state = 'unchanged'
            else:
                raise ValueError(f'Existing skill preserved: {destination}. Compare and merge or back up the installation before updating it; no files were replaced.')
        else:
            state = 'linked' if link else 'installed'
        plans.append((name, destination, state))

    result = []
    # Check every requested destination before creating any installation.
    for name, destination, state in plans:
        if state != 'unchanged':
            destination.parent.mkdir(parents=True, exist_ok=True)
            if link:
                destination.symlink_to(source, target_is_directory=True)
            else:
                temporary = Path(tempfile.mkdtemp(prefix='.research-paper-', dir=destination.parent))
                try:
                    for relative, path in files.items():
                        target = temporary / relative
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, target)
                    if destination.exists() or destination.is_symlink():
                        raise ValueError(f'Skill location appeared during installation; preserved: {destination}')
                    temporary.rename(destination)
                finally:
                    if temporary.exists():
                        shutil.rmtree(temporary)
        result.append({'host': name, 'path': str(destination), 'status': state,
                       'mode': 'development_link' if destination.is_symlink() else 'self_contained_copy'})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', choices=[*HOST_PATHS, 'all'], required=True,
                        help='Install for this agent, or all supported personal agents.')
    parser.add_argument('--link', action='store_true',
                        help='Link this permanent development checkout instead of copying it.')
    args = parser.parse_args()
    try:
        print(json.dumps({'installations': install(args.host, link=args.link),
                          'note': 'Use the skill in any project; it handles project setup through chat. No dependencies or providers were installed.'}, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f'Error: {exc}\n')


if __name__ == '__main__':
    raise SystemExit(main())
