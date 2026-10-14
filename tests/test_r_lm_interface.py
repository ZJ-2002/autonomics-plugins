import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest

from tools import prove_r_lm

ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / "plugins/r-stats-lm"


class OfficialLinearModelTests(unittest.TestCase):
    def test_evidence_cannot_silently_cover_changed_sources_or_production(self):
        record = json.loads((ROOT / "evidence/r-stats-lm-20261014.json").read_text())
        for path, key in [(FAMILY / "scripts/lm.R", "method_source_sha256"),
                          (FAMILY / "manifest.toml", "manifest_sha256"),
                          (ROOT / "tools/prove_r_lm.py", "proof_driver_sha256")]:
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record[key])
        self.assertEqual(record["original_function_id"], "FUNC_linear_regression")
        self.assertEqual(record["new_original_function_slots"], 0)
        for flag in ("whole_original_node_certified", "production_configuration_changed",
                     "native_statistical_fallback", "scientific_authorization_granted", "g0_granted"):
            self.assertFalse(record[flag])
        self.assertEqual(record["four_layers"]["plan_contract"], "NOT_FORMALLY_AUTHORIZED_TECHNICAL_ONLY")

    def test_manifest_binds_five_real_ports_and_immutable_image(self):
        manifest = tomllib.loads((FAMILY / "manifest.toml").read_text())
        self.assertIn("@sha256:", manifest["image"]["reference"])
        self.assertEqual(len(manifest["nodes"]), 1)
        node = manifest["nodes"][0]
        self.assertEqual(node["kind"], "r_stats_lm")
        self.assertEqual(len(node["ports"]["inputs"]), 2)
        self.assertEqual(len(node["ports"]["outputs"]), 5)
        self.assertTrue((FAMILY / node["command"]["script_file"]).is_file())

    def test_official_api_and_strict_scope_are_explicit(self):
        script = (FAMILY / "scripts/lm.R").read_text()
        for token in ("do.call(stats::lm", "stats::na.fail", "singular.ok = FALSE", "stats::confint", "stats::vcov", "TECHNICAL_ONLY_NOT_G0"):
            self.assertIn(token, script)
        self.assertNotIn("lm.fit <-", script)
        self.assertNotIn("na.omit", script)

    def test_every_case_has_separate_oracle_formula_or_expected_refusal(self):
        cases = prove_r_lm.fixtures()
        self.assertEqual(len(cases), len({case["name"] for case in cases}))
        positive = {case["name"] for case in cases if case["expected_error"] is None}
        self.assertTrue({"weighted", "zero-weight-row-retained", "offset", "weighted-offset", "factor-reference",
                         "factor-reversed-reference", "factor-interaction", "numeric-interaction", "intercept-only"}.issubset(positive))
        negative = {case["name"] for case in cases if case["expected_error"]}
        self.assertTrue({"wrong-hash", "duplicate-json-key", "rank-deficient", "untrusted-formula", "missing-response",
                         "absent-factor-reference", "reversed-duplicate-interaction", "no-residual-df"}.issubset(negative))

    def test_actual_r_parser_preserves_identity_and_rejects_invalid_values(self):
        interpreter = shutil.which("Rscript")
        self.assertIsNotNone(interpreter, "Mandatory parser test requires installed Rscript")
        program = r'''
source(commandArgs(TRUE)[[1]])
path <- tempfile()
writeLines(c("row_id\ty\tx", "0001\t1\t2", "1e03\t2\t3", "NA\t3\t4"),path)
parsed <- literal_tsv(path)
stopifnot(identical(parsed$row_id,c("0001","1e03","NA")),identical(numeric_column(parsed$y),c(1,2,3)))
for(value in c("NA","NaN","Inf"," 1","1x","")) stopifnot(inherits(try(numeric_column(value),silent=TRUE),"try-error"))
writeLines(c("row_id\ty\tx","bad\t1"),path)
stopifnot(inherits(try(literal_tsv(path),silent=TRUE),"try-error"))
unlink(path)
'''
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([interpreter, "--vanilla", "-", str(FAMILY / "scripts/lm.R")],
                                    input=program, text=True, capture_output=True, cwd=directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_actual_publication_preserves_existing_and_foreign_files(self):
        interpreter = shutil.which("Rscript")
        self.assertIsNotNone(interpreter, "Mandatory publication test requires installed Rscript")
        program = r'''
scope <- new.env(parent=globalenv())
sys.source(commandArgs(TRUE)[[1]],envir=scope)
scope$sha256 <- function(path) substr(system2("sha256sum",shQuote(path),stdout=TRUE),1L,64L)
scope$fit_model <- function(...) {
  fitted <- stats::lm(y~x,data=data.frame(x=1:5,y=c(2,4,5,9,10)))
  list(contract=list(analysis_id="PUBLICATION_TOY",scope="TECHNICAL_ONLY_NOT_G0"),
    fit=fitted,summary=summary(fitted),coefficients=data.frame(term=names(coef(fitted)),estimate=unname(coef(fitted))),
    observations=data.frame(row_id=paste0("D",1:5),weight=1),warnings=character(),
    input_sha256="TOY_NOT_METHOD_EVIDENCE",contract_sha256="TOY_NOT_METHOD_EVIDENCE")
}
run_case <- function(scenario) {
  directory <- tempfile("r-lm-publication-test-")
  stopifnot(dir.create(directory))
  on.exit(unlink(directory,recursive=TRUE),add=TRUE)
  outputs <- file.path(directory,paste0("port",0:4))
  names(outputs) <- paste0("AUTONOMICS_OUTPUT",0:4)
  if(scenario=="existing") writeLines("OLD",outputs[[3]])
  if(scenario=="alias") outputs[[2]] <- outputs[[1]]
  referent <- file.path(directory,"referent")
  writeLines("FOREIGN REFERENT",referent)
  if(scenario=="dangling") stopifnot(file.symlink(file.path(directory,"missing"),outputs[[1]]))
  calls <- 0L
  scope$file.link <- function(from,to) {
    calls <<- calls+1L
    if(scenario %in% c("foreign-regular","foreign-symlink","third-failure") && calls==3L) return(FALSE)
    if(scenario=="appeared-at-link" && calls==1L) writeLines("FOREIGN RACE",to)
    answer <- suppressWarnings(base::file.link(from,to))
    if(answer && calls==1L && scenario %in% c("foreign-regular","foreign-symlink")) {
      unlink(to)
      if(scenario=="foreign-regular") writeLines("FOREIGN",to) else stopifnot(file.symlink(referent,to))
    }
    answer
  }
  do.call(Sys.setenv,as.list(outputs))
  error <- tryCatch({scope$main();NULL},error=function(condition) conditionMessage(condition))
  if(scenario=="normal" && !is.null(error)) stop(error)
  present <- file.exists(outputs)|vapply(outputs,scope$has_link,logical(1))
  if(scenario=="normal") stopifnot(is.null(error),all(present),calls==5L)
  else if(scenario=="existing") stopifnot(!is.null(error),identical(readLines(outputs[[3]]),"OLD"),!any(present[-3]))
  else if(scenario=="alias") stopifnot(!is.null(error),!any(present))
  else if(scenario=="foreign-regular") stopifnot(!is.null(error),identical(readLines(outputs[[1]]),"FOREIGN"),!any(present[-1]))
  else if(scenario=="foreign-symlink") stopifnot(!is.null(error),identical(Sys.readlink(outputs[[1]]),referent),identical(readLines(referent),"FOREIGN REFERENT"),!any(present[-1]))
  else if(scenario=="appeared-at-link") stopifnot(!is.null(error),identical(readLines(outputs[[1]]),"FOREIGN RACE"),!any(present[-1]))
  else if(scenario=="dangling") stopifnot(!is.null(error),scope$has_link(outputs[[1]]),!any(present[-1]))
  else if(scenario=="third-failure") stopifnot(!is.null(error),!any(present))
  else stop("Unknown required case")
  stopifnot(!any(startsWith(list.files(directory,all.files=TRUE),".r-stats-lm-")))
  cat(scenario,"PASS\n")
}
for(scenario in c("normal","existing","alias","foreign-regular","foreign-symlink","appeared-at-link","dangling","third-failure")) run_case(scenario)
'''
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([interpreter, "--vanilla", "-", str(FAMILY / "scripts/lm.R")],
                                    input=program, text=True, capture_output=True, cwd=directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(result.stdout.count("PASS"), 8, result.stdout)


if __name__ == "__main__":
    unittest.main()
