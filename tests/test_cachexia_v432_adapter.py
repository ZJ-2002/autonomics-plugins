"""Opt-in latest-design rule transport; scientific approval is never implied."""
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / 'research-adapters/cachexia-contracts'
ADAPTER = ROOT / 'research-adapters/cachexia-contracts-v432'
spec = importlib.util.spec_from_file_location('v432_contract_guard', ADAPTER / 'scripts/guards.py')
guards = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guards)


class LatestContractTests(unittest.TestCase):
    def invoke(self, active='4.3.2', planned=4):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        raw = json.dumps({'version': '4.3.2', 'planned_counts': {'A_PRIMARY_EDGES': planned},
                          'new_supportive_planned_counts': {}}, indent=2).encode()
        (directory / 'rules.json').write_bytes(raw)
        (directory / 'universe.tsv').write_text('edge_id\tfamily\n' + ''.join(
            f'E{i}\tA_PRIMARY_EDGES\n' for i in range(1, 5)))
        (directory / 'request.json').write_text(json.dumps({
            'family': 'A_PRIMARY_EDGES', 'id_column': 'edge_id',
            'results': [{'test_id': 'E1', 'raw_p': 0.001, 'status': 'ESTIMATED'}]}))
        environment = os.environ.copy()
        environment.update(CACHEXIA_OPERATION='family', AUTONOMICS_INPUT0=str(directory / 'rules.json'),
                           AUTONOMICS_INPUT1=str(directory / 'request.json'),
                           AUTONOMICS_INPUT2=str(directory / 'universe.tsv'),
                           AUTONOMICS_OUTPUT0=str(directory / 'results.tsv'),
                           AUTONOMICS_OUTPUT1=str(directory / 'audit.json'),
                           AUTONOMICS_OUTPUT2=str(directory / 'guard.log'))
        environment.pop('CACHEXIA_ACTIVE_PROTOCOL', None)
        if active is not None:
            environment['CACHEXIA_ACTIVE_PROTOCOL'] = active
        result = subprocess.run([sys.executable, '-B', str(ADAPTER / 'scripts/guards.py')],
                                env=environment, capture_output=True, timeout=20)
        return directory, raw, result

    def test_original_unified_adapter_is_unchanged(self):
        # Parent is the unified repository's d5675a3 snapshot, whose earlier
        # image/protocol adaptations are distinct from the original import.
        expected = {'manifest.toml': 'd8e3204ac3ab65336b781e13be26a5f8275ba1e476fbedf7b0c994736a261613',
                    'scripts/guards.py': 'f12dfbfc7ca168903f16efa1410399ea982521534a243dbc96dc365de79113ca'}
        for name, digest in expected.items():
            self.assertEqual(hashlib.sha256((ORIGINAL / name).read_bytes()).hexdigest(), digest)

    def test_original_method_bytes_have_only_declared_version_changes(self):
        original = (ORIGINAL / 'scripts/guards.py').read_text()
        expected = original.replace(
            '# engineering reference. The user designated v4.2.1 as the final design on\n# 2026-10-07: its role permits preparation, never scientific authorization.',
            '# engineering reference. The user designated v4.3.2 as the current design.\n# This version role permits preparation, never scientific authorization.')
        expected = expected.replace('    "4.2.1": {"role": "RESEARCH_CONTRACT"},',
                                    '    "4.2.1": {"role": "RESEARCH_CONTRACT"},\n    "4.3.2": {"role": "RESEARCH_CONTRACT"},')
        self.assertNotEqual(expected, original)
        self.assertEqual((ADAPTER / 'scripts/guards.py').read_text(), expected)

    def test_exact_latest_role_and_both_version_mix_directions(self):
        self.assertEqual(guards.resolve_active_protocol({'version': '4.3.2'},
                         {'CACHEXIA_ACTIVE_PROTOCOL': '4.3.2'}), '4.3.2')
        self.assertEqual(guards.PROTOCOLS['4.3.2']['role'], 'RESEARCH_CONTRACT')
        for declared, active in [('4.3.2', '4.2.1'), ('4.2.1', '4.3.2')]:
            with self.subTest(declared=declared), self.assertRaises(ValueError):
                guards.resolve_active_protocol({'version': declared}, {'CACHEXIA_ACTIVE_PROTOCOL': active})

    def test_ungoverned_and_unregistered_designs_stay_blocked(self):
        for environment in [{}, {'CACHEXIA_ACTIVE_PROTOCOL': '4.3.3'}]:
            with self.subTest(environment=environment), self.assertRaises(ValueError):
                guards.resolve_active_protocol({'version': environment.get('CACHEXIA_ACTIVE_PROTOCOL')}, environment)

    def test_actual_cli_retains_full_denominator_and_no_scientific_permission(self):
        directory, raw, result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        with (directory / 'results.tsv').open(newline='') as stream:
            rows = list(csv.DictReader(stream, delimiter='\t'))
        self.assertEqual([r['test_id'] for r in rows], ['E1', 'E2', 'E3', 'E4'])
        self.assertAlmostEqual(float(rows[0]['q_bh']), 0.004)
        self.assertTrue(all(r['family_size'] == '4' and r['family_status'] == 'INCOMPLETE' for r in rows))
        self.assertTrue(all(r['raw_p'] == 'NA' and r['status'] == 'NOT_RUN' and float(r['adjustment_p']) == 1 for r in rows[1:]))
        audit = json.loads((directory / 'audit.json').read_text())
        self.assertEqual(audit['config_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(audit['active_protocol'], '4.3.2')
        self.assertEqual(audit['status'], 'TECHNICAL_CONTRACT_PASS')
        self.assertIs(audit['scientific_G0_granted'], False)
        self.assertEqual((directory / 'guard.log').read_bytes(), (directory / 'audit.json').read_bytes())

    def test_actual_cli_refuses_denominator_drift_missing_or_stale_protocol(self):
        for active, planned in [('4.3.2', 3), ('4.2.1', 4), (None, 4)]:
            with self.subTest(active=active, planned=planned):
                directory, raw, result = self.invoke(active, planned)
                self.assertEqual(result.returncode, 2)
                self.assertFalse((directory / 'results.tsv').exists())
                audit = json.loads((directory / 'audit.json').read_text())
                self.assertEqual(audit['status'], 'BLOCKED')
                self.assertEqual(audit['config_sha256'], hashlib.sha256(raw).hexdigest())
                self.assertIs(audit['scientific_G0_granted'], False)

    def test_manifest_is_explicit_isolated_opt_in_with_unchanged_image(self):
        old = tomllib.loads((ORIGINAL / 'manifest.toml').read_text())
        new = tomllib.loads((ADAPTER / 'manifest.toml').read_text())
        self.assertEqual(new['image'], old['image'])
        self.assertEqual(new['plugin_name'], 'cachexia-contracts-v432')
        self.assertEqual(len(new['nodes']), 5)
        for node, original in zip(new['nodes'], old['nodes']):
            self.assertEqual(node['kind'], original['kind'])
            self.assertEqual(node['resources'], original['resources'])
            self.assertEqual(node['resources']['network'], 'isolated')
            if 'CACHEXIA_ACTIVE_PROTOCOL' in node['command']['env']:
                self.assertEqual(node['command']['env']['CACHEXIA_ACTIVE_PROTOCOL'], '4.3.2')
        from tools.catalog import inventory
        entry = next(f for f in inventory(ROOT)['families'] if f['directory'] == 'research-adapters/cachexia-contracts-v432')
        self.assertIs(entry['auto_enable'], False)
        self.assertIs(entry['scientific_certified'], False)


if __name__ == '__main__':
    unittest.main()
