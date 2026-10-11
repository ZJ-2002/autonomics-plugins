import csv
import hashlib
import json
import os
import pathlib
import subprocess
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
IMAGE = "ghcr.io/zj-2002/susie@sha256:b1df377e428e6166cd8ac65ac3e131c46c3bb68f172969c0e0f910751792d87e"
PANEL = pathlib.Path(os.environ.get("SUSIE_TEST_PANEL", str(pathlib.Path.home() / ".autonomics/panels/wjixiang/catalog-mixer-g1000-eur@sha256:25b47a318e764d00ccdd015483323abe2bfb43ed032868b6ef8eeaf8441c173b")))
SCRIPT = pathlib.Path(os.environ.get("SUSIE_TEST_SCRIPT", str(ROOT / "scripts/run_susie_rss.R.sh")))
EVIDENCE = pathlib.Path(os.environ["SUSIE_TEST_EVIDENCE"])
REFERENCE_LIBRARY = pathlib.Path(os.environ["SUSIE_REFERENCE_LIBRARY"])
BASE_PARAMETERS = {"SUSIE_L": "2", "SUSIE_ESTIMATE_PRIOR_METHOD": "optim", "SUSIE_MAX_ITER": "100", "SUSIE_SEED": "1"}


def sha256(filename):
    with filename.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def execute(case, name, command):
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, timeout=180)
    (case / f"{name}.stdout.txt").write_bytes(result.stdout)
    (case / f"{name}.stderr.txt").write_bytes(result.stderr)
    (case / f"{name}.execution.json").write_text(json.dumps({"command": command, "exit": result.returncode,
                                                           "elapsed_seconds": time.monotonic() - started,
                                                           "scope": "ACTUAL_DECLARED_PORTS_PINNED_OCI_TECHNICAL_FIXTURE_NOT_PRODUCTION",
                                                           "G0": False}, indent=2) + "\n")
    return result


class SusieContract(unittest.TestCase):
    def setUp(self):
        self.case = EVIDENCE / self._testMethodName
        self.case.mkdir(parents=True, exist_ok=False)
        (self.case / "work/.autonomics").mkdir(parents=True)
        (self.case / "output").mkdir()
        with (ROOT / "fixtures/chr21.sumstats.tsv").open() as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.rows = [dict(rows[index]) for index in [0, 1, 3]]
        for row, score in zip(self.rows, ["2.7", "2", "1.3"]):
            row["z"] = score
        self.parameters = dict(BASE_PARAMETERS)

    def write_input(self):
        with (self.case / "input.tsv").open("w") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(self.rows[0]), delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(self.rows)

    def command(self):
        command = ["podman", "run", "--rm", "--pull=never", "--network=none", "--cpus=2", "--memory=2g",
                   "--entrypoint", "Rscript", "--mount", f"type=bind,src={SCRIPT},dst=/runner.R,ro=true",
                   "--mount", f"type=bind,src={self.case},dst=/case",
                   "-e", "AUTONOMICS_INPUT0=/case/input.tsv", "-e", "AUTONOMICS_WORKDIR=/case/work",
                   "-e", "AUTONOMICS_OUTPUT0=/case/output/fit.tsv", "-e", "AUTONOMICS_OUTPUT1=/case/output/fit.RDS",
                   "-e", "AUTONOMICS_OUTPUT2=/case/output/fit.log"]
        if self.parameters.get("SUSIE_LD_SOURCE", "mixer") == "mixer":
            command.extend(["--mount", f"type=bind,src={PANEL},dst=/panels/mixer_ref,ro=true"])
        for name, value in self.parameters.items():
            command.extend(["-e", f"{name}={value}"])
        return command + [IMAGE, "/runner.R"]

    def reject(self, expected, write=True):
        if write:
            self.write_input()
        result = execute(self.case, "node", self.command())
        self.assertNotEqual(result.returncode, 0, result.stdout.decode())
        self.assertIn(expected, result.stderr.decode())
        self.assertFalse((self.case / "output/fit.tsv").exists())
        self.assertFalse((self.case / "output/fit.RDS").exists())
        self.assertIn("ERROR:", (self.case / "output/fit.log").read_text())

    def positive(self):
        self.write_input()
        result = execute(self.case, "node", self.command())
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertIn("converged: TRUE", (self.case / "output/fit.log").read_text())
        settings = {"seed": self.parameters.get("SUSIE_SEED", "1"), "effects": self.parameters.get("SUSIE_L", "2"),
                    "scaled_prior_variance": self.parameters.get("SUSIE_SCALED_PRIOR_VARIANCE", "0.2"),
                    "estimate_prior_variance": self.parameters.get("SUSIE_ESTIMATE_PRIOR_VARIANCE", "true").upper(),
                    "prior_method": json.dumps(self.parameters.get("SUSIE_ESTIMATE_PRIOR_METHOD", "optim")),
                    "z_method": json.dumps(self.parameters.get("SUSIE_Z_METHOD", "wald")),
                    "null_threshold": self.parameters.get("SUSIE_CHECK_NULL_THRESHOLD", "0"),
                    "coverage": self.parameters.get("SUSIE_COVERAGE", "0.95"),
                    "min_abs_corr": self.parameters.get("SUSIE_MIN_ABS_CORR", "0.5"),
                    "max_iter": self.parameters.get("SUSIE_MAX_ITER", "100")}
        (self.case / "settings.R").write_text("list(" + ",".join(f"{name}={value}" for name, value in settings.items()) + ")\n")
        command = ["podman", "run", "--rm", "--pull=never", "--network=none", "--cpus=2", "--memory=2g",
                   "--entrypoint", "Rscript", "--mount", f"type=bind,src={self.case},dst=/case",
                   "--mount", f"type=bind,src={REFERENCE_LIBRARY},dst=/reference-library,ro=true",
                   "--mount", f"type=bind,src={ROOT / 'tests/official_reference.R'},dst=/reference.R,ro=true",
                   "--mount", f"type=bind,src={PANEL},dst=/panels/mixer_ref,ro=true", IMAGE, "/reference.R",
                   "/reference-library", "/case", "/panels/mixer_ref/stage_flat/chr21.bim", "/case/settings.R"]
        reference = execute(self.case, "independent-author", command)
        self.assertEqual(reference.returncode, 0, reference.stderr.decode())
        self.assertIn("FULL_OFFICIAL_OBJECT_AND_EVERY_TSV_COLUMN_MATCH", reference.stdout.decode())

    def test_official_complete_three_variants(self):
        self.positive()

    def test_official_mixed_effect_allele_reversal(self):
        for index, row in enumerate(self.rows):
            alleles = row["snp"].split(":")[-2:]
            if index == 1:
                alleles.reverse()
                row["z"] = str(-float(row["z"]))
            row["a1"], row["a2"] = alleles
        self.positive()

    def test_official_mixed_bim_allele_order(self):
        with (ROOT / "fixtures/chr21.sumstats.tsv").open() as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        self.rows = [dict(rows[index]) for index in [0, 7]]
        for row, score in zip(self.rows, ["2.7", "2"]):
            row["z"] = score
        self.positive()

    def test_official_em(self):
        self.parameters["SUSIE_ESTIMATE_PRIOR_METHOD"] = "EM"
        self.positive()

    def test_official_simple_fixed_score(self):
        self.parameters.update(SUSIE_ESTIMATE_PRIOR_METHOD="simple", SUSIE_ESTIMATE_PRIOR_VARIANCE="false", SUSIE_Z_METHOD="score")
        self.positive()

    def test_official_single_variant(self):
        self.rows = self.rows[:1]
        self.positive()

    def test_official_without_n(self):
        for row in self.rows:
            del row["n"]
        self.positive()

    def test_official_row_permutation(self):
        self.rows.reverse()
        self.positive()

    def test_duplicate_snp(self):
        self.rows.append(dict(self.rows[0]))
        self.reject("SNP keys")

    def test_varying_n(self):
        self.rows[1]["n"] = "1000"
        self.reject("n must be constant")

    def test_n_override_conflict(self):
        self.parameters["SUSIE_N"] = "1000"
        self.reject("SUSIE_N disagrees")

    def test_nonfinite_z(self):
        self.rows[1]["z"] = "Inf"
        self.reject("z must contain only finite")

    def test_invalid_chromosome(self):
        for row in self.rows:
            row["chrom"] = "21.5"
        self.reject("exactly one autosomal")

    def test_id_chromosome_mismatch(self):
        self.rows[0]["snp"] = self.rows[0]["snp"].replace("21:", "22:", 1)
        self.reject("SNP IDs must agree")

    def test_allele_pair_mismatch(self):
        for row in self.rows:
            row["a1"], row["a2"] = ["A", "G"]
        self.reject("a1/a2 must match")

    def test_incomplete_allele_columns(self):
        for row in self.rows:
            row["a1"] = row["snp"].split(":")[-2]
        self.reject("a1 and a2 must be supplied together")

    def test_sparse_original_fixture(self):
        with (ROOT / "fixtures/chr21.sumstats.tsv").open() as handle:
            self.rows = list(csv.DictReader(handle, delimiter="\t"))
        self.reject("absent sparse entries cannot be treated as zero")

    def test_filtering_does_not_create_zero_ld(self):
        self.parameters["SUSIE_R2_MIN"] = "0.9"
        self.reject("absent sparse entries cannot be treated as zero")

    def test_nonconvergence_does_not_publish(self):
        self.parameters["SUSIE_MAX_ITER"] = "1"
        self.reject("fit did not converge")

    def test_missing_reference_snp(self):
        self.rows[0]["snp"] = "21:1:C:T"
        self.reject("exactly one signed-LD BIM row")

    def test_no_implicit_residual_variance(self):
        self.parameters["SUSIE_ESTIMATE_RESIDUAL_VARIANCE"] = "true"
        self.reject("requires an in-sample LD route")

    def test_invalid_boolean(self):
        self.parameters["SUSIE_ESTIMATE_PRIOR_VARIANCE"] = "maybe"
        self.reject("must be true or false")

    def test_invalid_numeric(self):
        self.parameters["SUSIE_COVERAGE"] = "NaN"
        self.reject("must be a finite")

    def test_fractional_effect_count(self):
        self.parameters["SUSIE_L"] = "2.5"
        self.reject("must be a finite integer")

    def test_invalid_seed(self):
        self.parameters["SUSIE_SEED"] = "-1"
        self.reject("SUSIE_SEED must be a finite integer")

    def test_lowercase_em_is_not_official(self):
        self.parameters["SUSIE_ESTIMATE_PRIOR_METHOD"] = "em"
        self.reject("must be one of")

    def test_duplicate_headers(self):
        (self.case / "input.tsv").write_text("snp\tchrom\tz\tz\n21:9411410:C:T\t21\t1\t1\n")
        self.reject("column names", write=False)

    def test_ragged_tsv(self):
        (self.case / "input.tsv").write_text("snp\tchrom\tz\n21:9411410:C:T\t21\n")
        self.reject("rectangular TSV", write=False)

    def test_existing_output_never_overwritten(self):
        self.write_input()
        existing = self.case / "output/fit.tsv"
        existing.write_bytes(b"previous-run-must-survive\n")
        before = sha256(existing)
        result = execute(self.case, "node", self.command())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("prior artifacts are never overwritten", result.stderr.decode())
        self.assertEqual(sha256(existing), before)
        self.assertFalse((self.case / "output/fit.RDS").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
