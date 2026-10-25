import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "research-adapters/ieugwasr-official"
ORIGINAL = ROOT / "staged-adapters/ieugwasr-official/scripts/official.R"
ORIGINAL_SHA = "ea7815eef5b9d18681b87c288dc0d7097311a5fe32a2fe16bee5e82ce7e25931"


class IeugwasrDispatchContractTests(unittest.TestCase):
    def prefix(self):
        original = ORIGINAL.read_bytes()
        dispatch = (ADAPTER / "scripts/dispatch.R").read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(), ORIGINAL_SHA)
        before = b'jsonlite::write_json(projection, outputs[[2L]], auto_unbox = TRUE, null = "null", pretty = TRUE, digits = NA)'
        after = before.replace(b"digits = NA", b"digits = 17")
        self.assertEqual(original.count(before), 1)
        expected = original.replace(before, after, 1)
        self.assertTrue(dispatch.endswith(expected))
        return dispatch[:-len(expected)]

    def refused(self, policy, count, operation, expected, dataset=None):
        if not shutil.which("Rscript"):
            self.fail("Rscript required; a missing interpreter is not a passing contract test")
        with tempfile.TemporaryDirectory(prefix="ieugwasr-dispatch-toy-") as directory:
            work = Path(directory)
            prefix = work / "guard.R"
            prefix.write_bytes(self.prefix())
            request = work / "request.json"
            request.write_text(json.dumps({"operation": operation, "arguments": {}}))
            environment = {name: os.environ[name] for name in ("HOME", "PATH", "LANG", "LC_ALL", "TMPDIR", "R_LIBS", "R_LIBS_USER", "R_LIBS_SITE") if name in os.environ}
            environment.update(AUTONOMICS_IEUGWASR_INPUT_POLICY=policy, AUTONOMICS_INPUT_COUNT=count,
                               AUTONOMICS_INPUT0=str(request), OPENGWAS_JWT="")
            if dataset is not None:
                target = work / "dataset.RDS"
                prepared = subprocess.run(
                    ["Rscript", "--vanilla", "-e", "saveRDS(" + dataset + ",commandArgs(TRUE)[[1L]])", str(target)],
                    capture_output=True, text=True, env=environment, timeout=30,
                )
                self.assertEqual(prepared.returncode, 0, prepared.stderr)
                environment["AUTONOMICS_INPUT1"] = str(target)
            result = subprocess.run(["Rscript", "--vanilla", str(prefix)], capture_output=True, text=True,
                                    env=environment, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(expected, result.stderr)

    def test_dispatch_has_exact_original_wrapper_suffix(self):
        self.assertIn(b"AUTONOMICS_INPUT_COUNT", self.prefix())

    def test_manifest_has_two_required_port_shapes(self):
        manifest = tomllib.loads((ADAPTER / "manifest.toml").read_text())
        self.assertEqual(manifest["plugin_name"], "ieugwasr-official")
        nodes = manifest["nodes"]
        self.assertEqual([node["kind"] for node in nodes], ["official_ieugwasr_call", "official_ieugwasr_call_with_dataset"])
        self.assertEqual([len(node["ports"]["inputs"]) for node in nodes], [1, 2])
        self.assertEqual([len(node["ports"]["outputs"]) for node in nodes], [4, 4])
        for node in nodes:
            self.assertEqual(node["command"]["script_file"], "scripts/dispatch.R")
            self.assertNotIn("params", node)
            self.assertEqual(node["resources"]["network"], "egress")
            self.assertEqual(node["resources"]["pull_policy"], "never")
            self.assertNotIn("OPENGWAS_JWT", node["command"]["env"])
            self.assertEqual(node["command"]["env"]["R_PROFILE_USER"], "/dev/null")
            self.assertEqual(node["command"]["env"]["R_LIBS"], "/opt/ieugwasr-library")
            self.assertEqual(node["command"]["env"]["R_LIBS_USER"], "/opt/ieugwasr-library")

    def test_wrong_input_count_is_refused(self):
        self.refused("request_only", "2", "gwasinfo", "input count/policy mismatch")

    def test_unknown_policy_is_refused(self):
        self.refused("arbitrary", "1", "gwasinfo", "input count/policy mismatch")

    def test_request_only_rejects_clump(self):
        self.refused("request_only", "1", "ld_clump_api", "Request-only kind rejects")

    def test_request_only_rejects_undeclared_dataset(self):
        self.refused("request_only", "1", "gwasinfo", "Request-only kind rejects", dataset="NULL")

    def test_dataset_kind_cannot_use_null_to_switch_operation(self):
        self.refused("with_dataset", "2", "gwasinfo", "Dataset kind requires ld_clump_api", dataset="NULL")

    def test_dataset_kind_rejects_null_and_non_dataframe(self):
        for value in ("NULL", "1"):
            with self.subTest(value=value):
                self.refused("with_dataset", "2", "ld_clump_api", "non-NULL data.frame", dataset=value)


if __name__ == "__main__":
    unittest.main()
