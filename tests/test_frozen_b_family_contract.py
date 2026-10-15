import copy
from pathlib import Path
import tempfile
import unittest

from tests import test_frozen_b_project as fixtures

project = fixtures.project


class FamilyContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.case = fixtures.FrozenProjectTests()
        self.case.paths, self.case.lock = fixtures.fixture(Path(self.directory.name))
        self.lock = self.case.lock
        self.original = self.case.family_inputs()

    def changed_result(self, change):
        rows = project.rows(self.original['results']); change(rows)
        data = project.table(list(rows[0]),rows)
        audit = project.strict_json(self.original['limma_audit'])
        audit['plugin_transport_output_sha256']['results'] = project.identity(data)['sha256']
        return {**self.original,'results':data,'limma_audit':project.canonical(audit)}

    def test_origin_requires_complete_frozen_sources_and_false_authority(self):
        original = project.strict_json(self.original['intake'])
        changes = []
        for field in original:
            changed = copy.deepcopy(original); changed.pop(field); changes.append(changed)
        for field,value in [('scope','UNRELATED'),('scientific_authorization',True),('formal_authorized',True),
                ('G0',True),('metadata_certificate_is_not_full_scientific_permission',False),
                ('original_full_project_byte_verifier_executed',True),('original_full_project_byte_audit_verified',True),
                ('frozen_scientific_code_executed',True),('source_samples',['x']*9),('primary_samples',['x']*8),
                ('independent_unit_ids',['x']*8),('gene_count',4.0),('extra_scientific_authority',True)]:
            changed=copy.deepcopy(original); changed[field]=value; changes.append(changed)
        for name in project.INPUTS:
            for field,value in [('sha256','0'*64),('bytes',0),('bytes',True),('bytes',64*1024**2+1)]:
                changed=copy.deepcopy(original); changed['source_files'][name][field]=value; changes.append(changed)
        for changed in changes:
            with self.subTest(origin=changed),self.assertRaises(ValueError):
                project.family({**self.original,'intake':project.canonical(changed)},self.lock)

    def test_official_audit_requires_full_same_model_source_contract(self):
        original=project.strict_json(self.original['limma_audit'])
        changes=[]
        for field in original:
            changed=copy.deepcopy(original);changed.pop(field);changes.append(changed)
        for field,value in [('scope','UNRELATED'),('protocol_version','4.2.1'),('formal_authorized',True),
                ('scientific_approval_verified',True),('source_qualified',True),('family_frozen',True),
                ('method_warnings',['UNREVIEWED']),('design_receipt_sha256','bad'),('extra_authority',True)]:
            changed=copy.deepcopy(original);changed[field]=value;changes.append(changed)
        for field,value in [('sample_ids',list(reversed(original['design']['sample_ids']))),
                ('independent_unit_ids',['OTHER']*8),('n_case',3),('candidate_family_p_allowed',False),
                ('biological_independence_verified',True),('condition_coding','REVERSED')]:
            changed=copy.deepcopy(original);changed['design'][field]=value;changes.append(changed)
        for changed in changes:
            with self.subTest(audit=changed),self.assertRaises(ValueError):
                project.family({**self.original,'limma_audit':project.canonical(changed)},self.lock)

    def test_estimated_result_requires_exact_producer_schema_and_valid_numbers(self):
        self.assertEqual(list(project.rows(self.original['results'])[0]),project.RESULTS)
        for field,value in [('log2_expression_difference','Inf'),('standard_error','-0.1'),('standard_error','0'),
                ('moderated_df','NaN'),('moderated_df','0'),('ci_lower','999'),('ci_upper','-999'),
                ('moderated_t','NaN'),('average_expression','Inf'),('reason','POSTHOC'),
                ('family_p_status','NOT_ESTIMABLE'),('family_p_reason','POSTHOC'),('G0','TRUE')]:
            def change(rows,field=field,value=value):
                if field=='G0':
                    for row in rows:row[field]=value
                else:rows[0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                project.family(self.changed_result(change),self.lock)
        for field in project.RESULTS:
            def missing(rows,field=field):
                for row in rows:row.pop(field)
            with self.subTest(missing=field),self.assertRaises((ValueError,KeyError)):
                project.family(self.changed_result(missing),self.lock)

    def test_nonestimable_keeps_reason_specific_official_diagnostics(self):
        def diagnosed(rows):
            row=rows[1]
            row.update(reason='OFFICIAL_LIMMA_NONFINITE_OR_ZERO_PRECISION',family_p_reason='OFFICIAL_LIMMA_NONFINITE_OR_ZERO_PRECISION',
                log2_expression_difference='1.25',standard_error='0',ci_lower='1.25',ci_upper='1.25',
                moderated_t='Inf',moderated_df='4')
        raw=self.changed_result(diagnosed)
        output=project.rows(project.family(raw,self.lock)['family.tsv'])[1]
        self.assertEqual(output['raw_p'],'NA')
        for field,value in [('log2_expression_difference','1.25'),('standard_error','0'),('moderated_t','Inf'),('moderated_df','4')]:
            self.assertEqual(output[field],value)
        for field,value in [('log2_expression_difference','1'),('reason','ARBITRARY_FAILURE'),('family_p_reason','OTHER'),('raw_p','0.5')]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                project.family(self.changed_result(lambda rows,field=field,value=value:rows[1].update({field:value})),self.lock)

    def test_complete_rows_and_official_q_are_consumed_without_recomputation(self):
        def official_values(rows):
            rows[0]['q_BH']='0.5';rows[0]['q_BY']='0.75'
        raw=self.changed_result(official_values)
        output=project.rows(project.family(raw,self.lock)['family.tsv'])
        self.assertEqual((output[0]['q_BH'],output[0]['q_BY']),('0.5','0.75'))
        for field,value in [('matrix_row','2'),('gene_id','WRONG'),('analysis_id','WRONG'),('family_id','WRONG'),
                ('contrast_id','WRONG'),('estimand_id','WRONG'),('numerator','control'),('n_case','3'),('n_control','3')]:
            with self.subTest(field=field),self.assertRaises(ValueError):
                project.family(self.changed_result(lambda rows,field=field,value=value:rows[0].update({field:value})),self.lock)
        for model in project.MODELS:
            output=project.family(self.case.family_inputs(model),self.lock)
            self.assertEqual(len(project.rows(output['family.tsv'])),4)


if __name__=='__main__':unittest.main()
