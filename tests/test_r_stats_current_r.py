from pathlib import Path
import hashlib
import json
import subprocess
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CurrentRStatisticsCandidateTests(unittest.TestCase):
    def test_six_canonical_operations_use_the_existing_fixed_r_image(self):
        manifest = tomllib.loads((ROOT / 'plugins/r-stats/manifest.toml').read_text())
        self.assertEqual(manifest['plugin_name'], 'r-stats')
        self.assertEqual(manifest['status'], 'validating')
        self.assertEqual(manifest['image']['reference'], 'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d')
        expected = dict(t_test='t', cor_test='cor', var_test='var', wilcox_test='wilcox', prop_test='prop', p_adjust='adjust')
        self.assertEqual({node['kind'] for node in manifest['nodes']}, set(expected))
        for node in manifest['nodes']:
            self.assertEqual(len(node['ports']['inputs']), 2)
            self.assertTrue(all(port['type'] == 'file' for port in node['ports']['inputs']))
            self.assertEqual(len(node['ports']['outputs']), 5)
            self.assertEqual(node['command']['env']['STATISTICS_OPERATION'], expected[node['kind']])
            self.assertEqual(node['command']['env']['R_PROFILE_USER'], '/dev/null')
            self.assertEqual(node['command']['env']['R_ENVIRON_USER'], '/dev/null')

    def test_only_version_and_adjustment_row_limit_change_the_frozen_wrapper(self):
        current = (ROOT / 'plugins/r-stats/scripts/statistics.R').read_text()
        legacy = (ROOT / 'research-adapters/cachexia-r-stats/scripts/statistics.R').read_text()
        expected = legacy.replace('"4.5.1"', '"4.6.1"').replace(
            '  if (!"row_id" %in% names(data) || nrow(data) < 1L || nrow(data) > 10000L) stop("Data needs 1..10000 explicit row identities")',
            '  max_rows <- if (operation == "adjust") 25000L else 10000L\n  if (!"row_id" %in% names(data) || nrow(data) < 1L || nrow(data) > max_rows) stop("Data needs explicit row identities within the operation row limit")')
        self.assertEqual(current, expected)

    def test_all_calculations_still_call_stats_directly(self):
        source = (ROOT / 'plugins/r-stats/scripts/statistics.R').read_text()
        for method in ['t.test', 'cor.test', 'var.test', 'wilcox.test', 'prop.test', 'p.adjust']:
            self.assertIn('stats::' + method, source)
        self.assertIn('do.call(method, args)', source)
        self.assertIn('Frozen exact=true would fall back; blocked', source)
        self.assertIn('Existing or symlink output path forbidden; no overwrite', source)

    def test_candidate_r_entry_parses_in_the_existing_local_runtime(self):
        source = ROOT / 'plugins/r-stats/scripts/statistics.R'
        result = subprocess.run(['Rscript', '--vanilla', '-e', 'invisible(parse(commandArgs(TRUE)[1]));cat("PARSE_OK")', str(source)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn(b'PARSE_OK', result.stdout)

    def test_host_evidence_does_not_grant_container_dag_or_deployment(self):
        evidence = json.loads((ROOT / 'evidence/r-stats-current-r-host-20261020.json').read_text())
        for name, key in [('scripts/statistics.R', 'method_source_sha256'), ('manifest.toml', 'manifest_sha256')]:
            self.assertEqual(hashlib.sha256((ROOT / 'plugins/r-stats' / name).read_bytes()).hexdigest(), evidence[key])
        self.assertEqual(evidence['positive_full_reference_comparisons'] + evidence['specific_refusals'], evidence['current_cases'])
        self.assertEqual(evidence['current_cases'], 168)
        self.assertFalse(evidence['legacy_R_4_5_1_numeric_answers_reused'])
        for key in ['actual_container_executed', 'isolated_DAG_verified', 'resident_deployed', 'scientific_release_granted', 'g0_granted']:
            self.assertFalse(evidence[key])


if __name__ == '__main__':
    unittest.main()
