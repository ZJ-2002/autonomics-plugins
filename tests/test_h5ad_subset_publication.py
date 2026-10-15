import ast
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

from tools.published_test_source import published_source


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'plugins/single-cell/scripts/subset_by_obs.py'
TOY = b'EXPLICIT_NON_H5AD_TOY\n'
FOREIGN = b'FOREIGN_FILE_PAYLOAD\n'


def load_publish(source=None):
    tree = ast.parse(SOURCE.read_text() if source is None else source)
    names = {'ContractError', 'digest', 'publish'}
    selected = [node for node in tree.body if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    if {node.name for node in selected} != names:
        raise ValueError('Actual publication definitions missing')
    fragment = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
        *selected], type_ignores=[])
    ast.fix_missing_locations(fragment)
    namespace = dict(ExitStack=ExitStack, Path=Path, tempfile=tempfile, os=os, json=json, hashlib=hashlib,
        ad=types.SimpleNamespace(AnnData=object))
    exec(compile(fragment, str(SOURCE), 'exec'), namespace)
    return namespace['publish'], namespace['ContractError']


class FakeWriter:
    def write_h5ad(self, destination, **kwargs):
        if kwargs != dict(compression='lzf'):
            raise AssertionError('Original writer call changed')
        destination.write_bytes(TOY)


class H5ADSubsetPublicationTests(unittest.TestCase):
    def setUp(self):
        self.publish, self.error = load_publish()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.outputs = [self.root / 'output.h5ad', self.root / 'report.json']

    def invoke_hook(self, callback):
        original = os.link

        def link(source, destination, **kwargs):
            result = original(source, destination, **kwargs)
            callback(source, destination, self.outputs.index(Path(destination)))
            return result

        with mock.patch.object(os, 'link', side_effect=link):
            self.publish(FakeWriter(), {}, self.outputs)

    def test_success_checks_both_ports_and_preserves_cross_directory_support(self):
        other = self.root / 'other'
        other.mkdir()
        self.outputs[1] = other / 'report.json'
        self.publish(FakeWriter(), {}, self.outputs)
        self.assertEqual(self.outputs[0].read_bytes(), TOY)
        report = json.loads(self.outputs[1].read_text())
        self.assertEqual(report['outputs'][0]['sha256'], hashlib.sha256(TOY).hexdigest())
        self.assertEqual([path for path in self.root.rglob('.subset-*')], [])

    def test_invalid_output_count_type_and_duplicate_paths_are_rejected(self):
        for outputs in [self.outputs[:1], [*self.outputs, self.root / 'extra'], [str(self.outputs[0]), self.outputs[1]],
                        [self.outputs[0], self.outputs[0]]]:
            with self.subTest(outputs=outputs), self.assertRaises(self.error):
                self.publish(FakeWriter(), {}, outputs)

    def test_existing_files_and_dangling_links_are_not_overwritten(self):
        for position in range(2):
            self.outputs[position].write_bytes(FOREIGN)
            with self.subTest(position=position), self.assertRaises(self.error):
                self.publish(FakeWriter(), {}, self.outputs)
            self.assertEqual(self.outputs[position].read_bytes(), FOREIGN)
            self.outputs[position].unlink()
        self.outputs[0].symlink_to(self.root / 'absent')
        with self.assertRaises(self.error):
            self.publish(FakeWriter(), {}, self.outputs)
        self.assertTrue(self.outputs[0].is_symlink())

    def test_staged_symlink_is_rejected_before_any_publication(self):
        foreign = self.root / 'foreign'
        foreign.write_bytes(FOREIGN)

        class LinkedWriter:
            def write_h5ad(writer, destination, **kwargs):
                destination.symlink_to(foreign)

        with mock.patch.object(os, 'link', wraps=os.link) as called:
            with self.assertRaises(self.error):
                self.publish(LinkedWriter(), {}, self.outputs)
            self.assertEqual(called.call_count, 0)
        self.assertEqual(foreign.read_bytes(), FOREIGN)

    def test_first_port_replacement_is_rejected_and_foreign_preserved(self):
        def replace(source, destination, position):
            if position == 0:
                destination.unlink()
                destination.write_bytes(FOREIGN)
        with self.assertRaises(self.error):
            self.invoke_hook(replace)
        self.assertEqual(self.outputs[0].read_bytes(), FOREIGN)
        self.assertFalse(self.outputs[1].exists())

    def test_last_port_replacement_rolls_back_only_owned_first_port(self):
        def replace(source, destination, position):
            if position == 1:
                destination.unlink()
                destination.write_bytes(FOREIGN)
        with self.assertRaises(self.error):
            self.invoke_hook(replace)
        self.assertFalse(self.outputs[0].exists())
        self.assertEqual(self.outputs[1].read_bytes(), FOREIGN)

    def test_same_inode_same_size_content_changes_cannot_pass_or_be_deleted(self):
        for replaced in range(2):
            with self.subTest(port=replaced):
                def modify(source, destination, position):
                    if position == replaced:
                        original = destination.stat().st_ino
                        destination.write_bytes(b'X' * destination.stat().st_size)
                        self.assertEqual(destination.stat().st_ino, original)
                with self.assertRaises(self.error):
                    self.invoke_hook(modify)
                self.assertEqual(self.outputs[replaced].read_bytes(), b'X' * self.outputs[replaced].stat().st_size)
                self.assertFalse(self.outputs[1 - replaced].exists())
                self.outputs[replaced].unlink()

    def test_later_link_cannot_replace_an_earlier_checked_port_silently(self):
        def replace(source, destination, position):
            if position == 1:
                self.outputs[0].unlink()
                self.outputs[0].write_bytes(FOREIGN)
        with self.assertRaises(self.error):
            self.invoke_hook(replace)
        self.assertEqual(self.outputs[0].read_bytes(), FOREIGN)
        self.assertFalse(self.outputs[1].exists())

    def test_later_link_cannot_modify_earlier_owned_inode_silently(self):
        def modify(source, destination, position):
            if position == 1:
                self.outputs[0].write_bytes(b'X' * len(TOY))
        with self.assertRaises(self.error):
            self.invoke_hook(modify)
        self.assertEqual(self.outputs[0].read_bytes(), b'X' * len(TOY))
        self.assertFalse(self.outputs[1].exists())

    def test_symlink_replacement_is_preserved_without_reading_its_target_as_owned(self):
        foreign = self.root / 'foreign'
        foreign.write_bytes(FOREIGN)
        def replace(source, destination, position):
            if position == 1:
                destination.unlink()
                destination.symlink_to(foreign)
        with self.assertRaises(self.error):
            self.invoke_hook(replace)
        self.assertTrue(self.outputs[1].is_symlink())
        self.assertEqual(foreign.read_bytes(), FOREIGN)
        self.assertFalse(self.outputs[0].exists())

    def test_second_link_oserror_rolls_back_first_port(self):
        original = os.link
        def fail(source, destination, **kwargs):
            if destination == self.outputs[1]:
                raise OSError('injected second link failure')
            return original(source, destination, **kwargs)
        with mock.patch.object(os, 'link', side_effect=fail), self.assertRaises(OSError):
            self.publish(FakeWriter(), {}, self.outputs)
        self.assertTrue(all(not path.exists() for path in self.outputs))

    def test_link_exception_without_success_confirmation_preserves_unowned_path(self):
        original = os.link
        def fail(source, destination, **kwargs):
            original(source, destination, **kwargs)
            raise RuntimeError('injected non-OSError after link')
        with mock.patch.object(os, 'link', side_effect=fail), self.assertRaises(RuntimeError):
            self.publish(FakeWriter(), {}, self.outputs)
        self.assertEqual(self.outputs[0].read_bytes(), TOY)
        self.assertFalse(self.outputs[1].exists())

    def test_eexist_on_foreign_hardlink_with_matching_identity_never_authorizes_deletion(self):
        for replaced in range(2):
            with self.subTest(port=replaced):
                original = os.link
                def conflict(source, destination, **kwargs):
                    if destination == self.outputs[replaced]:
                        original(source, destination, **kwargs)
                    return original(source, destination, **kwargs)
                with mock.patch.object(os, 'link', side_effect=conflict), self.assertRaises(FileExistsError):
                    self.publish(FakeWriter(), {}, self.outputs)
                self.assertTrue(self.outputs[replaced].exists())
                self.assertFalse(self.outputs[1 - replaced].exists())
                self.outputs[replaced].unlink()

    def test_all_staged_identities_are_frozen_before_the_first_link(self):
        def modify(source, destination, position):
            if position == 0:
                staging = [path for path in self.root.glob('.subset-*/report.json')]
                self.assertEqual(len(staging), 1)
                staging[0].write_bytes(b'X' * staging[0].stat().st_size)
        with self.assertRaises(self.error):
            self.invoke_hook(modify)
        self.assertTrue(all(not path.exists() for path in self.outputs))

    def test_every_non_publication_ast_node_is_unchanged_from_published_baseline(self):
        original = published_source('plugins/single-cell/scripts/subset_by_obs.py',
            'b4712c853b1a605b3fa9a9cf2c3c6ddf2e7d1536',
            '0db6f4caadbb28f679f2d813c60de33d3c74ca1111934f01389b182306b088ec')
        def core(raw):
            tree = ast.parse(raw)
            tree.body = [node for node in tree.body if not
                (isinstance(node, ast.FunctionDef) and node.name == 'publish')]
            return ast.dump(tree, include_attributes=False)
        expected = core(original)
        self.assertEqual(core(SOURCE.read_bytes()), expected)
        # A same-interpreter comparison must still detect real method mutations.
        changed = original + b'\nUNDECLARED_METHOD_CHANGE = True\n'
        self.assertNotEqual(core(changed), expected)

    def test_subset_and_run_ast_are_exactly_unchanged_from_published_baseline(self):
        original = published_source('plugins/single-cell/scripts/subset_by_obs.py',
            'b4712c853b1a605b3fa9a9cf2c3c6ddf2e7d1536',
            '0db6f4caadbb28f679f2d813c60de33d3c74ca1111934f01389b182306b088ec')
        def functions(raw):
            return {node.name: ast.dump(node, include_attributes=False)
                for node in ast.parse(raw).body if isinstance(node, ast.FunctionDef)
                and node.name in {'subset', 'run'}}
        expected = functions(original)
        self.assertEqual(set(expected), {'subset', 'run'})
        self.assertEqual(functions(SOURCE.read_bytes()), expected)
        changed = ast.parse(original)
        subset = next(node for node in changed.body if isinstance(node, ast.FunctionDef) and node.name == 'subset')
        subset.body.append(ast.Return(value=ast.Constant('UNDECLARED_METHOD_CHANGE')))
        self.assertNotEqual(ast.dump(subset, include_attributes=False), expected['subset'])



if __name__ == '__main__':
    unittest.main()
