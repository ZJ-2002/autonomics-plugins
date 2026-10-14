import copy
from pathlib import Path
import tempfile
import unittest

from tools import prove_current_r_lm as proof


class CurrentOfficialRegressionTests(unittest.TestCase):
    def test_job_uses_original_current_plugin_and_only_engineering_rust_nodes(self):
        job = proof.make_job(Path("/technical/fresh"), Path("/technical/source"))
        self.assertEqual(job["scope"], "TECHNICAL_ONLY_NOT_G0")
        self.assertEqual([row["kind"] for row in job["nodes"]],
                         ["file_reference", "file_reference", "r_stats_lm", "file_to_dataframe", "dataframe_to_file"])
        self.assertEqual(len(job["edges"]), 4)
        self.assertEqual(job["plugin_manifest"], "/technical/source/manifest.toml")
        self.assertNotIn("linear_regression", str(job))

    def test_historical_engine_or_best_effort_hashing_cannot_pass_as_current(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for report in [dict(engine_source_revision="d8659cdf1ebf", input_hashing="ContentRequired"),
                           dict(engine_source_revision="a" * 40, input_hashing="Content")]:
                with self.assertRaisesRegex(RuntimeError, "Current compiled engine identity"):
                    proof.check_report(directory, directory, report, {}, {}, "a" * 40)

    def test_synthetic_failure_requires_actual_diagnostic_and_no_terminal(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            report = dict(engine_source_revision="a" * 40, input_hashing="ContentRequired",
                          scope="TECHNICAL_ONLY_NOT_G0", max_concurrency=1, incremental=False, g0_granted=False,
                          first_run=dict(errors={"analysis": "BLOCKED: finite values required"},
                                         nodes=[dict(id="analysis", status="failed")]))
            case = dict(name="nonfinite", expected_error="finite values required")
            record = proof.check_report(directory, directory, report, dict(ports=dict(outputs=[])), case, "a" * 40)
            self.assertTrue(record["expected_refusal"])
            changed = copy.deepcopy(report)
            changed["first_run"]["errors"] = {"analysis": "unrelated failure"}
            with self.assertRaisesRegex(RuntimeError, "Expected refusal"):
                proof.check_report(directory, directory, changed, dict(ports=dict(outputs=[])), case, "a" * 40)
            (directory / "materialized.tsv").write_text("FOREIGN OR PARTIAL")
            with self.assertRaisesRegex(RuntimeError, "Expected refusal"):
                proof.check_report(directory, directory, report, dict(ports=dict(outputs=[])), case, "a" * 40)


if __name__ == "__main__":
    unittest.main()
