from __future__ import annotations
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import readability as rd


class ReadabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()

    def tearDown(self):
        self.tmp.cleanup()

    def source(self, text, name='main.tex'):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def test_formula_counts_and_short_sample_are_advisory(self):
        source = self.source('Cats run. Dogs play.', 'prose.txt')
        result = rd.analyze(source)
        # Four words, 15 letters/characters, two sentences. Direct formula reference.
        self.assertEqual(result['overall']['words'], 4)
        self.assertEqual(result['overall']['sentences'], 2)
        self.assertAlmostEqual(result['overall']['automated_readability_index'], -2.7675, delta=.00051)
        self.assertAlmostEqual(result['overall']['coleman_liau_index'], -8.55, places=3)
        self.assertTrue(result['overall']['sample_warning'])
        rd.write_report(result, self.root/'report')
        checked = rd.check_report(self.root/'report/report.json', self.root)
        self.assertTrue(checked['passed'])
        self.assertTrue(checked['warnings'])

    def test_tex_excludes_nonprose_and_preserves_abstract_and_nested_wrappers(self):
        source = self.source(r'''\documentclass{article}
\title{Not part of the prose}
\newcommand{\macro}{Ignored preamble definition}
\begin{document}
\begin{abstract}
We test \textbf{a \emph{simple} method}.
\end{abstract}
\section{Method}
We compare $a^2+b^2=c^2$ two methods.\citep{SecretCitation}
\begin{equation}SECRET EQUATION\end{equation}
\begin{table}\caption{SECRET CAPTION}\begin{tabular}{c}SECRET DATA\end{tabular}\end{table}
\begin{verbatim}SECRET CODE\end{verbatim}
\begin{thebibliography}{9}\bibitem{KEY}SECRET REFERENCE\end{thebibliography}
\end{document}
''')
        result = rd.analyze(source, 'tex')
        self.assertEqual(result['extraction']['status'], 'ready')
        self.assertIn('We test a simple method.', result['cleaned_text'])
        self.assertIn('We compare two methods.', result['cleaned_text'])
        self.assertNotIn('SECRET', result['cleaned_text'])
        self.assertNotIn('SecretCitation', result['cleaned_text'])
        self.assertEqual(set(result['sections']), {'Abstract', 'Method'})
        self.assertGreaterEqual(len(result['extraction']['exclusions']), 7)

    def test_unknown_macro_is_visible_and_cannot_satisfy_extraction_gate(self):
        source = self.source(r'We test \custommacro{hidden content}. The result is clear.')
        result = rd.analyze(source, 'tex')
        self.assertEqual(result['extraction']['status'], 'needs_review')
        self.assertEqual(result['extraction']['unsupported'][0]['name'], 'custommacro')
        self.assertNotIn('hidden content', result['cleaned_text'])
        rd.write_report(result, self.root/'report')
        self.assertFalse(rd.check_report(self.root/'report/report.json')['passed'])

    def test_inline_verbatim_is_excluded_without_losing_following_prose(self):
        source = self.source(r'''Before \verb|\unknown{code} % [RAW]| after.
Next \verb*+CODE % \other+ sentence.
Third \verb*acodea passage.
\Needspace{3\baselineskip}Final prose. % hidden comment
''')
        result = rd.analyze(source, 'tex')
        self.assertEqual(result['cleaned_text'].strip(), 'Before after. Next sentence. Third passage. Final prose.')
        self.assertEqual(result['extraction']['status'], 'ready')
        self.assertEqual(sum(x['kind'] == 'inline-verbatim' for x in result['extraction']['exclusions']), 3)

    def test_literal_percent_in_verbatim_does_not_hide_its_end(self):
        source = self.source(r'''Before.
\begin{Verbatim}CODE % \unknown\end{Verbatim}
After. \% remains. \\% hidden comment
Last sentence.
''')
        result = rd.analyze(source, 'tex')
        self.assertEqual(result['extraction']['status'], 'ready')
        self.assertNotIn('CODE', result['cleaned_text'])
        self.assertNotIn('hidden', result['cleaned_text'])
        self.assertIn('After. % remains.', result['cleaned_text'])
        self.assertIn('Last sentence.', result['cleaned_text'])

    def test_malformed_inline_verbatim_fails_instead_of_guessing_prose(self):
        for text in ('Before \\verb|never closed', 'Before \\verb|crosses\na line| after.', 'Before \\verb no delimiter'):
            with self.subTest(text=text):
                with self.assertRaisesRegex(ValueError, 'verbatim'):
                    rd.analyze(self.source(text), 'tex')

    def test_literal_document_markers_do_not_change_prose_boundaries(self):
        samples = [
            r'Before \verb|\begin{document}| after.',
            r'\begin{document}Before \verb|\end{document}| after.\end{document}',
            '\\begin{document}Before.\n\\begin{Verbatim}\\begin{document}\n'
            '\\end{document}\\end{Verbatim}\nAfter.\\end{document}',
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                result = rd.analyze(self.source(sample), 'tex')
                self.assertEqual(result['extraction']['status'], 'ready')
                self.assertIn('Before', result['cleaned_text'])
                self.assertIn('after' if ' after.' in sample else 'After', result['cleaned_text'])
                self.assertNotIn('document', result['cleaned_text'])

    def test_manual_references_excluded_and_appendix_resumes(self):
        source = self.source(r'''\section{Method}
We test a method.
\section*{References}
Unwanted bibliography prose.
\section{Appendix}
We describe more details.
''')
        result = rd.analyze(source, 'tex')
        self.assertNotIn('Unwanted', result['cleaned_text'])
        self.assertIn('We describe more details.', result['cleaned_text'])

    def test_nested_inputs_record_hashes_and_original_location(self):
        source = self.source('\\section{Method}\n\\input{sections/method}')
        child = self.source('\n\nWe measure the result.\n', 'sections/method.tex')
        result = rd.analyze(source, 'tex')
        self.assertEqual(set(result['input_hashes']), {str(source), str(child)})
        location = result['overall']['longest_sentences'][0]['location']
        self.assertEqual(location['file'], str(child))
        self.assertEqual(location['line'], 3)
        rd.write_report(result, self.root/'report')
        child.write_text('Changed evidence.')
        self.assertFalse(rd.check_report(self.root/'report/report.json')['passed'])

    def test_nested_include_paths_match_project_build_directory(self):
        source = self.source('\\input{sections/method}')
        method = self.source('\\input{sections/details}', 'sections/method.tex')
        details = self.source('Correct project-root prose.', 'sections/details.tex')
        decoy = self.source('Wrong including-directory prose.', 'sections/sections/details.tex')
        for command in ('input', 'include'):
            with self.subTest(command=command):
                method.write_text('\\' + command + '{sections/details}')
                result = rd.analyze(source, 'tex', self.root)
                self.assertIn('Correct project-root prose.', result['cleaned_text'])
                self.assertNotIn('Wrong including-directory prose.', result['cleaned_text'])
                self.assertIn(str(details), result['input_hashes'])
                self.assertNotIn(str(decoy), result['input_hashes'])

    def test_preamble_includeonly_requires_extraction_review(self):
        source = self.source(r'''\documentclass{article}
\includeonly{first}
\begin{document}
\include{first}
\include{second}
\end{document}
''')
        self.source('Included paper section.', 'first.tex')
        self.source('Section excluded from the PDF.', 'second.tex')
        result = rd.analyze(source, 'tex')
        self.assertEqual(result['extraction']['status'], 'needs_review')
        controls = [item for item in result['extraction']['unsupported']
                    if item['kind'] == 'inclusion_control']
        self.assertEqual(len(controls), 1)
        self.assertEqual(controls[0]['name'], 'includeonly')
        self.assertEqual(controls[0]['line'], 2)
        rd.write_report(result, self.root/'report')
        self.assertFalse(rd.check_report(self.root/'report/report.json')['passed'])

    def test_input_cycles_and_escape_fail(self):
        cyclic = self.source('\\input{main}')
        with self.assertRaisesRegex(ValueError, 'Cyclic'):
            rd.analyze(cyclic, 'tex')
        cyclic.write_text('\\input{../outside}')
        with self.assertRaisesRegex(ValueError, 'escapes'):
            rd.analyze(cyclic, 'tex')

    def test_input_limit_and_unclosed_math_fail(self):
        source = self.source('\\input{child}')
        self.source('Text.', 'child.tex')
        with patch.object(rd, 'MAX_DEPTH', 1):
            with self.assertRaisesRegex(ValueError, 'limit'):
                rd.analyze(source, 'tex')
        source.write_text('We use $x and compare methods.')
        with self.assertRaisesRegex(ValueError, 'math'):
            rd.analyze(source, 'tex')

    def test_baseline_requires_matching_preprocessing_and_sections(self):
        source = self.source('We test the method. It works in this setting.', 'prose.txt')
        previous = rd.analyze(source)
        current = rd.analyze(source, baseline=previous)
        self.assertTrue(current['baseline_comparison']['comparable'])
        self.assertEqual(current['baseline_comparison']['changes_current_minus_baseline']['words'], 0)
        incompatible = copy.deepcopy(previous)
        incompatible['settings']['sentence_splitter'] = 'other'
        current = rd.analyze(source, baseline=incompatible)
        self.assertFalse(current['baseline_comparison']['comparable'])
        incompatible = copy.deepcopy(previous)
        incompatible['sections']['New section'] = {}
        self.assertFalse(rd.compare_baseline(previous, incompatible)['comparable'])

    def test_optional_backend_absent_is_unavailable_without_download(self):
        source = self.source('We test a method.', 'prose.txt')
        with patch.dict(sys.modules, {'spacy': None}):
            result = rd.analyze(source, spacy_model='installed-english-parser')
        self.assertEqual(result['syntax']['status'], 'unavailable')
        self.assertFalse(result['syntax']['available'])
        self.assertIsNotNone(result['overall']['automated_readability_index'])

    def test_abbreviations_and_decimal_do_not_split_sentences(self):
        result = rd.split_sentences('We use Eq. 2 and a value of 2.5, e.g. here. The result follows.')
        self.assertEqual(len(result), 2)

    def test_cleaned_text_tampering_and_unknown_report_rejected(self):
        source = self.source('We test a method.', 'prose.txt')
        rd.write_report(rd.analyze(source), self.root/'report')
        report_path = self.root/'report/report.json'
        self.assertTrue(rd.check_report(report_path)['passed'])
        (self.root/'report/cleaned.txt').write_text('Different prose.')
        self.assertFalse(rd.check_report(report_path)['passed'])
        report_path.write_text('[]')
        self.assertFalse(rd.check_report(report_path)['passed'])

    def test_empty_prose_and_existing_output_are_not_silently_accepted(self):
        source = self.source('\n', 'prose.txt')
        with self.assertRaisesRegex(ValueError, 'No assessable'):
            rd.analyze(source)
        source.write_text('We test a method.')
        result = rd.analyze(source)
        rd.write_report(result, self.root/'report')
        with self.assertRaisesRegex(ValueError, 'empty/new'):
            rd.write_report(result, self.root/'report')

    def test_real_command_writes_json_markdown_and_cleaned_prose(self):
        source = self.source('We compare two methods. The test uses the same budget.', 'prose.txt')
        completed = subprocess.run([sys.executable, str(ROOT/'scripts/readability.py'), '--text', str(source),
                                   '--output-dir', str(self.root/'report')], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        output = json.loads(completed.stdout)
        self.assertTrue(Path(output['report']).is_file())
        self.assertTrue(Path(output['markdown']).is_file())
        self.assertTrue(Path(output['cleaned']).is_file())
        self.assertTrue(rd.check_report(Path(output['report']), self.root)['passed'])


if __name__ == '__main__':
    unittest.main()
