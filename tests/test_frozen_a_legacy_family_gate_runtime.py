import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import prove_frozen_a_legacy_family_gate as proof


class LegacyFamilyGateRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='legacy-gate-runtime-toy-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.directory = self.root / 'permanent/frozen-a-legacy-mr-runtime'
        current = self.directory / 'current'
        current.mkdir(parents=True)
        self.driver = self.directory / 'driver.py'
        self.checker = self.directory / 'source/tools/check_frozen_a_legacy_mr_runtime.R'
        self.checker.parent.mkdir(parents=True)
        self.driver.write_bytes(b'TOY_REVIEWED_DRIVER\n')
        self.checker.write_bytes(b'TOY_REVIEWED_CHECKER\n')
        self.driver_sha = hashlib.sha256(self.driver.read_bytes()).hexdigest()
        self.checker_sha = hashlib.sha256(self.checker.read_bytes()).hexdigest()
        self.ports = []
        for index, name in enumerate(proof.MR_PORTS):
            path = current / name
            path.write_bytes(('TOY_PORT_' + str(index) + '\n').encode())
            self.ports.append(dict(port=index, name=name, **proof.fact(path)))
        self.report = dict(status='SCOPED_REAL_ALREADY_SEEN_39_IV_DIRECT_OFFICIAL_REPLAY_NOT_DAG_OR_G0',
            scope='FROZEN_V432_A_LEGACY', actual_DAG_executed=False, production_changed=False,
            scientific_authorization_granted=False, g0_granted=False,
            reference=dict(six_complete_TSVs_byte_equal=True, six_complete_TSVs_readback_equal=True,
                complete_RDS_object_identical=True, RDS_numeric_tolerance=0,
                all_nine_current_ports_checked=True, full_provenance_contract_checked=True,
                original_verifier_not_faked=True, whole_original_cli_executed=False,
                overlap_class='O2', primary_p_source='NA'),
            original_sources={'plugins/twosamplemr-v432-a/scripts/mr.R': {'sha256': proof.MR_SCRIPT_SHA}},
            current_ports=self.ports)

    def checked(self, report=None, archive=None):
        (self.directory / 'verification.json').write_text(json.dumps(self.report if report is None else report))
        archived = dict(artifact_root=str(self.root), positive_worker_exit_verified=True) if archive is None else archive
        with mock.patch.object(proof, 'verify_archive', return_value=archived), \
                mock.patch.object(proof, 'MR_DRIVER_SHA', self.driver_sha), \
                mock.patch.object(proof, 'MR_CHECKER_SHA', self.checker_sha):
            return proof.checked_mr_archive(self.root, 'a' * 32, 'b' * 64)

    def test_all_nine_actual_port_bytes_are_checked(self):
        paths, receipt = self.checked()
        self.assertEqual([path.name for path in paths], proof.MR_PORTS)
        self.assertTrue(receipt['all_members_rehashed'])
        for index, name in enumerate(proof.MR_PORTS):
            with self.subTest(port=index):
                path = self.directory / 'current' / name
                previous = path.read_bytes()
                path.write_bytes(previous + b'FOREIGN')
                with self.assertRaisesRegex(ValueError, 'differs from its sealed producer'):
                    self.checked()
                path.write_bytes(previous)

    def test_old_canary_cannot_replace_current_adapter(self):
        value = copy.deepcopy(self.report)
        value['original_sources']['plugins/twosamplemr-v432-a/scripts/mr.R']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'current reviewed MR adapter'):
            self.checked(value)

    def test_actual_reference_code_cannot_be_replaced_by_matching_report_claims(self):
        for path in (self.driver, self.checker):
            with self.subTest(source=path.name):
                before = path.read_bytes()
                path.write_bytes(before + b'FOREIGN')
                with self.assertRaisesRegex(ValueError, 'reviewed independent MR driver'):
                    self.checked()
                path.write_bytes(before)

    def test_missing_or_duplicate_ports_are_rejected(self):
        for mutation in ('missing', 'duplicate', 'reordered', 'boolean-port', 'boolean-bytes'):
            value = copy.deepcopy(self.report)
            if mutation == 'missing':
                value['current_ports'].pop()
            elif mutation == 'duplicate':
                value['current_ports'][-1] = copy.deepcopy(value['current_ports'][0])
            elif mutation == 'reordered':
                value['current_ports'].reverse()
            elif mutation == 'boolean-port':
                value['current_ports'][1]['port'] = True
            else:
                value['current_ports'][1]['bytes'] = True
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, 'nine ordered MR ports'):
                self.checked(value)

    def test_skipped_or_failed_archive_is_not_a_pass(self):
        for exit_value in (False, None):
            with self.subTest(value=exit_value), self.assertRaisesRegex(ValueError, 'actual exit zero'):
                self.checked(archive=dict(artifact_root=str(self.root), positive_worker_exit_verified=exit_value))

    def test_scientific_production_and_dag_authority_are_rejected(self):
        for name in ('actual_DAG_executed', 'production_changed', 'scientific_authorization_granted', 'g0_granted'):
            for replacement in (True, None, 0):
                value = copy.deepcopy(self.report)
                value[name] = replacement
                with self.subTest(name=name, replacement=replacement), self.assertRaises(ValueError):
                    self.checked(value)

    def test_independent_reference_and_exact_primary_contract_are_required(self):
        mutations = dict(six_complete_TSVs_byte_equal=False, six_complete_TSVs_readback_equal=False,
            complete_RDS_object_identical=False, RDS_numeric_tolerance=False,
            all_nine_current_ports_checked=False, full_provenance_contract_checked=False,
            original_verifier_not_faked=False, whole_original_cli_executed=True,
            overlap_class='O0', primary_p_source='IVW')
        for name, replacement in mutations.items():
            value = copy.deepcopy(self.report)
            value['reference'][name] = replacement
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'independent official-object'):
                self.checked(value)

    def test_negative_control_changes_only_target_table_field(self):
        payload = b'SNP\tp_primary\tp_for_family\nrs_toy1\tNA\t1\nrs_toy2\tNA\t1\n'
        changed = proof.changed_table(payload, 'p_primary', '0.01')
        self.assertEqual(changed, b'SNP\tp_primary\tp_for_family\nrs_toy1\t0.01\t1\nrs_toy2\tNA\t1\n')
        self.assertEqual(payload.splitlines()[1], b'rs_toy1\tNA\t1')
        with self.assertRaisesRegex(ValueError, 'Existing full table column'):
            proof.changed_table(payload, 'missing', '1')

    def test_broken_original_scope_or_missing_reference_cannot_pass(self):
        for field, replacement in [('scope', 'SYNTHETIC_METHOD_TEST'), ('status', 'PENDING'), ('reference', {})]:
            value = copy.deepcopy(self.report)
            value[field] = replacement
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.checked(value)

    def test_manifest_and_helper_checks_do_not_allow_substitution(self):
        with mock.patch.object(proof, 'fact', return_value={'sha256': '0' * 64}):
            with self.assertRaisesRegex(ValueError, 'Exact previously verified family helper'):
                proof.family_helper()
        with mock.patch.object(proof.sys, 'argv', ['proof', '--mr-session', 'a' * 32, '--mr-seal', 'b' * 64]), \
                mock.patch.object(proof.sys, 'stderr'), mock.patch.object(proof.Path, 'mkdir') as create:
            with self.assertRaises(SystemExit) as refused:
                proof.main()
            self.assertEqual(refused.exception.code, 2)
            create.assert_not_called()

    def test_helper_replacement_after_identity_check_cannot_execute_foreign_source(self):
        helper = self.root / proof.HELPER
        helper.parent.mkdir(parents=True)
        helper.write_bytes((proof.ROOT / proof.HELPER).read_bytes())
        foreign = b'raise AssertionError("UNAPPROVED_SOURCE_EXECUTED")\n'
        actual_open = proof.os.open
        def changed_before_open(path, *arguments, **keywords):
            if path == helper:
                helper.write_bytes(foreign + b' ' * (proof.HELPER_BYTES - len(foreign)))
            return actual_open(path, *arguments, **keywords)
        with mock.patch.object(proof, 'ROOT', self.root), mock.patch.object(proof.os, 'open', side_effect=changed_before_open):
            with self.assertRaisesRegex(ValueError, 'Frozen helper changed'):
                proof.family_helper()


if __name__ == '__main__':
    unittest.main()
