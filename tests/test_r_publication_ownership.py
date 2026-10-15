import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('r_publication_ownership',
    ROOT / 'tools/prove_r_publication_ownership.py')
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


class RPublicationOwnershipTests(unittest.TestCase):
    def actual(self, family, mode):
        relative, expected = TOOL.SOURCES[family]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'original.R'
            source.write_bytes(subprocess.run(['git', '-C', str(ROOT), 'show',
                TOOL.BASELINE_REVISION + ':' + relative], check=True, capture_output=True).stdout)
            self.assertEqual(TOOL.file_fact(source)['sha256'], expected)
            record = TOOL.trial(source, Path(directory) / 'observation', mode)
            self.assertEqual(record['host_R_exit'], 0)
            self.assertFalse(record['scientific_computation_executed'])
            return record

    def test_deseq2_actual_control(self):
        self.assertIn('CONTROL', TOOL.validate_observation(self.actual('deseq2', 'control'), baseline=True))

    def test_limma_actual_control(self):
        self.assertIn('CONTROL', TOOL.validate_observation(self.actual('limma', 'control'), baseline=True))

    def test_deseq2_actual_same_inode_success_is_defect(self):
        self.assertIn('NOT_PASS', TOOL.validate_observation(
            self.actual('deseq2', 'same-inode-success'), baseline=True))

    def test_limma_actual_same_inode_success_is_defect(self):
        self.assertIn('NOT_PASS', TOOL.validate_observation(
            self.actual('limma', 'same-inode-success'), baseline=True))

    def test_deseq2_actual_rollback_deletes_modified_inode(self):
        self.assertIn('NOT_PASS', TOOL.validate_observation(
            self.actual('deseq2', 'same-inode-later-link-failure'), baseline=True))

    def test_limma_actual_rollback_deletes_modified_inode(self):
        self.assertIn('NOT_PASS', TOOL.validate_observation(
            self.actual('limma', 'same-inode-later-link-failure'), baseline=True))

    def test_deseq2_actual_foreign_stage_child_deleted(self):
        self.assertIn('NOT_PASS', TOOL.validate_observation(
            self.actual('deseq2', 'foreign-stage-child'), baseline=True))

    def test_limma_actual_foreign_stage_child_deleted(self):
        self.assertIn('NOT_PASS', TOOL.validate_observation(
            self.actual('limma', 'foreign-stage-child'), baseline=True))

    def test_silent_success_cannot_pass_current_contract(self):
        record = self.actual('deseq2', 'same-inode-success')
        with self.assertRaisesRegex(ValueError, 'preserve foreign|reject changed'):
            TOOL.validate_observation(record, baseline=False)

    def test_deseq2_actual_last_link_mutation_baseline_and_current(self):
        self.check_both('deseq2', 'last-link-rewrites-first')

    def test_limma_actual_last_link_mutation_baseline_and_current(self):
        self.check_both('limma', 'last-link-rewrites-first')

    def test_deseq2_actual_staged_prelink_baseline_and_current(self):
        self.check_both('deseq2', 'staged-before-link')

    def test_limma_actual_staged_prelink_baseline_and_current(self):
        self.check_both('limma', 'staged-before-link')

    def check_both(self, family, mode):
        self.assertIn('NOT_PASS', TOOL.validate_observation(self.actual(family, mode), baseline=True))
        with tempfile.TemporaryDirectory() as directory:
            current = TOOL.trial(ROOT / TOOL.SOURCES[family][0], Path(directory) / 'current', mode)
            self.assertIn('REGRESSION', TOOL.validate_observation(current, baseline=False))

    def test_deseq2_all_current_publication_controls(self):
        self.check_current_modes('deseq2')

    def test_limma_all_current_publication_controls(self):
        self.check_current_modes('limma')

    def check_current_modes(self, family):
        with tempfile.TemporaryDirectory() as directory:
            for mode in TOOL.MODES:
                with self.subTest(mode=mode):
                    record = TOOL.trial(ROOT / TOOL.SOURCES[family][0], Path(directory) / mode, mode)
                    TOOL.validate_observation(record, baseline=False)

    def test_deleted_foreign_cannot_pass_current_contract(self):
        record = self.actual('limma', 'foreign-stage-child')
        with self.assertRaisesRegex(ValueError, 'preserve foreign'):
            TOOL.validate_observation(record, baseline=False)

    def test_observation_requires_strict_boolean(self):
        with self.assertRaises(ValueError):
            TOOL.parse_observation('mode\treturned_success\ncontrol\t1\n')

    def test_no_payload_or_package_execution_in_fragment(self):
        self.assertNotIn('library(', TOOL.R_PROGRAM)
        self.assertNotIn('requireNamespace(', TOOL.R_PROGRAM)
        self.assertIn('parse(source_path', TOOL.R_PROGRAM)
        self.assertIn('scientific_computation_executed=FALSE', TOOL.R_PROGRAM)

    def source_audit(self, family):
        relative, expected = TOOL.SOURCES[family]
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'original.R'
            source.write_bytes(subprocess.run(['git', '-C', str(ROOT), 'show',
                TOOL.BASELINE_REVISION + ':' + relative], check=True, capture_output=True).stdout)
            self.assertEqual(TOOL.file_fact(source)['sha256'], expected)
            return TOOL.audit_sources(source, ROOT / relative, Path(directory) / 'audit')

    def test_deseq2_statistical_AST_and_helper_fault_controls(self):
        record = self.source_audit('deseq2')
        self.assertTrue(record['statistical_AST_exact'])
        self.assertEqual(len(record['helper_controls']), 5)

    def test_limma_statistical_AST_and_helper_fault_controls(self):
        record = self.source_audit('limma')
        self.assertTrue(record['original_helpers_AST_exact'])
        self.assertEqual(len(record['helper_controls']), 5)

    def test_original_changed_statistical_AST_must_refuse(self):
        relative, _ = TOOL.SOURCES['deseq2']
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'original.R'
            source.write_bytes(subprocess.run(['git', '-C', str(ROOT), 'show',
                TOOL.BASELINE_REVISION + ':' + relative], check=True, capture_output=True).stdout)
            changed = Path(directory) / 'changed.R'
            changed.write_text((ROOT / relative).read_text().replace('alpha <- as.numeric(',
                'alpha <- as.integer(', 1))
            with self.assertRaisesRegex(ValueError, 'statistical AST/helper equality failed'):
                TOOL.audit_sources(source, changed, Path(directory) / 'audit')

    def test_two_family_identity_helpers_same_AST(self):
        program = '''
sources <- commandArgs(TRUE)
extract <- function(path) {
 answer <- list()
 for(value in parse(path,keep.source=FALSE)) if(is.call(value) &&
   identical(value[[1]],as.name("<-")) && as.character(value[[2]]) %in%
   c("publication_identity","publication_file_identity","publication_remove_owned_file"))
   answer[[as.character(value[[2]])]] <- value[[3]]
 answer
}
first <- extract(sources[[1]])
second <- extract(sources[[2]])
stopifnot(length(first)==3L,identical(first,second))
'''
        result = subprocess.run(['Rscript', '--vanilla', '-',
            str(ROOT / TOOL.SOURCES['deseq2'][0]), str(ROOT / TOOL.SOURCES['limma'][0])],
            input=program, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
