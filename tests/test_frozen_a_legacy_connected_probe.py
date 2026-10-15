"""Source-only connected legacy contracts; no SDK compilation or study execution."""

import ast
import hashlib
import inspect
from pathlib import Path
import re
import tempfile
import tomllib
import unittest
from unittest import mock

from tools import build_frozen_a_family_probe as original
from tools import build_frozen_a_legacy_connected_probe as builder


ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / 'tools/probes/frozen_a_legacy_connected_dag.rs'


def function(source, name):
    start = re.search(r'(?m)^fn ' + re.escape(name) + r'(?:<|\()', source).start()
    end = source.find('\nfn ', start + 1)
    if end < 0:
        end = source.find('\n#[cfg(test)]', start + 1)
    return source[start:end]


class FrozenALegacyConnectedProbeTests(unittest.TestCase):
    def test_preserves_all_thirty_seven_original_guard_names_and_bodies(self):
        prior = (ROOT / 'tools/probes/frozen_a_family_dag.rs').read_text()
        current = PROBE.read_text()
        original_tests = prior[prior.index('#[cfg(test)]\nmod transport_tests {'):]
        retained = current[current.index('#[cfg(test)]\nmod transport_tests {'):]
        retained = retained[:retained.index('\nconst CONNECTED_SCOPE:')]
        self.assertEqual(retained.rstrip(), original_tests.rstrip())
        self.assertTrue(original.GUARDS.issubset(builder.GUARDS))

    def test_fifty_three_exact_guards_include_sixteen_additive_connected_cases(self):
        source = PROBE.read_text()
        connected = source.split('#[cfg(test)]\nmod connected_tests {')[1]
        names = re.findall(r'#\[test\]\s*fn\s+(\w+)', connected)
        self.assertEqual(len(names), 16)
        self.assertEqual(builder.GUARDS, original.GUARDS | {'connected_tests::' + name for name in names})
        self.assertEqual(builder.EXPECTED_GUARD_COUNT, 53)
        self.assertEqual(len(builder.GUARDS), 53)
        self.assertEqual(builder.checked_probe_source(PROBE), hashlib.sha256(PROBE.read_bytes()).hexdigest())
        self.assertIn('("panel_overrides",json!([{}]))', connected)

    def test_latest_published_engine_parent_and_fixed_kernel_pins(self):
        self.assertEqual(builder.PARENT, '0593ad0e467ad7a4e5ec3f445d38f10f9a53a8f1')
        self.assertEqual(builder.KERNEL_SOURCE_PINS, original.KERNEL_SOURCE_PINS)
        self.assertEqual(builder.EXAMPLE, 'frozen_a_legacy_connected_dag')
        self.assertEqual(builder.SOURCE_PATH, 'crates/container-plugin/examples/frozen_a_legacy_connected_dag.rs')

    def test_pending_gate_or_unreviewed_probe_rejects_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'probe.rs'
            path.write_text('const CONNECTED_GATE_MANIFEST: &str = "PENDING";\n'
                            'const CONNECTED_GATE_SCRIPT: &str = "' + 'a' * 64 + '";\n')
            with mock.patch.object(builder, 'PROBE_SHA', hashlib.sha256(path.read_bytes()).hexdigest()):
                with self.assertRaisesRegex(RuntimeError, 'PENDING'):
                    builder.checked_probe_source(path)
            with self.assertRaises(RuntimeError):
                builder.checked_probe_source(path)

    def test_exact_gate_and_probe_identity_can_be_checked_without_building(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'probe.rs'
            path.write_text('const CONNECTED_GATE_MANIFEST: &str = "' + 'a' * 64 + '";\n'
                            'const CONNECTED_GATE_SCRIPT: &str = "' + 'b' * 64 + '";\n')
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            with mock.patch.object(builder, 'PROBE_SHA', checksum):
                self.assertEqual(builder.checked_probe_source(path), checksum)
                linked = path.with_name('alias.rs')
                linked.symlink_to(path)
                with self.assertRaises(RuntimeError):
                    builder.checked_probe_source(linked)
                path.write_text('changed')
                with self.assertRaises(RuntimeError):
                    builder.checked_probe_source(path)

    def test_six_manifests_preserve_all_actual_declared_method_input_output_counts(self):
        expected = {
            'research-adapters/frozen-a-input-qualification': [('frozen_a_v432_input_qualification', 9, 12)],
            'research-adapters/frozen-a-harmonisation': [('frozen_a_v432_harmonisation', 6, 5)],
            'plugins/twosamplemr-v432-a': [('twosamplemr_v432_a_exploratory', 5, 9)],
            'research-adapters/frozen-a-family-assembly': [('frozen_a_family_assemble', 10, 4), ('frozen_a_family_publish', 8, 4)],
            'research-adapters/frozen-a-family-adjustment': [('frozen_a_family_adjust', 4, 4)],
        }
        for relative, nodes in expected.items():
            manifest = tomllib.loads((ROOT / relative / 'manifest.toml').read_text())
            actual = [(node['kind'], len(node['ports']['inputs']), len(node['ports']['outputs'])) for node in manifest['nodes']]
            self.assertEqual(actual, nodes)
        self.assertEqual(sum(count for nodes in expected.values() for _, count, _ in nodes) + 23, 65)
        self.assertEqual(sum(len(nodes) for nodes in expected.values()) + 1, 7)

    def test_gate_uses_all_nine_mr_ports_and_only_gate_output_feeds_family_request(self):
        source = function(PROBE.read_text(), 'connected_edges')
        self.assertIn('for port in 0..9_u8 { bind("mr".into(), port, "gate", port); }', source)
        self.assertIn('bind("gate".into(), 0, "assemble", 9);', source)
        self.assertIn('bind("source20".into(), 0, "gate", 22);', source)
        self.assertIn('("raw",5,0),("raw",3,1)', source)
        self.assertIn('("harmonise",1,0)', source)
        self.assertNotIn('bind("mr".into(), 0, "assemble"', source)

    def test_source_mounts_are_direct_canonical_readonly_not_staged_aliases(self):
        source = PROBE.read_text()
        self.assertIn('for (port, filename) in connected_source_paths().iter().enumerate().skip(9)', source)
        self.assertIn('path: format!("/connected-inputs/{port}")', source)
        self.assertIn('read_only: true, permissions: Default::default()', source)
        self.assertIn('if port < 9 { a_raw_source_path(port) } else', source)
        self.assertIn('"format":"file","hash_content":true', function(source, 'connected_nodes'))
        self.assertIn('if path.canonicalize()?!=path', function(source, 'connected_source_facts'))
        self.assertIn('original_connected_sources != final_connected_sources', source)

    def test_new_scope_cannot_relax_old_scopes_or_invoke_synthetic_authority(self):
        source = PROBE.read_text()
        mode = function(source, 'transport_mode')
        self.assertLess(mode.index('validate_connected_job_with_pins'), mode.index('reject_family_other_scope'))
        self.assertIn('LOCKED_A_LEGACY_CONNECTED_TECHNICAL_O2_PRIMARY_NA_NOT_G0', source)
        self.assertIn('job["scope"] != CONNECTED_SCOPE && kinds.contains(&"frozen_a_legacy_family_gate")', source)
        self.assertIn('"mr_computed":false', source)
        self.assertIn('fields.remove("mr_computed")', function(source, 'apply_connected_report_scope'))
        self.assertIn('fields.remove("connected_primary_p_remains_missing")', function(source, 'apply_connected_report_scope'))
        self.assertIn('fields.insert("scope_permits_mr".into(), json!(true))', source)
        self.assertIn('fields.insert("is_connected_scope".into(), json!(true))', source)
        self.assertIn('apply_connected_report_scope(&mut evidence, a_connected)', source)
        self.assertIn('"scientific_authorized": false', source)
        self.assertIn('max_concurrency: 1', source)
        self.assertIn('incremental: false', source)
        self.assertIn('input_hashing: InputHashing::ContentRequired', source)

    def test_builder_keeps_managed_profile_canonical_cache_and_both_actual_compilations(self):
        source = inspect.getsource(builder.main)
        self.assertIn("session['profile'] != 'build'", source)
        self.assertIn("Path.home()/'.cache/localdeploy-target'", source)
        self.assertIn("['cargo',operation,'--release','--locked','--offline','-j','2'", source)
        self.assertIn("[('runner','build',[]),('guards','test',['--no-run'])]", source)
        self.assertIn('set(observed)!=GUARDS', source)
        self.assertIn('len(observed)!=EXPECTED_GUARD_COUNT', source)
        self.assertIn('0 ignored; 0 measured; 0 filtered out;', source)
        self.assertIn('active_before != active_after', source)
        self.assertIn('before != after', source)

    def test_source_file_itself_parses_without_importing_build_or_sdk(self):
        ast.parse(Path(builder.__file__).read_text())


if __name__ == '__main__':
    unittest.main()
