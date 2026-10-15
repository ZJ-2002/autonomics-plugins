import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'research-adapters/frozen-a-legacy-family-gate'
SPEC = importlib.util.spec_from_file_location('frozen_a_legacy_family_gate', FAMILY / 'scripts/gate.py')
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
HELPER_PATH = ROOT / 'research-adapters/frozen-a-family-assembly/scripts/family.py'


def tsv(rows, columns):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, columns, delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


def json_bytes(value):
    return (json.dumps(value, indent=2) + '\n').encode()


class FrozenALegacyFamilyGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.helper = GATE.load_helper(HELPER_PATH)
        self.real_loader = GATE.load_helper
        self.inputs = [self.root / ('input-' + str(index)) for index in range(23)]
        self.outputs = [self.root / name for name in GATE.OUTPUT_NAMES]
        self.payloads = self.toy_payloads()
        for path, data in zip(self.inputs, self.payloads, strict=True):
            path.write_bytes(data)
        self.frozen = [(name, len(self.payloads[index + 9]), self.helper.checksum(self.payloads[index + 9]))
            for index, (name, _, _) in enumerate(GATE.FROZEN)]
        self.helper.SOURCES = [(name, len(self.payloads[index + 13]), self.helper.checksum(self.payloads[index + 13]))
            for index, (name, _, _) in enumerate(self.helper.SOURCES)]
        self.patches = [mock.patch.object(GATE, 'load_helper', return_value=self.helper),
            mock.patch.object(GATE, 'FROZEN', self.frozen),
            mock.patch.object(GATE, 'QUALIFIED_SHA', self.helper.checksum(self.payloads[5]))]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)

    def toy_payloads(self):
        qualified = [dict(GATE.TRAIT, SNP='TOY_VARIANT_' + str(index), chr37='1', pos37=str(index + 10))
            for index in range(39)]
        estimates = [dict(GATE.TRAIT, method=method, nsnp='39', b='0.25', se='0.1', pval='0.02',
            role='EXPLORATORY_OVERLAP_UNRESOLVED', p_primary='NA', p_for_family='1', p_raw_exploratory='0.02')
            for method in GATE.METHODS]
        heterogeneity = [dict(GATE.TRAIT, method=method, Q='1.5', Q_df='37' if method == 'MR Egger' else '38', Q_pval='0.7')
            for method in GATE.METHODS[:2]]
        intercept = [dict(GATE.TRAIT, egger_intercept='0.01', se='0.1', pval='0.8')]
        loo = [dict(GATE.TRAIT, samplesize='NA', SNP=value, b='0.25', se='0.1', p='0.02')
            for value in [row['SNP'] for row in qualified] + ['All']]
        regions = [dict(GATE.TRAIT, method=method, nsnp='39', b='0.25', se='0.1', pval='0.02',
            p_primary='NA', role='REGISTERED_SENSITIVITY_ONLY', sensitivity=region)
            for region in GATE.REGIONS for method in GATE.METHODS]
        payloads = [tsv(estimates, GATE.MR_COLUMNS), tsv(heterogeneity, GATE.HET_COLUMNS),
            tsv(intercept, GATE.INTERCEPT_COLUMNS), tsv(loo, GATE.LOO_COLUMNS),
            tsv(regions, GATE.REGION_COLUMNS), tsv(qualified, list(qualified[0])),
            b'EXPLICIT OPAQUE TOY RDS NOT AN R OBJECT\n',
            b'Scope: FROZEN_V432_A_LEGACY\nseed=432202610; bootstrap_n=1000; overlap=O2; LEGACY_EXPLORATORY; primary_p=NA; family_p=1\n', b'']
        config = dict(status='LOCKED', version='4.3.2', enabled_edge='A_X01_M06', analysis_id='G0_V432_A_X01_M06',
            program_sha256=self.helper.checksum(payloads[5]), overlap_class='O2', primary_p_source='NA',
            exposure_role='LEGACY_EXPLORATORY', ordinary_ivw_parallel='EXPLORATORY_ONLY', seed=432202610, bootstrap_n=1000)
        certificate = dict(status='G0_V432_MINIMUM_COMPLETE', version='4.3.2',
            A=dict(allowed=True, confirmatory_allowed=False, analysis_id=config['analysis_id'], role='LEGACY_EXPLORATORY_O2_PRIMARY_NA'))
        lock = b'package\tversion\nTwoSampleMR\t0.7.11\n'
        helper_source = b'''def primary_p(*args, **kwargs): raise AssertionError("not used in mechanical ledger")
def strict_conjunction(*args): raise AssertionError("not used in mechanical ledger")
def assert_locked_ids(actual, expected):
    if len(actual)!=len(set(actual)) or len(expected)!=len(set(expected)) or set(actual)!=set(expected):
        raise ValueError("Toy ID membership differs")
'''
        methods_source = b'EXPLICIT TOY FROZEN METHODS IDENTITY ONLY\n'
        scientific_sha = self.helper.checksum(methods_source)
        first_four = [self.helper.checksum(value) for value in [payloads[5], json_bytes(config), json_bytes(certificate), lock]]
        proof = dict(scope='FROZEN_V432_A_LEGACY', input_sha256=first_four, scientific_code_sha256=scientific_sha,
            R='4.6.1', TwoSampleMR='0.7.11', scientific_authorization_granted=False, formal_scientific_pass_granted=False)
        payloads.extend([json_bytes(config), json_bytes(certificate), lock, json_bytes(proof)])
        provenance = dict(scope='FROZEN_V432_A_LEGACY', input_sha256=first_four + [self.helper.checksum(payloads[12])],
            adapter_sha256=GATE.ADAPTER_SHA, frozen_scientific_code_sha256=scientific_sha, R='4.6.1', TwoSampleMR='0.7.11',
            method_function_sha256=GATE.IVW_FUNCTION_SHA, package_description=dict(Package='TwoSampleMR', Version='0.7.11'),
            package_description_sha256=GATE.DESCRIPTION_SHA, dependency_lock_sha256=self.helper.checksum(lock),
            seed=432202610, bootstrap_n=1000, n_independent_IV=39, exposure_role='LEGACY_EXPLORATORY',
            certificate_role='LEGACY_EXPLORATORY_O2_PRIMARY_NA', overlap_class='O2', primary_p_source='NA',
            scientific_authorization_granted=False, formal_scientific_pass_granted=False)
        payloads[8] = json_bytes(provenance)
        edges = [dict(edge_id='A_X01_M06' if index == 0 else 'TOY_EDGE_' + str(index),
            family='A_PRIMARY_EDGES' if index < 88 else 'A_EXPANDED_EDGES') for index in range(276)]
        paths = [dict(path_id='TOY_PATH_' + str(index), family='A_PRIMARY_PATHS' if index < 36 else 'A_EXPANDED_PATHS',
            xm_edge_id=edges[0]['edge_id'], my_edge_id=edges[1]['edge_id'], xy_edge_id=edges[2]['edge_id'],
            test='max(p_XM,p_MY)', correction='BY', select_by_pairwise_significance='NO', product_p_can_promote='NO')
            for index in range(288)]
        ledger = []
        for row in edges + paths:
            entry = {name: '' for name in GATE.LEDGER_COLUMNS}
            entry.update(analysis_id=row.get('edge_id', row.get('path_id')), family_id=row['family'],
                status='NOT_ESTIMABLE', p_raw='NA', p_for_adjustment='1', role='LEGACY_EXPLORATORY')
            ledger.append(entry)
        decisions = [dict(edge_id=row['edge_id'], overlap_class='O2' if index == 0 else 'PENDING')
            for index, row in enumerate(edges)]
        locks = [dict(family_id=family, status='LOCKED', n_tests=str(count)) for family, count in self.helper.COUNTS.items()]
        multiplicity = [dict(family_id=family, locked_count=str(count)) for family, count in self.helper.COUNTS.items()]
        rules = dict(planned_counts=dict(self.helper.COUNTS, A_MVP_BRIDGE=11))
        payloads.extend([tsv(edges, list(edges[0])), tsv(paths, list(paths[0])), tsv(ledger, GATE.LEDGER_COLUMNS),
            tsv(decisions, list(decisions[0])), tsv(locks, list(locks[0])), tsv(multiplicity, list(multiplicity[0])),
            json_bytes(rules), helper_source, methods_source, HELPER_PATH.read_bytes()])
        return payloads

    def rewrite_table(self, port, mutate):
        rows = self.helper.table(self.inputs[port].read_bytes())
        mutate(rows)
        self.inputs[port].write_bytes(tsv(rows, list(rows[0])))

    def rewrite_provenance(self, mutate):
        value = json.loads(self.inputs[8].read_bytes())
        mutate(value)
        self.inputs[8].write_bytes(json_bytes(value))

    def refused(self, diagnostic):
        with self.assertRaisesRegex(ValueError, diagnostic):
            GATE.run(self.inputs, self.outputs)
        self.assertFalse(any(path.exists() for path in self.outputs[:3]))

    def test_toy_complete_gate_preserves_564_rows_and_all_false_authority(self):
        GATE.run(self.inputs, self.outputs)
        self.assertEqual(json.loads(self.outputs[0].read_bytes()), GATE.REQUEST)
        projection = self.helper.table(self.outputs[1].read_bytes(), GATE.LEDGER_COLUMNS)
        self.assertEqual(projection, self.helper.table(self.payloads[15], GATE.LEDGER_COLUMNS))
        self.assertEqual(len(projection), 564)
        receipt = json.loads(self.outputs[2].read_bytes())
        self.assertEqual(len(receipt['input_files']), 23)
        self.assertEqual(receipt['unresolved_overlap_entries_preserved'], 275)
        self.assertFalse(receipt['opaque_RDS']['readRDS_performed'])
        self.assertFalse(receipt['scientific_authorization_granted'])
        self.assertEqual(receipt['family_validation']['vector_rows'], 840)

    def test_primary_p_upgrade_is_refused(self):
        self.rewrite_table(0, lambda rows: rows[0].update(p_primary='0.001'))
        self.refused('Primary upgrade forbidden')

    def test_family_placeholder_upgrade_is_refused(self):
        self.rewrite_table(0, lambda rows: rows[0].update(p_for_family='0.001'))
        self.refused('Primary upgrade forbidden')

    def test_authority_upgrade_is_refused(self):
        self.rewrite_provenance(lambda value: value.update(scientific_authorization_granted=True))
        self.refused('Scientific authority upgrade forbidden')

    def test_stale_adapter_is_refused(self):
        self.rewrite_provenance(lambda value: value.update(adapter_sha256='1' * 64))
        self.refused('Stale MR adapter SHA forbidden')

    def test_missing_loo_variant_is_refused(self):
        self.rewrite_table(3, lambda rows: rows.pop())
        self.refused('Complete LOO membership')

    def test_qualified_source_change_is_refused(self):
        self.inputs[5].write_bytes(self.inputs[5].read_bytes() + b'\n')
        self.refused('Frozen qualified input SHA differs')

    def test_frozen_registry_change_is_refused(self):
        data = bytearray(self.inputs[13].read_bytes())
        data[-2] = ord('X')
        self.inputs[13].write_bytes(data)
        self.refused('Frozen source identity differs')

    def test_frozen_config_change_is_refused(self):
        data = self.inputs[9].read_bytes().replace(b'LOCKED', b'BROKEN')
        self.inputs[9].write_bytes(data)
        self.refused('Frozen contract input SHA differs')

    def test_synthetic_source_scope_is_refused(self):
        self.rewrite_provenance(lambda value: value.update(scope='SYNTHETIC_METHOD_TEST'))
        self.refused('Exact frozen legacy MR input lineage')

    def test_probability_and_nonfinite_estimates_are_refused(self):
        for value in ('NaN', 'Inf', '-0.01', '1.1'):
            with self.subTest(value=value):
                self.inputs[0].write_bytes(self.payloads[0])
                self.rewrite_table(0, lambda rows: rows[0].update(pval=value))
                self.refused('Finite')

    def test_duplicate_methods_and_wrong_trait_are_refused(self):
        self.rewrite_table(0, lambda rows: rows[1].update(method=rows[0]['method']))
        self.refused('Exactly three original')
        self.inputs[0].write_bytes(self.payloads[0])
        self.rewrite_table(0, lambda rows: rows[0].update(exposure='OTHER_TRAIT'))
        self.refused('Frozen X01 to M06 trait identity')

    def test_missing_regional_sensitivity_is_refused(self):
        self.rewrite_table(4, lambda rows: rows.pop())
        self.refused('Complete three-region')

    def test_wrong_regional_variant_count_is_refused(self):
        self.rewrite_table(4, lambda rows: rows[0].update(nsnp='38'))
        self.refused('Registered region variant membership differs')

    def test_changed_provenance_input_hash_and_seed_are_refused(self):
        self.rewrite_provenance(lambda value: value['input_sha256'].__setitem__(0, 'a' * 64))
        self.refused('Exact frozen legacy MR input lineage')
        self.inputs[8].write_bytes(self.payloads[8])
        self.rewrite_provenance(lambda value: value.update(seed=True))
        self.refused('Frozen MR scalar identity differs')

    def test_empty_rds_and_missing_log_are_refused(self):
        self.inputs[6].write_bytes(b'')
        self.refused('Opaque RDS artifact must not be empty')
        self.inputs[6].write_bytes(self.payloads[6])
        self.inputs[7].write_bytes(b'OTHER LOG\n')
        self.refused('Original exploratory log declaration missing')

    def test_symlink_and_hardlink_inputs_are_refused(self):
        self.inputs[0].unlink()
        self.inputs[0].symlink_to(self.inputs[1])
        self.refused('Unaliased regular input required')
        self.inputs[0].unlink()
        os.link(self.inputs[1], self.inputs[0])
        self.refused('Input aliases')

    def test_existing_and_aliased_outputs_are_preserved(self):
        self.outputs[0].write_bytes(b'FOREIGN\n')
        with self.assertRaisesRegex(ValueError, 'Existing or foreign output'):
            GATE.run(self.inputs, self.outputs)
        self.assertEqual(self.outputs[0].read_bytes(), b'FOREIGN\n')

    def test_duplicate_and_input_aliased_outputs_are_refused(self):
        duplicate = [self.outputs[0], self.outputs[0], *self.outputs[2:]]
        with self.assertRaisesRegex(ValueError, 'Four distinct output ports'):
            GATE.run(self.inputs, duplicate)
        aliases = [self.inputs[0], *self.outputs[1:]]
        before = self.inputs[0].read_bytes()
        with self.assertRaisesRegex(ValueError, 'Output aliases an input'):
            GATE.run(self.inputs, aliases)
        self.assertEqual(self.inputs[0].read_bytes(), before)

    def test_foreign_replacement_during_publication_is_preserved(self):
        link = os.link
        def replace(source, destination, *args, **kwargs):
            link(source, destination, *args, **kwargs)
            if destination == self.outputs[0]:
                destination.write_bytes(b'FOREIGN MODIFIED INODE\n')
        with mock.patch.object(self.helper.os, 'link', side_effect=replace):
            with self.assertRaisesRegex(ValueError, 'Published output replaced'):
                GATE.run(self.inputs, self.outputs)
        self.assertEqual(self.outputs[0].read_bytes(), b'FOREIGN MODIFIED INODE\n')
        self.assertFalse(any(path.exists() for path in self.outputs[1:]))

    def test_inputs_changed_during_publication_refuse_and_rollback(self):
        link = os.link
        def change(source, destination, *args, **kwargs):
            link(source, destination, *args, **kwargs)
            if destination == self.outputs[3]:
                self.inputs[7].write_bytes(self.inputs[7].read_bytes() + b'CHANGED\n')
        with mock.patch.object(self.helper.os, 'link', side_effect=change):
            self.refused('Gate inputs changed')
        self.assertFalse(any(path.exists() for path in self.outputs))

    def test_main_failure_publishes_only_owned_diagnostic(self):
        self.rewrite_table(0, lambda rows: rows[0].update(p_primary='0.02'))
        environment = {**{'AUTONOMICS_INPUT' + str(index): str(path) for index, path in enumerate(self.inputs)},
            **{'AUTONOMICS_OUTPUT' + str(index): str(path) for index, path in enumerate(self.outputs)}}
        with mock.patch.dict(os.environ, environment), mock.patch.object(sys_argv(), 'argv', ['gate.py']):
            self.assertEqual(GATE.main(), 2)
        self.assertFalse(any(path.exists() for path in self.outputs[:3]))
        self.assertIn('Primary upgrade forbidden', self.outputs[3].read_text())

    def test_main_failure_preserves_foreign_diagnostic(self):
        self.outputs[3].write_bytes(b'FOREIGN LOG\n')
        environment = {**{'AUTONOMICS_INPUT' + str(index): str(path) for index, path in enumerate(self.inputs)},
            **{'AUTONOMICS_OUTPUT' + str(index): str(path) for index, path in enumerate(self.outputs)}}
        with mock.patch.dict(os.environ, environment), mock.patch.object(sys_argv(), 'argv', ['gate.py']):
            self.assertEqual(GATE.main(), 2)
        self.assertEqual(self.outputs[3].read_bytes(), b'FOREIGN LOG\n')
        self.assertFalse(any(path.exists() for path in self.outputs[:3]))

    def test_manifest_is_fixed_23_to_4_and_no_parameters(self):
        data = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        node = data['nodes'][0]
        self.assertEqual(len(node['ports']['inputs']), 23)
        self.assertEqual([row['path'] for row in node['ports']['outputs']], GATE.OUTPUT_NAMES)
        self.assertNotIn('params', node)
        self.assertEqual(node['resources']['pull_policy'], 'never')
        self.assertEqual(node['stage_in_mode'], 'copy')

    def test_production_helper_pin_is_real_and_bad_helper_is_never_imported(self):
        self.assertEqual(hashlib.sha256(HELPER_PATH.read_bytes()).hexdigest(), GATE.HELPER_SHA)
        self.assertEqual(HELPER_PATH.stat().st_size, GATE.HELPER_BYTES)
        bad = self.root / 'bad-helper.py'
        bad.write_bytes(b'raise AssertionError("must never execute")\n')
        with self.assertRaisesRegex(ValueError, 'helper size differs'):
            self.real_loader(bad)

    def test_same_size_bad_helper_sha_is_rejected_before_execution(self):
        bad = self.root / 'same-size-bad-helper.py'
        source = b'raise AssertionError("must never execute")\n'
        bad.write_bytes(source + b' ' * (GATE.HELPER_BYTES - len(source)))
        with self.assertRaisesRegex(ValueError, 'Frozen family helper SHA differs'):
            self.real_loader(bad)

    def foreign_helper(self, marker):
        prefix = ('from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("UNAPPROVED")\n'
            'def primary_p(*args, **kwargs): pass\n'
            'def strict_conjunction(*args): pass\n'
            'def assert_locked_ids(*args): pass\n').encode()
        self.assertLess(len(prefix), len(self.payloads[20]))
        return prefix + b' ' * (len(self.payloads[20]) - len(prefix))

    def test_gate_indirect_helper_reopen_refuses_foreign_code_before_execution(self):
        marker = self.root / 'unapproved-code-executed'
        foreign = self.foreign_helper(marker)
        original = self.helper.helpers
        observed = []
        def replace_before_load(path):
            self.assertEqual(path, self.inputs[20])
            self.inputs[20].write_bytes(foreign)
            observed.append(path)
            return original(path)
        with mock.patch.object(self.helper, 'helpers', side_effect=replace_before_load):
            self.refused('Frozen original helper source identity differs')
        self.assertEqual(observed, [self.inputs[20]])
        self.assertFalse(marker.exists())

    def test_gate_indirect_helper_executes_checked_buffer_at_compile_window(self):
        marker = self.root / 'unapproved-code-at-compile'
        foreign = self.foreign_helper(marker)
        observed = []
        original = compile
        def replace_at_compile(payload, filename, mode, **keywords):
            self.assertEqual(payload, self.payloads[20])
            self.assertEqual(filename, str(self.inputs[20]))
            self.inputs[20].write_bytes(foreign)
            observed.append(filename)
            return original(payload, filename, mode, **keywords)
        with mock.patch.object(self.helper, 'compile', side_effect=replace_at_compile, create=True):
            self.refused('Gate inputs changed during execution')
        self.assertEqual(observed, [str(self.inputs[20])])
        self.assertFalse(marker.exists())


def sys_argv():
    import sys
    return sys


if __name__ == '__main__':
    unittest.main()
