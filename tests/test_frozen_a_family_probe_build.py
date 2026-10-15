"""Self-cleaning build-source contracts; no Cargo, containers or production mutation."""

import hashlib
import inspect
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import build_frozen_a_family_probe as builder


class FrozenAFamilyProbeBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_exact_probe_hash_and_thirty_seven_guard_inventory(self):
        source = Path(builder.__file__).parent / 'probes/frozen_a_family_dag.rs'
        self.assertEqual(builder.PROBE_SHA, '5dd86143bc70829d8caeffffc12487119681ce03512b66eccdb423d5299e2b43')
        self.assertEqual(builder.checked_probe_source(source), builder.PROBE_SHA)
        text = source.read_text()
        original, family = text.split('#[cfg(test)]\nmod family_tests {')
        original_names = re.findall(r'#\[test\]\s*fn\s+([^\s(]+)', original)
        family_names = re.findall(r'#\[test\]\s*fn\s+([^\s(]+)', family)
        observed = {'transport_tests::' + name for name in original_names}
        observed.update('family_tests::' + name for name in family_names)
        self.assertEqual((len(original_names), len(family_names)), (23, 14))
        self.assertEqual(len(observed), 37)
        self.assertEqual(observed, builder.GUARDS)

    def test_production_family_pins_are_explicit_without_pending_identity(self):
        source = (Path(builder.__file__).parent / 'probes/frozen_a_family_dag.rs').read_text()
        hashes = dict(re.findall(r'const (FAMILY_(?:PYTHON|R)_(?:MANIFEST|SCRIPT)): &str =\s*"([^"]+)";', source))
        self.assertEqual(len(hashes), 4)
        for value in hashes.values():
            self.assertRegex(value, r'^[0-9a-f]{64}$')
        images = re.findall(r'const FAMILY_(?:PYTHON|R)_IMAGE: &str =\s*"([^"]+)";', source)
        self.assertEqual(len(images), 2)
        for value in images:
            self.assertRegex(value, r'^[^\s@]+@sha256:[0-9a-f]{64}$')
        self.assertNotEqual(builder.PROBE_SHA, 'PENDING')

    def test_exact_fixed_engine_parent_three_kernel_sources_and_binary_name(self):
        self.assertEqual(builder.PARENT, '11f061589473cb8e4fa57d364ad7107108245de1')
        self.assertEqual(builder.EXAMPLE, 'frozen_a_family_dag')
        self.assertEqual(builder.SOURCE_PATH, 'crates/container-plugin/examples/frozen_a_family_dag.rs')
        self.assertEqual(builder.KERNEL_SOURCE_PINS, {
            'crates/dag-core/src/resource.rs': '21c32eb20d1a4b22573b1032048329ee7c5f29217066123b718cbbb2b8d75e06',
            'crates/dag-core/src/resource_tests.rs': '9a80098c52b5242b8d3f34734052d0ee26a5ddac021d4ac3e90578c63697a1d7',
            'crates/dag-core/src/dag/execution/local.rs': 'da748075d402c0c1cefebe3a8a1a364f17f3eef6a085599628bc6302979765eb',
        })

    def test_reviewed_source_rejects_mutation_missing_and_symlink(self):
        source = self.root / 'source.rs'
        source.write_bytes(b'toy-source')
        linked = self.root / 'link.rs'
        linked.symlink_to(source)
        with mock.patch.object(builder, 'PROBE_SHA', hashlib.sha256(b'toy-source').hexdigest()):
            self.assertEqual(builder.checked_probe_source(source), builder.PROBE_SHA)
            for candidate in [linked, self.root / 'missing.rs']:
                with self.assertRaises(RuntimeError):
                    builder.checked_probe_source(candidate)
            source.write_bytes(b'changed')
            with self.assertRaises(RuntimeError):
                builder.checked_probe_source(source)

    def test_kernel_snapshot_matches_pinned_parent_export_and_saved_bytes(self):
        repository = self.root / 'repository'
        exported = self.root / 'exported'
        saved = self.root / 'saved'
        payloads = {name: ('toy-source-' + str(index)).encode()
                    for index, name in enumerate(builder.KERNEL_SOURCE_PINS)}
        pins = {name: hashlib.sha256(payload).hexdigest() for name, payload in payloads.items()}
        for name, payload in payloads.items():
            target = exported / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)

        def git_payload(command):
            self.assertEqual(command[:4], ['git', '-C', str(repository), 'show'])
            revision, name = command[4].split(':', 1)
            self.assertEqual(revision, builder.PARENT)
            return payloads[name]

        with mock.patch.object(builder, 'KERNEL_SOURCE_PINS', pins), mock.patch.object(
                builder.subprocess, 'check_output', side_effect=git_payload):
            records = builder.snapshot_kernel_sources(repository, exported, saved)
        self.assertEqual(set(records), set(pins))
        for name, payload in payloads.items():
            self.assertEqual((saved / name).read_bytes(), payload)
            self.assertEqual(records[name], {'sha256': pins[name], 'bytes': len(payload)})

    def test_kernel_snapshot_rejects_wrong_git_bytes_before_publication(self):
        exported = self.root / 'exported'
        target = exported / 'kernel.rs'
        target.parent.mkdir()
        target.write_bytes(b'expected')
        with mock.patch.object(builder, 'KERNEL_SOURCE_PINS',
                {'kernel.rs': hashlib.sha256(b'expected').hexdigest()}), mock.patch.object(
                builder.subprocess, 'check_output', return_value=b'wrong-parent'):
            with self.assertRaises(RuntimeError):
                builder.snapshot_kernel_sources(self.root, exported, self.root / 'saved')
        self.assertFalse((self.root / 'saved').exists())

    def test_private_git_environment_uses_current_temporary_index_only(self):
        before = dict(os.environ)
        environment = builder.private_git_environment(self.root)
        self.assertEqual(environment['GIT_INDEX_FILE'], str(self.root / 'frozen-a-family-probe.index'))
        self.assertEqual(dict(os.environ), before)
        self.assertEqual({key: value for key, value in environment.items() if key != 'GIT_INDEX_FILE'},
                         {key: value for key, value in before.items() if key != 'GIT_INDEX_FILE'})

    def test_private_index_candidate_keeps_actual_toy_active_head_and_index(self):
        repository = self.root / 'repository'
        repository.mkdir()
        environment = dict(os.environ, GIT_AUTHOR_NAME='Toy', GIT_AUTHOR_EMAIL='toy@example.invalid',
                           GIT_COMMITTER_NAME='Toy', GIT_COMMITTER_EMAIL='toy@example.invalid')
        environment.pop('GIT_INDEX_FILE', None)

        def git(*arguments, env=None, payload=None):
            return subprocess.check_output(['git', '-C', str(repository), *arguments],
                                           env=env or environment, input=payload).decode().strip()

        git('init', '-q')
        (repository / 'base.txt').write_text('toy base\n')
        git('add', 'base.txt')
        tree = git('write-tree')
        commit = git('commit-tree', tree, '-m', 'Initialize self-cleaning toy')
        git('update-ref', 'HEAD', commit)
        with mock.patch.dict(os.environ, environment, clear=True):
            before = builder.repository_identity(repository)
            private = builder.private_git_environment(self.root)
            git('read-tree', commit, env=private)
            blob = git('hash-object', '-w', '--stdin', env=private, payload=b'toy probe')
            git('update-index', '--add', '--cacheinfo', '100644,' + blob + ',' + builder.SOURCE_PATH, env=private)
            candidate_tree = git('write-tree', env=private)
            candidate = git('commit-tree', candidate_tree, '-p', commit, '-m', 'Toy isolated candidate', env=private)
            after = builder.repository_identity(repository)
        self.assertEqual(before, after)
        self.assertNotEqual(candidate, commit)
        self.assertEqual(git('diff-tree', '--no-commit-id', '--name-only', '-r', commit, candidate),
                         builder.SOURCE_PATH)
        self.assertTrue((self.root / 'frozen-a-family-probe.index').is_file())

    def test_active_git_identity_detects_real_toy_index_and_head_changes(self):
        repository = self.root / 'repo'
        repository.mkdir()
        index = repository / 'index'
        index.write_bytes(b'active index')
        responses = [b'first-head\n', b'index\n']

        def observe():
            with mock.patch.object(builder.subprocess, 'check_output', side_effect=responses):
                return builder.repository_identity(repository)

        first = observe()
        index.write_bytes(b'mutated index')
        self.assertNotEqual(first, observe())
        responses = [b'changed-head\n', b'index\n']
        self.assertNotEqual(first, observe())

    def test_builder_requires_exact_execution_and_never_checks_out_candidate(self):
        source = inspect.getsource(builder.main)
        self.assertIn('len(observed)!=37', source)
        self.assertIn('set(observed)!=GUARDS', source)
        self.assertIn('37 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;', source)
        self.assertIn('active_before != active_after', source)
        self.assertIn('active-git-preservation.json', source)
        self.assertIn("changed != [SOURCE_PATH]", source)
        for forbidden in ["git('checkout'", "git('reset'", "git('switch'", "git('merge'", "git('push'"]:
            self.assertNotIn(forbidden, source)


if __name__ == '__main__':
    unittest.main()
