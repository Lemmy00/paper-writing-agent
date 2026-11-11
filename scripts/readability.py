#!/usr/bin/env python3
"""Local English prose diagnostics; no network, model calls, or score cutoffs.

ARI and Coleman--Liau are descriptive formulas, not scientific-quality scores.
The conservative TeX reader never executes TeX and is not a complete TeX parser.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = '1.0.1'
MAX_FILES, MAX_DEPTH, MAX_BYTES = 100, 16, 10 * 1024 * 1024
WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*|\d+(?:\.\d+)?")
TEXT_COMMANDS = {'emph', 'textbf', 'textit', 'texttt', 'textrm', 'textsf',
                 'textnormal', 'underline', 'mbox', 'MakeUppercase', 'MakeLowercase'}
DROP_ARGUMENT = {'label', 'ref', 'eqref', 'pageref', 'autoref', 'cref', 'Cref',
                 'cite', 'citet', 'citep', 'citealt', 'citeauthor', 'citeyear',
                 'parencite', 'textcite', 'bibliography', 'bibliographystyle',
                 'addbibresource', 'includegraphics', 'url', 'footnote',
                 'footnotetext', 'caption', 'captionof', 'thanks', 'index',
                 'Needspace', 'needspace'}
LAYOUT = {'maketitle', 'noindent', 'centering', 'raggedright', 'raggedleft',
          'clearpage', 'newpage', 'pagebreak', 'nopagebreak', 'small', 'large',
          'normalsize', 'footnotesize', 'scriptsize', 'tiny', 'bfseries',
          'itshape', 'normalfont', 'hfill', 'vfill', 'appendix'}
DROP_ENV = {'equation', 'equation*', 'align', 'align*', 'gather', 'gather*',
            'multline', 'multline*', 'displaymath', 'math', 'tabular', 'tabular*',
            'tabularx', 'longtable', 'table', 'table*', 'figure', 'figure*',
            'verbatim', 'Verbatim', 'lstlisting', 'minted', 'algorithm',
            'algorithm*', 'algorithmic', 'thebibliography', 'tikzpicture'}
TEXT_ENV = {'document', 'abstract', 'itemize', 'enumerate', 'description',
            'quote', 'quotation', 'center', 'flushleft', 'flushright'}
VERBATIM_ENV = {'verbatim', 'Verbatim', 'lstlisting', 'minted'}


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def clean_space(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def inline_verbatim_end(text: str, start: int) -> int:
    """Return the end of a literal delimited verb body, never interpreting it."""
    if start >= len(text) or text[start].isspace():
        raise ValueError('Missing inline verbatim delimiter; inspect extraction.')
    finish = text.find(text[start], start + 1)
    newline = text.find('\n', start + 1)
    if finish < 0 or (newline >= 0 and newline < finish):
        raise ValueError('Unclosed inline verbatim; inspect extraction.')
    return finish + 1


def mask_comments(text: str, *, mask_literals: bool = False) -> str:
    """Preserve offsets; optionally hide literal regions for boundary discovery."""
    masked = list(text)
    i = 0
    while i < len(text):
        if text[i] == '%':
            end = text.find('\n', i)
            end = len(text) if end < 0 else end
            masked[i:end] = ' ' * (end - i)
            i = end
        elif text[i] == '\\':
            verb = re.match(r'\\verb(?![A-Za-z@])\*?', text[i:])
            begin = re.match(r'\\begin\s*\{([^}]+)\}', text[i:])
            if verb:
                end = inline_verbatim_end(text, i + len(verb.group()))
                if mask_literals:
                    masked[i:end] = ' ' * (end - i)
                i = end
            elif begin and begin.group(1) in VERBATIM_ENV:
                ending = re.search(r'\\end\s*\{' + re.escape(begin.group(1)) + r'\}',
                                   text[i + len(begin.group()):])
                if not ending:
                    raise ValueError('Unclosed excluded environment: ' + begin.group(1))
                end = i + len(begin.group()) + ending.end()
                if mask_literals:
                    masked[i:end] = re.sub(r'[^\n]', ' ', text[i:end])
                i = end
            else:
                i += 2
        else:
            i += 1
    return ''.join(masked)


def group_at(text: str, start: int, opening='{', closing='}') -> tuple[str, int, int]:
    """Return group content, first content offset, and offset after the group."""
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text) or text[start] != opening:
        raise ValueError('Expected a literal braced argument; use vetted prose for dynamic TeX.')
    depth, i = 1, start + 1
    while i < len(text):
        if text[i] == '\\':
            i += 2
            continue
        if text[i] == opening:
            depth += 1
        elif text[i] == closing:
            depth -= 1
            if not depth:
                return text[start + 1:i], start + 1, i + 1
        i += 1
    raise ValueError('Unclosed TeX group; inspect source rather than scoring guessed prose.')


class TexReader:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.inputs: dict[str, str] = {}
        self.blocks: list[dict] = []
        self.exclusions: list[dict] = []
        self.unknown: list[dict] = []
        self.section = 'Preamble-free prose'
        self.bytes = 0
        self.parsed_chars = 0
        self.raw_chars = 0
        self.stack: list[Path] = []

    def location(self, path: Path, line: int) -> dict:
        return {'file': str(path), 'line': line}

    def exclude(self, kind: str, path: Path, line: int, count: int) -> None:
        self.exclusions.append({'kind': kind, **self.location(path, line), 'characters': count})

    def read(self, path: Path) -> None:
        unresolved = path.absolute()
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('TeX include escapes the selected project root.')
        if unresolved.is_symlink() or any(p.is_symlink() for p in unresolved.parents if p.is_relative_to(self.root)):
            raise ValueError('Symlinked TeX inputs are unsupported.')
        if path in self.stack:
            raise ValueError('Cyclic TeX input; cannot determine prose coverage.')
        if len(self.stack) >= MAX_DEPTH or len(self.inputs) >= MAX_FILES:
            raise ValueError('TeX inclusion limit reached; supply a smaller vetted prose sample.')
        data = path.read_bytes()
        self.bytes += len(data)
        if self.bytes > MAX_BYTES:
            raise ValueError('TeX input size limit reached.')
        text = data.decode('utf-8')
        self.inputs[str(path)] = sha_bytes(data)
        self.raw_chars += len(text)
        # Mask comments, preserving offsets and line numbers.
        text = mask_comments(text)
        boundaries = mask_comments(text, mask_literals=True)
        start = re.search(r'\\begin\s*\{document\}', boundaries)
        if start:
            # Preamble text is not measured, but it can change which body files
            # reach the PDF. Do not silently claim full coverage in that case.
            for control in re.finditer(r'\\includeonly\b', boundaries[:start.start()]):
                self.unknown.append({
                    'kind': 'inclusion_control', 'name': 'includeonly',
                    **self.location(path, text.count('\n', 0, control.start()) + 1),
                    'reason': 'Preamble-controlled inclusion is unsupported; use vetted prose from the actual compiled manuscript.',
                })
            self.exclude('preamble', path, 1, start.end())
            offset = start.end()
            end = re.search(r'\\end\s*\{document\}', boundaries[offset:])
            selected = text[offset:offset + end.start()] if end else text[offset:]
            start_line = text.count('\n', 0, offset) + 1
        else:
            selected, start_line = text, 1
        self.stack.append(path)
        self.parse(selected, path, start_line)
        self.stack.pop()

    def parse(self, text: str, path: Path, start_line: int) -> None:
        buffer: list[str] = []
        block_line, i = start_line, 0

        def line(position: int) -> int:
            return start_line + text.count('\n', 0, position)

        def flush() -> None:
            nonlocal buffer
            value = clean_space(''.join(buffer))
            if value and WORD.search(value):
                if self.section.lower() in {'references', 'bibliography'}:
                    self.exclude('reference-section', path, block_line, len(value))
                else:
                    self.blocks.append({'section': self.section, 'text': value,
                                        'location': self.location(path, block_line)})
            buffer = []

        while i < len(text):
            blank = re.match(r'\n[ \t]*\n', text[i:]) if text[i] == '\n' else None
            if blank:
                flush()
                i += len(blank.group())
                block_line = line(i)
                continue
            if text[i] == '$' or text.startswith('\\(', i) or text.startswith('\\[', i):
                opener = '$$' if text.startswith('$$', i) else text[i:i+2] if text[i] == '\\' else '$'
                closer = {'\\(': '\\)', '\\[': '\\]'}.get(opener, opener)
                end = text.find(closer, i + len(opener))
                if end < 0:
                    raise ValueError('Unclosed math delimiter; inspect extraction.')
                finish = end + len(closer)
                self.exclude('math', path, line(i), finish - i)
                buffer.append(' ')
                i = finish
                continue
            if text[i] != '\\':
                c = text[i]
                if c in '{}':
                    c = ''
                elif c == '~':
                    c = ' '
                buffer.append(c)
                i += 1
                continue
            command = re.match(r'\\([A-Za-z@]+)\*?', text[i:])
            if not command:
                if i + 1 < len(text):
                    char = text[i + 1]
                    buffer.append(char if char in '%&#_' else ' ')
                i += 2
                continue
            name = command.group(1)
            end = i + len(command.group())
            if name == 'verb':
                finish = inline_verbatim_end(text, end)
                self.exclude('inline-verbatim', path, line(i), finish - i)
                buffer.append(' ')
                i = finish
                continue
            optional = end
            while optional < len(text) and text[optional].isspace():
                optional += 1
            if optional < len(text) and text[optional] == '[':
                _, _, end = group_at(text, optional, '[', ']')
            if name in {'input', 'include'}:
                target, _, finish = group_at(text, end)
                if not re.fullmatch(r'[A-Za-z0-9_./ -]+', target) or '\\' in target:
                    raise ValueError('Dynamic TeX input path is unsupported.')
                flush()
                # Match the managed LaTeX build, whose working directory is the
                # configured project root, not the directory of this include.
                child = self.root / target
                if not child.suffix:
                    child = child.with_suffix('.tex')
                self.read(child)
                i, block_line = finish, line(finish)
                continue
            if name in {'section', 'subsection', 'subsubsection', 'paragraph', 'chapter', 'part'}:
                title, _, finish = group_at(text, end)
                flush()
                self.section = clean_space(re.sub(r'\\[A-Za-z]+|[{}]', '', title))
                self.exclude('heading', path, line(i), finish - i)
                i, block_line = finish, line(finish)
                continue
            if name == 'begin':
                env, _, finish = group_at(text, end)
                if env in DROP_ENV:
                    ending = re.search(r'\\end\s*\{' + re.escape(env) + r'\}', text[finish:])
                    if not ending:
                        raise ValueError('Unclosed excluded environment: ' + env)
                    final = finish + ending.end()
                    self.exclude('environment:' + env, path, line(i), final-i)
                    buffer.append(' ')
                    i = final
                    continue
                flush()
                if env == 'abstract':
                    self.section = 'Abstract'
                elif env not in TEXT_ENV:
                    self.unknown.append({'kind': 'environment', 'name': env, **self.location(path, line(i))})
                i, block_line = finish, line(finish)
                continue
            if name == 'end':
                env, _, finish = group_at(text, end)
                flush()
                if env == 'abstract':
                    self.section = 'Unsectioned prose'
                i, block_line = finish, line(finish)
                continue
            if name in TEXT_COMMANDS:
                body, body_start, finish = group_at(text, end)
                # Flatten only the wrapper; recursively parse in the same context
                # so nested markup remains prose, without executing a macro.
                old_count = len(self.blocks)
                self.parse(body, path, line(body_start))
                nested = self.blocks[old_count:]
                del self.blocks[old_count:]
                buffer.append(' '.join(b['text'] for b in nested))
                i = finish
                continue
            if name == 'href':
                _, _, finish = group_at(text, end)
                body, body_start, finish = group_at(text, finish)
                old_count = len(self.blocks)
                self.parse(body, path, line(body_start))
                buffer.append(' '.join(b['text'] for b in self.blocks[old_count:]))
                del self.blocks[old_count:]
                i = finish
                continue
            if name in DROP_ARGUMENT:
                _, _, finish = group_at(text, end)
                if name == 'captionof':
                    _, _, finish = group_at(text, finish)
                self.exclude('command:' + name, path, line(i), finish-i)
                buffer.append(' ')
                i = finish
                continue
            if name in LAYOUT:
                i = end
                continue
            if name in {'par', 'item'}:
                flush()
                i, block_line = end, line(end)
                continue
            if name == 'printbibliography':
                self.exclude('bibliography', path, line(i), end-i)
                i = end
                continue
            self.unknown.append({'kind': 'command', 'name': name, **self.location(path, line(i))})
            # Unknown macro arguments may be code, labels, or prose. Do not guess.
            finish = end
            while True:
                probe = finish
                while probe < len(text) and text[probe].isspace():
                    probe += 1
                if probe >= len(text) or text[probe] != '{':
                    break
                _, _, finish = group_at(text, probe)
            self.exclude('unknown:' + name, path, line(i), finish-i)
            buffer.append(' ')
            i = finish
        flush()
        self.parsed_chars += len(text)


def split_sentences(text: str) -> list[str]:
    """Conservative heuristic, with common academic abbreviations protected."""
    protected = text
    for pattern in [r'\b(?:e\.g|i\.e)\.', r'\b(?:Dr|Mr|Ms|Prof|Fig|Eq|Sec|vs|al|cf)\.', r'(?<=\d)\.(?=\d)', r'\b[A-Z]\.(?=\s+[A-Z])']:
        protected = re.sub(pattern, lambda m: m.group().replace('.', '\u2024'), protected)
    pieces = re.split(r'(?<=[.!?])\s+', protected)
    return [s.replace('\u2024', '.').strip() for s in pieces if WORD.search(s)]


def percentile(values: list[int], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered)-1)*fraction
    low, high = math.floor(position), math.ceil(position)
    return round(ordered[low] + (ordered[high]-ordered[low])*(position-low), 3)


def metrics(blocks: list[dict]) -> dict:
    located = []
    for block in blocks:
        for sentence in split_sentences(block['text']):
            located.append({'text': sentence, 'words': len(WORD.findall(sentence)),
                            'section': block['section'], 'location': block['location'],
                            'location_precision': 'paragraph start; inspect source for exact sentence'})
    words = WORD.findall(' '.join(b['text'] for b in blocks))
    n, s = len(words), len(located)
    letters = sum(sum(c.isalpha() for c in w) for w in words)
    characters = sum(sum(c.isalnum() for c in w) for w in words)
    if n and s:
        ari = 4.71*characters/n + .5*n/s - 21.43
        cli = .0588*(100*letters/n) - .296*(100*s/n) - 15.8
    else:
        ari = cli = None
    lengths = [sentence['words'] for sentence in located]
    return {'words': n, 'sentences': s, 'paragraphs': len(blocks), 'letters': letters,
            'alphanumeric_characters': characters,
            'automated_readability_index': round(ari, 3) if ari is not None else None,
            'coleman_liau_index': round(cli, 3) if cli is not None else None,
            'sentence_words_mean': round(n/s, 3) if s else None,
            'sentence_words_p50': percentile(lengths, .5),
            'sentence_words_p90': percentile(lengths, .9),
            'longest_sentences': sorted(located, key=lambda x: x['words'], reverse=True)[:5],
            'sample_warning': 'Fewer than 100 words or 5 sentences; formulas are especially unstable.' if n < 100 or s < 5 else None}


def syntax_diagnostics(blocks: list[dict], model: str | None) -> dict:
    result = {'requested': bool(model), 'available': False, 'model': model,
              'status': 'not_requested', 'note': 'Optional local spaCy; no model downloads. Raw dependency lengths are not the standardized metric in arXiv:2610.29162.'}
    if not model:
        return result
    try:
        import spacy
        nlp = spacy.load(model)
        if 'parser' not in nlp.pipe_names:
            raise ValueError('The selected local model has no dependency parser.')
        if nlp.lang != 'en':
            raise ValueError('The selected local parser is not English.')
    except (ImportError, OSError, ValueError) as exc:
        result.update(status='unavailable', reason=str(exc))
        return result
    distances, examples = [], []
    total_tokens = 0
    for block in blocks:
        doc = nlp(block['text'])
        total_tokens += sum(not t.is_punct and not t.is_space for t in doc)
        for token in doc:
            if token.dep_ != 'ROOT' and not token.is_punct and not token.is_space:
                distances.append(abs(token.i-token.head.i))
            if token.pos_ not in {'NOUN', 'PROPN'}:
                continue
            if token.dep_ == 'compound' and token.head.pos_ in {'NOUN', 'PROPN'}:
                continue  # count each maximal compound once
            stack, members = [token], []
            while stack:
                item = stack.pop()
                members.append(item)
                stack.extend(c for c in item.children if c.dep_ == 'compound' and c.pos_ in {'NOUN', 'PROPN'})
            if len(members) >= 3:
                examples.append({'text': ' '.join(t.text for t in sorted(members, key=lambda t: t.i)),
                                 'noun_count': len(members), 'location': block['location'], 'section': block['section']})
    result.update(available=True, status='available', spacy_version=spacy.__version__,
                  model_version=nlp.meta.get('version', 'unknown'), model_lang=nlp.lang,
                  tokens=total_tokens, raw_mean_dependency_length=round(statistics.mean(distances), 3) if distances else None,
                  raw_max_dependency_length=max(distances) if distances else None,
                  noun_compounds_three_or_more=len(examples), noun_compound_examples=examples,
                  interpretation='Candidates for human review; established domain terms can be appropriate. Not an AI detector or a paper replication.')
    return result


def compare_baseline(report: dict, baseline: dict) -> dict:
    reasons = []
    for key in ['schema_version', 'engine', 'settings']:
        if report.get(key) != baseline.get(key):
            reasons.append('Different ' + key)
    syntax_keys = ['available', 'spacy_version', 'model', 'model_version', 'model_lang']
    if any(report.get('syntax', {}).get(k) != baseline.get('syntax', {}).get(k) for k in syntax_keys):
        reasons.append('Different syntax backend or model')
    if report.get('extraction', {}).get('status') != 'ready' or baseline.get('extraction', {}).get('status') != 'ready':
        reasons.append('Unresolved extraction coverage')
    if set(report.get('sections', {})) != set(baseline.get('sections', {})):
        reasons.append('Different section coverage')
    if reasons:
        return {'comparable': False, 'reasons': reasons}
    changes = {}
    for key in ['automated_readability_index', 'coleman_liau_index', 'sentence_words_mean', 'sentence_words_p90', 'words']:
        a, b = report['overall'].get(key), baseline.get('overall', {}).get(key)
        changes[key] = round(a-b, 3) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
    return {'comparable': True, 'changes_current_minus_baseline': changes,
            'note': 'Matched measurement settings only; authors must check that excerpts, claims, and audience remain comparable. Lower is not automatically better.'}


def analyze(path: Path, input_format: str = 'text', root: Path | None = None,
            spacy_model: str | None = None, baseline: dict | None = None) -> dict:
    path = path.resolve()
    if input_format not in {'text', 'tex'}:
        raise ValueError('Input format must be text or tex.')
    if input_format == 'tex':
        reader = TexReader(root or path.parent)
        reader.read(path)
        blocks, inputs = reader.blocks, reader.inputs
        extraction = {'method': 'conservative-tex-reader-v1', 'status': 'needs_review' if reader.unknown else 'ready',
                      'exclusions': reader.exclusions, 'unsupported': reader.unknown,
                      'raw_characters': reader.raw_chars,
                      'note': 'Never executes TeX. Inspect cleaned.txt; custom macros, conditionals, and unusual environments require vetted prose. Exclusion counts are not semantic completeness.'}
    else:
        data = path.read_bytes()
        if len(data) > MAX_BYTES:
            raise ValueError('Input too large; use a bounded prose sample.')
        text = data.decode('utf-8')
        blocks, offset = [], 0
        for part in re.split(r'\n\s*\n', text):
            stripped = clean_space(part)
            if stripped and WORD.search(stripped):
                start = text.find(part, offset)
                blocks.append({'section': 'Prose', 'text': stripped,
                               'location': {'file': str(path), 'line': text.count('\n', 0, start)+1}})
                offset = start + len(part)
        inputs = {str(path): sha_bytes(data)}
        extraction = {'method': 'supplied-prose-v1', 'status': 'ready', 'exclusions': [], 'unsupported': [],
                      'raw_characters': len(text),
                      'note': 'Caller must supply vetted English prose without bibliography, formula blocks, code, or table cells. This tool does not certify that choice.'}
    if not blocks:
        raise ValueError('No assessable prose extracted; do not report an empty sample as a pass.')
    cleaned = '\n\n'.join(b['text'] for b in blocks) + '\n'
    extraction['cleaned_characters'] = len(cleaned)
    sections = {}
    for block in blocks:
        sections.setdefault(block['section'], []).append(block)
    report = {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
              'engine': {'name': 'paperkit-readability', 'version': VERSION,
                         'script_sha256': sha_file(Path(__file__))},
              'settings': {'language': 'en', 'input_format': input_format,
                           'tokenizer': 'ascii-english-words-digits-v1', 'sentence_splitter': 'academic-abbreviation-heuristic-v1',
                           'minimum_recommended_words': 100, 'minimum_recommended_sentences': 5,
                           'spacy_model': spacy_model,
                           'excluded': 'TeX preamble, heading labels, bibliography, math, code, tables, figures, captions, footnotes, citation/ref keys'},
              'entrypoint': str(path), 'input_hashes': inputs, 'extraction': extraction,
              'cleaned_text': cleaned, 'cleaned_sha256': sha_bytes(cleaned.encode()),
              'overall': metrics(blocks), 'sections': {k: metrics(v) for k, v in sections.items()},
              'syntax': syntax_diagnostics(blocks, spacy_model),
              'interpretation': ['ARI and Coleman–Liau estimate US school-grade reading difficulty, not audience competence or scientific merit.',
                                 'No universal target or pass/fail cutoff is used.',
                                 'Technical terms, abbreviations, numerals, and imperfect sentence segmentation can distort formulas.',
                                 'Review flagged passages and preserve meaning, necessary terms, citations, and scope.',
                                 'No Flesch score is fabricated; syllable/dictionary-based tooling is not bundled.',
                                 'This is not a replication of arXiv:2610.29162 or an AI-text detector.']}
    if baseline is not None:
        report['baseline_comparison'] = compare_baseline(report, baseline)
    return report


def markdown(report: dict) -> str:
    lines = ['# Readability diagnostics', '', '**Advisory measurements, not a paper-quality score.**', '',
             f"Engine: {report['engine']['name']} {report['engine']['version']}. Language: English.", '',
             '| Prose scope | Words | Sentences | ARI | Coleman–Liau | Mean sentence words | p90 |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for name, value in [('Overall', report['overall']), *report['sections'].items()]:
        columns = [value[k] for k in ['words', 'sentences', 'automated_readability_index', 'coleman_liau_index', 'sentence_words_mean', 'sentence_words_p90']]
        lines.append('| ' + str(name).replace('|', '\\|') + ' | ' + ' | '.join(str(x) for x in columns) + ' |')
    lines += ['', '## Interpretation', ''] + ['- ' + x for x in report['interpretation']]
    if report['overall']['sample_warning']:
        lines += ['', report['overall']['sample_warning']]
    lines += ['', '## Extraction coverage', '', f"Status: **{report['extraction']['status']}**. {report['extraction']['note']}",
              '', f"Recorded exclusions: {len(report['extraction']['exclusions'])}. Unsupported constructs: {len(report['extraction']['unsupported'])}.",
              'Inspect `cleaned.txt`; detailed locations and input hashes are in `report.json`.', '', '## Sentences to inspect', '']
    for item in report['overall']['longest_sentences']:
        loc = item['location']
        lines += [f"- {item['words']} words; {item['section']}; {loc['file']}:{loc['line']} (paragraph start): {item['text']}"]
    lines += ['', '## Optional syntax diagnostics', '', f"Status: {report['syntax']['status']}.", report['syntax']['note']]
    if report['syntax'].get('reason'):
        lines += [report['syntax']['reason']]
    if report['syntax'].get('available'):
        lines += [f"Raw mean dependency length: {report['syntax']['raw_mean_dependency_length']}; noun compounds of at least three nouns: {report['syntax']['noun_compounds_three_or_more']}."]
    if 'baseline_comparison' in report:
        lines += ['', '## Baseline comparison', '', '```json', json.dumps(report['baseline_comparison'], indent=2), '```']
    return '\n'.join(lines) + '\n'


def write_report(report: dict, output_dir: Path) -> dict:
    output_dir = output_dir.resolve()
    if output_dir.exists() and (not output_dir.is_dir() or any(output_dir.iterdir())):
        raise ValueError('Choose an empty/new report directory; keep old reports for comparisons.')
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir/'cleaned.txt').write_text(report['cleaned_text'], encoding='utf-8')
    (output_dir/'report.md').write_text(markdown(report), encoding='utf-8')
    (output_dir/'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return {'report': str(output_dir/'report.json'), 'markdown': str(output_dir/'report.md'),
            'cleaned': str(output_dir/'cleaned.txt'), 'extraction_status': report['extraction']['status']}


def check_report(report_path: Path, project: Path | None = None) -> dict:
    errors, warnings = [], []
    try:
        report = json.loads(report_path.read_text())
        if report.get('schema_version') != 1 or report.get('engine', {}).get('version') != VERSION:
            errors.append('Unsupported readability report version.')
        if report.get('engine', {}).get('script_sha256') != sha_file(Path(__file__)):
            errors.append('Readability tool changed; recompute report.')
        if report.get('settings', {}).get('language') != 'en':
            errors.append('Unsupported report language.')
        inputs = report.get('input_hashes', {})
        if not isinstance(inputs, dict) or not inputs:
            errors.append('Missing readability input hashes.')
        else:
            for path, expected in inputs.items():
                p = Path(path)
                if project is not None and not p.resolve().is_relative_to(project.resolve()):
                    errors.append('Readability input is outside the selected project: ' + path)
                if not p.is_file() or sha_file(p) != expected:
                    errors.append('Readability input missing or changed: ' + path)
        cleaned = report_path.parent/'cleaned.txt'
        if not cleaned.is_file() or sha_file(cleaned) != report.get('cleaned_sha256'):
            errors.append('Cleaned prose missing or changed.')
        if sha_bytes(report.get('cleaned_text', '').encode()) != report.get('cleaned_sha256'):
            errors.append('Embedded cleaned text hash mismatch.')
        if report.get('extraction', {}).get('status') != 'ready':
            errors.append('Unresolved TeX extraction; inspect coverage and supply vetted prose.')
        if report.get('overall', {}).get('words', 0) <= 0:
            errors.append('No assessed prose.')
        if report.get('overall', {}).get('sample_warning'):
            warnings.append(report['overall']['sample_warning'])
        if report.get('syntax', {}).get('requested') and not report.get('syntax', {}).get('available'):
            warnings.append('Requested optional syntax diagnostics unavailable; no score was substituted.')
        return {'passed': not errors, 'errors': errors, 'warnings': warnings,
                'report_sha256': sha_file(report_path),
                'scope': 'Freshness and declared extraction coverage only; neither author comprehension nor a numerical quality cutoff.'}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        return {'passed': False, 'errors': ['Unreadable or invalid readability report: '+str(exc)], 'warnings': warnings}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--tex', type=Path)
    inputs.add_argument('--text', type=Path)
    inputs.add_argument('--check', type=Path, help='Check an existing report.json without recomputing scores.')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--spacy-model', help='Already installed English parser package/path; never downloaded.')
    parser.add_argument('--baseline', type=Path, help='Prior report.json; mismatched settings are not compared.')
    args = parser.parse_args()
    try:
        if args.check:
            result = check_report(args.check, args.root)
        else:
            if not args.output_dir:
                parser.error('--output-dir is required for a new assessment.')
            baseline = json.loads(args.baseline.read_text()) if args.baseline else None
            report = analyze(args.tex or args.text, 'tex' if args.tex else 'text', args.root, args.spacy_model, baseline)
            result = write_report(report, args.output_dir)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 1 if result.get('passed') is False else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print('Error: '+str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
