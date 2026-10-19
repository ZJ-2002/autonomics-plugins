import contextlib
import csv
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
PROGRAM = Path(os.environ.get('AUTONOMICS_HASHUTIL_TEST_SOURCE',
    str(ROOT / 'research-adapters/cachexia-hashutil/scripts/file_hashes.py')))
SPECIFICATION = importlib.util.spec_from_file_location('hashutil_publication_subject', PROGRAM)
MODULE = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(MODULE)


class HashutilPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(prefix='hashutil-publication-toy-')
        self.root = Path(self.temporary_directory.name)
        self.input_file = self.root / 'input.bin'
        self.input_file.write_bytes(b'TOY_HASH_PUBLICATION\x00\xff\n')
        self.output = self.root / 'hashes.tsv'
        self.partial = self.root / 'hashes.tsv.partial'
        self.log = self.root / 'hashes.log'
        self.environment = {'AUTONOMICS_INPUT_COUNT': '1', 'AUTONOMICS_INPUT0': str(self.input_file),
            'AUTONOMICS_OUTPUT0': str(self.output), 'AUTONOMICS_OUTPUT1': str(self.log),
            'HASHUTIL_ALGOS': 'sha256', 'HASHUTIL_CHUNK_MB': '1'}

    def tearDown(self):
        self.temporary_directory.cleanup()

    def run_subject(self, environment=None):
        with contextlib.redirect_stderr(io.StringIO()):
            return MODULE.main(self.environment if environment is None else environment)

    def assert_fresh_table_absent(self):
        self.assertFalse(os.path.lexists(self.output))
        self.assertFalse(os.path.lexists(self.partial))

    def test_fresh_result_matches_exact_sha256_and_tsv_contract(self):
        self.assertEqual(self.run_subject(), 0)
        with self.output.open(newline='') as handle:
            rows = list(csv.reader(handle, delimiter='\t'))
        self.assertEqual(rows, [['file', 'algorithm', 'digest', 'size_bytes'],
            ['input.bin', 'sha256', hashlib.sha256(self.input_file.read_bytes()).hexdigest(), str(self.input_file.stat().st_size)]])
        self.assertIn('status\tPASS\n', self.log.read_text())
        self.assertFalse(self.partial.exists())

    def test_empty_file_remains_valid(self):
        self.input_file.write_bytes(b'')
        self.assertEqual(self.run_subject(), 0)
        self.assertIn(hashlib.sha256(b'').hexdigest(), self.output.read_text())
        self.assertTrue(self.output.read_text().endswith('\t0\n'))

    def test_existing_result_is_not_replaced(self):
        self.output.write_bytes(b'FOREIGN_RESULT')
        before = self.output.stat()
        self.assertEqual(self.run_subject(), 2)
        self.assertEqual(self.output.read_bytes(), b'FOREIGN_RESULT')
        self.assertEqual(self.output.stat().st_ino, before.st_ino)
        self.assertFalse(self.partial.exists())
        self.assertFalse(self.log.exists())

    def test_existing_partial_is_not_deleted(self):
        self.partial.write_bytes(b'FOREIGN_PARTIAL')
        self.assertEqual(self.run_subject(), 2)
        self.assertEqual(self.partial.read_bytes(), b'FOREIGN_PARTIAL')
        self.assertFalse(self.output.exists())
        self.assertFalse(self.log.exists())

    def test_existing_log_is_not_truncated(self):
        self.log.write_bytes(b'FOREIGN_LOG')
        self.assertEqual(self.run_subject(), 2)
        self.assertEqual(self.log.read_bytes(), b'FOREIGN_LOG')
        self.assert_fresh_table_absent()

    def test_output_symlink_and_target_are_not_replaced(self):
        target = self.root / 'foreign-target'
        target.write_bytes(b'FOREIGN_TARGET')
        self.output.symlink_to(target)
        self.assertEqual(self.run_subject(), 2)
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(target.read_bytes(), b'FOREIGN_TARGET')

    def test_dangling_output_symlink_is_not_deleted(self):
        self.output.symlink_to(self.root / 'absent-target')
        self.assertEqual(self.run_subject(), 2)
        self.assertTrue(self.output.is_symlink())
        self.assertFalse(self.partial.exists())

    def test_dangling_partial_symlink_is_not_deleted(self):
        self.partial.symlink_to(self.root / 'absent-target')
        self.assertEqual(self.run_subject(), 2)
        self.assertTrue(self.partial.is_symlink())
        self.assertFalse(self.output.exists())

    def test_dangling_log_symlink_is_not_followed(self):
        absent = self.root / 'absent-target'
        self.log.symlink_to(absent)
        self.assertEqual(self.run_subject(), 2)
        self.assertTrue(self.log.is_symlink())
        self.assertFalse(absent.exists())
        self.assert_fresh_table_absent()

    def test_input_alias_is_never_removed(self):
        before = self.input_file.read_bytes()
        self.assertEqual(self.run_subject(dict(self.environment, AUTONOMICS_OUTPUT0=str(self.input_file))), 2)
        self.assertEqual(self.input_file.read_bytes(), before)
        self.assertFalse(self.log.exists())

    def test_invalid_parameters_leave_only_owned_failure_diagnostic(self):
        with patch.object(MODULE, 'file_digests', side_effect=AssertionError('must not hash invalid request')) as hashed:
            self.assertEqual(self.run_subject(dict(self.environment, HASHUTIL_CHUNK_MB='0')), 2)
            hashed.assert_not_called()
        self.assert_fresh_table_absent()
        self.assertIn('status\tBLOCKED\n', self.log.read_text())
        self.assertNotIn('status\tPASS\n', self.log.read_text())

    def test_late_foreign_result_is_not_overwritten(self):
        original = MODULE.file_digests

        def competing(*arguments):
            rows = original(*arguments)
            self.output.write_bytes(b'LATE_FOREIGN_RESULT')
            return rows

        with patch.object(MODULE, 'file_digests', competing):
            self.assertEqual(self.run_subject(), 2)
        self.assertEqual(self.output.read_bytes(), b'LATE_FOREIGN_RESULT')
        self.assertFalse(self.partial.exists())
        self.assertIn('status\tBLOCKED\n', self.log.read_text())

    def test_late_foreign_partial_is_not_overwritten(self):
        original = MODULE.file_digests

        def competing(*arguments):
            rows = original(*arguments)
            self.partial.write_bytes(b'LATE_FOREIGN_PARTIAL')
            return rows

        with patch.object(MODULE, 'file_digests', competing):
            self.assertEqual(self.run_subject(), 2)
        self.assertEqual(self.partial.read_bytes(), b'LATE_FOREIGN_PARTIAL')
        self.assertFalse(self.output.exists())

    def test_replaced_log_is_not_appended_or_removed(self):
        original = MODULE.file_digests

        def competing(*arguments):
            self.log.unlink()
            self.log.write_bytes(b'REPLACEMENT_FOREIGN_LOG')
            return original(*arguments)

        with patch.object(MODULE, 'file_digests', competing):
            self.assertEqual(self.run_subject(), 2)
        self.assertEqual(self.log.read_bytes(), b'REPLACEMENT_FOREIGN_LOG')
        self.assert_fresh_table_absent()

    def test_replaced_partial_during_serialization_survives_cleanup(self):
        original = csv.writer
        partial = self.partial

        class CompetingWriter:
            def __init__(self, *arguments, **keywords):
                self.delegate = original(*arguments, **keywords)

            def writerow(self, row):
                return self.delegate.writerow(row)

            def writerows(self, rows):
                self.delegate.writerows(rows)
                partial.unlink()
                partial.write_bytes(b'REPLACEMENT_FOREIGN_PARTIAL')

        with patch.object(MODULE.csv, 'writer', CompetingWriter):
            self.assertEqual(self.run_subject(), 2)
        self.assertEqual(self.partial.read_bytes(), b'REPLACEMENT_FOREIGN_PARTIAL')
        self.assertFalse(self.output.exists())

    def test_serialization_failure_removes_only_owned_partial(self):
        original = csv.writer

        class BrokenWriter:
            def __init__(self, *arguments, **keywords):
                self.delegate = original(*arguments, **keywords)

            def writerow(self, row):
                return self.delegate.writerow(row)

            def writerows(self, rows):
                raise OSError('intentional serialization failure')

        with patch.object(MODULE.csv, 'writer', BrokenWriter):
            self.assertEqual(self.run_subject(), 2)
        self.assert_fresh_table_absent()
        self.assertIn('intentional serialization failure', self.log.read_text())


if __name__ == '__main__':
    unittest.main()
