import ast
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from tools import prove_pseudobulk_publication_ownership as proof


ORIGINAL_PUBLICATION = '''staged = []
published = []
try:
    for path in output_paths:
        descriptor, temporary_name = tempfile.mkstemp(prefix=".pseudobulk-", dir=path.parent)
        os.close(descriptor)
        staged.append(Path(temporary_name))
    with staged[0].open("w", encoding="utf-8", newline="\\n") as handle:
        writer = csv.writer(handle, delimiter="\\t", doublequote=True, lineterminator="\\n")
        writer.writerow([first_col] + ids)
        rows_per_chunk = max(1, min(len(genes), 10_000_000 // max(1, len(kept))))
        for start in range(0, len(genes), rows_per_chunk):
            stop = min(start + rows_per_chunk, len(genes))
            block = counts_sparse[start:stop].toarray()
            for row_offset in range(block.shape[0]):
                gene_name = genes[start + row_offset]
                writer.writerow([gene_name] + block[row_offset].tolist())
        handle.flush()
        os.fsync(handle.fileno())
    with staged[1].open("w", encoding="utf-8", newline="\\n") as handle:
        writer = csv.writer(handle, delimiter="\\t", doublequote=True, lineterminator="\\n")
        writer.writerow(metadata_columns)
        writer.writerows(sample_rows)
    staged[2].write_text("\\n".join(log_lines) + "\\n", encoding="utf-8")
    for temporary in staged[1:]:
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
    for temporary, destination in zip(staged, output_paths):
        os.link(temporary, destination)
        published.append((destination, temporary.stat().st_dev, temporary.stat().st_ino))
except BaseException:
    for destination, device, inode in published:
        try:
            current = destination.lstat()
            if current.st_dev == device and current.st_ino == inode:
                destination.unlink()
        except FileNotFoundError:
            pass
    raise
finally:
    for temporary in staged:
        temporary.unlink(missing_ok=True)
'''


class PseudobulkPublicationOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = (proof.ROOT / proof.RELATIVE).read_text()

    def run_case(self, source, name, mode):
        return proof.trial(source, self.root / name, mode)

    def test_original_and_fixed_control_write_exact_three_toy_files_without_scientific_dependencies(self):
        for name, source in [('original', ORIGINAL_PUBLICATION), ('fixed', self.source)]:
            result = self.run_case(source, name, 'control')
            self.assertTrue(result['function_returned_normally'])
            self.assertTrue(result['all_declared_toy_bytes_equal'])
            self.assertEqual(len(result['actual_link_calls']), 3)
            self.assertFalse(result['AnnData_imported'])
            self.assertFalse(result['numerical_aggregation_executed'])

    def test_real_original_postlink_same_inode_change_returns_normally_with_wrong_bytes(self):
        result = self.run_case(ORIGINAL_PUBLICATION, 'original-success', 'same-inode-success')
        self.assertTrue(result['function_returned_normally'])
        self.assertFalse(result['all_declared_toy_bytes_equal'])
        self.assertTrue(result['injections'][0]['actual_link_succeeded'])
        facts = result['injections'][0]['foreign']
        self.assertEqual((facts[0]['device'], facts[0]['inode']), (facts[1]['device'], facts[1]['inode']))

    def test_fixed_postlink_same_inode_change_refuses_and_preserves_both_foreign_aliases(self):
        result = self.run_case(self.source, 'fixed-success', 'same-inode-success')
        self.assertFalse(result['function_returned_normally'])
        self.assertTrue(result['all_injected_foreign_paths_preserved'])
        self.assertEqual(len(result['foreign_preservation']), 2)

    def test_real_original_second_link_failure_deletes_foreign_content_after_inplace_change(self):
        result = self.run_case(ORIGINAL_PUBLICATION, 'original-failure', 'same-inode-second-link-failure')
        self.assertTrue(result['injected_second_link_failure'])
        self.assertFalse(result['function_returned_normally'])
        self.assertFalse(result['all_injected_foreign_paths_preserved'])
        self.assertFalse(result['output_facts'][0]['exists'])
        self.assertIn('EXPLICIT_SECOND_LINK_FAILURE', result['observed_exception']['message'])

    def test_fixed_detects_changed_content_before_second_link_and_preserves_foreign(self):
        result = self.run_case(self.source, 'fixed-failure', 'same-inode-second-link-failure')
        self.assertFalse(result['function_returned_normally'])
        self.assertFalse(result['injected_second_link_failure'])
        self.assertEqual(len(result['actual_link_calls']), 1)
        self.assertTrue(result['all_injected_foreign_paths_preserved'])

    def test_original_staging_replacement_is_deleted_but_fixed_foreign_staging_survives(self):
        original = self.run_case(ORIGINAL_PUBLICATION, 'original-stage', 'staging-replaced-after-link')
        fixed = self.run_case(self.source, 'fixed-stage', 'staging-replaced-after-link')
        self.assertTrue(original['function_returned_normally'])
        self.assertFalse(original['all_injected_foreign_paths_preserved'])
        self.assertFalse(fixed['function_returned_normally'])
        self.assertTrue(fixed['all_injected_foreign_paths_preserved'])

    def test_fixed_destination_replacement_is_refused_without_deleting_replacement(self):
        original = self.run_case(ORIGINAL_PUBLICATION, 'original-destination', 'destination-replaced-after-link')
        fixed = self.run_case(self.source, 'fixed-destination', 'destination-replaced-after-link')
        self.assertTrue(original['function_returned_normally'])
        self.assertFalse(original['all_declared_toy_bytes_equal'])
        self.assertFalse(fixed['function_returned_normally'])
        self.assertTrue(fixed['all_injected_foreign_paths_preserved'])

    def test_fixed_prelink_staging_replacement_preserves_both_foreign_links(self):
        result = self.run_case(self.source, 'fixed-before-link', 'staging-replaced-before-link')
        self.assertFalse(result['function_returned_normally'])
        self.assertTrue(result['all_injected_foreign_paths_preserved'])
        self.assertTrue(result['injections'][0]['actual_link_succeeded'])

    def test_all_eighteen_explicit_observations_satisfy_original_vs_fixed_contract(self):
        original = [self.run_case(ORIGINAL_PUBLICATION, 'original-' + mode, mode) for mode in proof.MODES]
        fixed = [self.run_case(self.source, 'fixed-' + mode, mode) for mode in proof.MODES]
        proof.validate_trials(original, fixed)
        self.assertEqual((len(original), len(fixed)), (9, 9))
        with self.assertRaises(ValueError):
            proof.validate_trials(original[:-1], fixed)
        modified = copy.deepcopy(fixed)
        modified[-1]['all_injected_foreign_paths_preserved'] = False
        with self.assertRaises(ValueError):
            proof.validate_trials(original, modified)

    def test_foreign_staging_replacement_before_writer_open_is_not_truncated_by_fixed_writer(self):
        for port, mode in enumerate(proof.MODES[-3:]):
            original = self.run_case(ORIGINAL_PUBLICATION, 'original-' + mode, mode)
            fixed = self.run_case(self.source, 'fixed-' + mode, mode)
            self.assertTrue(original['injections'][0]['actual_writer_open_reached'])
            self.assertFalse(original['all_injected_foreign_paths_preserved'])
            self.assertTrue(fixed['injections'][0]['actual_writer_open_reached'])
            self.assertEqual(fixed['injections'][0]['writer_port'], port)
            self.assertFalse(fixed['function_returned_normally'])
            self.assertTrue(fixed['all_injected_foreign_paths_preserved'])
            self.assertEqual(fixed['actual_link_calls'], [])

    def test_current_source_pin_and_publication_boundary_are_explicit_and_stable(self):
        self.assertEqual(hashlib.sha256(self.source.encode()).hexdigest(), proof.CURRENT_SHA)
        prefix, _, suffix = proof.publication_parts(self.source)
        self.assertTrue(prefix)
        self.assertEqual(suffix.body[0].name, '_publication_handle_fact')
        imports = [item.names[0].name for item in ast.walk(suffix) if isinstance(item, ast.Import)]
        self.assertNotIn('anndata', imports)
        self.assertNotIn('numpy', imports)
        self.assertNotIn('scipy', imports)
        with self.assertRaises(ValueError):
            proof.publication_parts('pass\n')

    def test_unknown_control_and_aliased_source_identity_are_refused(self):
        with self.assertRaises(ValueError):
            self.run_case(self.source, 'unknown', 'arbitrary-study')
        original = self.root / 'source.py'
        original.write_text('TOY SOURCE')
        alias = self.root / 'alias.py'
        alias.symlink_to(original)
        with self.assertRaises(ValueError):
            proof.identity(alias)
        self.assertEqual(proof.identity(original)['bytes'], 10)


if __name__ == '__main__':
    unittest.main()
