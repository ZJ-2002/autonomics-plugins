import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_frozen_b_project import fixture, project


class FrozenIntakeBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.paths, self.lock = fixture(Path(self.temporary.name))

    def test_wrong_first_identity_rejected_before_payload_collection(self):
        self.paths['config'].write_bytes(self.paths['config'].read_bytes() + b'\n')
        reads = []
        original = Path.read_bytes

        def observed(path):
            reads.append(path)
            return original(path)

        with patch.object(Path, 'read_bytes', observed):
            with self.assertRaisesRegex(ValueError, 'frozen source bytes differ'):
                project.intake(self.paths, self.lock)
        self.assertEqual(reads, [])

    def test_source_order_cannot_delay_first_frozen_identity_failure(self):
        self.paths['config'].write_bytes(self.paths['config'].read_bytes() + b'\n')
        opened = []
        original = Path.open

        def observed(path, *arguments, **keywords):
            opened.append(path)
            return original(path, *arguments, **keywords)

        with patch.object(Path, 'open', observed):
            with self.assertRaisesRegex(ValueError, 'frozen source bytes differ'):
                project.intake(dict(reversed(list(self.paths.items()))), self.lock)
        self.assertFalse(set(opened) - {self.paths['config']})

    def test_total_budget_refuses_before_reading_any_source(self):
        reads = []
        original = Path.open

        def observed(path, *arguments, **keywords):
            reads.append(path)
            return original(path, *arguments, **keywords)

        total = sum(path.stat().st_size for path in self.paths.values())
        with patch.object(project, 'MAX_TOTAL_INPUT_BYTES', total - 1, create=True):
            with patch.object(Path, 'open', observed):
                with self.assertRaisesRegex(ValueError, 'aggregate input byte budget exceeded'):
                    project.intake(self.paths, self.lock)
        self.assertEqual(reads, [])

    def test_complete_toy_retains_actual_independent_unit_axis(self):
        outputs = project.intake(self.paths, self.lock)
        samples = project.rows(outputs['samples.tsv'])
        for name in ['intake.json', 'unadjusted-intake.json', 'therapy_sensitivity-intake.json']:
            receipt = json.loads(outputs[name])
            self.assertEqual(receipt['independent_unit_ids'], [row['independent_unit_id'] for row in samples])
            self.assertEqual(set(receipt['source_files']), set(project.INPUTS))

    def test_input_mutation_during_transport_is_rejected(self):
        original = project.method_config

        def changed(*arguments, **keywords):
            self.paths['source_metadata'].write_bytes(b'CHANGED after verification\n')
            return original(*arguments, **keywords)

        with patch.object(project, 'method_config', changed):
            with self.assertRaisesRegex(ValueError, 'input changed during intake'):
                project.intake(self.paths, self.lock)


if __name__ == '__main__':
    unittest.main()
