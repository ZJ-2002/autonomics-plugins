import hashlib
import json
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def test_declared_ports_and_required_parameters(self):
        manifest = tomllib.loads((ROOT / "manifest.toml").read_text())
        self.assertEqual(manifest["plugin_name"], "cachexia-ucell")
        self.assertEqual(len(manifest["nodes"]), 1)
        node = manifest["nodes"][0]
        self.assertEqual(node["kind"], "cachexia_ucell_official")
        self.assertEqual(len(node["ports"]["inputs"]), 2)
        self.assertEqual([port["path"] for port in node["ports"]["outputs"]],
            ["ucell_scores.tsv", "ucell.RDS", "ucell.log", "audit.json"])
        self.assertEqual(set(node["params"]), {"max_rank", "negative_weight", "missing_genes"})
        self.assertTrue(all("default" not in parameter for parameter in node["params"].values()))

    def test_wrapper_immutable_proved_bytes(self):
        self.assertEqual(hashlib.sha256((ROOT / "scripts/ucell.R").read_bytes()).hexdigest(),
            "43ca20c8a63417c4ef26d8c56a61b65b064fbe71f4974add726b75998b8624d0")

    def test_official_source_lock_and_recipe(self):
        lock = json.loads((ROOT / "source-lock.json").read_text())
        recipe = (ROOT / "Containerfile").read_text()
        self.assertEqual(lock["bioconductor_release"], "3.23")
        self.assertIn(lock["base_image"], recipe)
        self.assertEqual(len(lock["archives"]), 5)
        for record in lock["archives"]:
            self.assertIn(record["archive"], recipe)
            self.assertEqual(len(record["sha256"]), 64)
        official = next(record for record in lock["archives"] if record["package"] == "UCell")
        self.assertEqual(official["version"], "2.16.0")
        self.assertEqual(official["sha256"], "816526fc4fb2958ecac6432f8c574c2bd51a6ff2c179d6ec8d2d6bcb1e9f5c9c")


if __name__ == "__main__":
    unittest.main()
