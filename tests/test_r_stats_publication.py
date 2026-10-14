import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

from tools import prove_r_stats_publication as proof


class OfficialStatisticsPublicationTests(unittest.TestCase):
    def test_content_identity_ignores_access_time_but_not_mutation_or_replacement(self):
        values = dict(st_dev=1, st_ino=2, st_mode=3, st_nlink=1, st_uid=1000,
                      st_gid=1000, st_size=50, st_mtime_ns=100, st_ctime_ns=101, st_atime_ns=90)
        original = proof.content_identity(SimpleNamespace(**values))
        self.assertEqual(original, proof.content_identity(SimpleNamespace(**dict(values, st_atime_ns=999))))
        for key in ["st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid", "st_size", "st_mtime_ns", "st_ctime_ns"]:
            self.assertNotEqual(original, proof.content_identity(SimpleNamespace(**dict(values, **{key: values[key]+1}))))

    def test_every_declared_port_refuses_before_truncation_in_actual_r(self):
        script = proof.ROOT / "research-adapters/cachexia-r-stats/scripts/statistics.R"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for port in range(5):
                directory = root / str(port)
                directory.mkdir()
                outputs = [directory / str(index) for index in range(5)]
                outputs[port].write_bytes(b"keep original output")
                environment = dict(os.environ)
                environment.update({f"AUTONOMICS_OUTPUT{index}": str(path) for index, path in enumerate(outputs)})
                observed = subprocess.run(["Rscript", "--vanilla", str(script)], env=environment,
                                          capture_output=True, timeout=30)
                self.assertNotEqual(observed.returncode, 0)
                self.assertIn(b"no overwrite", observed.stderr)
                self.assertEqual(outputs[port].read_bytes(), b"keep original output")
                self.assertEqual([path.name for path in directory.iterdir()], [str(port)])

    def test_duplicate_dangling_symlink_and_traversing_ports_refuse_in_actual_r(self):
        script = proof.ROOT / "research-adapters/cachexia-r-stats/scripts/statistics.R"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for scenario in ["duplicate", "link", "traversal"]:
                directory = root / scenario
                directory.mkdir()
                outputs = [directory / str(index) for index in range(5)]
                if scenario == "duplicate":
                    outputs[1] = outputs[0]
                elif scenario == "link":
                    outputs[0].symlink_to(directory / "not-created")
                else:
                    outputs[0] = directory / ".." / "foreign"
                environment = dict(os.environ)
                environment.update({f"AUTONOMICS_OUTPUT{index}": str(path) for index, path in enumerate(outputs)})
                observed = subprocess.run(["Rscript", "--vanilla", str(script)], env=environment,
                                          capture_output=True, timeout=30)
                self.assertNotEqual(observed.returncode, 0)
                self.assertFalse((root / "foreign").exists())
                self.assertEqual(len(list(directory.iterdir())), 1 if scenario == "link" else 0)

    def test_method_requalification_does_not_claim_current_dag_or_production(self):
        self.assertIn('"new_method_calls_are_not_current_engine_DAGs"', proof.R_DRIVER)
        self.assertIn("asNamespace(\"stats\")", proof.R_DRIVER)
        self.assertIn("all.equal(actual$fit,expected", proof.R_DRIVER)
        self.assertIn("identical(actual$row_id,fixture$row_ids)", proof.R_DRIVER)


if __name__ == "__main__":
    unittest.main()
