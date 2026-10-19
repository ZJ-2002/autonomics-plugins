import ast
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'research-adapters/cachexia-permutation/scripts/permutation.py'
NAMES = ['values.parquet', 'state.pkl', 'audit.json', 'permutation.log', 'input_ledger.tsv']
AUXILIARY = 'failed-official-state.pkl'
TREE = ast.parse(SOURCE.read_text())
NAMESPACE = {'Path': Path, 'os': os, 'shutil': shutil, 'sys': sys, 'tempfile': tempfile}
FUNCTIONS = [node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name in {'require', 'publish_outputs'}]
exec(compile(ast.Module(body=FUNCTIONS, type_ignores=[]), str(SOURCE), 'exec'), NAMESPACE)


class PermutationPublicationTests(unittest.TestCase):
    def execute(self, directory, writer):
        inputs = [directory / ('input-' + str(position)) for position in range(2)]
        for filename in inputs:
            filename.write_text('{}')
        environment = {'AUTONOMICS_INPUT' + str(position): str(filename) for position, filename in enumerate(inputs)}
        environment.update({'AUTONOMICS_OUTPUT' + str(position): str(directory / name) for position, name in enumerate(NAMES)})
        with patch.dict(os.environ, environment):
            return NAMESPACE['publish_outputs'](writer)

    @staticmethod
    def products(outputs):
        for filename in outputs:
            filename.write_text('owned-product')
        return 0

    @staticmethod
    def diagnostic(outputs):
        outputs[2].write_text(json.dumps({'status': 'BLOCKED', 'G0_granted': False}))
        outputs[3].write_text('known diagnostic refusal')
        (outputs[2].parent / AUXILIARY).write_bytes(b'COMPLETE_FAILED_STATE_TOY_BYTES')
        return 2

    def test_success_has_five_ports_and_no_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.assertEqual(self.execute(directory, self.products), 0)
            self.assertTrue(all((directory / name).is_file() for name in NAMES))
            self.assertFalse(list(directory.glob('.permutation-owned-*')))

    def test_every_dangling_output_or_diagnostic_is_preserved(self):
        for name in NAMES + [AUXILIARY]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                target = directory / name
                target.symlink_to(directory / 'absent')
                self.assertEqual(self.execute(directory, self.products), 2)
                self.assertTrue(target.is_symlink())
                self.assertFalse((directory / 'absent').exists())

    def test_every_existing_output_or_diagnostic_is_preserved(self):
        for name in NAMES + [AUXILIARY]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                target = directory / name
                target.write_text('FOREIGN')
                self.assertEqual(self.execute(directory, self.products), 2)
                self.assertEqual(target.read_text(), 'FOREIGN')

    def test_late_foreign_analytical_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            def writer(outputs):
                (directory / NAMES[0]).write_text('FOREIGN')
                return self.products(outputs)
            self.assertEqual(self.execute(directory, writer), 2)
            self.assertEqual((directory / NAMES[0]).read_text(), 'FOREIGN')
            self.assertFalse((directory / NAMES[1]).exists())

    def test_diagnostic_state_is_retained_without_normal_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.assertEqual(self.execute(directory, self.diagnostic), 2)
            self.assertEqual((directory / AUXILIARY).read_bytes(), b'COMPLETE_FAILED_STATE_TOY_BYTES')
            self.assertFalse(any((directory / NAMES[position]).exists() for position in (0, 1, 4)))

    def test_late_diagnostic_collision_rolls_back_only_owned_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original = os.link
            def link(source, destination, **options):
                if Path(destination).name == AUXILIARY:
                    Path(destination).write_text('FOREIGN')
                return original(source, destination, **options)
            with patch.object(os, 'link', side_effect=link):
                self.assertEqual(self.execute(directory, self.diagnostic), 2)
            self.assertEqual((directory / AUXILIARY).read_text(), 'FOREIGN')
            self.assertFalse(any((directory / name).exists() for name in NAMES))

    def test_rollback_preserves_foreign_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original = os.link
            def link(source, destination, **options):
                if Path(destination).name == NAMES[1]:
                    (directory / NAMES[0]).unlink()
                    (directory / NAMES[0]).write_text('FOREIGN')
                    raise OSError('injected second link failure')
                return original(source, destination, **options)
            with patch.object(os, 'link', side_effect=link):
                self.assertEqual(self.execute(directory, self.products), 2)
            self.assertEqual((directory / NAMES[0]).read_text(), 'FOREIGN')

    def test_stage_is_removed_after_unhandled_writer_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            def writer(outputs):
                outputs[0].write_text('partial')
                raise ValueError('unhandled toy failure')
            self.assertEqual(self.execute(directory, writer), 2)
            self.assertFalse(list(directory.glob('.permutation-owned-*')))
            self.assertFalse(any((directory / name).exists() for name in NAMES))

    def test_boolean_writer_status_is_not_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(self.execute(Path(temporary), lambda outputs: False), 2)


if __name__ == '__main__':
    unittest.main()
