from pathlib import Path
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / 'research-adapters/cachexia-sensitivity/scripts/sensitivity.R'
PROGRAM = r'''
arguments <- commandArgs(trailingOnly = TRUE)
program <- parse(arguments[[1]])
assignments <- list()
walk <- function(expression) {
  if (!is.call(expression) && !is.expression(expression)) return(invisible(NULL))
  if (is.call(expression) && identical(expression[[1]], as.name("<-")) &&
      identical(expression[[2]], as.name("ledger")) && is.call(expression[[3]]) &&
      "source_value" %in% names(as.list(expression[[3]]))) {
    assignments[[length(assignments) + 1L]] <<- expression
  }
  for (child in as.list(expression)) walk(child)
}
walk(program)
stopifnot(length(assignments) == 1L)
assignment <- assignments[[1]]
run_ledger <- function(effect) {
  environment <- new.env(parent = globalenv())
  environment$effect <- effect
  eval(assignment, environment)
  environment$ledger
}
effect <- list(effect_id = "toy", measure = "OLS", est = 1 + .Machine$double.eps,
               lo = NULL, hi = NULL, se = .Machine$double.xmin,
               sd = .Machine$double.xmax, delta = -.Machine$double.xmin,
               true_val = .Machine$double.xmin * .Machine$double.eps, rare = FALSE)
ledger <- run_ledger(effect)
stopifnot(identical(ledger$parameter, names(effect)), nrow(ledger) == length(effect))
recover <- function(parameter) jsonlite::fromJSON(ledger$source_value[ledger$parameter == parameter])
case <- arguments[[3]]
if (case == "finite_roundtrip") {
  for (parameter in c("est", "se", "sd", "delta", "true_val")) {
    stopifnot(identical(as.double(recover(parameter)), as.double(effect[[parameter]])))
  }
  for (parameter in c("est", "se", "sd")) {
    old <- jsonlite::fromJSON(jsonlite::toJSON(effect[[parameter]], auto_unbox = TRUE, digits = NA))
    stopifnot(!identical(as.double(old), as.double(effect[[parameter]])))
  }
} else if (case == "non_numeric_and_tsv") {
  stopifnot(identical(recover("effect_id"), "toy"), identical(recover("measure"), "OLS"),
            is.null(recover("lo")), is.null(recover("hi")), identical(recover("rare"), FALSE))
  destination <- file.path(arguments[[2]], "ledger.tsv")
  write.table(ledger, destination, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  recovered <- read.delim(destination, colClasses = "character", check.names = FALSE,
                          quote = "", na.strings = character())
  stopifnot(identical(names(recovered), names(ledger)),
            identical(unname(as.list(recovered)), unname(as.list(ledger))))
} else if (case == "rds_signed_zero_authority") {
  effect$est <- -0.0
  ledger <- run_ledger(effect)
  destination <- file.path(arguments[[2]], "state.rds")
  state <- list(input = effect, input_ledger = ledger)
  saveRDS(state, destination)
  restored <- readRDS(destination)
  stopifnot(identical(writeBin(restored$input$est, raw(), size = 8L), writeBin(effect$est, raw(), size = 8L)),
            identical(1 / restored$input$est, -Inf), identical(recover("est"), 0L))
} else stop("Unknown case")
cat("PASS", case, "R", as.character(getRversion()), "jsonlite", as.character(packageVersion("jsonlite")), "\n")
'''


class SensitivityInputLedgerPrecisionTests(unittest.TestCase):
    def run_case(self, case):
        with tempfile.TemporaryDirectory() as temporary:
            program = Path(temporary) / 'probe.R'
            program.write_text(PROGRAM)
            result = subprocess.run(['Rscript', '--vanilla', str(program), str(SOURCE), temporary, case],
                text=True, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('PASS ' + case, result.stdout)

    def test_finite_input_numeric_values_roundtrip(self):
        self.run_case('finite_roundtrip')

    def test_non_numeric_parameters_and_written_ledger_are_preserved(self):
        self.run_case('non_numeric_and_tsv')

    def test_rds_remains_signed_zero_authority(self):
        self.run_case('rds_signed_zero_authority')


if __name__ == '__main__':
    unittest.main()
