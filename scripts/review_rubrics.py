"""Select local review rubrics and preserve their native forms in frozen packets."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

KIT = Path(__file__).resolve().parents[1]
DEFAULT_ID = 'user-supplied-iclr-form'
DEFAULT_PATH = KIT / 'rubrics' / (DEFAULT_ID + '.md')
MAX_RUBRICS = 8
MAX_RUBRIC_BYTES = 256 * 1024
BASE_PACKET_FILES = {'manuscript.pdf', 'manuscript.txt', 'rubric.md',
                     'instructions.md', 'review.schema.json'}


def resolve_rubrics(values=None, *, base: Path | None = None) -> list[Path]:
    """An explicit list replaces the default; an empty list selects the default."""
    if values is not None and not isinstance(values, (list, tuple)):
        raise ValueError('Rubrics must be a list of bundled names or local Markdown paths.')
    values = values or [DEFAULT_ID]
    if len(values) > MAX_RUBRICS:
        raise ValueError(f'Select at most {MAX_RUBRICS} rubrics per review packet.')
    base = Path.cwd() if base is None else Path(base)
    result = []
    for value in values:
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ValueError('Each rubric needs a bundled name or local Markdown path.')
        path = DEFAULT_PATH if str(value) == DEFAULT_ID else Path(value).expanduser()
        path = path if path.is_absolute() else base / path
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in ('.md', '.markdown'):
            raise ValueError('Rubric must be an existing Markdown file, not a URL or file link: ' + str(value))
        path = path.resolve()
        if path in result:
            raise ValueError('The same rubric was selected more than once.')
        if path.stat().st_size > MAX_RUBRIC_BYTES:
            raise ValueError('Rubric is too large for an inline review: ' + path.name)
        content = path.read_text(encoding='utf-8')
        if not content.strip():
            raise ValueError('Rubric is empty: ' + path.name)
        result.append(path)
    return result


def _metadata(packet: Path) -> dict | None:
    path = packet / 'rubrics.json'
    if not path.exists():
        return None
    manifest = json.loads((packet / 'packet.json').read_text(encoding='utf-8'))
    if not isinstance(manifest, dict) or 'rubrics.json' not in manifest.get('files', {}):
        raise ValueError('Rubric metadata is outside the frozen packet manifest.')
    if path.is_symlink() or path.stat().st_size > MAX_RUBRIC_BYTES:
        raise ValueError('Unsafe rubric metadata.')
    metadata = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(metadata, dict) or set(metadata) != {'version', 'rubrics'} or
            metadata['version'] != 1 or not isinstance(metadata['rubrics'], list) or
            not 1 <= len(metadata['rubrics']) <= MAX_RUBRICS):
        raise ValueError('Invalid rubric metadata.')
    for index, rubric in enumerate(metadata['rubrics'], 1):
        if (not isinstance(rubric, dict) or set(rubric) != {'id', 'name', 'sha256'} or
                rubric['id'] != f'rubric-{index:03d}' or
                not isinstance(rubric['name'], str) or not rubric['name'].strip() or
                len(rubric['name']) > 160 or
                not re.fullmatch(r'[0-9a-f]{64}', str(rubric['sha256']))):
            raise ValueError('Invalid selected rubric identity.')
    return metadata


def packet_rubrics(packet: Path) -> list[dict]:
    metadata = _metadata(packet)
    return metadata['rubrics'] if metadata else [{'id': DEFAULT_ID, 'name': 'User-supplied ICLR-style form'}]


def _native_schema(metadata: dict) -> dict:
    schema = json.loads((KIT / 'schemas/review.schema.json').read_text(encoding='utf-8'))
    schema['title'] = 'Native rubric assessments with a shared improvement plan'
    # These ratings belong to the bundled form, not to arbitrary venue forms.
    for field in ('presentation', 'informativeness', 'soundness', 'rating'):
        del schema['properties'][field]
        schema['required'].remove(field)
        for condition in schema.get('allOf', []):
            condition.get('then', {}).get('properties', {}).pop(field, None)
    assessments = {
        rubric['id']: {'type': 'string', 'minLength': 1, 'pattern': r'\S',
                       'description': 'Complete this rubric using its own headings, questions, and rating anchors. Return Markdown; do not translate its scale into the bundled form.'}
        for rubric in metadata['rubrics']
    }
    schema['properties']['rubric_assessments'] = {
        'type': 'object', 'additionalProperties': False,
        'required': list(assessments), 'properties': assessments}
    schema['required'].append('rubric_assessments')
    return schema


def packet_schema(packet: Path) -> dict:
    schema_path = packet / 'review.schema.json'
    if schema_path.is_symlink() or schema_path.stat().st_size > MAX_RUBRIC_BYTES:
        raise ValueError('Unsafe frozen review schema.')
    schema = json.loads(schema_path.read_text(encoding='utf-8'))
    metadata = _metadata(packet)
    if metadata is not None and schema != _native_schema(metadata):
        raise ValueError('Frozen schema does not match the selected rubrics.')
    return schema


def write_packet(packet: Path, values=None) -> str:
    """Write selected forms and their output contract; return provenance."""
    paths = resolve_rubrics(values)
    schema = json.loads((KIT / 'schemas/review.schema.json').read_text(encoding='utf-8'))
    if paths == [DEFAULT_PATH.resolve()]:
        (packet / 'rubric.md').write_bytes(DEFAULT_PATH.read_bytes())
        provenance = 'user_supplied_exact_official_year_unverified'
    else:
        metadata = {'version': 1, 'rubrics': []}
        sections = ['# Selected review rubrics', '',
                    'Complete each selected form separately using its own questions and score anchors. '
                    'Keep disagreements explicit; never average or translate scores across rubrics.', '']
        for index, path in enumerate(paths, 1):
            content = path.read_bytes()
            if len(content) > MAX_RUBRIC_BYTES or not content.decode('utf-8').strip():
                raise ValueError('Rubric changed or is empty/oversized: ' + path.name)
            title = next((line.lstrip('#').strip() for line in content.decode('utf-8').splitlines()
                          if line.startswith('# ')), path.stem)
            rubric = {'id': f'rubric-{index:03d}', 'name': (title or path.stem)[:160],
                      'sha256': hashlib.sha256(content).hexdigest()}
            metadata['rubrics'].append(rubric)
            sections += ['## ' + rubric['id'] + ' — ' + rubric['name'], '', content.decode('utf-8').rstrip(), '']
        (packet / 'rubrics.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        (packet / 'rubric.md').write_text('\n'.join(sections), encoding='utf-8')
        schema = _native_schema(metadata)
        provenance = 'author_selected_native_forms; official status is not inferred'
    (packet / 'review.schema.json').write_text(json.dumps(schema, indent=2) + '\n', encoding='utf-8')
    return provenance
