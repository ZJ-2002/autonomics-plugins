import csv
import json
import os
import pathlib
import subprocess
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
EVIDENCE = pathlib.Path(os.environ["COLOC_TEST_EVIDENCE"])
REFERENCE = pathlib.Path(os.environ["COLOC_REFERENCE_LIBRARY"])
AUTHOR_FIXTURE = pathlib.Path(os.environ["COLOC_AUTHOR_FIXTURE"])
IMAGE = "ghcr.io/auto-nomics/autonomics/coloc@sha256:a2afe7aa83ae6f1ecb9573317aa022af4db0870771378c7fe90d295d70057322"
DEFAULTS = {"n1": 10000, "n2": 10000, "type1": "quant", "type2": "quant", "sd_y1": 1,
            "sd_y2": 1, "case_fraction1": .4, "case_fraction2": .4, "l": 10, "coverage": .95,
            "min_abs_corr": .5, "p1": 1e-4, "p2": 1e-4, "p12": 5e-6, "max_iter": 100,
            "seed": 1, "alignment_evidence": "SYNTHETIC_TECHNICAL_FIXTURE_NOT_SCIENTIFIC_APPROVAL"}


def execute(directory, name, command):
    started = time.monotonic()
    result = subprocess.run(command, capture_output=True, timeout=180)
    (directory / (name + ".stdout.txt")).write_bytes(result.stdout)
    (directory / (name + ".stderr.txt")).write_bytes(result.stderr)
    (directory / (name + ".execution.json")).write_text(json.dumps({"command": command,
        "exit": result.returncode, "elapsed_seconds": time.monotonic()-started,
        "scope": "PINNED_OFFICIAL_STACK_DECLARED_PORTS_NOT_PRODUCTION", "G0": False}, indent=2)+"\n")
    return result


class ColocContract(unittest.TestCase):
    def setUp(self):
        self.case = EVIDENCE / self._testMethodName
        self.case.mkdir(parents=True, exist_ok=False)
        (self.case / "output").mkdir()
        self.parameters = dict(DEFAULTS)
        self.tables = []
        for index in range(4):
            with (ROOT / "fixtures" / f"input{index}.tsv").open() as handle:
                self.tables.append(list(csv.DictReader(handle, delimiter="\t")))

    def write_inputs(self):
        for index, rows in enumerate(self.tables):
            with (self.case / f"input{index}.tsv").open("w") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)

    def command(self):
        command = ["podman", "run", "--rm", "--pull=never", "--network=none", "--cpus=2", "--memory=2g",
                   "--entrypoint", "Rscript", "--mount", f"type=bind,src={self.case},dst=/case",
                   "--mount", f"type=bind,src={ROOT}/scripts/coloc_susie.R,dst=/node.R,ro=true"]
        for index in range(4):
            command.extend(["-e", f"AUTONOMICS_INPUT{index}=/case/input{index}.tsv"])
        for index, name in enumerate(["coloc_summary.tsv", "coloc_variants.tsv", "coloc.RDS", "coloc.log"]):
            command.extend(["-e", f"AUTONOMICS_OUTPUT{index}=/case/output/{name}"])
        for name, value in self.parameters.items():
            command.extend(["-e", "COLOC_"+name.upper()+"="+str(value)])
        return command+[IMAGE, "/node.R"]

    def positive(self):
        self.write_inputs()
        result = execute(self.case, "node", self.command())
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        for name in ["coloc_summary.tsv", "coloc_variants.tsv", "coloc.RDS", "coloc.log"]:
            self.assertGreater((self.case / "output" / name).stat().st_size, 0)
        expression = "list("+",".join(name+"="+(json.dumps(value) if isinstance(value,str) else repr(value))
                                       for name,value in self.parameters.items())+")\n"
        (self.case / "settings.R").write_text(expression)
        command = ["podman", "run", "--rm", "--pull=never", "--network=none", "--cpus=2", "--memory=2g",
                   "--entrypoint", "Rscript", "--mount", f"type=bind,src={self.case},dst=/case",
                   "--mount", f"type=bind,src={REFERENCE},dst=/reference-library,ro=true",
                   "--mount", f"type=bind,src={ROOT}/tests/official_reference.R,dst=/reference.R,ro=true",
                   IMAGE, "/reference.R", "/reference-library", "/case", "/case/settings.R"]
        reference = execute(self.case, "independent-author", command)
        self.assertEqual(reference.returncode, 0, reference.stderr.decode())
        self.assertIn("Whole official datasets, fits and coloc result", reference.stdout.decode())

    def reject(self, reason):
        self.write_inputs()
        result = execute(self.case, "node", self.command())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(reason, result.stderr.decode())
        for name in ["coloc_summary.tsv", "coloc_variants.tsv", "coloc.RDS"]:
            self.assertFalse((self.case / "output" / name).exists())
        self.assertIn("ERROR:", (self.case / "output/coloc.log").read_text())

    def test_complete_50_default(self):
        self.positive()

    def test_author_500_multiple_signals(self):
        self.tables = []
        for index in range(4):
            with (AUTHOR_FIXTURE / f"input{index}.tsv").open() as handle:
                self.tables.append(list(csv.DictReader(handle, delimiter="\t")))
        with (AUTHOR_FIXTURE / "settings.tsv").open() as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                index = row["index"]
                self.parameters["n"+index] = int(row["N"])
                self.parameters["sd_y"+index] = float(row["sdY"])
                self.parameters["type"+index] = row["type"]
        self.positive()
        with (self.case / "output/coloc_summary.tsv").open() as handle:
            self.assertGreaterEqual(len(list(csv.DictReader(handle, delimiter="\t"))), 2)

    def test_explicit_p12_1e6(self):
        self.parameters["p12"] = 1e-6
        self.positive()

    def test_explicit_p12_1e5(self):
        self.parameters["p12"] = 1e-5
        self.positive()

    def test_explicit_p12_1e4_L20(self):
        self.parameters.update(p12=1e-4, l=20)
        self.positive()

    def test_explicit_p12_1e4_L10(self):
        self.parameters["p12"] = 1e-4
        self.positive()

    def test_explicit_p12_1e6_L20(self):
        self.parameters.update(p12=1e-6, l=20)
        self.positive()

    def test_explicit_p12_1e5_L20(self):
        self.parameters.update(p12=1e-5, l=20)
        self.positive()

    def test_literal_NA_snp_identity_is_retained(self):
        old = self.tables[0][0]["snp"]
        for table in self.tables:
            for index,row in enumerate(table):
                replaced = {("NA" if name == old else name): ("NA" if name == "snp" and value == old else value)
                            for name,value in row.items()}
                table[index] = replaced
        self.positive()

    def test_different_trait_SNP_set_is_not_intersected(self):
        old = self.tables[1][0]["snp"]
        self.tables[1][0]["snp"] = "OTHER_LITERAL_ID"
        for index,row in enumerate(self.tables[3]):
            self.tables[3][index] = {("OTHER_LITERAL_ID" if name == old else name):
                                    ("OTHER_LITERAL_ID" if name == "snp" and value == old else value)
                                    for name,value in row.items()}
        self.reject("Both traits require exactly the same ordered SNP identities")

    def test_quant_case_control(self):
        self.parameters["type2"] = "cc"
        self.positive()

    def test_no_credible_sets_preserves_absent_posterior(self):
        for table in self.tables[:2]:
            for row in table:
                row["beta"] = "0"
        self.positive()
        with (self.case / "output/coloc_summary.tsv").open() as handle:
            row = next(csv.DictReader(handle, delimiter="\t"))
        self.assertEqual(row, {"status": "NOT_ESTIMABLE_NO_MATCHED_CREDIBLE_SETS"})

    def test_trait_effect_reversal(self):
        for row in self.tables[1]:
            row["effect_allele"], row["other_allele"] = row["other_allele"], row["effect_allele"]
            row["beta"] = str(-float(row["beta"]))
        self.positive()

    def test_ld_counting_reversal(self):
        for index in range(2):
            changed = self.tables[index][0]["snp"]
            self.tables[index][0]["ld_a1"],self.tables[index][0]["ld_a2"] = self.tables[index][0]["ld_a2"],self.tables[index][0]["ld_a1"]
            for row in self.tables[index+2]:
                for name in list(row)[1:]:
                    if (row["snp"] == changed) != (name == changed):
                        row[name] = str(-float(row[name]))
        self.positive()

    def test_duplicate_snp(self):
        self.tables[0][1]["snp"] = self.tables[0][0]["snp"]
        self.reject("Invalid or duplicate SNP identity")

    def test_bad_se(self):
        self.tables[0][0]["se"] = "0"
        self.reject("SE and its variance")

    def test_nonfinite_beta(self):
        self.tables[0][0]["beta"] = "NaN"
        self.reject("Nonfinite or nonnumeric beta")

    def test_missing_ld_metadata(self):
        for row in self.tables[0]:
            del row["ld_a1"]
        self.reject("lacks declared SNP/effect/LD metadata")

    def test_trait_allele_mismatch(self):
        for name in ["effect_allele", "ld_a1"]:
            self.tables[1][0][name] = "AT"
        self.reject("Trait allele pairs disagree")

    def test_ld_allele_mismatch(self):
        self.tables[0][0]["ld_a1"] = "AT"
        self.reject("LD counting alleles disagree")

    def test_fractional_ld_count(self):
        self.tables[0][0]["ld_n"] = "2.5"
        self.reject("ld_n must be a constant integer")

    def test_ld_order_mismatch(self):
        self.tables[2][0],self.tables[2][1] = self.tables[2][1],self.tables[2][0]
        self.reject("LD row/column identity or order mismatch")

    def test_ld_missing_pair_column(self):
        name = list(self.tables[2][0])[-1]
        for row in self.tables[2]:
            del row[name]
        self.reject("LD row/column identity or order mismatch")

    def test_ld_asymmetry(self):
        self.tables[2][0][self.tables[0][1]["snp"]] = "0.12345"
        self.reject("Signed LD must be square, symmetric")

    def test_ld_non_PSD(self):
        identifiers = [row["snp"] for row in self.tables[0]]
        for index,row in enumerate(self.tables[2]):
            for column,name in enumerate(identifiers):
                row[name] = "1" if column == index else "-0.9"
        self.reject("Signed LD is not positive semidefinite")

    def test_unknown_trait_type(self):
        self.parameters["type1"] = "gaussian"
        self.reject("Trait types must be explicitly quant or cc")

    def test_missing_quant_sd(self):
        del self.parameters["sd_y1"]
        self.reject("Invalid setting COLOC_SD_Y1")

    def test_invalid_case_fraction(self):
        self.parameters.update(type2="cc", case_fraction2=1)
        self.reject("Known case fraction must lie strictly")

    def test_missing_alignment_evidence(self):
        self.parameters["alignment_evidence"] = ""
        self.reject("alignment_evidence must identify")

    def test_invalid_prior(self):
        self.parameters["p12"] = .5
        self.reject("Priors must be in (0,1)")

    def test_nonconvergence_is_not_retried(self):
        self.parameters["max_iter"] = 1
        self.reject("did not converge")

    def test_existing_output_is_not_overwritten(self):
        filename = self.case / "output/coloc.RDS"
        filename.write_bytes(b"SENTINEL")
        self.write_inputs()
        result = execute(self.case, "node", self.command())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("overwrite refused", result.stderr.decode())
        self.assertEqual(filename.read_bytes(), b"SENTINEL")
        self.assertFalse((self.case / "output/coloc_summary.tsv").exists())


if __name__ == "__main__":
    unittest.main()
