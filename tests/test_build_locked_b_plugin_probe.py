"""Small self-cleaning source contracts, without invoking Cargo or containers."""

import hashlib
import inspect
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from tools import build_locked_b_plugin_probe as builder


class LockedPluginProbeBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / 'repository'
        self.exported = self.root / 'exported'
        self.snapshots = self.root / 'snapshots'
        self.payloads = {name: ('toy-native-source-' + str(index)).encode()
            for index, name in enumerate(builder.KERNEL_SOURCE_PINS)}
        self.pins = {name: hashlib.sha256(payload).hexdigest() for name, payload in self.payloads.items()}
        for name, payload in self.payloads.items():
            path = self.exported / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)

    def git_payload(self, command):
        self.assertEqual(command[:4], ['git', '-C', str(self.repository), 'show'])
        revision, name = command[4].split(':', 1)
        self.assertEqual(revision, '11f061589473cb8e4fa57d364ad7107108245de1')
        return self.payloads[name]

    def snapshot(self, callback=None):
        with mock.patch.object(builder, 'KERNEL_SOURCE_PINS', self.pins), mock.patch.object(
                builder.subprocess, 'check_output', side_effect=callback or self.git_payload):
            return builder.snapshot_kernel_sources(self.repository, self.exported, self.snapshots)

    def test_parent_probe_and_all_three_native_memory_identities_are_exact(self):
        self.assertEqual(builder.PARENT, '11f061589473cb8e4fa57d364ad7107108245de1')
        self.assertEqual(builder.PROBE_SHA, '2a23a4189c0a3df9d8c39071e0d5b33a386f342338d2076e1c29b8f97aa1c4c7')
        self.assertEqual(builder.KERNEL_SOURCE_PINS, {
            'crates/dag-core/src/resource.rs': '21c32eb20d1a4b22573b1032048329ee7c5f29217066123b718cbbb2b8d75e06',
            'crates/dag-core/src/resource_tests.rs': '9a80098c52b5242b8d3f34734052d0ee26a5ddac021d4ac3e90578c63697a1d7',
            'crates/dag-core/src/dag/execution/local.rs': 'da748075d402c0c1cefebe3a8a1a364f17f3eef6a085599628bc6302979765eb',
        })

    def test_exact_twenty_three_guard_inventory_matches_reviewed_probe_source(self):
        source = Path(builder.__file__).parent / 'probes/official_plugin_dag.rs'
        self.assertEqual(builder.checked_probe_source(source), builder.PROBE_SHA)
        names = re.findall(r'#\[test\]\s*fn\s+([^\s(]+)', source.read_text())
        self.assertEqual(len(names), 23)
        self.assertEqual({'transport_tests::' + name for name in names}, builder.GUARDS)

    def test_checked_probe_accepts_only_reviewed_regular_bytes(self):
        path = self.root / 'toy-probe.rs'
        path.write_bytes(b'toy-reviewed-rust-source')
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        with mock.patch.object(builder, 'PROBE_SHA', expected):
            self.assertEqual(builder.checked_probe_source(path), expected)
            path.write_bytes(b'changed')
            with self.assertRaises(RuntimeError):
                builder.checked_probe_source(path)

    def test_checked_probe_rejects_missing_and_symlink_sources(self):
        target = self.root / 'target.rs'
        target.write_bytes(b'toy')
        linked = self.root / 'linked.rs'
        linked.symlink_to(target)
        with mock.patch.object(builder, 'PROBE_SHA', hashlib.sha256(b'toy').hexdigest()):
            for path in [linked, self.root / 'missing.rs']:
                with self.subTest(path=path.name), self.assertRaises(RuntimeError):
                    builder.checked_probe_source(path)

    def test_snapshot_binds_parent_git_bytes_exported_bytes_and_saved_evidence(self):
        records = self.snapshot()
        self.assertEqual(set(records), set(self.pins))
        for name, payload in self.payloads.items():
            self.assertEqual(records[name], {'sha256': self.pins[name], 'bytes': len(payload)})
            self.assertEqual((self.snapshots / name).read_bytes(), payload)
            self.assertEqual((self.exported / name).read_bytes(), payload)

    def test_snapshot_rejects_wrong_committed_git_payload_without_old_parent_fallback(self):
        calls = []

        def changed_git(command):
            calls.append(command)
            return self.git_payload(command) + b'wrong'

        with self.assertRaises(RuntimeError):
            self.snapshot(changed_git)
        self.assertEqual(len(calls), 1)
        self.assertFalse(self.snapshots.exists())

    def test_snapshot_rejects_changed_exported_source(self):
        name = next(iter(self.payloads))
        (self.exported / name).write_bytes(b'old-sdk-or-dirty-source')
        with self.assertRaises(RuntimeError):
            self.snapshot()
        self.assertFalse(self.snapshots.exists())

    def test_snapshot_rejects_missing_exported_source(self):
        name = next(iter(self.payloads))
        (self.exported / name).unlink()
        with self.assertRaises(RuntimeError):
            self.snapshot()

    def test_snapshot_rejects_exported_symlink_even_when_target_bytes_match(self):
        name = next(iter(self.payloads))
        target = self.root / 'foreign-source.rs'
        target.write_bytes(self.payloads[name])
        (self.exported / name).unlink()
        (self.exported / name).symlink_to(target)
        with self.assertRaises(RuntimeError):
            self.snapshot()
        self.assertEqual(target.read_bytes(), self.payloads[name])

    def test_snapshot_never_overwrites_existing_evidence(self):
        name = next(iter(self.payloads))
        existing = self.snapshots / name
        existing.parent.mkdir(parents=True)
        existing.write_bytes(b'preserve-existing-evidence')
        with self.assertRaises(FileExistsError):
            self.snapshot()
        self.assertEqual(existing.read_bytes(), b'preserve-existing-evidence')

    def test_main_keeps_canonical_offline_locked_release_two_job_build_and_exact_guard_count(self):
        source = inspect.getsource(builder.main)
        self.assertIn("Path.home()/'.cache/localdeploy-target'", source)
        self.assertIn("'--release','--locked','--offline','-j','2'", source)
        self.assertIn("CARGO_BUILD_JOBS='2'", source)
        self.assertIn("session['profile'] != 'build'", source)
        self.assertIn('len(observed)!=23 or set(observed)!=GUARDS', source)
        self.assertIn('23 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;', source)
        self.assertIn('no old executable fallback', source)
        self.assertIn('changed != [SOURCE_PATH]', source)

    def test_main_records_actual_native_snapshots_before_any_cargo_invocation(self):
        source = inspect.getsource(builder.main)
        snapshot_position = source.index('snapshot_kernel_sources(')
        self.assertLess(snapshot_position, source.index("command = ['cargo'"))
        self.assertIn("output/'kernel-source-pins.json'", source)
        self.assertIn('exported_sources_equal_committed_parent=True', source)
        self.assertIn('kernel_source_pins=kernel_sources', source)
        self.assertIn('old_sdk_fallback_allowed=False', source)
        self.assertIn('before != after', source)


if __name__ == '__main__':
    unittest.main()
