from __future__ import annotations
import copy
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import paperkit as pk
import workspace
import readability
import visual_audit


def review():
    return {'mode': 'development', 'packet_hash': 'a'*64, 'reviewer_id': 'synthetic-test-only',
            'reviewer_perspective': 'evidence_evaluation',
            'coverage': ['Synthetic methods-only fixture; no visual inspection'], 'summary': 'A synthetic fixture.',
            **{k: {'score': 3, 'rationale': 'Synthetic rationale.'} for k in ['presentation','informativeness','soundness']},
            'critical_strengths': [], 'critical_weaknesses': [], 'questions_for_authors': [],
            'ethics_review': {'answer': 'no', 'details': ''},
            'confidence': {'score': 2, 'rationale': 'Synthetic AI proxy based only on supplied methods; no human expertise asserted.'},
            'rating': {'score': None, 'rationale': 'No experimental evidence supplied.'}, 'improvement_plan': []}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory();self.root = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()
    def test_init_defaults(self):
        created=workspace.initialize(self.root)
        self.assertIn('config/paper.yaml', created)
        self.assertTrue((self.root/'.claude/skills/research-paper/SKILL.md').is_file())
        self.assertTrue((self.root/'.agents/skills/research-paper/SKILL.md').is_file())
    def test_init_preserves_existing(self):
        workspace.initialize(self.root)
        config=self.root/'config/paper.yaml';config.write_text('author content')
        (self.root/'AGENTS.md').write_text('private instructions')
        workspace.initialize(self.root)
        self.assertEqual(config.read_text(),'author content')
        self.assertEqual((self.root/'AGENTS.md').read_text(),'private instructions')
    def test_no_host_option(self):
        workspace.initialize(self.root,'none')
        self.assertFalse((self.root/'.agents').exists())
    def test_antigravity_uses_shared_project_skill(self):
        workspace.initialize(self.root,'antigravity')
        self.assertTrue((self.root/'.agents/skills/research-paper/SKILL.md').is_file())
        self.assertFalse((self.root/'.claude').exists())
    def test_all_hosts_have_one_shared_kit(self):
        workspace.initialize(self.root,'all')
        self.assertTrue((self.root/'.agents/skills/research-paper/SKILL.md').is_file())
        self.assertTrue((self.root/'.claude/skills/research-paper/SKILL.md').is_file())
        self.assertEqual(list((self.root/'.paper-tools').iterdir()),
                         [self.root/'.paper-tools/research-paper'])
    def test_init_excludes_repo_metadata_and_local_dependencies(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as kit_dir:
            kit=Path(kit_dir)
            (kit/'config').mkdir();(kit/'assets').mkdir()
            (kit/'config/paper.yaml').write_text('paper: ""\n')
            (kit/'assets/paper-todos.sty').write_text('% Synthetic guard\n')
            (kit/'SKILL.md').write_text('Synthetic kit')
            for name in ('.git', '__pycache__', '.venv', 'venv', 'node_modules', '.local-tests'):
                (kit/name).mkdir();(kit/name/'sentinel').write_text('Must not copy')
            with patch.object(workspace,'KIT',kit):
                workspace.initialize(self.root,'none')
            copied=self.root/'.paper-tools/research-paper'
            self.assertTrue((copied/'SKILL.md').is_file())
            for name in ('.git', '__pycache__', '.venv', 'venv', 'node_modules', '.local-tests'):
                self.assertFalse((copied/name).exists(), name)
    def test_invalid_host_is_rejected_before_initialization(self):
        with self.assertRaises(ValueError):workspace.initialize(self.root,'unknown')
        self.assertFalse((self.root/'.paper-tools').exists())
    def test_reject_symlink_escape(self):
        with tempfile.TemporaryDirectory() as other:
            (self.root/'config').symlink_to(other, target_is_directory=True)
            with self.assertRaises(ValueError):workspace.initialize(self.root)


class TodoTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        workspace.initialize(self.root,'none')
        self.main=self.root/'main.tex';self.main.write_text('Supported final-intended prose.\n')
    def tearDown(self):self.tmp.cleanup()
    def approved(self):
        return pk.add_todo(self.root,'T001','main.tex','Confirm matched budget.','TEST APPROVAL')
    def test_clean_draft(self):self.assertTrue(pk.preflight(self.root)['passed'])
    def test_no_sources_fails(self):
        self.main.unlink();self.assertFalse(pk.preflight(self.root)['passed'])
    def test_approved_wrapper_draft(self):
        self.main.write_text(self.approved())
        self.assertTrue(pk.preflight(self.root)['passed'])
    def test_wrapper_blocks_submission(self):
        self.main.write_text(self.approved())
        self.assertFalse(pk.preflight(self.root,'submission')['passed'])
    def test_unapproved_wrapper(self):
        self.main.write_text(r'\PaperTODO{T001}{Check.}')
        self.assertTrue(any('unapproved' in e for e in pk.preflight(self.root)['errors']))
    def test_changed_body_requires_new_approval(self):
        self.main.write_text(self.approved().replace('matched','larger'))
        self.assertTrue(any('differs' in e for e in pk.preflight(self.root)['errors']))
    def test_wrong_target_file(self):
        marker=self.approved();(self.root/'other.tex').write_text(marker)
        self.assertFalse(pk.preflight(self.root)['passed'])
    def test_comment_marker_detected(self):
        self.main.write_text('% TODO: hidden author note\nFinal prose.')
        self.assertFalse(pk.preflight(self.root)['passed'])
    def test_unwrapped_placeholders(self):
        for marker in ['TBD','FIXME','XXX','??','[INSERT RESULT]','lorem ipsum']:
            with self.subTest(marker=marker):
                self.main.write_text(marker);self.assertFalse(pk.preflight(self.root)['passed'])
    def test_environment_wrapper(self):
        self.approved()
        self.main.write_text('\\begin{PaperProvisional}{T001}\nConfirm matched budget.\n\\end{PaperProvisional}')
        self.assertTrue(pk.preflight(self.root)['passed'])
    def test_duplicate_wrapper(self):
        marker=self.approved();self.main.write_text(marker+'\n'+marker)
        self.assertFalse(pk.preflight(self.root)['passed'])
    def test_malformed_wrapper(self):
        self.main.write_text(r'\PaperTODO{T001}{broken')
        self.assertFalse(pk.preflight(self.root)['passed'])
    def test_cannot_close_visible_wrapper(self):
        self.main.write_text(self.approved())
        with self.assertRaises(ValueError):pk.close_todo(self.root,'T001','resolved','TEST','Resolved')
    def test_close_preserves_history(self):
        self.approved();pk.close_todo(self.root,'T001','removed','TEST DECISION','Removed dependent claim.')
        self.assertEqual(pk.load_state(self.root)['todos'][0]['status'],'removed')
    def test_closed_wrapper_reappearance(self):
        marker=self.approved();pk.close_todo(self.root,'T001','resolved','TEST','Replaced with evidence.')
        self.main.write_text(marker);self.assertFalse(pk.preflight(self.root)['passed'])
    def test_no_approval_no_registration(self):
        with self.assertRaises(ValueError):pk.add_todo(self.root,'T001','main.tex','Something','')
    def test_unique_ids(self):
        self.approved()
        with self.assertRaises(ValueError):self.approved()
    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):pk.add_todo(self.root,'T001','../outside.tex','X','TEST')
    def test_modified_guard_not_exempt(self):
        p=self.root/'paper-todos.sty';p.write_text(p.read_text()+'\n% TODO conceal\n')
        self.assertFalse(pk.preflight(self.root)['passed'])
    def test_exact_literal_exception(self):
        content='We cite the TODO algorithm.';self.main.write_text(content)
        state=pk.load_state(self.root)
        state['literal_exceptions']=[{'file':'main.tex','line':1,'sha256':pk.digest(content.encode()),
                                     'approval_ref':'TEST','reason':'Synthetic literal acronym.'}]
        pk.dump(self.root/'.paper/state.json',state)
        self.assertTrue(pk.preflight(self.root)['passed'])
        self.main.write_text(content+' changed');self.assertFalse(pk.preflight(self.root)['passed'])
    def test_arbitrary_input_is_hashed(self):
        (self.root/'data.custom').write_text('original')
        before=pk.snapshot(self.root);(self.root/'data.custom').write_text('changed')
        self.assertNotEqual(before,pk.snapshot(self.root))
    def test_scanned_input_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            p=Path(other)/'a.tex';p.write_text('hidden')
            (self.root/'linked.tex').symlink_to(p)
            with self.assertRaises(ValueError):pk.preflight(self.root)


class ReviewTests(unittest.TestCase):
    def test_development_null_valid(self):self.assertEqual(pk.validate_review(review()),[])
    def test_submission_null_invalid(self):
        v=review();v['mode']='submission_mock';self.assertTrue(pk.validate_review(v))
    def test_submission_complete_valid(self):
        v=review();v['mode']='submission_mock';v['rating']['score']=3
        self.assertEqual(pk.validate_review(v),[])
    def test_scores_reject_bool_and_old_scales(self):
        for x in [True,0,4,10,'3',3.5]:
            with self.subTest(x=x):
                v=review();v['soundness']['score']=x;self.assertTrue(pk.validate_review(v))
    def test_two_critical_findings_max(self):
        v=review();v['critical_weaknesses']=[{'claim':'x','location':'Sec. 1','why_consequential':'y'}]*3
        self.assertTrue(pk.validate_review(v))
    def test_no_forced_weakness(self):
        v=review();self.assertEqual(v['critical_weaknesses'],[]);self.assertEqual(pk.validate_review(v),[])
    def test_located_evidence_required(self):
        v=review();v['critical_strengths']=[{'claim':'x','location':'','why_consequential':'y'}]
        self.assertTrue(pk.validate_review(v))
    def test_assessment_effect_required(self):
        v=review();v['questions_for_authors']=[{'question':'Why?','location':'Sec 1','assessment_effect':''}]
        self.assertTrue(pk.validate_review(v))
    def test_optional_is_not_required(self):
        v=review();v['improvement_plan']=[{'category':'optional_extension','priority':'decision_critical',
           'resolution_basis':'new_research','claim':'x','evidence':'y','action':'z','completion_criterion':'done'}]
        self.assertTrue(pk.validate_review(v))
    def test_experiment_needs_design(self):
        v=review();v['improvement_plan']=[{'category':'experiment','priority':'useful',
           'resolution_basis':'new_research','claim':'x','evidence':'y','action':'z','completion_criterion':'done'}]
        self.assertTrue(pk.validate_review(v))
    def test_experiment_design_valid(self):
        v=review();v['improvement_plan']=[{'category':'experiment','priority':'useful',
           'resolution_basis':'new_research','claim':'x','evidence':'y','action':'z','completion_criterion':'done',
           'experiment_design':{k:'synthetic' for k in ['hypothesis','comparison','controls','metric','possible_outcomes','stop_condition']}}]
        self.assertEqual(pk.validate_review(v),[])
    def test_ethics_concern_requires_details(self):
        v=review();v['ethics_review']['answer']='yes'
        self.assertTrue(pk.validate_review(v))
        v['ethics_review']['details']='Sec. 4 contains identifying records without a consent statement.'
        self.assertEqual(pk.validate_review(v),[])
    def test_ethics_rejects_invalid_answer(self):
        for answer in [True,'unknown',None]:
            with self.subTest(answer=answer):
                v=review();v['ethics_review']['answer']=answer
                self.assertTrue(pk.validate_review(v))
    def test_confidence_anchors_and_null_mode(self):
        for score in [True,0,5,'3',3.5]:
            with self.subTest(score=score):
                v=review();v['confidence']['score']=score
                self.assertTrue(pk.validate_review(v))
        v=review();v['confidence']['score']=None
        self.assertEqual(pk.validate_review(v),[])
        v['mode']='submission_mock';v['rating']['score']=3
        self.assertTrue(pk.validate_review(v))
    def test_reviewer_perspective_required(self):
        v=review();v['reviewer_perspective']='always_reject'
        self.assertTrue(pk.validate_review(v))
    def test_missing_theory_cannot_be_a_writing_fix(self):
        v=review();v['improvement_plan']=[{'category':'theory','priority':'decision_critical',
            'resolution_basis':'writing','claim':'Theorem 1 holds.','evidence':'No proof supplied.',
            'action':'Prove the stated invariant under the listed assumptions.',
            'completion_criterion':'A checked proof or an author-approved change of claim.'}]
        self.assertTrue(pk.validate_review(v))
        v['improvement_plan'][0]['resolution_basis']='new_research'
        self.assertEqual(pk.validate_review(v),[])
    def test_experiment_stop_condition_required(self):
        v=review();v['improvement_plan']=[{'category':'experiment','priority':'decision_critical',
            'resolution_basis':'new_research','claim':'Claim A','evidence':'Missing control.',
            'action':'Run a matched control.','completion_criterion':'Compare confidence intervals.',
            'experiment_design':{k:'synthetic' for k in ['hypothesis','comparison','controls','metric','possible_outcomes']}}]
        self.assertTrue(pk.validate_review(v))
    def test_unknown_field_rejected(self):
        v=review();v['acceptance_probability']=0.99;self.assertTrue(pk.validate_review(v))
    def test_json_schema_parity(self):
        try:import jsonschema
        except ImportError:self.skipTest('Optional jsonschema is not installed.')
        schema=json.loads((ROOT/'schemas/review.schema.json').read_text())
        cases=[review()]
        v=review();v['mode']='submission_mock';cases.append(v)
        v=review();v['ethics_review']['answer']='yes';cases.append(v)
        v=review();v['ethics_review']={'answer':'yes','details':'Specific concern in Section 4.'};cases.append(v)
        v=review();v['confidence']['score']=True;cases.append(v)
        v=review();v['reviewer_perspective']='always_reject';cases.append(v)
        v=review();v['improvement_plan']=[{'category':'theory','priority':'decision_critical',
            'resolution_basis':'writing','claim':'x','evidence':'y','action':'z','completion_criterion':'done'}];cases.append(v)
        for index,value in enumerate(cases):
            with self.subTest(case=index):
                schema_valid=not list(jsonschema.Draft202012Validator(schema).iter_errors(value))
                self.assertEqual(not pk.validate_review(value),schema_valid)


@unittest.skipUnless(shutil.which('latexmk') and shutil.which('pdflatex') and shutil.which('pdftotext'), 'Local LaTeX/Poppler unavailable')
class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve()/'project'
        workspace.initialize(self.root,'none')
    def tearDown(self):self.tmp.cleanup()
    def source(self,body='This is a synthetic test document.',draft=False):
        guard=r'\usepackage[draft]{paper-todos}' if draft else r'\usepackage{paper-todos}'
        (self.root/'main.tex').write_text('\\documentclass{article}\n'+guard+'\n\\begin{document}\n'+body+'\n\\end{document}\n')
    def synthetic_quality_records(self):
        """Exercise record enforcement only; these are NOT real visual/editorial approvals."""
        receipt=json.loads((self.root/'.paper/build-receipt.json').read_text())
        pdf=self.root/receipt['pdf'];out=self.root/'.paper/visual'
        manifest=visual_audit.render_pdf(pdf,out)
        for page in range(1,manifest['pdf_pages']+1):
            visual_audit.record_page(pdf,out/'audit.json',page,'SYNTHETIC TEST FIXTURE',
                f'SYNTHETIC-IMAGE-{page}',
                f'Synthetic fixture observation for page {page}; tests records, not visual understanding.')
        report=readability.analyze(self.root/'main.tex','tex',root=self.root)
        output=self.root/'.paper/readability/test'
        readability.write_report(report,output)
        pk.record_readability_review(self.root,output/'report.json','SYNTHETIC TEST FIXTURE',
            'Synthetic fixture prose coverage; no real paper is being approved.',
            'Synthetic disposition for exercising the gate; short-sample warning is expected.')
    def test_final_macro_errors(self):
        self.source(r'\PaperTODO{T001}{An unresolved item.}')
        with self.assertRaises(ValueError):pk.build(self.root,'main.tex',True)
        self.assertFalse((self.root/'.paper/build-receipt.json').exists())
    def test_draft_marker_visible_and_release_blocked(self):
        marker=pk.add_todo(self.root,'T001','main.tex','Confirm the result.','TEST')
        self.source(marker,True);receipt=pk.build(self.root,'main.tex',True)
        self.assertIn('TODO T001',pk.extract_pdf(self.root/receipt['pdf']))
        self.assertFalse(pk.preflight(self.root,'submission')['passed'])
    def test_clean_release_and_stale_source(self):
        self.source();pk.build(self.root,'main.tex',True)
        self.assertFalse(pk.preflight(self.root,'submission')['passed'])
        self.synthetic_quality_records()
        pk.approve_release(self.root,'SYNTHETIC TEST ATTESTATION',pk.CHECKS)
        self.assertTrue(pk.preflight(self.root,'submission')['passed'])
        with (self.root/'main.tex').open('a') as f:f.write('% changed\n')
        self.assertFalse(pk.preflight(self.root,'submission')['passed'])
    def test_changed_pdf_rejected(self):
        self.source();r=pk.build(self.root,'main.tex',True)
        self.synthetic_quality_records()
        pk.approve_release(self.root,'SYNTHETIC TEST ATTESTATION',pk.CHECKS)
        with (self.root/r['pdf']).open('ab') as f:f.write(b'\nchanged')
        self.assertFalse(pk.preflight(self.root,'submission')['passed'])
    def test_missing_citation_blocks(self):
        self.source(r'Unresolved citation \cite{doesnotexist}.');pk.build(self.root,'main.tex',True)
        self.assertTrue(any('undefined' in e for e in pk.preflight(self.root,'submission')['errors']))
    def test_packet_and_unread_ingestion(self):
        self.source();r=pk.build(self.root,'main.tex',True);pdf=self.root/r['pdf']
        item=pk.ingest(self.root,pdf,'Synthetic fixture','','style')
        self.assertEqual(item['read_status'],'unread');self.assertFalse(item['visual_inspection'])
        self.assertEqual(item['extraction'],'complete')
        packet=Path(self.tmp.name)/'packet1';manifest=pk.prepare_review(pdf,packet,'development')
        second=pk.prepare_review(pdf,Path(self.tmp.name)/'packet2','development')
        self.assertEqual(manifest['packet_hash'],second['packet_hash'])
        self.assertEqual(set(p.name for p in packet.iterdir()),{'manuscript.pdf','manuscript.txt','rubric.md','instructions.md','review.schema.json','packet.json'})
        self.assertEqual(pk.ingest(self.root,pdf,'Duplicate','','style'),item)
        with self.assertRaises(ValueError):pk.prepare_review(pdf,packet,'development')
    def test_build_requires_permission(self):
        self.source()
        with self.assertRaises(ValueError):pk.build(self.root,'main.tex',False)
    def test_build_through_symlinked_root_uses_canonical_paths(self):
        self.source()
        alias=self.root.parent/'project-alias'
        alias.symlink_to(self.root,target_is_directory=True)
        receipt=pk.build(alias,'main.tex',True)
        self.assertEqual(receipt['main'],'main.tex')
        self.assertEqual(receipt['pdf'],'.paper/build/main.pdf')
        self.assertTrue((self.root/receipt['pdf']).is_file())
        self.assertTrue(all(str(Path(path).resolve()) == path
                            for path in receipt['recorded_inputs']))
    def test_excluded_library_input_is_rejected(self):
        (self.root/'sources/hidden.tex').write_text('Hidden input.')
        self.source(r'\input{sources/hidden.tex}')
        with self.assertRaises(ValueError):pk.build(self.root,'main.tex',True)
    def test_external_recorded_input_change_rejected(self):
        external=Path(self.tmp.name)/'external.tex';external.write_text('External fixed content.')
        self.source('\\input{'+external.as_posix()+'}')
        pk.build(self.root,'main.tex',True)
        external.write_text('Changed external content.')
        self.assertTrue(any('Recorded LaTeX input' in e for e in pk.preflight(self.root,'submission')['errors']))
    def test_quality_records_are_required(self):
        self.source();pk.build(self.root,'main.tex',True)
        result=pk.preflight(self.root,'submission',require_signoff=False)
        self.assertTrue(any('Visual audit' in e for e in result['errors']))
        self.assertTrue(any('Readability review incomplete' in e for e in result['errors']))
        with self.assertRaises(ValueError):pk.approve_release(self.root,'SYNTHETIC TEST',pk.CHECKS)
    def test_quality_change_invalidates_final_signoff(self):
        self.source();pk.build(self.root,'main.tex',True);self.synthetic_quality_records()
        pk.approve_release(self.root,'SYNTHETIC TEST',pk.CHECKS)
        p=self.root/'.paper/readability-review.json';entry=json.loads(p.read_text())
        entry['disposition']+=' Revised synthetic observation.';pk.dump(p,entry)
        self.assertTrue(any('signoff is stale' in e for e in pk.preflight(self.root,'submission')['errors']))
    def test_missing_page_after_signoff_blocks_release(self):
        self.source();pk.build(self.root,'main.tex',True);self.synthetic_quality_records()
        pk.approve_release(self.root,'SYNTHETIC TEST',pk.CHECKS)
        (self.root/'.paper/visual/page-001.png').unlink()
        self.assertFalse(pk.preflight(self.root,'submission')['passed'])
    def test_changed_readability_report_blocks_release(self):
        self.source();pk.build(self.root,'main.tex',True);self.synthetic_quality_records()
        pk.approve_release(self.root,'SYNTHETIC TEST',pk.CHECKS)
        p=self.root/'.paper/readability/test/report.json';r=json.loads(p.read_text())
        r['overall']['automated_readability_index']=0;pk.dump(p,r)
        self.assertTrue(any('report changed since interpretation' in e for e in pk.preflight(self.root,'submission')['errors']))
    def test_blocking_decision_prevents_signoff(self):
        self.source();pk.build(self.root,'main.tex',True)
        state=pk.load_state(self.root);state['decisions']=[{'id':'D1','blocking':True,'status':'open'}]
        pk.dump(self.root/'.paper/state.json',state)
        with self.assertRaises(ValueError):pk.approve_release(self.root,'TEST',pk.CHECKS)


if __name__=='__main__':unittest.main()
