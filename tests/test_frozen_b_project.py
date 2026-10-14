import copy
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from tools import build_frozen_b_project_dag as graph

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/frozen-b-project'
spec = importlib.util.spec_from_file_location('frozen_project', PLUGIN / 'scripts/project.py')
project = importlib.util.module_from_spec(spec)
spec.loader.exec_module(project)


def fixture(root):
    """Self-contained engineering inputs; no real sample/assay payload imports."""
    lock = copy.deepcopy(graph.LOCK)
    lock.update(gene_count=4, source_samples=9, primary_samples=8, case_n=4, control_n=4, residual_df=4)
    raw = {}
    raw['source_metadata'] = b'SYNTHETIC source metadata\n'
    samples = []
    for i in range(8):
        row = dict.fromkeys(project.SAMPLES, 'SYNTHETIC')
        row.update(sample_id='SYN_A' + str(i), independent_unit_id='SYN_A' + str(i), group='case' if i < 4 else 'control',
                   include='YES', age=str([25, 31, 29, 43, 28, 37, 35, 46][i]), sex='F' if i % 2 == 0 else 'M',
                   source_metadata_sha256=project.identity(raw['source_metadata'])['sha256'])
        samples.append(row)
    raw['samples'] = project.table(project.SAMPLES, samples)
    features = []
    for i in range(4):
        row = dict.fromkeys(project.FEATURES, 'SYNTHETIC')
        row.update(feature_id='SYN_G' + str(i), source_probe_id='SYN_G' + str(i) + '_at', included='YES',
                   contrast_id=lock['contrast_id'], family_id='B_TRANSCRIPTOME', role='LEGACY_EXPLORATORY',
                   measurement_filter='ALL_SOURCE_ROWS_UNIQUE_ENTREZ_AND_FINITE;NO_EFFECT_OR_PROGRAM_SELECTION')
        features.append(row)
    raw['features'] = project.table(project.FEATURES, features)
    matrix = project.table(['ID_REF', *[r['sample_id'] for r in samples], 'SYN_EXCLUDED'],
        [{'ID_REF': r['source_probe_id'], **{s['sample_id']: str(5 + i + j / 20) for j, s in enumerate(samples)},
          'SYN_EXCLUDED': '6'} for i, r in enumerate(features)])
    raw['matrix'] = gzip.compress(b'!series_matrix_table_begin\n' + matrix + b'!series_matrix_table_end\n', mtime=0)
    raw['scope'] = project.canonical(dict(N_primary=8, case_n=4, control_n=4))
    raw['design_certificate'] = project.canonical(dict(matrix_genes=4, source_samples=9, primary_samples=8, case_n=4, control_n=4,
        designs=dict(primary=dict(columns=['(Intercept)', 'groupcase', 'age', 'sexM'], rank=4, residual_df=4, identifiable=True))))
    raw['scope_decision'] = project.canonical(dict(investigator_scientific_signature=None))
    raw['scientific_code'] = b'# SYNTHETIC frozen scientific code identity\n'
    raw['scientific_rules'] = b'{"scope":"SYNTHETIC"}'
    raw['byte_verifier'] = b'# SYNTHETIC original verifier identity\n'
    raw['family_lock'] = b'SYNTHETIC family lock\n'
    raw['restore_acceptance'] = b'{"scope":"SYNTHETIC"}'
    raw['g0_certificate'] = project.canonical(dict(status='G0_V432_MINIMUM_COMPLETE',
        B=dict(allowed=True, role='LEGACY_EXPLORATORY_FULL_FEATURE_DISEASE_ASSOCIATION', independent_validation_allowed=False,
               config_file=lock['files']['config']['relative_path']),
        investigator_scientific_signature=None, all_project_scientific_gates_passed=False, full_denominators=dict(B_TRANSCRIPTOME=4),
        family_lock_sha256=project.identity(raw['family_lock'])['sha256'], restore_evidence_sha256=project.identity(raw['restore_acceptance'])['sha256'],
        scientific_rules_sha256=project.identity(raw['scientific_rules'])['sha256']))
    raw['software_lock'] = project.table(['component', 'version_or_commit', 'status'],
        [dict(component='limma_edgeR_or_DESeq2', version_or_commit='limma3.68.5;R4.6.1;statmod1.5.2', status='LOCKED_V432_MINIMUM_SCOPE')])
    raw['r_dependencies'] = project.table(['package', 'version'],
        [dict(package=p, version=v) for p, v in lock['software_lock'].items() if p not in ['R', 'stats']])
    raw['r_session'] = b'R version 4.6.1 (SYNTHETIC declared session)\n'
    raw['manifest'] = project.canonical([dict(file=lock['files'][n]['relative_path'], sha256=project.identity(raw[n])['sha256'])
        for n in ['matrix', 'source_metadata', 'samples', 'features', 'scope']])
    cfg = dict(status='LOCKED', version='4.3.2', module='B', family_ids=['B_TRANSCRIPTOME'], resource_ids=[],
        contrast_id=lock['contrast_id'], estimand_id='E_B_DIS', model_formula='~group+age+sex', model_df=4,
        matrix_type='GENE_LEVEL_MICROARRAY_RMA_LOG2', normalization='SOURCE_RMA_LOG2_NOT_RENORMALIZED_NO_RAW_COUNT_OR_GENE_LENGTH_MODEL',
        transcriptome_method='limma3.68.5 lmFit+eBayes(trend=TRUE,robust=TRUE)', followup_exposure_at_lock='LEGACY_EXPLORATORY',
        predefined_program_panel_enabled=False, correction='BH', sensitivity_correction='BY', q=.05, raw_missing_p='NA', adjustment_missing_p=1,
        matrix_file=lock['files']['matrix']['relative_path'], software_lock_file=lock['files']['software_lock']['relative_path'])
    for name, prefix in [('manifest', 'input_manifest'), ('samples', 'sample_map'), ('features', 'feature_definition'),
                         ('scope', 'discovery_scope'), ('scientific_code', 'scientific_code'), ('scientific_rules', 'scientific_rules')]:
        cfg[prefix + '_sha256'] = project.identity(raw[name])['sha256']
        cfg[prefix + '_file'] = lock['files'][name]['relative_path']
    raw['config'] = project.canonical(cfg)
    raw['runtime_manifest'] = project.canonical(dict(files=[dict(path=lock['files'][n]['relative_path'],
        sha256=project.identity(data)['sha256'], size_bytes=len(data)) for n, data in raw.items()]))
    paths = {}
    for n, data in raw.items():
        path = root / (n + '.input'); path.write_bytes(data); paths[n] = path
        lock['files'][n]['sha256'] = project.identity(data)['sha256']
    return paths, lock


class FrozenProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths, self.lock = fixture(Path(self.temp.name))

    def test_intake_preserves_raw_decimals_all_rows_and_locked_labels(self):
        out = project.intake(self.paths, self.lock)
        self.assertEqual(set(out), set(project.OUTPUTS))
        expr = project.rows(out['expression.tsv'])
        self.assertEqual(len(expr), 4)
        self.assertEqual(expr[2]['SYN_A3'], '7.15')
        self.assertEqual(out['samples.tsv'], self.paths['samples'].read_bytes())
        audit = project.strict_json(out['intake.json'])
        self.assertEqual(len(audit['source_samples']), 9)
        self.assertEqual(len(audit['primary_samples']), 8)
        self.assertEqual(audit['family_role'], 'LEGACY_EXPLORATORY_PRIMARY_MODEL')
        self.assertFalse(audit['original_full_project_byte_verifier_executed'])
        self.assertFalse(audit['G0'])
        cfg = project.strict_json(out['config.json'])
        self.assertEqual(cfg['input_sha256']['genes'], project.identity(out['genes.tsv'])['sha256'])
        self.assertEqual(cfg['design']['covariates'][1]['levels'], ['F', 'M'])

    def test_stale_actual_bytes_reject_before_source_matrix_decompression(self):
        self.paths['matrix'].write_bytes(b'not a gzip; different bytes')
        with self.assertRaisesRegex(ValueError, 'frozen source bytes differ'):
            project.intake(self.paths, self.lock)

    def test_same_hash_bound_old_registry_scope_is_still_rejected(self):
        cfg = project.strict_json(self.paths['config'].read_bytes())
        cfg['resource_ids'] = ['OLD_ZIP_RESOURCE']
        raw = project.canonical(cfg)
        self.paths['config'].write_bytes(raw)
        self.lock['files']['config']['sha256'] = project.identity(raw)['sha256']
        with self.assertRaisesRegex(ValueError, 'old ZIP registry cannot substitute'):
            project.intake(self.paths, self.lock)

    def family_inputs(self):
        out = project.intake(self.paths, self.lock)
        audit = project.strict_json(out['intake.json'])
        genes = project.rows(out['genes.tsv'])
        results = []
        for g, p in zip(genes, ['0.01', 'NA', '0.04', '0.03'], strict=True):
            results.append({**g, 'status': 'NOT_ESTIMABLE' if p == 'NA' else 'ESTIMATED', 'raw_p': p, 'family_p': p})
        result_raw = project.table(list(results[0]), results)
        limma = dict(stage='LIMMA', method_executed=True, formal_authorized=False,
            input_sha256=audit['input_sha256'], config_sha256=audit['config_sha256'], software_lock=self.lock['software_lock'],
            plugin_transport_output_sha256=dict(results=project.identity(result_raw)['sha256'], rds='a' * 64))
        return dict(results=result_raw, genes=out['genes.tsv'], intake=out['intake.json'], limma_audit=project.canonical(limma))

    def test_complete_bh_by_manual_expected_values_include_na_as_one(self):
        result = project.family(self.family_inputs(), self.lock)
        completed = project.rows(result['family.tsv'])
        for row, expected in zip(completed, [.04, 1., 4 / 75, 4 / 75], strict=True):
            self.assertAlmostEqual(float(row['q_BH']), expected)
            self.assertAlmostEqual(float(row['q_BY']), min(1., expected * 25 / 12))
            self.assertEqual(row['role'], 'LEGACY_EXPLORATORY_PRIMARY_MODEL')
        self.assertEqual(completed[1]['raw_p'], 'NA')
        self.assertEqual(len(completed), 4)

    def test_family_refuses_output_mutation_missing_gene_and_conditional_role(self):
        original = self.family_inputs()
        bad = {**original, 'results': original['results'].replace(b'0.01', b'0.02')}
        with self.assertRaisesRegex(ValueError, 'actual limma output hash differs'):
            project.family(bad, self.lock)
        audit = project.strict_json(original['intake']); audit['family_role'] = 'CONDITIONAL_EXPLORATORY'
        with self.assertRaisesRegex(ValueError, 'old conditional roles forbidden'):
            project.family({**original, 'intake': project.canonical(audit)}, self.lock)
        gene_rows = project.rows(original['genes'])[:-1]
        with self.assertRaisesRegex(ValueError, 'same actual intake'):
            project.family({**original, 'genes': project.table(project.GENES, gene_rows)}, self.lock)

    def test_generated_tui_graph_binds_all_inputs_and_actual_design_edge(self):
        built = graph.build('vfs://study_v432')
        self.assertTrue(built['dry_run'])
        self.assertEqual(built['script'].count('node('), 23)
        self.assertEqual(built['script'].count('edge('), 34)
        self.assertIn('edge("frozen_b_design", 0, "frozen_b_limma", 5);', built['script'])
        self.assertIn('edge("frozen_b_intake", 5, "frozen_b_family", 2);', built['script'])
        self.assertIn('hash_content: true', built['script'])
        for value in ['/host/study', 'vfs://study/../raw', 'vfs://study//raw']:
            with self.assertRaises(ValueError):
                graph.build(value)

    def test_inlined_entry_closure_and_project_lock_are_exact(self):
        prefix = (PLUGIN / 'scripts/project_lock.py').read_text()
        component = (PLUGIN / 'scripts/project.py').read_text()
        namespace = {}
        exec(prefix, namespace)
        self.assertEqual(namespace['PROJECT_LOCK'], graph.LOCK)
        self.assertEqual(graph.LOCK['gene_count'], 23786)
        self.assertEqual([graph.LOCK[k] for k in ['primary_samples', 'case_n', 'control_n', 'residual_df']], [22, 17, 5, 18])
        self.assertEqual(graph.LOCK['files']['scientific_code']['sha256'],
                         'f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd')
        for filename in ['run-intake.py', 'run-family.py']:
            assembled = (PLUGIN / 'scripts' / filename).read_text()
            self.assertTrue(assembled.startswith(prefix + '\n' + component + '\n'))


if __name__ == '__main__':
    unittest.main()
