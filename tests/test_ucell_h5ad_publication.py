import ast
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'plugins/ucell-h5ad/scripts/score.py'
BASELINE_SOURCE_SHA256 = 'a7a9dff18744e702c9caffa5d12076cd0fa008511892237b972e590d27f3b861'
BASELINE_PUBLICATION_SHA256 = '2747175419376369beeb3798fe670899b6ea0d79fcf24688a99255d647fbbfec'
NON_PUBLICATION_AST_SHA256 = '40c8ecec26d37d18bf0ec19abb9d03d0216b94d3da3030beba65e040028af69f'
TOY = b'EXPLICIT_NON_H5AD_PUBLICATION_TOY\n'
FOREIGN = b'FOREIGN_REPLACEMENT_NOT_A_RESULT\n'
BASELINE_PUBLICATION = '''def publish(data, report, output, report_path):
    published = []
    with ExitStack() as stack:
        directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='.ucell-', dir=output.parent)))
        report_directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='.ucell-', dir=report_path.parent)))
        staged, staged_report = directory / 'output.h5ad', report_directory / 'report.json'
        data.write_h5ad(staged, compression='lzf')
        report['outputs'] = [{'port': 0, 'name': output.name, 'bytes': staged.stat().st_size, 'sha256': digest(staged)}]
        report['report_hash_policy'] = 'port_1_hash_recorded_externally_not_recursively'
        staged_report.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\\n')
        for path in [staged, staged_report]:
            with path.open('rb') as handle:
                os.fsync(handle.fileno())
        try:
            for source, destination in [(staged, output), (staged_report, report_path)]:
                status = source.stat()
                os.link(source, destination)
                published.append((destination, (status.st_dev, status.st_ino)))
        except OSError:
            for destination, identity in reversed(published):
                try:
                    status = destination.lstat()
                    if (status.st_dev, status.st_ino) == identity:
                        destination.unlink()
                except FileNotFoundError:
                    pass
            raise'''


def load_publication(baseline=False):
    tree = ast.parse(SOURCE.read_bytes())
    selected = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and
                node.name in ['ContractError', 'digest', 'publish']]
    if {node.name for node in selected} != {'ContractError', 'digest', 'publish'}:
        raise ValueError('Actual publication definitions missing')
    if baseline:
        if hashlib.sha256(BASELINE_PUBLICATION.encode()).hexdigest() != BASELINE_PUBLICATION_SHA256:
            raise ValueError('Published baseline function fixture changed')
        selected = [node for node in selected if node.name != 'publish'] + ast.parse(BASELINE_PUBLICATION).body
    namespace = dict(ExitStack=ExitStack, Path=Path, tempfile=tempfile, os=os, json=json, hashlib=hashlib)
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(SOURCE), 'exec'), namespace)
    return namespace['publish'], namespace['ContractError']


class FakeWriter:
    def write_h5ad(self, destination, **keywords):
        if keywords != dict(compression='lzf'):
            raise AssertionError('Original H5AD writer invocation changed')
        destination.write_bytes(TOY)


class UCellH5ADPublicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.outputs = [self.root / 'output.h5ad', self.root / 'report.json']
        self.publish, self.error = load_publication()

    def invoke(self, callback, *, baseline=False):
        publisher = load_publication(True)[0] if baseline else self.publish
        original = os.link
        def link(source, destination, **keywords):
            position = self.outputs.index(Path(destination))
            return callback(original, Path(source), Path(destination), position, keywords)
        with mock.patch.object(os, 'link', side_effect=link):
            publisher(FakeWriter(), {}, *self.outputs)

    def test_all_nonpublication_source_ast_is_exactly_unchanged(self):
        tree = ast.parse(SOURCE.read_bytes())
        body = [node for node in tree.body if not (isinstance(node, ast.FunctionDef) and node.name == 'publish')]
        encoded = ast.dump(ast.Module(body=body, type_ignores=[]), include_attributes=False).encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), NON_PUBLICATION_AST_SHA256)
        self.assertEqual(hashlib.sha256(BASELINE_PUBLICATION.encode()).hexdigest(), BASELINE_PUBLICATION_SHA256)

    def test_actual_baseline_deletes_same_inode_foreign_write_after_later_failure(self):
        reached = []
        def mutate(original, source, destination, position, keywords):
            reached.append(position)
            if position == 1:
                raise OSError('CONTROLLED_SECOND_LINK_FAILURE')
            result = original(source, destination, **keywords)
            destination.write_bytes(FOREIGN)
            return result
        with self.assertRaises(OSError):
            self.invoke(mutate, baseline=True)
        self.assertEqual(reached, [0, 1])
        self.assertFalse(self.outputs[0].exists())

    def test_actual_baseline_silently_accepts_first_last_or_earlier_port_replacement(self):
        for mode in ['first', 'last', 'earlier']:
            with self.subTest(mode=mode):
                def mutate(original, source, destination, position, keywords):
                    result = original(source, destination, **keywords)
                    if mode == 'first' and position == 0 or mode == 'last' and position == 1:
                        destination.unlink()
                        destination.write_bytes(FOREIGN)
                    elif mode == 'earlier' and position == 1:
                        self.outputs[0].write_bytes(FOREIGN)
                    return result
                self.invoke(mutate, baseline=True)
                affected = 1 if mode == 'last' else 0
                self.assertEqual(self.outputs[affected].read_bytes(), FOREIGN)
                for path in self.outputs:
                    path.unlink()

    def test_normal_two_complete_output_bytes_equal_baseline_across_directories(self):
        other = self.root / 'other'
        other.mkdir()
        self.outputs[1] = other / 'report.json'
        old, _ = load_publication(True)
        old(FakeWriter(), {}, *self.outputs)
        expected = [path.read_bytes() for path in self.outputs]
        for path in self.outputs:
            path.unlink()
        self.publish(FakeWriter(), {}, *self.outputs)
        self.assertEqual([path.read_bytes() for path in self.outputs], expected)
        self.assertEqual(list(self.root.rglob('.ucell-*')), [])

    def test_existing_files_and_dangling_links_are_preserved_without_link_attempt(self):
        for position in range(2):
            with self.subTest(port=position):
                self.outputs[position].write_bytes(FOREIGN)
                with mock.patch.object(os, 'link', wraps=os.link) as linked, self.assertRaises(self.error):
                    self.publish(FakeWriter(), {}, *self.outputs)
                self.assertEqual(linked.call_count, 0)
                self.assertEqual(self.outputs[position].read_bytes(), FOREIGN)
                self.outputs[position].unlink()
        self.outputs[0].symlink_to(self.root / 'absent')
        with self.assertRaises(self.error):
            self.publish(FakeWriter(), {}, *self.outputs)
        self.assertTrue(self.outputs[0].is_symlink())

    def test_output_types_and_duplicate_paths_are_rejected(self):
        for outputs in [[str(self.outputs[0]), self.outputs[1]], [self.outputs[0], self.outputs[0]]]:
            with self.subTest(outputs=outputs), self.assertRaises(self.error):
                self.publish(FakeWriter(), {}, *outputs)

    def test_first_and_last_foreign_inode_replacements_refuse_and_preserve_foreign(self):
        for affected in range(2):
            with self.subTest(port=affected):
                def mutate(original, source, destination, position, keywords):
                    result = original(source, destination, **keywords)
                    if position == affected:
                        destination.unlink()
                        destination.write_bytes(FOREIGN)
                    return result
                with self.assertRaises(self.error):
                    self.invoke(mutate)
                self.assertEqual(self.outputs[affected].read_bytes(), FOREIGN)
                self.assertFalse(self.outputs[1 - affected].exists())
                self.outputs[affected].unlink()

    def test_same_inode_same_size_write_is_refused_and_never_rolled_back_as_owned(self):
        for affected in range(2):
            with self.subTest(port=affected):
                def mutate(original, source, destination, position, keywords):
                    result = original(source, destination, **keywords)
                    if position == affected:
                        inode = destination.stat().st_ino
                        destination.write_bytes(b'X' * destination.stat().st_size)
                        self.assertEqual(destination.stat().st_ino, inode)
                    return result
                with self.assertRaises(self.error):
                    self.invoke(mutate)
                self.assertEqual(self.outputs[affected].read_bytes(), b'X' * self.outputs[affected].stat().st_size)
                self.assertFalse(self.outputs[1 - affected].exists())
                self.outputs[affected].unlink()

    def test_same_inode_write_refuses_before_a_later_link_can_mask_it(self):
        linked = []
        def mutate(original, source, destination, position, keywords):
            linked.append(position)
            if position == 1:
                raise OSError('CONTROLLED_SECOND_LINK_FAILURE')
            result = original(source, destination, **keywords)
            destination.write_bytes(FOREIGN)
            return result
        with self.assertRaises(self.error):
            self.invoke(mutate)
        self.assertEqual(linked, [0])
        self.assertEqual(self.outputs[0].read_bytes(), FOREIGN)

    def test_same_inode_mode_change_is_refused_and_preserved(self):
        expected = []
        def mutate(original, source, destination, position, keywords):
            result = original(source, destination, **keywords)
            if position == 0:
                destination.chmod(0o600)
                expected.append(destination.stat().st_mode)
            return result
        with self.assertRaises(self.error):
            self.invoke(mutate)
        self.assertEqual(self.outputs[0].stat().st_mode, expected[0])
        self.assertEqual(self.outputs[0].read_bytes(), TOY)
        self.assertFalse(self.outputs[1].exists())

    def test_later_link_cannot_rewrite_or_replace_an_earlier_checked_port(self):
        for replace in [False, True]:
            with self.subTest(replace=replace):
                def mutate(original, source, destination, position, keywords):
                    result = original(source, destination, **keywords)
                    if position == 1:
                        if replace:
                            self.outputs[0].unlink()
                        self.outputs[0].write_bytes(FOREIGN)
                    return result
                with self.assertRaises(self.error):
                    self.invoke(mutate)
                self.assertEqual(self.outputs[0].read_bytes(), FOREIGN)
                self.assertFalse(self.outputs[1].exists())
                self.outputs[0].unlink()

    def test_later_stage_replacement_is_not_adopted_after_first_link(self):
        captured = []
        def mutate(original, source, destination, position, keywords):
            result = original(source, destination, **keywords)
            if position == 0:
                report_stage = next(self.root.glob('.ucell-*/report.json'))
                report_stage.unlink()
                report_stage.write_bytes(FOREIGN)
                captured.append(report_stage)
            return result
        with self.assertRaises(self.error):
            self.invoke(mutate)
        self.assertEqual(captured[0].read_bytes(), FOREIGN)
        self.assertTrue(all(not path.exists() for path in self.outputs))

    def test_output_symlink_replacement_is_preserved_without_reading_its_target(self):
        foreign = self.root / 'foreign'
        foreign.write_bytes(FOREIGN)
        def mutate(original, source, destination, position, keywords):
            result = original(source, destination, **keywords)
            if position == 1:
                destination.unlink()
                destination.symlink_to(foreign)
            return result
        with self.assertRaises(self.error):
            self.invoke(mutate)
        self.assertTrue(self.outputs[1].is_symlink())
        self.assertEqual(foreign.read_bytes(), FOREIGN)
        self.assertFalse(self.outputs[0].exists())

    def test_staged_symlink_is_refused_before_any_link_and_preserved(self):
        foreign = self.root / 'foreign'
        foreign.write_bytes(FOREIGN)
        captured = []
        class LinkedWriter:
            def write_h5ad(writer, destination, **keywords):
                destination.symlink_to(foreign)
                captured.append(destination)
        with mock.patch.object(os, 'link', wraps=os.link) as linked, self.assertRaises(self.error):
            self.publish(LinkedWriter(), {}, *self.outputs)
        self.assertEqual(linked.call_count, 0)
        self.assertTrue(captured[0].is_symlink())
        self.assertEqual(foreign.read_bytes(), FOREIGN)

    def test_writer_replaced_stage_directory_cannot_supply_approved_foreign_file(self):
        captured = []
        class ReplacedWriter:
            def write_h5ad(writer, destination, **keywords):
                moved = destination.parent.with_name(destination.parent.name + '-moved')
                destination.parent.rename(moved)
                destination.parent.mkdir()
                sentinel = destination.parent / 'foreign-sentinel'
                sentinel.write_bytes(FOREIGN)
                destination.write_bytes(FOREIGN)
                captured.extend([destination, sentinel])
        with mock.patch.object(os, 'link', wraps=os.link) as linked, \
                self.assertRaisesRegex(self.error, 'staging directory identity changed'):
            self.publish(ReplacedWriter(), {}, *self.outputs)
        self.assertEqual(linked.call_count, 0)
        self.assertTrue(all(path.read_bytes() == FOREIGN for path in captured))
        self.assertTrue(all(not path.exists() for path in self.outputs))

    def test_stage_directory_replaced_before_writer_is_refused_without_writing(self):
        original = tempfile.mkdtemp
        created, foreign = [], []
        def replace(*arguments, **keywords):
            result = original(*arguments, **keywords)
            created.append(Path(result))
            if len(created) == 2:
                moved = created[0].with_name(created[0].name + '-moved')
                created[0].rename(moved)
                created[0].mkdir()
                path = created[0] / 'output.h5ad'
                path.write_bytes(FOREIGN)
                foreign.append(path)
            return result
        writer = mock.Mock()
        with mock.patch.object(tempfile, 'mkdtemp', side_effect=replace), \
                mock.patch.object(os, 'link', wraps=os.link) as linked, \
                self.assertRaisesRegex(self.error, 'staging directory identity changed'):
            self.publish(writer, {}, *self.outputs)
        writer.write_h5ad.assert_not_called()
        self.assertEqual(linked.call_count, 0)
        self.assertEqual(foreign[0].read_bytes(), FOREIGN)

    def test_staging_directory_mode_change_is_rejected_before_hash_approval(self):
        captured = []
        class ModeChangedWriter:
            def write_h5ad(writer, destination, **keywords):
                destination.write_bytes(FOREIGN)
                destination.parent.chmod(0o755)
                captured.append(destination)
        with mock.patch.object(os, 'link', wraps=os.link) as linked, \
                self.assertRaisesRegex(self.error, 'staging directory identity changed'):
            self.publish(ModeChangedWriter(), {}, *self.outputs)
        self.assertEqual(linked.call_count, 0)
        self.assertEqual(captured[0].read_bytes(), FOREIGN)

    def test_second_link_error_rolls_back_only_the_confirmed_owned_first_port(self):
        def fail(original, source, destination, position, keywords):
            if position == 1:
                raise OSError('CONTROLLED_SECOND_LINK_FAILURE')
            return original(source, destination, **keywords)
        with self.assertRaises(OSError):
            self.invoke(fail)
        self.assertTrue(all(not path.exists() for path in self.outputs))
        self.assertEqual(list(self.root.rglob('.ucell-*')), [])

    def test_racing_eexist_same_inode_foreign_hard_link_is_not_deleted(self):
        for affected in range(2):
            with self.subTest(port=affected):
                def fail(original, source, destination, position, keywords):
                    if position == affected:
                        original(source, destination, **keywords)
                    return original(source, destination, **keywords)
                with self.assertRaises(FileExistsError):
                    self.invoke(fail)
                self.assertTrue(self.outputs[affected].is_file())
                self.assertFalse(self.outputs[1 - affected].exists())
                self.outputs[affected].unlink()

    def test_link_raises_after_creation_without_confirmation_preserves_uncertain_file(self):
        def fail(original, source, destination, position, keywords):
            original(source, destination, **keywords)
            raise ValueError('CONTROLLED_AFTER_LINK_WITHOUT_RETURN')
        with self.assertRaises(ValueError):
            self.invoke(fail)
        self.assertEqual(self.outputs[0].read_bytes(), TOY)
        self.assertFalse(self.outputs[1].exists())

    def test_cleanup_does_not_recursively_delete_a_foreign_stage_child(self):
        captured = []
        def mutate(original, source, destination, position, keywords):
            result = original(source, destination, **keywords)
            if position == 0:
                sentinel = source.parent / 'foreign-child'
                sentinel.write_bytes(FOREIGN)
                captured.append(sentinel)
            return result
        self.invoke(mutate)
        self.assertEqual(captured[0].read_bytes(), FOREIGN)
        self.assertEqual(self.outputs[0].read_bytes(), TOY)

    def test_cleanup_preserves_replaced_stage_directory(self):
        captured = []
        def mutate(original, source, destination, position, keywords):
            result = original(source, destination, **keywords)
            if position == 1:
                moved = source.parent.with_name(source.parent.name + '-moved')
                source.parent.rename(moved)
                source.parent.mkdir()
                sentinel = source.parent / 'foreign-child'
                sentinel.write_bytes(FOREIGN)
                captured.append(sentinel)
            return result
        with self.assertRaisesRegex(self.error, 'staging directory identity changed'):
            self.invoke(mutate)
        self.assertEqual(captured[0].read_bytes(), FOREIGN)
        self.assertTrue(all(not path.exists() for path in self.outputs))

    def test_post_cleanup_check_refuses_mutation_during_final_directory_retirement(self):
        original = Path.rmdir
        reached = []
        def retire(path):
            result = original(path)
            if not reached:
                self.outputs[0].write_bytes(FOREIGN)
                reached.append(path)
            return result
        with mock.patch.object(Path, 'rmdir', retire), self.assertRaises(self.error):
            self.publish(FakeWriter(), {}, *self.outputs)
        self.assertEqual(len(reached), 1)
        self.assertEqual(self.outputs[0].read_bytes(), FOREIGN)
        self.assertFalse(self.outputs[1].exists())


if __name__ == '__main__':
    unittest.main()
