"""Self-cleaning publication tests; byte writers are not Scanpy method substitutes."""

import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.published_test_source import published_source


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'plugins/single-cell/scripts/score_genes.py'
BASELINE_SHA = '9cad19728810b8e9c9933fed33f556870419a985a12f1485ce61d4f4da8c58e8'
BASELINE_WRITES = '''data.write_h5ad(os.environ["AUTONOMICS_OUTPUT0"], compression="lzf")
Path(os.environ["AUTONOMICS_OUTPUT1"]).write_text(content)
'''
TOY = b'NON_H5AD_EXPLICIT_IO_TOY\n'
FOREIGN = b'FOREIGN_FILE_DO_NOT_CHANGE\n'


def load_source():
    specification = importlib.util.spec_from_file_location('score_genes_publication_target', SOURCE)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def scientific_core(raw=None):
    module = ast.parse(SOURCE.read_bytes() if raw is None else raw)
    functions = {node.name: node for node in module.body if isinstance(node, ast.FunctionDef)}
    body = functions['main'].body
    begin = next(index for index, node in enumerate(body) if isinstance(node, ast.If))
    end = next(index for index, node in enumerate(body) if isinstance(node, ast.Assign) and
        any(isinstance(target, ast.Name) and target.id == 'content' for target in node.targets))
    core = copy.deepcopy(ast.Module(body=[functions[name] for name in
        ['unique_object', 'parse_sets', 'integer', 'summarize']] + body[begin:end + 1], type_ignores=[]))
    for node in ast.walk(core):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == 'ad' and node.func.attr == 'read_h5ad':
            node.args = [ast.Constant('CHECKED_INPUT_FILE')]
    return hashlib.sha256(ast.dump(core, include_attributes=False).encode()).hexdigest()


class ByteWriter:
    def write_h5ad(self, path, **keywords):
        if keywords != {'compression': 'lzf'}:
            raise AssertionError('Original H5AD writer options changed')
        Path(path).write_bytes(TOY)


class OriginalScoringPublicationDefectTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'input.h5ad'
        self.source.write_bytes(b'ORIGINAL_INPUT_NOT_REAL_SCIENTIFIC_DATA')
        self.h5ad = self.root / 'output.h5ad'
        self.report = self.root / 'report.json'

    def baseline(self):
        namespace = dict(data=ByteWriter(), content='{"toy":true}\n', Path=Path,
            os=type('Environment', (), {'environ': {'AUTONOMICS_OUTPUT0': str(self.h5ad),
                'AUTONOMICS_OUTPUT1': str(self.report)}})())
        exec(compile(ast.parse(BASELINE_WRITES), 'original-score-final-two-writes', 'exec'), namespace)

    def test_original_report_input_alias_reproduces_source_truncation(self):
        self.report = self.source
        self.baseline()
        self.assertEqual(self.source.read_bytes(), b'{"toy":true}\n')

    def test_original_existing_outputs_are_overwritten(self):
        self.h5ad.write_bytes(b'FOREIGN_H5AD')
        self.report.write_bytes(b'FOREIGN_REPORT')
        self.baseline()
        self.assertEqual(self.h5ad.read_bytes(), TOY)
        self.assertEqual(self.report.read_bytes(), b'{"toy":true}\n')

    def test_original_late_report_failure_leaves_normal_h5ad(self):
        self.report = self.root / 'absent-parent' / 'report.json'
        with self.assertRaises(FileNotFoundError):
            self.baseline()
        self.assertEqual(self.h5ad.read_bytes(), TOY)


class ScoringPublicationTests(unittest.TestCase):
    def setUp(self):
        self.score = load_source()
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'input.h5ad'
        self.source.write_bytes(b'ORIGINAL_INPUT_NOT_REAL_SCIENTIFIC_DATA')
        self.outputs = [self.root / 'output.h5ad', self.root / 'report.json']
        self.content = '{"operation":"gene_set_score","scientific_signoff_granted":false}\n'

    def prepare(self, source=None):
        environment = dict(AUTONOMICS_INPUT0=str(source or self.source),
            AUTONOMICS_OUTPUT0=str(self.outputs[0]), AUTONOMICS_OUTPUT1=str(self.outputs[1]))
        with mock.patch.dict(os.environ, environment):
            return self.score.prepare_paths()

    def publish(self, writer=None, paths=None):
        self.score.publish(ByteWriter() if writer is None else writer, self.content,
            self.prepare() if paths is None else paths)

    def hook_link(self, callback, *, before=False):
        original = os.link

        def link(source, destination, **keywords):
            position = self.outputs.index(Path(destination))
            if before:
                callback(Path(source), Path(destination), position)
            result = original(source, destination, **keywords)
            if not before:
                callback(Path(source), Path(destination), position)
            return result

        return mock.patch.object(self.score.os, 'link', side_effect=link)

    def test_official_scoring_core_and_report_generation_ast_are_unchanged(self):
        original = published_source('plugins/single-cell/scripts/score_genes.py',
            'd91be9dad535e79c97fb3566b07fe1f68d0954ba', BASELINE_SHA)
        self.assertEqual(scientific_core(), scientific_core(original))
        changed = original.replace(b'ctrl_as_ref=True', b'ctrl_as_ref=False')
        self.assertNotEqual(changed, original)
        self.assertNotEqual(scientific_core(changed), scientific_core(original))
        source = SOURCE.read_text()
        self.assertIn('data = ad.read_h5ad(paths["input"])', source)
        self.assertNotIn('shutil.rmtree', source)
        self.assertNotIn('TemporaryDirectory', source)

    def test_success_materializes_both_unchanged_ports_and_cleans_owned_stages(self):
        self.publish()
        self.assertEqual(self.outputs[0].read_bytes(), TOY)
        self.assertEqual(self.outputs[1].read_text(), self.content)
        self.assertEqual(list(self.root.glob('.score-genes-*')), [])

    def test_cross_directory_outputs_remain_supported(self):
        other = self.root / 'other'
        other.mkdir()
        self.outputs[1] = other / 'report.json'
        self.publish()
        self.assertEqual(self.outputs[0].read_bytes(), TOY)
        self.assertEqual(self.outputs[1].read_text(), self.content)

    def test_report_input_alias_is_refused_without_source_truncation(self):
        before = self.source.read_bytes()
        self.outputs[1] = self.source
        with self.assertRaises(self.score.PublicationError):
            self.publish()
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse(self.outputs[0].exists())

    def test_existing_outputs_and_hardlinked_input_are_preserved(self):
        for position in range(2):
            with self.subTest(port=position):
                self.outputs[position].write_bytes(FOREIGN)
                with self.assertRaises(self.score.PublicationError):
                    self.publish()
                self.assertEqual(self.outputs[position].read_bytes(), FOREIGN)
                self.outputs[position].unlink()
        os.link(self.source, self.outputs[0])
        before = self.source.read_bytes()
        with self.assertRaises(self.score.PublicationError):
            self.publish()
        self.assertEqual(self.source.read_bytes(), before)

    def test_missing_report_parent_is_refused_before_any_method_writer(self):
        self.outputs[1] = self.root / 'missing' / 'report.json'
        writer = mock.Mock()
        with self.assertRaises(FileNotFoundError):
            self.publish(writer)
        writer.write_h5ad.assert_not_called()
        self.assertFalse(self.outputs[0].exists())

    def test_duplicate_and_symlink_parent_outputs_are_refused(self):
        second = self.outputs[1]
        self.outputs[1] = self.outputs[0]
        with self.assertRaises(self.score.PublicationError):
            self.prepare()
        self.outputs[1] = second
        alias = self.root / 'parent-alias'
        alias.symlink_to(self.root, target_is_directory=True)
        self.outputs[1] = alias / 'report.json'
        with self.assertRaises(self.score.PublicationError):
            self.prepare()

    def test_dangling_outputs_and_existing_directories_are_not_replaced(self):
        self.outputs[0].symlink_to(self.root / 'absent')
        with self.assertRaises(self.score.PublicationError):
            self.prepare()
        self.assertTrue(self.outputs[0].is_symlink())
        self.outputs[0].unlink()
        self.outputs[0].mkdir()
        with self.assertRaises(self.score.PublicationError):
            self.prepare()
        self.assertTrue(self.outputs[0].is_dir())

    def test_bound_input_symlink_is_read_as_checked_target_and_retargeting_refused(self):
        binding = self.root / 'staged-input.h5ad'
        binding.symlink_to(self.source)
        paths = self.prepare(binding)
        self.assertEqual(paths['input'], self.source)
        other = self.root / 'other-input'
        other.write_bytes(self.source.read_bytes())
        binding.unlink()
        binding.symlink_to(other)
        with self.assertRaises(self.score.PublicationError):
            self.publish(paths=paths)
        self.assertFalse(any(path.exists() for path in self.outputs))

    def test_source_change_during_writer_prevents_all_publication(self):
        source = self.source

        class MutatingWriter(ByteWriter):
            def write_h5ad(writer, path, **keywords):
                super().write_h5ad(path, **keywords)
                source.write_bytes(b'EXPLICIT_TEST_MUTATION')

        with self.assertRaises(self.score.PublicationError):
            self.publish(MutatingWriter())
        self.assertFalse(any(path.exists() for path in self.outputs))
        self.assertEqual(self.source.read_bytes(), b'EXPLICIT_TEST_MUTATION')

    def test_report_write_failure_rolls_back_no_normal_outputs(self):
        with mock.patch.object(self.score, 'write_descriptor_text', side_effect=OSError('INJECTED_REPORT_WRITE_ERROR')):
            with self.assertRaises(OSError):
                self.publish()
        self.assertFalse(any(path.exists() for path in self.outputs))

    def test_second_link_error_rolls_back_only_confirmed_owned_first_port(self):
        def fail(source, destination, position):
            if position == 1:
                raise OSError('INJECTED_SECOND_LINK')

        with self.hook_link(fail, before=True), self.assertRaises(OSError):
            self.publish()
        self.assertFalse(any(path.exists() for path in self.outputs))

    def test_nonthrowing_replaced_first_or_last_port_is_refused_and_preserved(self):
        for target in range(2):
            with self.subTest(port=target):
                def replace(source, destination, position):
                    if position == target:
                        destination.unlink()
                        destination.write_bytes(FOREIGN)
                with self.hook_link(replace), self.assertRaises(self.score.PublicationError):
                    self.publish()
                self.assertEqual(self.outputs[target].read_bytes(), FOREIGN)
                self.assertFalse(self.outputs[1 - target].exists())
                self.outputs[target].unlink()

    def test_same_inode_same_size_modified_first_or_last_port_is_preserved(self):
        for target in range(2):
            with self.subTest(port=target):
                def rewrite(source, destination, position):
                    if position == target:
                        before = destination.stat().st_ino
                        destination.write_bytes(b'X' * destination.stat().st_size)
                        self.assertEqual(destination.stat().st_ino, before)
                with self.hook_link(rewrite), self.assertRaises(self.score.PublicationError):
                    self.publish()
                self.assertEqual(self.outputs[target].read_bytes(), b'X' * self.outputs[target].stat().st_size)
                self.assertFalse(self.outputs[1 - target].exists())
                self.outputs[target].unlink()

    def test_final_complete_set_check_detects_earlier_port_changed_by_last_link(self):
        def replace(source, destination, position):
            if position == 1:
                self.outputs[0].write_bytes(b'X' * len(TOY))

        with self.hook_link(replace), self.assertRaises(self.score.PublicationError):
            self.publish()
        self.assertEqual(self.outputs[0].read_bytes(), b'X' * len(TOY))
        self.assertFalse(self.outputs[1].exists())

    def test_late_failure_does_not_delete_same_inode_modified_earlier_port(self):
        def fail(source, destination, position):
            if position == 1:
                self.outputs[0].write_bytes(b'X' * len(TOY))
                raise OSError('INJECTED_LATE_FAILURE')

        with self.hook_link(fail, before=True), self.assertRaises(OSError):
            self.publish()
        self.assertEqual(self.outputs[0].read_bytes(), b'X' * len(TOY))
        self.assertFalse(self.outputs[1].exists())

    def test_eexist_foreign_hardlink_matching_owned_inode_never_authorizes_delete(self):
        for target in range(2):
            with self.subTest(port=target):
                original = os.link

                def competing(source, destination, **keywords):
                    if self.outputs.index(Path(destination)) == target:
                        original(source, destination)
                    return original(source, destination, **keywords)

                with mock.patch.object(self.score.os, 'link', side_effect=competing), self.assertRaises(FileExistsError):
                    self.publish()
                expected = TOY if target == 0 else self.content.encode()
                self.assertEqual(self.outputs[target].read_bytes(), expected)
                self.assertFalse(self.outputs[1 - target].exists())
                self.outputs[target].unlink()

    def test_link_exception_without_success_confirmation_preserves_ambiguous_path(self):
        original = os.link

        def uncertain(source, destination, **keywords):
            original(source, destination, **keywords)
            raise RuntimeError('INJECTED_AMBIGUOUS_LINK')

        with mock.patch.object(self.score.os, 'link', side_effect=uncertain), self.assertRaises(RuntimeError):
            self.publish()
        self.assertEqual(self.outputs[0].read_bytes(), TOY)
        self.assertFalse(self.outputs[1].exists())

    def test_replaced_staging_directory_is_not_deleted_or_published(self):
        foreign = []
        original = self.score.write_stage

        def replace(stage, writer):
            def competing(destination):
                directory = stage['directory']
                directory.rename(directory.with_name(directory.name + '-original'))
                directory.mkdir()
                stage['path'].write_bytes(FOREIGN)
                foreign.append(stage['path'])
                writer(destination)
            return original(stage, competing)

        with mock.patch.object(self.score, 'write_stage', side_effect=replace), self.assertRaises(self.score.PublicationError):
            self.publish()
        self.assertEqual(foreign[0].read_bytes(), FOREIGN)
        self.assertFalse(any(path.exists() for path in self.outputs))

    def test_unknown_staging_member_is_preserved_not_recursively_deleted(self):
        foreign = []
        original = self.score.write_stage

        def extra(stage, writer):
            original(stage, writer)
            path = stage['directory'] / 'unowned-extra'
            path.write_bytes(FOREIGN)
            foreign.append(path)

        with mock.patch.object(self.score, 'write_stage', side_effect=extra):
            self.publish()
        self.assertEqual(foreign[0].read_bytes(), FOREIGN)
        self.assertEqual(self.outputs[0].read_bytes(), TOY)

    def test_staged_earlier_content_changed_before_first_link_is_not_reowned(self):
        original = self.score.write_stage
        mutated = []

        def write(stage, writer):
            original(stage, writer)
            if stage['path'].name == 'output.h5ad':
                mutated.append(stage['path'])
            else:
                mutated[0].write_bytes(FOREIGN)

        with mock.patch.object(self.score, 'write_stage', side_effect=write), self.assertRaises(self.score.PublicationError):
            self.publish()
        self.assertEqual(mutated[0].read_bytes(), FOREIGN)
        self.assertFalse(any(path.exists() for path in self.outputs))

    def test_named_stage_replacement_before_writer_is_refused_without_truncation(self):
        original = self.score.write_stage
        foreign = []

        def replace(stage, writer):
            stage['path'].unlink()
            stage['path'].write_bytes(FOREIGN)
            foreign.append(stage['path'])
            return original(stage, writer)

        with mock.patch.object(self.score, 'write_stage', side_effect=replace), self.assertRaises(self.score.PublicationError):
            self.publish()
        self.assertEqual(foreign[0].read_bytes(), FOREIGN)
        self.assertFalse(any(path.exists() for path in self.outputs))

    def test_h5ad_and_text_writers_target_owned_fd_not_replaced_named_entry(self):
        original = self.score.write_stage
        for target in ['output.h5ad', 'report.json']:
            with self.subTest(stage=target):
                foreign = []

                def replace(stage, writer):
                    def competing(descriptor_path):
                        if stage['path'].name == target:
                            stage['path'].unlink()
                            stage['path'].write_bytes(FOREIGN)
                            foreign.append(stage['path'])
                        return writer(descriptor_path)
                    return original(stage, competing)

                with mock.patch.object(self.score, 'write_stage', side_effect=replace), self.assertRaises(self.score.PublicationError):
                    self.publish()
                self.assertEqual(foreign[0].read_bytes(), FOREIGN)
                self.assertFalse(any(path.exists() for path in self.outputs))

    def test_owned_descriptors_are_closed_after_success_and_failure(self):
        original = self.score.create_stage
        descriptors = []

        def create(destination, paths):
            stage = original(destination, paths)
            descriptors.append(stage['descriptor'])
            return stage

        with mock.patch.object(self.score, 'create_stage', side_effect=create):
            self.publish()
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)
        for output in self.outputs:
            output.unlink()
        descriptors.clear()
        with mock.patch.object(self.score, 'create_stage', side_effect=create), mock.patch.object(
                self.score, 'write_descriptor_text', side_effect=OSError('INJECTED_REPORT_FAILURE')):
            with self.assertRaises(OSError):
                self.publish()
        for descriptor in descriptors:
            with self.assertRaises(OSError):
                os.fstat(descriptor)

    def test_input_change_after_last_link_rolls_back_confirmed_outputs(self):
        def change(source, destination, position):
            if position == 1:
                self.source.write_bytes(b'EXPLICIT_LATE_INPUT_MUTATION')

        with self.hook_link(change), self.assertRaises(self.score.PublicationError):
            self.publish()
        self.assertEqual(self.source.read_bytes(), b'EXPLICIT_LATE_INPUT_MUTATION')
        self.assertFalse(any(path.exists() for path in self.outputs))


if __name__ == '__main__':
    unittest.main()
