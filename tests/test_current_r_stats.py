import copy
import hashlib
import json
from pathlib import Path
import unittest

from tools import build_current_r_stats as builder
from tools import prove_current_r_stats as proof


class CurrentOfficialStatisticsTests(unittest.TestCase):
    def test_current_scoped_evidence_binds_both_drivers_manifest_and_method_without_production_grant(self):
        root = proof.ROOT
        evidence = json.loads((root / "evidence/r-stats-current-engine-20261015.json").read_text())
        for name, key in [("tools/prove_current_r_stats.py", "driver_sha256"),
                          ("tools/build_current_r_stats.py", "build_driver_sha256"),
                          ("research-adapters/cachexia-r-stats/manifest.toml", "manifest_sha256"),
                          ("research-adapters/cachexia-r-stats/scripts/statistics.R", "method_source_sha256")]:
            self.assertEqual(hashlib.sha256((root / name).read_bytes()).hexdigest(), evidence[key])
        self.assertEqual({row["kind"] for row in evidence["per_node"]}, set(proof.METHODS.values()))
        self.assertEqual(sum(row["positive_DAGs"]+row["refusal_DAGs"] for row in evidence["per_node"]), 164)
        self.assertEqual(evidence["layer_status"]["study_contract_and_current_deployment"], "NOT_GRANTED")
        self.assertFalse(evidence["g0_granted"])
        self.assertFalse(evidence["resident_daemon_or_production_configuration_changed"])

    def test_every_method_uses_exact_declared_columns_and_only_engineering_rust_nodes(self):
        self.assertEqual(len(proof.COLUMNS), len(set(proof.COLUMNS)))
        self.assertTrue(set(proof.NUMERIC) <= set(proof.COLUMNS))
        allowed = {"file_reference", "file_to_dataframe", "dataframe_to_file", "datafusion_sql"}
        for operation, method in proof.METHODS.items():
            job = proof.make_job(Path("/technical/toy"), Path("/technical/source"), dict(operation=operation), ["0001", "NA"])
            self.assertEqual(len(job["nodes"]), 8)
            self.assertEqual(len(job["edges"]), 7)
            self.assertEqual(job["nodes"][2]["kind"], method)
            self.assertTrue(set(node["kind"] for node in job["nodes"]) <= allowed | {method})
            columns = proof.ADJUST if operation == "adjust" else proof.COLUMNS
            self.assertEqual([field["name"] for field in job["nodes"][3]["spec"]["csv_schema"]], columns)
            self.assertTrue(all(field["data_type"] == "utf8" for field in job["nodes"][3]["spec"]["csv_schema"]))

    def test_frozen_identity_order_does_not_filter_members_or_nullify_literal_na(self):
        job = proof.make_job(Path("/technical/toy"), Path("/technical/source"), dict(operation="adjust"), ["0001", "NA"])
        query = job["nodes"][5]["spec"]["sql"]
        self.assertIn("WHEN '0001' THEN 0 WHEN 'NA' THEN 1 ELSE 2", query)
        self.assertNotIn("WHERE", query)
        self.assertNotIn('NULLIF("test_id"', query)
        self.assertIn('"test_id" AS "test_id"', query)
        self.assertIn('"status" AS "status"', query)
        self.assertIn('CAST(NULLIF("p_adj", \'NA\') AS DOUBLE)', query)
        for ids in [["same", "same"], ["unsafe'query"]]:
            with self.assertRaises(RuntimeError):
                proof.make_job(Path("/technical/toy"), Path("/technical/source"), dict(operation="adjust"), ids)

    def test_materialized_nulls_lexical_ids_and_boolean_values_are_checked(self):
        expected = [dict(test_id="NA", p_value="NA", p_adj="NA", reject="NA", family_n="9", method="BH", status="NOT_ESTIMABLE")]
        actual = [dict(expected[0], p_value="", p_adj="", reject="")]
        proof.compare_rows(actual, expected, "adjust")
        renamed = dict(actual[0])
        renamed['?table?.test_id'] = renamed.pop('test_id')
        with self.assertRaisesRegex(RuntimeError, "column names differ"):
            proof.compare_rows([renamed], expected, "adjust")
        for key, value in [("test_id", ""), ("p_adj", "0"), ("family_n", "8"), ("reject", "true"), ("status", "ESTIMABLE")]:
            changed = copy.deepcopy(actual)
            changed[0][key] = value
            with self.assertRaises(RuntimeError):
                proof.compare_rows(changed, expected, "adjust")

    def test_old_executables_and_metadata_hashing_cannot_satisfy_current_engine(self):
        case = dict(id="case", operation="adjust", negative="true")
        for report in [dict(engine_source_revision="historical", input_hashing="ContentRequired"),
                       dict(engine_source_revision="a"*40, input_hashing="Metadata")]:
            with self.assertRaisesRegex(RuntimeError, "Exact current engine identity"):
                proof.check_report(Path("/technical/toy"), {}, case, report, "a"*40, "failure")
        self.assertEqual(builder.EXAMPLE_PATH, "crates/container-plugin/examples/official_r_stats_dag.rs")
        self.assertIn("readRDS", proof.R_READBACK)
        self.assertNotIn("do.call", proof.R_READBACK)


if __name__ == "__main__":
    unittest.main()
