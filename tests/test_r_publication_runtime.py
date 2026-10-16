import copy
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import subprocess
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('r_publication_runtime_under_test', ROOT / 'tools/prove_r_publication_runtime.py')
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


def summary(label):
    item = TOOL.FAMILIES[label]
    records = []
    for case in TOOL.CASES:
        mode = 'normal' if case in TOOL.CASES[:2] else case.removeprefix('fixed-')
        success = mode in ('normal', 'foreign-stage-child')
        diagnostic = None if success else ('output changed before publication completed' if mode == 'last-link-rewrites-first'
            else 'staged output changed before publication' if mode == 'staged-before-link'
            else 'published output identity or contents changed')
        ports = 5 if success else (0 if mode == 'staged-before-link' else 1)
        records.append(dict(case=case, mode=mode, returned_success=success, diagnostic=diagnostic,
            actual_link_calls=5 if success or mode == 'last-link-rewrites-first' else 1,
            injected=mode != 'normal', same_inode=None if success else True,
            complete_entry_sys_source_executed=True, full_fit_before_publication=True,
            no_scientific_authorization=True, all_foreign_paths_preserved=mode != 'normal',
            foreign_paths=[] if mode == 'normal' else ['/proof/' + label + '/' + case + '/foreign.txt'],
            products=[dict(port=port, name=item['outputs'][port], bytes=4, sha256='a' * 64) for port in range(ports)],
            actual_present_ports=ports))
    comparisons = []
    for port, name in enumerate(item['outputs']):
        record = dict(port=port, name=name, original=dict(bytes=4, sha256='a' * 64), fixed=dict(bytes=4, sha256='a' * 64))
        if label == 'deseq2' and port == 3:
            record['fixed']['sha256'] = 'b' * 64
            record.update(complete_object_equal=True, check_environment=False, tolerance=0, compressed_bytes_equal=False)
        elif label == 'deseq2' and port == 4:
            record['fixed']['sha256'] = 'c' * 64
            record.update(complete_bytes_equal=False, single_exact_dataset_md5_field_exception=True,
                all_other_fields_exact=True, dataset_rds_md5=dict(original='a' * 32, fixed='b' * 32))
        else:
            record['complete_bytes_equal'] = True
        comparisons.append(record)
    for record, version in zip(records[:2], ('original', 'fixed'), strict=True):
        for product, comparison in zip(record['products'], comparisons, strict=True):
            product.update(comparison[version])
    return dict(schema='TWO_R_PUBLICATION_FULL_ENTRY_RUNTIME_V1', family=label, actual_cases=7,
        genes=200, samples=12, per_entry_seed=432202610, source_sha256=dict(original=item['original'], fixed=item['fixed']),
        scientific_body_AST_identical=True, official_package_entries_executed=True,
        R_version='4.5.3', packages={**item['packages'], 'jsonlite': '2.0.0'},
        actual_DAG_executed=False, full_manifest_resource_certified=False, production_changed=False,
        scientific_authorization_granted=False, g0_granted=False, records=records,
        complete_normal_port_comparisons=comparisons,
        DESeq2_scope='MEAN_DISPERSION_NONE_SHRINKAGE_ONLY_NOT_APEGLM_OR_ALL_FIT_BRANCHES' if label == 'deseq2' else None,
        parameters=dict(AUTONOMICS_DESEQ2_LFC_SHRINK='none', AUTONOMICS_DESEQ2_FIT_TYPE='mean'))


class RPublicationRuntimeTests(unittest.TestCase):
    def rejected(self, value, label='deseq2'):
        with self.assertRaises((ValueError, RuntimeError, AssertionError)):
            TOOL.validate_summary(value, label)

    def test_historical_source_pins_are_preserved_and_refuse_new_method_policy(self):
        # Never retarget a frozen AST-equality proof to a new method policy.
        with self.assertRaisesRegex(ValueError,'Exact reviewed R scripts'):
            TOOL.sources()
        pins={TOOL.INNER:TOOL.INNER_SHA,**TOOL.HELPERS}
        for item in TOOL.FAMILIES.values():
            pins[item['manifest']]=item['manifest_sha'];pins[item['script']]=item['fixed']
            raw=subprocess.check_output(['git','-C',str(ROOT),'show',
                '33fe0102567df90c3c5273fb5c721bff02a5d26f:'+item['manifest']])
            self.assertEqual(tomllib.loads(raw.decode())['image']['reference'],item['image'])
        self.assertEqual(len(pins),8)
        for name,expected in pins.items():
            raw=subprocess.check_output(['git','-C',str(ROOT),'show','33fe0102567df90c3c5273fb5c721bff02a5d26f:'+name])
            self.assertEqual(hashlib.sha256(raw).hexdigest(),expected)

    def test_inner_executes_full_sys_source_and_preserves_scientific_ast(self):
        source = (ROOT / TOOL.INNER).read_text()
        self.assertIn('sys.source(script, envir=scope, keep.source=FALSE)', source)
        self.assertIn('stopifnot(identical(old_body, new_body))', source)
        self.assertIn('all.equal(readRDS(old), readRDS(current), check.environment=FALSE, tolerance=0)', source)
        self.assertNotIn('install.packages(', source)
        self.assertNotIn('BiocManager::install', source)
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(), TOOL.INNER_SHA)

    def test_inventory_is_exact_two_normal_and_five_faults(self):
        self.assertEqual(len(TOOL.CASES), 7)
        self.assertEqual(len(set(TOOL.CASES)), 7)
        self.assertEqual(TOOL.CASES[:2], ('original-normal', 'fixed-normal'))
        self.assertEqual(len(TOOL.FAULTS), 5)
        self.assertTrue(all(len(item['outputs']) == 5 for item in TOOL.FAMILIES.values()))

    def test_container_command_is_bounded_offline_readonly_and_uses_r_entry(self):
        for label in TOOL.FAMILIES:
            command = TOOL.container_command(['/toy/shim', '--cgroup-manager=cgroupfs'], Path('/toy/source'), Path('/toy/proof'), label)
            for expected in ('--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1g', '--userns=keep-id', '--entrypoint=/opt/autonomics/Rscript-vanilla'):
                self.assertIn(expected, command)
            self.assertIn('/toy/source:/source:ro', command)
            self.assertIn('/toy/proof:/proof:rw', command)
            self.assertIn(TOOL.FAMILIES[label]['image'], command)
            self.assertIn('/source/fixed/' + TOOL.INNER, command)
            self.assertNotIn('--detach', command)
            self.assertTrue(all(name + '=1' in command for name in TOOL.inherited.THREAD_VARIABLES))

    def test_complete_deseq2_summary_accepts_disclosed_rds_file_difference(self):
        packet = summary('deseq2')
        self.assertIs(TOOL.validate_summary(packet, 'deseq2'), packet)
        self.assertFalse(packet['complete_normal_port_comparisons'][3]['compressed_bytes_equal'])

    def test_complete_limma_summary_accepts_all_five_byte_comparisons(self):
        packet = summary('limma')
        self.assertIs(TOOL.validate_summary(packet, 'limma'), packet)

    def test_missing_duplicate_or_reordered_full_entries_are_rejected(self):
        for operation in ('missing', 'duplicate', 'reordered'):
            with self.subTest(operation=operation):
                packet = summary('deseq2')
                if operation == 'missing':
                    packet['records'].pop()
                elif operation == 'duplicate':
                    packet['records'][-1] = copy.deepcopy(packet['records'][0])
                else:
                    packet['records'][0], packet['records'][1] = packet['records'][1], packet['records'][0]
                self.rejected(packet)

    def test_boolean_counts_wrong_case_or_missing_fit_cannot_pass(self):
        for mutate in (lambda packet: packet.update(actual_cases=True),
                       lambda packet: packet['records'][0].update(actual_link_calls=True),
                       lambda packet: packet['records'][0].update(full_fit_before_publication=False),
                       lambda packet: packet['records'][0].update(complete_entry_sys_source_executed=False),
                       lambda packet: packet['records'][2].update(mode='normal')):
            packet = summary('deseq2')
            mutate(packet)
            self.rejected(packet)

    def test_oom_permission_or_arbitrary_error_is_not_publication_refusal(self):
        for diagnostic in ('OOM 137', 'Permission denied', '', None, 'unexpected package failure'):
            with self.subTest(diagnostic=diagnostic):
                packet = summary('deseq2')
                packet['records'][2]['diagnostic'] = diagnostic
                self.rejected(packet)

    def test_deleted_foreign_and_unreached_hook_are_rejected(self):
        for changes in ({'all_foreign_paths_preserved': False}, {'injected': False}, {'same_inode': False}, {'foreign_paths': []}):
            packet = summary('deseq2')
            packet['records'][2].update(changes)
            self.rejected(packet)

    def test_missing_port_and_disclosed_rds_environment_cannot_be_hidden(self):
        for mutate in (lambda packet: packet['complete_normal_port_comparisons'].pop(),
                       lambda packet: packet['records'][0]['products'].pop(),
                       lambda packet: packet['complete_normal_port_comparisons'][3].update(check_environment=True),
                       lambda packet: packet['complete_normal_port_comparisons'][3].update(complete_object_equal=False),
                       lambda packet: packet['complete_normal_port_comparisons'][4].update(all_other_fields_exact=False)):
            packet = summary('deseq2')
            mutate(packet)
            self.rejected(packet)

    def test_rds_tolerance_must_be_explicit_numeric_zero(self):
        for tolerance in (True, False, None, '0', 1e-12, 1e-8):
            with self.subTest(tolerance=tolerance):
                packet = summary('deseq2')
                packet['complete_normal_port_comparisons'][3]['tolerance'] = tolerance
                self.rejected(packet)
        packet = summary('deseq2')
        del packet['complete_normal_port_comparisons'][3]['tolerance']
        self.rejected(packet)

    def test_only_exact_dataset_md5_field_can_differ(self):
        original = dict(outputs=dict(dataset=dict(path='dataset.rds', md5='a' * 32), results=dict(md5='c' * 32)), dimensions=dict(genes=200, samples=12))
        fixed = copy.deepcopy(original)
        fixed['outputs']['dataset']['md5'] = 'b' * 32
        self.assertTrue(TOOL.validate_deseq_reports(original, fixed, 'a' * 32, 'b' * 32))
        self.assertEqual(original['outputs']['dataset']['md5'], 'a' * 32)
        for mutate in (lambda report: report['outputs']['results'].update(md5='d' * 32),
                       lambda report: report['dimensions'].update(genes=201),
                       lambda report: report['outputs']['dataset'].update(path='other.rds'),
                       lambda report: report.update(extra='not allowed'),
                       lambda report: report['dimensions'].update(samples=True)):
            wrong = copy.deepcopy(fixed)
            mutate(wrong)
            with self.assertRaisesRegex((ValueError, RuntimeError, AssertionError), 'Only the exact'):
                TOOL.validate_deseq_reports(original, wrong, 'a' * 32, 'b' * 32)

    def test_each_report_md5_must_match_its_own_complete_rds_checksum(self):
        original = dict(outputs=dict(dataset=dict(path='dataset.rds', md5='a' * 32)))
        fixed = dict(outputs=dict(dataset=dict(path='dataset.rds', md5='b' * 32)))
        for old_md5, new_md5 in (('b' * 32, 'b' * 32), ('a' * 32, 'a' * 32), ('a' * 31, 'b' * 32), ('a' * 32, None)):
            with self.assertRaisesRegex((ValueError, RuntimeError, AssertionError), 'Each exact'):
                TOOL.validate_deseq_reports(original, fixed, old_md5, new_md5)

    def test_version_source_scope_and_false_authority_changes_are_rejected(self):
        for mutate in (lambda packet: packet['source_sha256'].update(fixed='b' * 64),
                       lambda packet: packet.update(R_version='4.6.1'),
                       lambda packet: packet['packages'].update(DESeq2='unknown'),
                       lambda packet: packet.update(scientific_body_AST_identical=False),
                       lambda packet: packet.update(actual_DAG_executed=True),
                       lambda packet: packet.update(g0_granted=True),
                       lambda packet: packet['parameters'].update(AUTONOMICS_DESEQ2_LFC_SHRINK='apeglm')):
            packet = summary('deseq2')
            mutate(packet)
            self.rejected(packet)

    def test_actual_small_file_and_foreign_evidence_are_checked(self):
        packet = summary('limma')
        with tempfile.TemporaryDirectory(prefix='r-runtime-contract-') as temporary:
            directory = Path(temporary)
            for record in packet['records']:
                case = directory / record['case']
                case.mkdir()
                for product in record['products']:
                    path = case / product['name']
                    path.write_bytes(b'TOY\n')
                    product.update(bytes=4, sha256=hashlib.sha256(b'TOY\n').hexdigest())
                for foreign in record['foreign_paths']:
                    relative = Path(foreign).relative_to('/proof/limma')
                    (directory / relative).write_bytes(b'EXPLICIT FOREIGN NONSCIENTIFIC BYTES\n')
            for product in packet['complete_normal_port_comparisons']:
                product['original'] = dict(bytes=4, sha256=hashlib.sha256(b'TOY\n').hexdigest())
                product['fixed'] = dict(product['original'])
            self.assertIs(TOOL.validate_summary(packet, 'limma', directory), packet)
            (directory / 'fixed-normal' / 'results.tsv').write_bytes(b'TAMPERED\n')
            with self.assertRaisesRegex((ValueError, RuntimeError, AssertionError), 'output differs|output was changed'):
                TOOL.validate_summary(packet, 'limma', directory)


if __name__ == '__main__':
    unittest.main()
