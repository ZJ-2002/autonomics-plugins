import csv
import json
import pathlib
import unittest

import numpy as np

import test_contract as legacy


ROOT = pathlib.Path(__file__).resolve().parents[1]


class DenseSusieContract(unittest.TestCase):
    command = legacy.SusieContract.command
    write_input = legacy.SusieContract.write_input
    reject = legacy.SusieContract.reject

    def setUp(self):
        self.case = legacy.EVIDENCE / self._testMethodName
        self.case.mkdir(parents=True, exist_ok=False)
        (self.case / "work/.autonomics").mkdir(parents=True)
        (self.case / "output").mkdir()
        with (ROOT / "fixtures/complete_ld_50.tsv").open() as handle:
            self.rows = list(csv.DictReader(handle, delimiter="\t"))
        self.parameters = {"SUSIE_LD_SOURCE": "input", "SUSIE_LD_ROLE": "external", "SUSIE_SEED": "1"}

    def matrix(self):
        return np.array([[float(row["ld:" + other["snp"]]) for other in self.rows] for row in self.rows])

    def strong_scores(self):
        scores = 10 * self.matrix()[:, 0]
        for row, score in zip(self.rows, scores):
            row["z"] = format(score, ".17g")

    def positive(self, expect_credible_set=False, expect_nonconverged=False):
        self.write_input()
        result = legacy.execute(self.case, "node", self.command())
        if expect_nonconverged:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("official SuSiE fit did not converge", result.stderr.decode())
            self.assertFalse((self.case / "output/fit.RDS").exists())
            self.assertFalse((self.case / "output/fit.tsv").exists())
        else:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertIn("converged: TRUE", (self.case / "output/fit.log").read_text())
        self.assertIn("LD source: input", (self.case / "output/fit.log").read_text())
        settings = {"seed": self.parameters.get("SUSIE_SEED", "1"), "effects": self.parameters.get("SUSIE_L", "10"),
                    "scaled_prior_variance": self.parameters.get("SUSIE_SCALED_PRIOR_VARIANCE", "0.2"),
                    "estimate_prior_variance": self.parameters.get("SUSIE_ESTIMATE_PRIOR_VARIANCE", "true").upper(),
                    "estimate_residual_variance": self.parameters.get("SUSIE_ESTIMATE_RESIDUAL_VARIANCE", "false").upper(),
                    "prior_method": json.dumps(self.parameters.get("SUSIE_ESTIMATE_PRIOR_METHOD", "optim")),
                    "z_method": json.dumps(self.parameters.get("SUSIE_Z_METHOD", "wald")),
                    "null_threshold": self.parameters.get("SUSIE_CHECK_NULL_THRESHOLD", "0"),
                    "coverage": self.parameters.get("SUSIE_COVERAGE", "0.95"),
                    "min_abs_corr": self.parameters.get("SUSIE_MIN_ABS_CORR", "0.5"),
                    "max_iter": self.parameters.get("SUSIE_MAX_ITER", "100")}
        (self.case / "settings.R").write_text("list(" + ",".join(f"{name}={value}" for name, value in settings.items()) + ")\n")
        command = ["podman", "run", "--rm", "--pull=never", "--network=none", "--cpus=2", "--memory=2g",
                   "--entrypoint", "Rscript", "--mount", f"type=bind,src={self.case},dst=/case",
                   "--mount", f"type=bind,src={legacy.REFERENCE_LIBRARY},dst=/reference-library,ro=true",
                   "--mount", f"type=bind,src={ROOT}/tests/dense_reference.R,dst=/reference.R,ro=true",
                   legacy.IMAGE, "/reference.R", "/reference-library", "/case", "/case/settings.R"]
        if expect_nonconverged:
            command.append("nonconverged")
        reference = legacy.execute(self.case, "independent-author", command)
        self.assertEqual(reference.returncode, 0, reference.stderr.decode())
        expected = "OFFICIAL_NONCONVERGENCE_MATCH_NO_RESULT_PUBLICATION" if expect_nonconverged else "FULL_OFFICIAL_OBJECT_AND_EVERY_TSV_COLUMN_MATCH"
        self.assertIn(expected, reference.stdout.decode())
        if expect_credible_set:
            with (self.case / "output/fit.tsv").open() as handle:
                output = list(csv.DictReader(handle, delimiter="\t"))
            self.assertTrue(any(row["cs_all"] for row in output))

    def test_complete_50_default_external(self):
        self.positive()

    def test_complete_50_strong_credible_set(self):
        self.strong_scores()
        self.positive(expect_credible_set=True)

    def test_complete_50_L20_EM(self):
        self.strong_scores()
        self.parameters.update(SUSIE_L="20", SUSIE_ESTIMATE_PRIOR_METHOD="EM", SUSIE_SEED="17")
        self.positive(expect_nonconverged=True)

    def test_complete_50_L20_EM_explicit_iteration_budget(self):
        self.strong_scores()
        self.parameters.update(SUSIE_L="20", SUSIE_ESTIMATE_PRIOR_METHOD="EM", SUSIE_SEED="17", SUSIE_MAX_ITER="1000")
        self.positive(expect_credible_set=True)

    def test_complete_50_fixed_prior_score(self):
        self.strong_scores()
        self.parameters.update(SUSIE_ESTIMATE_PRIOR_METHOD="simple", SUSIE_ESTIMATE_PRIOR_VARIANCE="false", SUSIE_Z_METHOD="score")
        self.positive(expect_credible_set=True)

    def test_complete_50_effect_allele_reversal(self):
        self.strong_scores()
        for index, row in enumerate(self.rows):
            alleles = row["snp"].split(":")[-2:]
            if index % 3 == 0:
                alleles.reverse()
                row["z"] = format(-float(row["z"]), ".17g")
            row["a1"], row["a2"] = alleles
        self.positive(expect_credible_set=True)

    def test_complete_50_counting_allele_reversal(self):
        self.strong_scores()
        signs = np.array([-1 if index % 3 == 0 else 1 for index in range(len(self.rows))])
        transformed = self.matrix() * np.outer(signs, signs)
        for index, row in enumerate(self.rows):
            if signs[index] == -1:
                row["ld_a1"], row["ld_a2"] = row["ld_a2"], row["ld_a1"]
            for column, other in enumerate(self.rows):
                row["ld:" + other["snp"]] = format(transformed[index, column], ".17g")
        self.positive(expect_credible_set=True)

    def test_complete_50_coherent_row_and_column_permutation(self):
        self.strong_scores()
        self.rows.reverse()
        metadata = [name for name in self.rows[0] if not name.startswith("ld:")]
        order = metadata + ["ld:" + row["snp"] for row in self.rows]
        self.rows = [{name: row[name] for name in order} for row in self.rows]
        self.positive(expect_credible_set=True)

    def test_in_sample_known_synthetic_cohort_residual_estimation(self):
        generator = np.random.default_rng(314159)
        genotypes = generator.binomial(2, .3, size=(128, 50))
        standardized = (genotypes - genotypes.mean(axis=0)) / genotypes.std(axis=0, ddof=1)
        phenotype = .6 * standardized[:, 0] + generator.normal(size=128)
        correlations = np.array([np.corrcoef(standardized[:, index], phenotype)[0, 1] for index in range(50)])
        scores = correlations * np.sqrt(126 / (1 - correlations ** 2))
        matrix = np.corrcoef(genotypes, rowvar=False)
        for index, row in enumerate(self.rows):
            row["n"] = row["ld_n"] = "128"
            row["z"] = format(scores[index], ".17g")
            for column, other in enumerate(self.rows):
                row["ld:" + other["snp"]] = format(matrix[index, column], ".17g")
        np.save(self.case / "synthetic-genotypes.npy", genotypes)
        np.save(self.case / "synthetic-phenotype.npy", phenotype)
        self.parameters.update(SUSIE_LD_ROLE="in_sample", SUSIE_ESTIMATE_RESIDUAL_VARIANCE="true")
        self.positive(expect_credible_set=True)

    def test_missing_matrix_column(self):
        missing = "ld:" + self.rows[0]["snp"]
        for row in self.rows:
            del row[missing]
        self.reject("exactly match the ordered SNP rows")

    def test_extra_matrix_column(self):
        for row in self.rows:
            row["ld:21:1:C:T"] = "0"
        self.reject("exactly match the ordered SNP rows")

    def test_wrong_column_order_is_not_silently_repaired(self):
        order = list(self.rows[0]); order[-1], order[-2] = order[-2], order[-1]
        self.rows = [{name: row[name] for name in order} for row in self.rows]
        self.reject("exactly match the ordered SNP rows")

    def test_wrong_row_identity_is_not_intersected(self):
        alleles = self.rows[0]["snp"].split(":")[-2:]
        self.rows[0]["snp"] = "21:1:" + ":".join(alleles)
        self.reject("exactly match the ordered SNP rows")

    def test_matrix_NaN(self):
        self.rows[0]["ld:" + self.rows[1]["snp"]] = "NaN"
        self.reject("must contain only finite numeric")

    def test_matrix_infinite(self):
        self.rows[0]["ld:" + self.rows[1]["snp"]] = "Inf"
        self.reject("must contain only finite numeric")

    def test_matrix_out_of_bounds(self):
        self.rows[0]["ld:" + self.rows[1]["snp"]] = "1.1"
        self.reject("bounded by one")

    def test_matrix_nonunit_diagonal(self):
        self.rows[0]["ld:" + self.rows[0]["snp"]] = "0.99"
        self.reject("unit diagonal")

    def test_matrix_nonsymmetric(self):
        self.rows[0]["ld:" + self.rows[1]["snp"]] = "0.12345"
        self.reject("symmetric")

    def test_matrix_non_PSD_is_not_repaired(self):
        identifiers = [row["snp"] for row in self.rows]
        for index, row in enumerate(self.rows):
            for column, identifier in enumerate(identifiers):
                row["ld:" + identifier] = "1" if index == column else "0"
        for first, second, correlation in [(0, 1, .9), (0, 2, .9), (1, 2, -.9)]:
            self.rows[first]["ld:" + identifiers[second]] = str(correlation)
            self.rows[second]["ld:" + identifiers[first]] = str(correlation)
        self.reject("not positive semidefinite")

    def test_missing_counting_allele(self):
        for row in self.rows:
            del row["ld_a1"]
        self.reject("requires ld_a1 and ld_a2")

    def test_incompatible_counting_allele(self):
        self.rows[0]["ld_a1"] = "XXX"
        self.reject("counting alleles must match")

    def test_missing_ld_n(self):
        for row in self.rows:
            del row["ld_n"]
        self.reject("requires its measured ld_n")

    def test_nonconstant_ld_n(self):
        self.rows[0]["ld_n"] = "490"
        self.reject("constant integer")

    def test_fractional_ld_n(self):
        for row in self.rows:
            row["ld_n"] = "489.5"
        self.reject("constant integer")

    def test_in_sample_count_mismatch(self):
        self.parameters["SUSIE_LD_ROLE"] = "in_sample"
        self.reject("GWAS n equal to ld_n")

    def test_in_sample_without_known_n(self):
        for row in self.rows:
            del row["n"]
        self.parameters["SUSIE_LD_ROLE"] = "in_sample"
        self.reject("known GWAS n equal")

    def test_external_residual_estimation_is_refused(self):
        self.parameters["SUSIE_ESTIMATE_RESIDUAL_VARIANCE"] = "true"
        self.reject("requires an in-sample LD route")

    def test_nonzero_sparsification_threshold_is_refused(self):
        self.parameters["SUSIE_R2_MIN"] = "0.01"
        self.reject("sparsification is unsupported")

    def test_unknown_ld_source(self):
        self.parameters["SUSIE_LD_SOURCE"] = "automatic"
        self.reject("ld_source must be mixer or input")

    def test_unknown_ld_role(self):
        self.parameters["SUSIE_LD_ROLE"] = "guessed"
        self.reject("ld_role must be external or in_sample")

    def test_explicit_matrix_is_not_ignored_by_mixer_default(self):
        self.parameters["SUSIE_LD_SOURCE"] = "mixer"
        self.reject("supplied LD is never silently ignored")


if __name__ == "__main__":
    unittest.main(verbosity=2)
