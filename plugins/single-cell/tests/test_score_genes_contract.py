import hashlib
import json
from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ScoringContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads((ROOT / "manifest.toml").read_text())
        self.node = next(node for node in self.manifest["nodes"] if node["kind"] == "gene_set_score")

    def test_current_ten_nodes_keep_other_nine_definitions_unchanged(self):
        others = {node["kind"]: node for node in self.manifest["nodes"] if node["kind"] != "gene_set_score"}
        self.assertEqual(len(self.manifest["nodes"]), 10)
        self.assertEqual(len(others), 9)
        digest = hashlib.sha256(json.dumps(others, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(digest, "5037b5c80b82a617c9b7ef5bcfce24984bcebaa6ad2007474e8f81027ba53256")

    def test_injected_script_and_ports(self):
        self.assertEqual(self.node["command"]["script_file"], "scripts/score_genes.py")
        self.assertEqual(len(self.node["ports"]["inputs"]), 1)
        self.assertEqual([port["path"] for port in self.node["ports"]["outputs"]], ["output.h5ad", "report.json"])
        self.assertEqual(set(self.node["command"]["env"]), {"SC_P_JSON_GENE_SETS", "SC_P_INT_CTRL_SIZE", "SC_P_INT_RANDOM_STATE"})

    def test_proved_script_bytes(self):
        digest = hashlib.sha256((ROOT / "scripts/score_genes.py").read_bytes()).hexdigest()
        self.assertEqual(digest, "dc2815e79b289327ef4ef3c15bf744c1e1557063692b9989c77b2002bf47f774")

    def test_seed_domain(self):
        self.assertEqual(self.node["params"]["random_state"]["min"], 0)
        self.assertEqual(self.node["params"]["random_state"]["max"], 4294967295)

    def test_retained_image_and_family_panel(self):
        self.assertEqual(self.manifest["image"]["reference"], "ghcr.io/zj-2002/single-cell-preprocessor@sha256:e2f9fcd5ccf9e97b0f0129466df5abb21ae47ed32f123f6953b79fd83d915e20")
        self.assertEqual(self.manifest["panels"][0]["bundle"], "wjixiang/catalog-celltypist-models-pan-immune")


if __name__ == "__main__":
    unittest.main()
