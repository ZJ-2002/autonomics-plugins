import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ROutputPublicationTests(unittest.TestCase):
    def run_component(self, relative, family):
        interpreter = shutil.which('Rscript')
        self.assertIsNotNone(interpreter, 'Rscript must execute mandatory publication counterexamples')
        program = r'''
source <- commandArgs(TRUE)[[1]]
family <- commandArgs(TRUE)[[2]]
lines <- readLines(source, warn = FALSE)
first <- which(lines == "main <- function() {")
front_last <- which(lines == "report_path <- staged_outputs[[5]]")
last <- which(lines == "complete <- TRUE")
tail_first <- if (family == "deseq2") max(which(lines == "links <- Sys.readlink(output_targets)")) else which(startsWith(lines, "if (any(file.exists(output_targets)) || any(!is.na(Sys.readlink(output_targets))"))
stopifnot(length(first) == 1L, length(front_last) == 1L, length(last) == 1L, length(tail_first) == 1L)
scope <- new.env(parent = globalenv())
for (expression in parse(source)) {
    if (is.call(expression) && identical(expression[[1]], as.name("<-")) && is.call(expression[[3]]) && identical(expression[[3]][[1]], as.name("function")) && !identical(expression[[2]], as.name("main"))) eval(expression, scope)
}
component <- c(lines[first:front_last], "for (index in seq_along(staged_outputs)) writeLines(paste0('OWN-', index), staged_outputs[[index]])", lines[tail_first:last], "}")
eval(parse(text = component), scope)
run_case <- function(scenario) {
    directory <- tempfile("publication-contract-")
    stopifnot(dir.create(directory))
    on.exit(unlink(directory, recursive = TRUE), add = TRUE)
    parents <- rep(directory, 5)
    if (scenario == "multiple-parents") {
        parents <- file.path(directory, paste0("parent-", seq_len(5)))
        stopifnot(all(vapply(parents, dir.create, logical(1))))
    }
    targets <- file.path(parents, paste0("port-'", seq_len(5), " $;\""))
    if (scenario == "alias") targets[[2]] <- file.path(directory, ".", basename(targets[[1]]))
    if (scenario == "existing") writeLines("OLD", targets[[3]])
    referent <- file.path(directory, "referent")
    writeLines("FOREIGN REFERENT", referent)
    calls <- 0L
    scope$file.link <- function(from, to) {
        calls <<- calls + 1L
        if (scenario %in% c("foreign-regular", "foreign-symlink", "third-failure") && calls == 3L) return(FALSE)
        if (scenario == "appeared-at-link" && calls == 1L) writeLines("FOREIGN RACE", to)
        answer <- base::file.link(from, to)
        if (isTRUE(answer)) stopifnot(identical(scope$publication_identity(from), scope$publication_identity(to)))
        if (isTRUE(answer) && calls == 1L && scenario %in% c("foreign-regular", "foreign-symlink")) {
            unlink(to)
            if (scenario == "foreign-regular") writeLines("FOREIGN", to) else stopifnot(file.symlink(referent, to))
        }
        answer
    }
    values <- c(AUTONOMICS_INPUT0 = "unused", AUTONOMICS_INPUT1 = "unused")
    names(targets) <- paste0("AUTONOMICS_OUTPUT", 0:4)
    do.call(Sys.setenv, as.list(c(values, targets)))
    error <- tryCatch({suppressWarnings(scope$main()); NULL}, error = function(condition) conditionMessage(condition))
    links <- Sys.readlink(targets)
    present <- file.exists(targets) | (!is.na(links) & nzchar(links))
    if (scenario %in% c("normal", "multiple-parents")) {
        stopifnot(is.null(error), all(present), calls == 5L)
        for (index in seq_len(5)) stopifnot(identical(readLines(targets[[index]]), paste0("OWN-", index)))
    } else if (scenario == "foreign-regular") stopifnot(!is.null(error), identical(readLines(targets[[1]]), "FOREIGN"), !any(present[2:5]))
    else if (scenario == "foreign-symlink") stopifnot(!is.null(error), identical(links[[1]], referent), identical(readLines(referent), "FOREIGN REFERENT"), !any(present[2:5]))
    else if (scenario == "third-failure") stopifnot(!is.null(error), !any(present))
    else if (scenario == "appeared-at-link") stopifnot(!is.null(error), identical(readLines(targets[[1]]), "FOREIGN RACE"), !any(present[2:5]))
    else if (scenario == "existing") stopifnot(!is.null(error), identical(readLines(targets[[3]]), "OLD"), !any(present[-3]))
    else if (scenario == "alias") stopifnot(!is.null(error), !any(present))
    else stop("unknown test case")
    stopifnot(!any(grepl("publication-", list.files(directory, all.files = TRUE, recursive = TRUE, include.dirs = TRUE), fixed = TRUE)))
    cat(scenario, "PASS\n")
}
for (scenario in c("normal", "multiple-parents", "foreign-regular", "foreign-symlink", "third-failure", "appeared-at-link", "existing", "alias")) run_case(scenario)
'''
        result = subprocess.run([interpreter, '--vanilla', '-', str(ROOT / relative), family], input=program,
            text=True, capture_output=True, env=dict(os.environ, OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count('PASS'), 8, result.stdout)

    def test_deseq2_actual_publication_component_preserves_foreign_outputs(self):
        self.run_component('plugins/deseq2/deseq2_runner.R', 'deseq2')

    def test_limma_actual_publication_component_preserves_foreign_outputs(self):
        self.run_component('plugins/bulk-rnaseq/limma_voom_runner.R', 'limma')
