import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'research-adapters/frozen-a-family-assembly/scripts/family.py'
SPEC = importlib.util.spec_from_file_location('frozen_a_family_assembly_test_target', SCRIPT)
family = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(family)

TOY_HELPERS = '''def assert_locked_ids(actual_ids, locked_ids):
    actual, expected = list(actual_ids), list(locked_ids)
    if len(actual) != len(set(actual)) or len(expected) != len(set(expected)) or set(actual) != set(expected):
        raise ValueError('Toy frozen IDs differ')
def primary_p(overlap_class, ivw_p, mrlap_p, *, usual_eligible, mrlap_eligible, rules):
    if not usual_eligible:
        return dict(p=None,method='NA',reason='PRIMARY_ELIGIBILITY_FAILED')
    policy=rules['pairwise']['primary_p_policy'][overlap_class]['primary']
    if policy=='IVW':
        return dict(p=None if ivw_p is None else float(ivw_p),method='IVW',reason='FROZEN_O0')
    if policy=='MRlap_corrected' and mrlap_eligible and mrlap_p is not None:
        return dict(p=float(mrlap_p),method=policy,reason='FROZEN_O1')
    return dict(p=None,method='NA',reason='OVERLAP_UNRESOLVED')
def strict_conjunction(first, second):
    return None if first is None or second is None else max(first,second)
def adjust_complete_family(*args,**kwargs):
    raise AssertionError('Python adjustment must never be called')
'''


class FrozenAFamilyAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.edges = [dict(edge_id='E' + str(index), family='A_PRIMARY_EDGES' if index < 88 else 'A_EXPANDED_EDGES')
            for index in range(276)]
        self.paths = [dict(path_id='P' + str(index), family='A_PRIMARY_PATHS' if index < 36 else 'A_EXPANDED_PATHS',
            xm_edge_id='E0' if index % 2 == 0 else 'E2', my_edge_id='E1', xy_edge_id='E2',
            test='max(p_XM,p_MY)', correction='BY', select_by_pairwise_significance='NO', product_p_can_promote='NO')
            for index in range(288)]
        hypotheses = family.hypotheses(self.edges, self.paths)
        ledger = [dict(**row, status='NOT_ESTIMABLE', p_raw='NA', p_for_adjustment='1') for row in hypotheses]
        decisions = [dict(edge_id=row['edge_id'], overlap_class='PENDING') for row in self.edges]
        locks = [dict(family_id=name, status='LOCKED', n_tests=count) for name, count in family.COUNTS.items()]
        multiplicity = [dict(family_id=name, locked_count=count) for name, count in family.COUNTS.items()]
        rules = dict(planned_counts={**family.COUNTS, 'A_MVP_BRIDGE': 11}, pairwise=dict(primary_p_policy={
            name: dict(primary=method) for name, method in [('O0', 'IVW'), ('O1', 'MRlap_corrected'), ('O2', 'NA'), ('O3', 'NA')]}))
        payloads = [family.tsv(rows, list(rows[0])) for rows in [self.edges, self.paths, ledger, decisions, locks, multiplicity]]
        payloads += [family.json_bytes(rules), TOY_HELPERS.encode(), b'adjust_full <- function(p,method="BH") p.adjust(ifelse(is.finite(p),p,1),method=method)\n']
        self.sources = [(entry[0], len(payload), family.checksum(payload)) for entry, payload in zip(family.SOURCES, payloads, strict=True)]
        self.pins = mock.patch.object(family, 'SOURCES', self.sources)
        self.pins.start()
        self.addCleanup(self.pins.stop)
        self.inputs = []
        for index, payload in enumerate(payloads):
            path = self.root / ('input-' + str(index) + '.staged')
            path.write_bytes(payload)
            self.inputs.append(path)
        self.request = dict(schema='FROZEN_A_FAMILY_TECHNICAL_REQUEST_V1', scope=family.SYNTHETIC,
            scenario='INTERIOR', edges=[dict(analysis_id=row['edge_id'], family_id=row['family'], scope=family.SYNTHETIC,
                scenario='INTERIOR', overlap_class=['O0', 'O1', 'O1'][index % 3], usual_eligible=True,
                mrlap_eligible=index % 3 == 1, ivw_p=.01, mrlap_p=.004 if index % 3 == 1 else None)
                for index, row in enumerate(self.edges)])
        self.request_path = self.root / 'request.staged'
        self.request_path.write_bytes(family.json_bytes(self.request))
        self.inputs.append(self.request_path)

    def assembly(self, request=None):
        if request is not None:
            self.request_path.write_bytes(family.json_bytes(request))
        return family.assemble(self.inputs)

    def publish_inputs(self, bundle=None):
        bundle = self.assembly() if bundle is None else bundle
        receipt = family.strict_json(bundle['assembly-receipt.json'])
        vectors = family.table(bundle['vectors.tsv'], family.VECTOR_COLUMNS)
        adjusted = family.tsv([dict(**row, q='1' if row['p_raw'] == 'NA' else '0.42') for row in vectors],
            [*family.VECTOR_COLUMNS, 'q'])
        rds = b'OPAQUE_TOY_RDS_NOT_AN_OFFICIAL_RUNTIME_PROOF'
        official = dict(schema='FROZEN_A_OFFICIAL_ADJUSTMENT_RECEIPT_V1', scope=receipt['scope'], scenario=receipt['scenario'],
            input_sha256={'vectors.tsv': family.checksum(bundle['vectors.tsv']), 'assembly.tsv': family.checksum(bundle['assembly.tsv']),
                'assembly-receipt.json': family.checksum(bundle['assembly-receipt.json']), 'g0_v432_methods.R': self.sources[8][2]},
            output_sha256={'adjusted.tsv': family.checksum(adjusted), 'adjustment.RDS': family.checksum(rds)},
            R_version='4.6.1', stats_version='4.6.1', adjustment_definition_sha256=family.DEFINITION_SHA,
            vector_count=6, rows=840, family_counts=family.COUNTS, official_function='stats::p.adjust',
            invocation='adjust_full(p, method)', missing_for_adjustment=1, **family.AUTHORITY)
        payloads = [bundle['assembly.tsv'], bundle['vectors.tsv'], bundle['assembly-receipt.json'], adjusted, rds,
            family.json_bytes(official), self.inputs[0].read_bytes(), self.inputs[1].read_bytes()]
        directory = self.root / 'publish-inputs'
        directory.mkdir()
        paths = []
        for index, payload in enumerate(payloads):
            path = directory / ('port-' + str(index))
            path.write_bytes(payload)
            paths.append(path)
        return paths

    def rewrite_adjusted(self, paths, rows):
        paths[3].write_bytes(family.tsv(rows, [*family.VECTOR_COLUMNS, 'q']))
        receipt = family.strict_json(paths[5].read_bytes())
        receipt['output_sha256']['adjusted.tsv'] = family.checksum(paths[3].read_bytes())
        paths[5].write_bytes(family.json_bytes(receipt))

    def test_full_564_ids_and_840_vector_rows_preserve_all_four_denominators(self):
        result = self.assembly()
        rows = family.table(result['assembly.tsv'], family.ASSEMBLY_COLUMNS)
        vectors = family.table(result['vectors.tsv'], family.VECTOR_COLUMNS)
        receipt = family.strict_json(result['assembly-receipt.json'])
        self.assertEqual((len(rows), len(vectors), len({row['vector_id'] for row in vectors})), (564, 840, 6))
        self.assertEqual(receipt['family_counts'], family.COUNTS)
        self.assertEqual(receipt['source_inputs'][0]['name'], self.sources[0][0])
        self.assertFalse(receipt['official_adjustment_performed'])
        self.assertNotIn(b'\r\n', result['assembly.tsv'])

    def test_original_helper_selects_o1_corrected_p_without_smaller_p_fallback(self):
        request = copy.deepcopy(self.request)
        request['edges'][1]['ivw_p'] = .000001
        rows = family.table(self.assembly(request)['assembly.tsv'])
        self.assertEqual(rows[1]['p_raw'], '0.004')
        self.assertEqual(rows[1]['primary_method'], 'MRlap_corrected')
        self.assertEqual(rows[2]['p_raw'], 'NA')

    def test_strict_iut_uses_xm_my_and_preserves_missing_without_requiring_xy_p(self):
        rows = family.table(self.assembly()['assembly.tsv'])
        self.assertEqual(rows[276]['p_raw'], '0.01')
        self.assertEqual(rows[277]['p_raw'], 'NA')
        self.assertEqual(rows[277]['reason'], 'MISSING_COMPONENT')

    def test_ledger_scope_transports_only_564_frozen_missing_rows(self):
        before = [path.read_bytes() for path in self.inputs[:9]]
        request = dict(schema=self.request['schema'], scope=family.LEDGER, scenario='REAL_FROZEN_NA_LEDGER', edges=[])
        result = self.assembly(request)
        rows = family.table(result['assembly.tsv'])
        self.assertTrue(all(row['p_raw'] == 'NA' and row['reason'] == 'NOT_ESTIMABLE' for row in rows))
        self.assertEqual([path.read_bytes() for path in self.inputs[:9]], before)
        request['edges'] = self.request['edges']
        with self.assertRaises(ValueError):
            self.assembly(request)

    def test_strict_json_rejects_duplicate_keys_nonfinite_literals_and_overflow(self):
        for payload in [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}']:
            with self.assertRaises(ValueError):
                family.strict_json(payload)

    def test_request_cannot_mix_scope_scenario_or_introduce_extra_keys(self):
        for key, value in [('scope', 'RESEARCH'), ('scenario', 'REAL_FROZEN_NA_LEDGER'), ('extra', True)]:
            changed = copy.deepcopy(self.request)
            changed[key] = value
            with self.assertRaises(ValueError):
                self.assembly(changed)

    def test_complete_ids_reject_missing_duplicate_and_foreign_edges(self):
        for case in ['missing', 'duplicate', 'foreign']:
            changed = copy.deepcopy(self.request)
            if case == 'missing':
                changed['edges'].pop()
            elif case == 'duplicate':
                changed['edges'][-1] = changed['edges'][0]
            else:
                changed['edges'][-1]['analysis_id'] = 'FOREIGN'
            with self.assertRaises(ValueError):
                self.assembly(changed)

    def test_edge_family_scope_scenario_and_pending_overlap_are_rejected(self):
        for key, value in [('family_id', 'A_PRIMARY_PATHS'), ('scope', family.LEDGER),
                           ('scenario', 'BOUNDARY'), ('overlap_class', 'PENDING')]:
            changed = copy.deepcopy(self.request)
            changed['edges'][0][key] = value
            with self.assertRaises(ValueError):
                self.assembly(changed)

    def test_boolean_out_of_range_and_string_probabilities_are_rejected(self):
        for value in [True, -0.01, 1.001, '.01']:
            changed = copy.deepcopy(self.request)
            changed['edges'][0]['ivw_p'] = value
            with self.assertRaises(ValueError):
                self.assembly(changed)

    def test_source_byte_drift_or_symlink_is_rejected_with_staged_filenames_allowed(self):
        self.inputs[0].write_bytes(self.inputs[0].read_bytes() + b'\n')
        with self.assertRaises(ValueError):
            self.assembly()
        original = self.inputs[1]
        alias = self.root / 'source-alias'
        alias.symlink_to(original)
        with self.assertRaises(ValueError):
            family.read(alias)

    def test_publish_transports_q_without_python_adjustment_or_rds_deserialization(self):
        result = family.publish(self.publish_inputs())
        rows = family.table(result['family.tsv'])
        self.assertEqual(len(rows), 564)
        self.assertEqual(rows[0]['q_BH'], '0.42')
        self.assertEqual(rows[276]['q_BH'], 'NA')
        self.assertEqual(rows[2]['p_raw'], 'NA')
        self.assertEqual(rows[2]['p_for_adjustment'], '1')
        audit = family.strict_json(result['family-audit.json'])
        self.assertFalse(audit['Python_q_recomputation_performed'])
        self.assertFalse(audit['RDS_parsed_in_Python'])

    def test_official_receipt_rejects_wrong_version_definition_flags_and_count(self):
        paths = self.publish_inputs()
        baseline = paths[5].read_bytes()
        for key, value in [('R_version', '4.6.0'), ('stats_version', '4.5.0'), ('rows', 839),
                           ('adjustment_definition_sha256', '0' * 64), ('g0_granted', True), ('missing_for_adjustment', True)]:
            receipt = family.strict_json(baseline)
            receipt[key] = value
            paths[5].write_bytes(family.json_bytes(receipt))
            with self.assertRaises(ValueError):
                family.publish(paths)

    def test_rds_tamper_or_empty_artifact_cannot_pass_hash_guard(self):
        paths = self.publish_inputs()
        paths[4].write_bytes(b'substituted RDS')
        with self.assertRaises(ValueError):
            family.publish(paths)
        paths[4].write_bytes(b'')
        receipt = family.strict_json(paths[5].read_bytes())
        receipt['output_sha256']['adjustment.RDS'] = family.checksum(b'')
        paths[5].write_bytes(family.json_bytes(receipt))
        with self.assertRaisesRegex(ValueError, 'must not be empty'):
            family.publish(paths)

    def test_adjusted_row_order_or_truncation_is_rejected_even_after_receipt_rehash(self):
        paths = self.publish_inputs()
        rows = family.table(paths[3].read_bytes())
        for altered in [rows[1:] + rows[:1], rows[:-1]]:
            self.rewrite_adjusted(paths, altered)
            with self.assertRaises(ValueError):
                family.publish(paths)

    def test_nonfinite_or_invalid_official_q_is_rejected_without_recalculation(self):
        paths = self.publish_inputs()
        baseline = family.table(paths[3].read_bytes())
        for value in ['NaN', 'Inf', '-0.01', '1.01']:
            rows = copy.deepcopy(baseline)
            rows[0]['q'] = value
            self.rewrite_adjusted(paths, rows)
            with self.assertRaises(ValueError):
                family.publish(paths)

    def test_missing_raw_p_cannot_receive_nonunit_q(self):
        paths = self.publish_inputs()
        rows = family.table(paths[3].read_bytes())
        next(row for row in rows if row['p_raw'] == 'NA')['q'] = '0.1'
        self.rewrite_adjusted(paths, rows)
        with self.assertRaisesRegex(ValueError, 'placeholder'):
            family.publish(paths)

    def test_publisher_rejects_original_registry_and_source_receipt_drift(self):
        paths = self.publish_inputs()
        original = paths[6].read_bytes()
        paths[6].write_bytes(original + b'\n')
        with self.assertRaises(ValueError):
            family.publish(paths)
        paths[6].write_bytes(original)
        receipt = family.strict_json(paths[2].read_bytes())
        receipt['source_inputs'][0]['sha256'] = '0' * 64
        paths[2].write_bytes(family.json_bytes(receipt))
        with self.assertRaises(ValueError):
            family.publish(paths)

    def test_existing_foreign_outputs_and_input_aliases_are_not_overwritten(self):
        outputs = [self.root / name for name in family.ASSEMBLE_OUTPUTS]
        outputs[0].write_bytes(b'FOREIGN')
        with self.assertRaises(ValueError):
            family.run('assemble', self.inputs, outputs)
        self.assertEqual(outputs[0].read_bytes(), b'FOREIGN')
        outputs[0] = self.inputs[0]
        with self.assertRaises(ValueError):
            family.preflight_outputs(self.inputs, outputs)

    def test_publication_failure_rolls_back_only_own_inodes_and_cleans_temporary_files(self):
        outputs = [self.root / name for name in family.ASSEMBLE_OUTPUTS]
        parents = family.preflight_outputs(self.inputs, outputs)
        original_link = os.link
        calls = []
        def fail_second(source, destination):
            calls.append(destination)
            if len(calls) == 2:
                raise OSError('toy second link failure')
            return original_link(source, destination)
        with mock.patch.object(family.os, 'link', side_effect=fail_second):
            with self.assertRaises(OSError):
                family.exclusive_publish([b'first', b'second', b'third', b'log'], outputs, parents)
        self.assertTrue(all(not path.exists() for path in outputs))
        self.assertEqual(list(self.root.glob('.frozen-a-family-*')), [])

    def test_foreign_inode_replacing_new_output_survives_rollback(self):
        outputs = [self.root / name for name in family.ASSEMBLE_OUTPUTS]
        parents = family.preflight_outputs(self.inputs, outputs)
        original_link = os.link
        def substitute(source, destination):
            original_link(source, destination)
            destination.unlink()
            destination.write_bytes(b'FOREIGN_REPLACEMENT')
        with mock.patch.object(family.os, 'link', side_effect=substitute):
            with self.assertRaisesRegex(ValueError, 'foreign inode'):
                family.exclusive_publish([b'first', b'second', b'third', b'log'], outputs, parents)
        self.assertEqual(outputs[0].read_bytes(), b'FOREIGN_REPLACEMENT')
        self.assertTrue(all(not path.exists() for path in outputs[1:]))

    def test_input_mutation_during_publication_refuses_and_rolls_back_owned_outputs(self):
        outputs = [self.root / name for name in family.ASSEMBLE_OUTPUTS]
        original_link = os.link
        changed = []
        def mutate(source, destination):
            original_link(source, destination)
            if not changed:
                self.inputs[0].write_bytes(self.inputs[0].read_bytes() + b'\n')
                changed.append(True)
        with mock.patch.object(family.os, 'link', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed during publication'):
                family.run('assemble', self.inputs, outputs)
        self.assertTrue(all(not path.exists() for path in outputs))

    def test_same_inode_content_rewrite_after_link_is_rejected_and_preserved(self):
        outputs = [self.root / name for name in family.ASSEMBLE_OUTPUTS]
        parents = family.preflight_outputs(self.inputs, outputs)
        original_link = os.link
        identities = []
        def rewrite(source, destination):
            original_link(source, destination)
            identities.append(destination.stat().st_ino)
            destination.write_bytes(b'ALIEN')
            self.assertEqual(destination.stat().st_ino, identities[-1])
        with mock.patch.object(family.os, 'link', side_effect=rewrite):
            with self.assertRaisesRegex(ValueError, 'foreign inode or content'):
                family.exclusive_publish([b'first', b'second', b'third', b'log'], outputs, parents)
        self.assertEqual(outputs[0].read_bytes(), b'ALIEN')
        self.assertTrue(all(not path.exists() for path in outputs[1:]))

    def test_rollback_preserves_earlier_output_rewritten_in_place_before_later_failure(self):
        outputs = [self.root / name for name in family.ASSEMBLE_OUTPUTS]
        parents = family.preflight_outputs(self.inputs, outputs)
        original_link = os.link
        calls = []
        def fail_later(source, destination):
            calls.append(destination)
            if len(calls) == 2:
                before = outputs[0].stat().st_ino
                outputs[0].write_bytes(b'ALIEN')
                self.assertEqual(outputs[0].stat().st_ino, before)
                raise OSError('later publication failed')
            original_link(source, destination)
        with mock.patch.object(family.os, 'link', side_effect=fail_later):
            with self.assertRaises(OSError):
                family.exclusive_publish([b'first', b'second', b'third', b'log'], outputs, parents)
        self.assertEqual(outputs[0].read_bytes(), b'ALIEN')
        self.assertTrue(all(not path.exists() for path in outputs[1:]))

    def test_stage_replacement_is_rejected_before_any_output_link(self):
        outputs = [self.root / name for name in family.ASSEMBLE_OUTPUTS]
        parents = family.preflight_outputs(self.inputs, outputs)
        original_sync = os.fsync
        stages = []
        calls = []
        def substitute(descriptor):
            original_sync(descriptor)
            calls.append(descriptor)
            if len(calls) == 1:
                inode = os.fstat(descriptor).st_ino
                stages.extend(path for path in self.root.glob('.frozen-a-family-*') if path.stat().st_ino == inode)
            if len(calls) == 4:
                stages[0].unlink()
                stages[0].write_bytes(b'FOREIGN_STAGE')
        with mock.patch.object(family.os, 'fsync', side_effect=substitute), mock.patch.object(family.os, 'link') as linked:
            with self.assertRaisesRegex(ValueError, 'Staged output content or inode changed'):
                family.exclusive_publish([b'first', b'second', b'third', b'log'], outputs, parents)
            linked.assert_not_called()
        self.assertEqual(stages[0].read_bytes(), b'FOREIGN_STAGE')
        self.assertTrue(all(not path.exists() for path in outputs))

    def test_failed_entry_preserves_foreign_file_and_writes_exclusive_diagnostic(self):
        outputs = [self.root / name for name in family.ASSEMBLE_OUTPUTS]
        outputs[0].write_bytes(b'FOREIGN')
        environment = {'FROZEN_A_FAMILY_MODE': 'assemble', **{'AUTONOMICS_INPUT' + str(i): str(path) for i, path in enumerate(self.inputs)},
            **{'AUTONOMICS_OUTPUT' + str(i): str(path) for i, path in enumerate(outputs)}}
        with mock.patch.dict(os.environ, environment), mock.patch.object(sys, 'argv', [str(SCRIPT)]), \
                mock.patch.object(sys, 'version_info', (3, 14, 7)):
            self.assertEqual(family.main(), 2)
        self.assertEqual(outputs[0].read_bytes(), b'FOREIGN')
        self.assertIn(b'Frozen A family refused', outputs[3].read_bytes())
        self.assertFalse(outputs[1].exists())

    def test_manifest_has_exact_two_zero_parameter_kinds_and_pinned_runtime(self):
        manifest = tomllib.loads((SCRIPT.parents[1] / 'manifest.toml').read_text())
        self.assertEqual([node['kind'] for node in manifest['nodes']], ['frozen_a_family_assemble', 'frozen_a_family_publish'])
        for node, inputs in zip(manifest['nodes'], [10, 8], strict=True):
            self.assertEqual(len(node['ports']['inputs']), inputs)
            self.assertEqual(len(node['ports']['outputs']), 4)
            self.assertEqual(node['stage_in_mode'], 'copy')
            self.assertEqual(node['resources']['memory'], '1Gi')
            self.assertEqual(node['command']['script_file'], 'scripts/family.py')
            self.assertNotIn('params', node)

    def test_source_contract_and_original_proof_keep_exact_same_nine_pins(self):
        contract = json.loads((SCRIPT.parents[1] / 'contracts/source-lock.json').read_text())
        source_spec = importlib.util.spec_from_file_location('original_family_contract_fixture', ROOT / 'tools/prove_frozen_a_family_contract.py')
        source_module = importlib.util.module_from_spec(source_spec)
        source_spec.loader.exec_module(source_module)
        self.assertEqual(contract['inputs'], [dict(port=i, name=name, bytes=size, sha256=sha)
            for i, (name, size, sha) in enumerate(source_module.SOURCES)])

    def test_wrong_frozen_size_is_rejected_without_opening_any_payload(self):
        self.inputs[0].write_bytes(self.inputs[0].read_bytes() + b'\n')
        with mock.patch.object(Path, 'open') as opened:
            with self.assertRaisesRegex(ValueError, 'size differs before reading'):
                family.source_inputs(self.inputs[:9])
            opened.assert_not_called()

    def test_growth_during_bounded_read_is_rejected_by_descriptor_postcheck(self):
        target = self.inputs[0]
        original_open = Path.open
        sizes = []
        class GrowingReader:
            def __init__(self):
                self.handle = original_open(target, 'rb')
            def __enter__(self):
                return self
            def __exit__(self, *arguments):
                self.handle.close()
            def fileno(self):
                return self.handle.fileno()
            def read(self, size):
                sizes.append(size)
                payload = self.handle.read(size)
                with original_open(target, 'ab') as writer:
                    writer.write(b'grew after stat')
                return payload
        with mock.patch.object(Path, 'open', side_effect=lambda path, *args, **kwargs: GrowingReader(), autospec=True):
            with self.assertRaisesRegex(ValueError, 'changed while reading'):
                family.read(target, expected_size=self.sources[0][1])
        self.assertEqual(sizes, [self.sources[0][1] + 1])

    def test_oversized_request_is_rejected_before_json_loading(self):
        with self.request_path.open('wb') as handle:
            handle.truncate(family.REQUEST_MAX_BYTES + 1)
        with self.assertRaisesRegex(ValueError, 'bounded byte budget'):
            self.assembly()

    def test_oversized_rds_is_rejected_before_payload_hash_or_deserialization(self):
        paths = self.publish_inputs()
        with paths[4].open('wb') as handle:
            handle.truncate(family.PUBLISH_MAX_BYTES[4] + 1)
        with self.assertRaisesRegex(ValueError, 'bounded byte budget'):
            family.publish(paths)


if __name__ == '__main__':
    unittest.main()
