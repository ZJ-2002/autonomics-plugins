"""Offline publication controls; injected fetch is not an official HTTP proof."""

import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'research-adapters/cachexia-msigdb/scripts/gmt.py'


class MSigDBPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.work = Path(self.temporary.name)
        specification = importlib.util.spec_from_file_location('gmt_publication_tested', SOURCE)
        self.module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(self.module)
        self.raw = self.work / 'input.gmt'
        self.raw.write_bytes(b'SET_A\t\tNA\t0001\t"A"\t0001\nSET_B\tdescription\tb\tC\n')
        self.contract = self.work / 'request.json'
        self.request = {
            'schema_version': 1, 'scope': 'TECHNICAL_RESOURCE_ONLY_NOT_G0', 'test_id': 'PUBLICATION_TOY',
            'input_role': 'SYNTHETIC_TECHNICAL_INPUT', 'mode': 'parse', 'release': '2025.1.Hs',
            'collection': 'h.all', 'gene_id_type': 'symbols', 'expected_sha256': hashlib.sha256(self.raw.read_bytes()).hexdigest(),
            'expected_bytes': self.raw.stat().st_size, 'expected_set_ids': ['SET_A', 'SET_B'],
            'expected_n_sets': 2, 'expected_n_memberships': 6, 'connect_timeout': 1, 'read_timeout': 1,
            'max_attempts': 1, 'max_redirects': 0, 'max_bytes': 1024, 'max_line_bytes': 1024, 'encoding': 'ascii'}
        self.outputs = [self.work / name for name in self.module.OUTPUT_NAMES]
        self.environment = {'CACHEXIA_GMT_MODE': 'parse', 'AUTONOMICS_WORKDIR': str(self.work),
                            'AUTONOMICS_INPUT0': str(self.raw), 'AUTONOMICS_INPUT1': str(self.contract)}
        self.environment.update({f'AUTONOMICS_OUTPUT{port}': str(path) for port, path in enumerate(self.outputs)})

    def invoke(self):
        self.contract.write_text(json.dumps(self.request))
        with patch.dict(os.environ, self.environment, clear=True), contextlib.redirect_stderr(io.StringIO()):
            try:
                return self.module.main()
            except Exception:
                return 99

    def test_all_declared_input_roles_are_accepted_without_changing_scope(self):
        for mode in ('parse', 'fetch'):
            for role in ('OFFICIAL_RESOURCE_TECHNICAL_ONLY', 'LEGACY_SEEN', 'SYNTHETIC_TECHNICAL_INPUT'):
                with self.subTest(mode=mode, role=role):
                    self.request.update(mode=mode, input_role=role)
                    self.contract.write_text(json.dumps(self.request))
                    accepted = self.module.read_contract(self.contract, mode)
                    self.assertEqual(accepted, self.request)
                    self.assertEqual(accepted['scope'], 'TECHNICAL_RESOURCE_ONLY_NOT_G0')

    def test_unapproved_role_or_scientific_scope_is_not_accepted(self):
        for mode in ('parse', 'fetch'):
            for role, scope in (
                ('FORMAL_RESEARCH', 'TECHNICAL_RESOURCE_ONLY_NOT_G0'),
                ('LEGACY_SEEN', 'G0_PASS'),
            ):
                with self.subTest(mode=mode, role=role, scope=scope):
                    self.request.update(mode=mode, input_role=role, scope=scope)
                    self.contract.write_text(json.dumps(self.request))
                    with self.assertRaises(ValueError):
                        self.module.read_contract(self.contract, mode)

    def inject(self, action):
        original = self.module.parse_gmt

        def parse(*arguments):
            result = original(*arguments)
            action()
            return result

        return patch.object(self.module, 'parse_gmt', side_effect=parse)

    def test_dangling_output_rejected_without_following_target(self):
        target = self.work / 'foreign-absent-target'
        self.outputs[0].symlink_to(target)
        self.assertNotEqual(self.invoke(), 0)
        self.assertFalse(target.exists())
        self.assertTrue(self.outputs[0].is_symlink())

    def test_racing_foreign_output_not_replaced(self):
        with self.inject(lambda: self.outputs[0].write_text('FOREIGN')):
            self.assertNotEqual(self.invoke(), 0)
        self.assertEqual(self.outputs[0].read_text(), 'FOREIGN')

    def test_rollback_does_not_delete_foreign_replacement(self):
        original_link, original_replace = os.link, Path.replace

        def before(source, target, operation):
            if Path(target) == self.outputs[1]:
                self.outputs[0].unlink()
                self.outputs[0].write_text('FOREIGN_REPLACEMENT')
                raise OSError('INJECTED_SECOND_PUBLICATION_FAILURE')
            return operation(source, target)

        with patch.object(self.module.os, 'link', side_effect=lambda source, target: before(source, target, original_link)), \
                patch.object(Path, 'replace', lambda source, target: before(source, target, original_replace)):
            self.assertNotEqual(self.invoke(), 0)
        self.assertTrue(self.outputs[0].exists())
        self.assertEqual(self.outputs[0].read_text(), 'FOREIGN_REPLACEMENT')

    def test_dangling_fallback_diagnostic_not_followed(self):
        self.outputs[0].write_text('FOREIGN')
        target = self.work / 'foreign-diagnostic-target'
        (self.work / 'blocked-audit.json').symlink_to(target)
        self.assertNotEqual(self.invoke(), 0)
        self.assertFalse(target.exists())
        self.assertEqual(self.outputs[0].read_text(), 'FOREIGN')

    def test_complete_parse_preserves_literal_members_and_occurrences(self):
        self.assertEqual(self.invoke(), 0)
        with self.outputs[0].open() as handle:
            rows = list(csv.DictReader(handle, delimiter='\t'))
        self.assertEqual([row['gene_id'] for row in rows], ['NA', '0001', '"A"', '0001', 'b', 'C'])
        self.assertEqual([row['member_position'] for row in rows], ['1', '2', '3', '4', '1', '2'])
        self.assertEqual(self.outputs[2].read_bytes(), self.raw.read_bytes())
        audit = json.loads(self.outputs[3].read_text())
        self.assertEqual(audit['duplicate_member_occurrences_preserved'], 1)
        self.assertFalse(audit['HTTP_retrieval_performed'])

    def test_fetch_publication_with_explicit_synthetic_transport(self):
        self.request['mode'] = 'fetch'
        self.environment.update(CACHEXIA_GMT_MODE='fetch', AUTONOMICS_INPUT0=str(self.contract))
        with patch.object(self.module, 'fetch', side_effect=lambda request, destination, attempts: shutil.copyfile(self.raw, destination)):
            self.assertEqual(self.invoke(), 0)
        self.assertEqual(self.outputs[2].read_bytes(), self.raw.read_bytes())

    def test_each_existing_output_is_preserved(self):
        for position in range(7):
            with self.subTest(port=position):
                for filename in list(self.work.iterdir()):
                    if filename not in {self.raw, self.contract} and filename.is_file():
                        filename.unlink()
                self.outputs[position].write_text('FOREIGN')
                self.assertNotEqual(self.invoke(), 0)
                self.assertEqual(self.outputs[position].read_text(), 'FOREIGN')

    def test_bad_content_hash_retains_only_failure_diagnostics(self):
        self.request['expected_sha256'] = '0' * 64
        self.assertEqual(self.invoke(), 2)
        self.assertTrue(all(not self.outputs[position].exists() for position in (0, 1, 2, 6)))
        self.assertEqual(json.loads(self.outputs[3].read_text())['status'], 'BLOCKED')
        self.assertTrue((self.work / 'blocked-request.tsv').is_file())

    def test_failed_second_publication_rolls_back_owned_output(self):
        original_link, original_replace = os.link, Path.replace

        def before(source, target, operation):
            if Path(target) == self.outputs[1]:
                raise OSError('INJECTED_SECOND_PUBLICATION_FAILURE')
            return operation(source, target)

        with patch.object(self.module.os, 'link', side_effect=lambda source, target: before(source, target, original_link)), \
                patch.object(Path, 'replace', lambda source, target: before(source, target, original_replace)):
            self.assertNotEqual(self.invoke(), 0)
        self.assertFalse(self.outputs[0].exists())
        self.assertFalse(self.outputs[1].exists())

    def test_input_output_alias_is_preserved(self):
        self.environment['AUTONOMICS_OUTPUT0'] = str(self.raw)
        original = self.raw.read_bytes()
        self.assertNotEqual(self.invoke(), 0)
        self.assertEqual(self.raw.read_bytes(), original)

    def test_duplicate_destinations_do_not_publish_normal_outputs(self):
        self.environment['AUTONOMICS_OUTPUT1'] = str(self.outputs[0])
        self.assertNotEqual(self.invoke(), 0)
        self.assertFalse(self.outputs[0].exists())


if __name__ == '__main__':
    unittest.main()
