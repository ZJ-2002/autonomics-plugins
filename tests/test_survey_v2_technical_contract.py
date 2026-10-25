import hashlib
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from tests.conditional_v2_baseline import published_bytes


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'research-adapters/cachexia-survey'
BASELINE_REVISION = 'f3715049facecc04abf8778ac71e01abb5b4b0e4'
PROGRAM = r'''
arguments <- commandArgs(trailingOnly = TRUE)
load_functions <- function(filename) {
  environment <- new.env(parent = globalenv())
  for (expression in parse(filename)) {
    if (is.call(expression) && identical(expression[[1]], as.name("<-")) &&
        (as.character(expression[[2]]) %in% c("ROLE", "METHOD_KEYS") ||
         (is.call(expression[[3]]) && identical(expression[[3]][[1]], as.name("function"))))) {
      eval(expression, environment)
    }
  }
  environment
}
survey <- load_functions(file.path(arguments[[1]], "scripts/survey.R"))
binder <- load_functions(file.path(arguments[[1]], "scripts/bind_contract.R"))
environments <- list(survey, binder)
request <- function(version = 2L, role = "EMPIRICAL_TECHNICAL_INPUT") {
  list(schema_version = version, mode = "mean", scope = "TECHNICAL_ONLY_NOT_G0",
       input_role = role, scientific_qualification = "NOT_GRANTED",
       analysis_role = "SURVEY_TECHNICAL_BACKGROUND_ASSOCIATION_NOT_CANCER_MECHANISM",
       test_id = "toy_guard", input0_sha256 = paste(rep("a", 64), collapse = ""),
       expected_row_ids = list("001", "NA"), max_input_bytes = 1024L, max_rows = 2L,
       params = list(variables = list("value"), na_rm = FALSE, deff = FALSE, conf_level = .95, ci_df = "DESIGN"))
}
rejected <- function(expression) {
  result <- tryCatch({ force(expression); FALSE }, error = function(condition) TRUE)
  stopifnot(result)
}
state <- function(current) {
  bundle <- list(schema_version = 1L, scope = current$scope, analysis_role = current$analysis_role,
    original_row_ids = c("001", "NA"), design_options = list(), design = structure(list(), class = "survey.design2"),
    result = NULL, lineage = list(list(mode = "design", request = current, parent_sha256 = current$input0_sha256)))
  survey$declare_state_contract(bundle, current)
}
case <- arguments[[3]]
if (case == "v1_default_and_v2_bypass_rejection") {
  Sys.unsetenv("AUTONOMICS_TECHNICAL_CONTRACT_VERSION")
  for (environment in environments) {
    stopifnot(environment$technical_contract_version() == 1L)
    environment$validate_technical_identity(request(1L, "SYNTHETIC_TECHNICAL_INPUT"))
    rejected(environment$validate_technical_identity(request(1L)))
    rejected(environment$validate_technical_identity(request(2L)))
  }
} else if (case == "v2_truthful_roles_and_no_scientific_escalation") {
  Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION = "2")
  for (environment in environments) {
    for (role in c("EMPIRICAL_TECHNICAL_INPUT", "SYNTHETIC_TECHNICAL_INPUT")) environment$validate_technical_identity(request(2L, role))
    for (field in c("scope", "scientific_qualification", "analysis_role", "input_role")) {
      changed <- request(); changed[[field]] <- "GRANTED"
      rejected(environment$validate_technical_identity(changed))
    }
    rejected(environment$validate_technical_identity(request(1L, "SYNTHETIC_TECHNICAL_INPUT")))
    Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION = "3")
    rejected(environment$validate_technical_identity(request()))
    Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION = "2")
  }
} else if (case == "v2_state_rds_and_cross_version_role_laundering") {
  Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION = "2")
  current <- request()
  bundle <- state(current)
  destination <- file.path(arguments[[2]], "state.rds")
  saveRDS(bundle, destination)
  recovered <- readRDS(destination)
  stopifnot(identical(recovered, bundle), recovered$schema_version == 2L,
    identical(recovered$input_role, current$input_role), identical(recovered$scientific_qualification, "NOT_GRANTED"))
  for (environment in environments) {
    environment$validate_state_contract(recovered, current)
    changed <- recovered; changed$schema_version <- 1L
    rejected(environment$validate_state_contract(changed, current))
    rejected(environment$validate_state_contract(recovered, request(2L, "SYNTHETIC_TECHNICAL_INPUT")))
    changed <- recovered; changed$input_role <- "SYNTHETIC_TECHNICAL_INPUT"
    rejected(environment$validate_state_contract(changed, request(2L, "SYNTHETIC_TECHNICAL_INPUT")))
    changed <- recovered; changed$lineage[[1]]$request$schema_version <- 1L
    rejected(environment$validate_state_contract(changed, current))
    changed <- recovered; changed$scientific_qualification <- "GRANTED"
    rejected(environment$validate_state_contract(changed, current))
  }
} else if (case == "explicit_population_role_and_values_not_invented") {
  Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION = "1")
  survey$validate_population_role("SYNTHETIC_KNOWN_POPULATION_NOT_STUDY")
  rejected(survey$validate_population_role("EXPLICIT_POPULATION_TOTALS_NOT_STUDY_QUALIFIED"))
  Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION = "2")
  survey$validate_population_role("EXPLICIT_POPULATION_TOTALS_NOT_STUDY_QUALIFIED")
  rejected(survey$validate_population_role("SYNTHETIC_KNOWN_POPULATION_NOT_STUDY"))
  data <- data.frame(group = factor(c("F", "M"), levels = c("F", "M")))
  population <- list(list(group = "F", Freq = 17), list(group = "M", Freq = 23))
  original <- population
  result <- survey$population_frame(population, "group", data)
  stopifnot(identical(population, original), identical(result$Freq, c(17, 23)))
  rejected(survey$population_frame(list(), "group", data))
  rejected(survey$population_frame(list(list(group = "F")), "group", data))
  rejected(survey$population_frame(list(population[[1]], population[[1]]), "group", data))
  rejected(survey$population_frame(list(list(group = "X", Freq = 1)), "group", data))
} else if (case == "v2_binder_preserves_raw_params_and_shared_guard_definitions") {
  Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION = "2")
  for (name in c("technical_contract_version", "validate_technical_identity", "validate_state_contract")) {
    stopifnot(identical(deparse(survey[[name]]), deparse(binder[[name]])))
  }
  original <- charToRaw('{"schema_version":2,"input_role":"EMPIRICAL_TECHNICAL_INPUT","input0_sha256":"UPSTREAM_CONTENT_HASH","params":{"value":1.0000000000000002,"tiny":2.2250738585072014e-308}}')
  checksum <- paste(rep("b", 64), collapse = "")
  bound <- binder$bind_json_hash(original, checksum)
  expected <- charToRaw(sub('"UPSTREAM_CONTENT_HASH"', paste0('"', checksum, '"'), rawToChar(original), fixed = TRUE))
  stopifnot(identical(bound, expected))
} else if (case == "actual_v2_R_audit_records_request_and_complete_state_role") {
  Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION = "2")
  blocks <- list()
  walk <- function(expression) {
    if (missing(expression) || !is.call(expression)) return(invisible(NULL))
    if (identical(expression[[1]], as.name("if")) &&
        identical(paste(deparse(expression[[2]]), collapse = ""), "technical_contract_version() == 2L") &&
        grepl("audit\\$state_schema_version", paste(deparse(expression), collapse = "\n"))) {
      blocks[[length(blocks) + 1L]] <<- expression
    }
    for (child in as.list(expression)) walk(child)
  }
  walk(body(survey$run_survey))
  stopifnot(length(blocks) == 1L)
  environment <- new.env(parent = survey)
  environment$request <- request()
  environment$computed <- list(bundle = state(environment$request))
  environment$audit <- list(G0_granted = FALSE, scientific_qualification_granted = FALSE)
  eval(blocks[[1]], environment)
  audit <- environment$audit
  stopifnot(audit$schema_version == 2L, audit$state_schema_version == 2L,
    identical(audit$input_role, "EMPIRICAL_TECHNICAL_INPUT"), identical(audit$state_input_role, audit$input_role),
    identical(audit$scientific_qualification, "NOT_GRANTED"), identical(audit$state_scientific_qualification, "NOT_GRANTED"),
    identical(audit$G0_granted, FALSE), identical(audit$scientific_qualification_granted, FALSE))
} else if (case == "official_numeric_calls_and_v1_state_keys_unchanged") {
  baseline <- load_functions(arguments[[4]])
  calls <- function(expression) {
    result <- character()
    walk <- function(current) {
      if (missing(current)) return(invisible(NULL))
      if (!is.call(current) && !is.expression(current)) return(invisible(NULL))
      if (is.call(current)) {
        head <- current[[1]]
        if ((is.call(head) && identical(head[[1]], as.name("::")) && identical(head[[2]], as.name("survey"))) ||
            (identical(head, as.name("do.call")) && is.call(current[[2]]) && identical(current[[2]][[1]], as.name("::")) && identical(current[[2]][[2]], as.name("survey")))) {
          result <<- c(result, paste(deparse(current), collapse = "\n"))
        }
      }
      for (child in as.list(current)) walk(child)
    }
    walk(expression)
    result
  }
  for (name in c("build_design", "analyse", "run_survey")) stopifnot(identical(calls(body(survey[[name]])), calls(body(baseline[[name]]))))
  Sys.setenv(AUTONOMICS_TECHNICAL_CONTRACT_VERSION = "1")
  current <- request(1L, "SYNTHETIC_TECHNICAL_INPUT")
  bundle <- state(current)
  stopifnot(identical(names(bundle), c("schema_version", "scope", "analysis_role", "original_row_ids", "design_options", "design", "result", "lineage")), bundle$schema_version == 1L)
} else stop("Unknown test case")
cat("PASS", case, "\n")
'''


def git_source(name):
    return published_bytes(name)


class SurveyV2TechnicalContractTests(unittest.TestCase):
    def run_case(self, case):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / 'guard.R'
            program.write_text(PROGRAM)
            baseline = Path(temporary) / 'baseline-survey.R'
            baseline.write_bytes(git_source('research-adapters/cachexia-survey/scripts/survey.R'))
            result = subprocess.run(['Rscript', '--vanilla', str(program), str(FAMILY), temporary, case, str(baseline)],
                text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS ' + case, result.stdout)

    def test_v1_default_and_v2_bypass_rejection(self):
        self.run_case('v1_default_and_v2_bypass_rejection')

    def test_v2_truthful_roles_and_no_scientific_escalation(self):
        self.run_case('v2_truthful_roles_and_no_scientific_escalation')

    def test_v2_state_rds_and_cross_version_role_laundering(self):
        self.run_case('v2_state_rds_and_cross_version_role_laundering')

    def test_explicit_population_role_and_values_not_invented(self):
        self.run_case('explicit_population_role_and_values_not_invented')

    def test_v2_binder_preserves_raw_params_and_shared_guard_definitions(self):
        self.run_case('v2_binder_preserves_raw_params_and_shared_guard_definitions')

    def test_official_numeric_calls_and_v1_state_keys_unchanged(self):
        self.run_case('official_numeric_calls_and_v1_state_keys_unchanged')

    def test_actual_v2_R_audit_records_request_and_complete_state_role(self):
        self.run_case('actual_v2_R_audit_records_request_and_complete_state_role')

    def test_manifest_keeps_all_v1_nodes_and_adds_eleven_explicit_v2_kinds(self):
        before = tomllib.loads(git_source('research-adapters/cachexia-survey/manifest.toml').decode())
        current = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.assertEqual(len(current['nodes']), 22)
        self.assertEqual(current['nodes'][:11], before['nodes'])
        self.assertEqual(current['image'], before['image'])
        for original, versioned in zip(before['nodes'], current['nodes'][11:], strict=True):
            self.assertEqual(versioned['kind'], original['kind'] + '_v2')
            self.assertEqual(versioned['ports'], original['ports'])
            self.assertEqual(versioned['resources'], original['resources'])
            expected = dict(original['command']['env'], AUTONOMICS_TECHNICAL_CONTRACT_VERSION='2')
            self.assertEqual(versioned['command']['env'], expected)
            self.assertEqual(versioned['command']['script_file'], original['command']['script_file'])


if __name__ == '__main__':
    unittest.main()
