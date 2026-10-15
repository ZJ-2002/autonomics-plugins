"""Regression for approved-source execution, including the published old loader."""

import ast
import hashlib
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'research-adapters/frozen-a-family-assembly/scripts/family.py'
SPEC = importlib.util.spec_from_file_location('family_source_identity_under_test', SCRIPT)
FAMILY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FAMILY)
OLD_COMMIT = '10ee527'
OLD_WHOLE_SHA = '3370bf9a604de0c3e6acab9e1e7617f7caba579c6630e96f17e0d2f4c002d1ba'
OLD_HELPERS_SHA = 'fbf5a9e4368ab303a1a7c96ca796470901d02f5966d93e268772ff0f8d4c1cfc'
OLD_HELPERS = '''def helpers(path):
    loader = importlib.machinery.SourceFileLoader('frozen_a_family_original_helpers', str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return {name: getattr(module, name) for name in FUNCTIONS}
'''
TOY_SOURCE = ('''def primary_p(*arguments, **keywords):
    return 'APPROVED_TOY_FUNCTION'
def strict_conjunction(*arguments, **keywords):
    return 'APPROVED_TOY_FUNCTION'
def assert_locked_ids(*arguments, **keywords):
    return 'APPROVED_TOY_FUNCTION'
''' + 'TOY_PADDING = ' + repr('x' * 512) + '\n').encode()


class FrozenAHelperSourceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='approved-family-source-toy-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'original-helpers.staged'
        self.source.write_bytes(TOY_SOURCE)
        self.marker = self.root / 'unapproved-code-executed.txt'
        self.production_sources = tuple(FAMILY.SOURCES)
        replacement = list(FAMILY.SOURCES)
        replacement[7] = (replacement[7][0], len(TOY_SOURCE), hashlib.sha256(TOY_SOURCE).hexdigest())
        patcher = mock.patch.object(FAMILY, 'SOURCES', replacement)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.foreign = ('from pathlib import Path\nPath(' + repr(str(self.marker)) +
            ').write_text("UNAPPROVED TOY SOURCE EXECUTED")\n').encode() + TOY_SOURCE.split(b'TOY_PADDING', 1)[0]
        self.assertLess(len(self.foreign), len(TOY_SOURCE))
        self.foreign += b' ' * (len(TOY_SOURCE) - len(self.foreign))

    def assert_approved(self, result):
        self.assertEqual(set(result), set(FAMILY.FUNCTIONS))
        self.assertTrue(all(function() == 'APPROVED_TOY_FUNCTION' for function in result.values()))
        self.assertFalse(self.marker.exists())

    def old_helpers(self):
        namespace = dict(importlib=importlib, sys=sys, FUNCTIONS=FAMILY.FUNCTIONS)
        exec(compile(OLD_HELPERS, 'published-old-helpers-10ee527.py', 'exec'), namespace)
        return namespace['helpers']

    def test_published_baseline_fixture_and_current_source_contract_are_exact(self):
        self.assertEqual(hashlib.sha256(OLD_HELPERS.encode()).hexdigest(), OLD_HELPERS_SHA)
        self.assertEqual(OLD_WHOLE_SHA, '3370bf9a604de0c3e6acab9e1e7617f7caba579c6630e96f17e0d2f4c002d1ba')
        self.assertEqual(OLD_COMMIT, '10ee527')
        self.assertEqual(self.production_sources[7], ('02_EXECUTION/execution_utils.py', 5243,
            '2dd34cf6887e829334c2b3ba49f58be5c81b503333dc9183474208ebab49f08d'))
        tree = ast.parse(SCRIPT.read_text())
        current = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'helpers')
        source = ast.get_source_segment(SCRIPT.read_text(), current)
        self.assertIn('checksum(payload) == SOURCES[7][2]', source)
        self.assertIn("exec(compile(payload, str(path), 'exec'), module.__dict__)", source)
        self.assertNotIn('SourceFileLoader', source)

    def test_old_loader_reopens_after_approved_hash_and_executes_foreign_source(self):
        approved = FAMILY.read(self.source, expected_size=len(TOY_SOURCE))
        self.assertEqual(hashlib.sha256(approved).hexdigest(), FAMILY.SOURCES[7][2])
        original_loader = importlib.machinery.SourceFileLoader
        observed = []
        def replace_after_approval(name, path):
            self.assertEqual(Path(path), self.source)
            self.source.write_bytes(self.foreign)
            observed.append(path)
            return original_loader(name, path)
        with mock.patch.object(importlib.machinery, 'SourceFileLoader', side_effect=replace_after_approval):
            self.old_helpers()(self.source)
        self.assertEqual(observed, [str(self.source)])
        self.assertEqual(self.marker.read_text(), 'UNAPPROVED TOY SOURCE EXECUTED')

    def test_current_loader_reads_real_approved_source_and_returns_all_three_functions(self):
        self.assert_approved(FAMILY.helpers(self.source))
        self.assertFalse((self.root / '__pycache__').exists())

    def test_current_loader_refuses_same_size_replacement_before_its_bounded_read(self):
        original_read = FAMILY.read
        observed = []
        def replaced_read(path, **keywords):
            observed.append(path)
            self.source.write_bytes(self.foreign)
            return original_read(path, **keywords)
        with mock.patch.object(FAMILY, 'read', side_effect=replaced_read):
            with self.assertRaisesRegex(ValueError, 'Frozen original helper source identity differs'):
                FAMILY.helpers(self.source)
        self.assertEqual(observed, [self.source])
        self.assertFalse(self.marker.exists())

    def test_current_loader_executes_only_approved_buffer_if_path_changes_after_read(self):
        original_read = FAMILY.read
        def replace_after_read(path, **keywords):
            approved = original_read(path, **keywords)
            self.source.write_bytes(self.foreign)
            return approved
        with mock.patch.object(FAMILY, 'read', side_effect=replace_after_read):
            self.assert_approved(FAMILY.helpers(self.source))
        self.assertEqual(self.source.read_bytes(), self.foreign)

    def test_current_loader_executes_only_approved_buffer_at_final_compile_window(self):
        original_compile = compile
        observed = []
        def replace_at_compile(payload, filename, mode, **keywords):
            self.assertEqual(payload, TOY_SOURCE)
            observed.append(hashlib.sha256(payload).hexdigest())
            self.source.write_bytes(self.foreign)
            return original_compile(payload, filename, mode, **keywords)
        with mock.patch.object(FAMILY, 'compile', side_effect=replace_at_compile, create=True):
            self.assert_approved(FAMILY.helpers(self.source))
        self.assertEqual(observed, [FAMILY.SOURCES[7][2]])
        self.assertEqual(self.source.read_bytes(), self.foreign)

    def test_current_loader_refuses_bad_hash_or_bad_size_without_execution(self):
        for payload in (self.foreign, b'', self.foreign + b'EXTRA'):
            with self.subTest(size=len(payload)):
                self.source.write_bytes(payload)
                with self.assertRaisesRegex(ValueError, 'Frozen original helper source identity differs|Frozen input size differs'):
                    FAMILY.helpers(self.source)
                self.assertFalse(self.marker.exists())

    def test_current_loader_refuses_symlink_leaf_and_symlink_parent(self):
        linked = self.root / 'linked-source'
        linked.symlink_to(self.source)
        parent_alias = self.root / 'linked-parent'
        parent_alias.symlink_to(self.root, target_is_directory=True)
        for path in (linked, parent_alias / self.source.name):
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, 'Unaliased regular input required'):
                    FAMILY.helpers(path)
                self.assertFalse(self.marker.exists())


if __name__ == '__main__':
    unittest.main()
