import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROGRAM = Path(__file__).resolve().parents[1] / "research-adapters/ieugwasr-official/scripts/dispatch.R"


class IeugwasrProjectionPrecisionTests(unittest.TestCase):
    def run_r(self, values, checks=None):
        self.assertIsNotNone(shutil.which("Rscript"), "Rscript is required; missing execution is not a pass")
        with tempfile.TemporaryDirectory(prefix="ieugwasr-projection-precision-") as directory:
            script = Path(directory) / "check.R"
            script.write_text(
                "source(" + json.dumps(str(PROGRAM)) + ")\n"
                "setwd(" + json.dumps(directory) + ")\n"
                "values <- " + values + "\n"
                "result <- data.frame(value=values,row.names=paste0('donor-',rev(seq_along(values))))\n"
                "outputs <- file.path(getwd(),paste0('port-',0:3))\n"
                "request <- list(operation='gwasinfo',arguments=list())\n"
                "publish_ports(outputs,function(staged)write_official_products(request,NULL,staged,function(operation)function(...)result))\n"
                "stopifnot(identical(readRDS(outputs[[1]]),result))\n"
                "projection <- jsonlite::read_json(outputs[[2]],simplifyVector=FALSE)\n"
                "stopifnot(identical(unlist(projection$row_names),rownames(result)))\n"
                "stopifnot(identical(unlist(projection$result_classes),class(result)))\n"
                "stopifnot(identical(projection$columns[[1]]$storage_type,'double'))\n"
                "cells <- projection$columns[[1]]$cells\n"
                + (checks if checks is not None else
                "stopifnot(all(vapply(cells,function(cell)identical(cell$state,'PRESENT'),logical(1))))\n"
                "restored <- vapply(cells,function(cell)as.double(cell$value),numeric(1))\n"
                "stopifnot(identical(writeBin(restored,raw(),size=8L),writeBin(values,raw(),size=8L)))\n"),
                encoding="utf-8",
            )
            environment = {
                name: os.environ[name]
                for name in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "R_LIBS", "R_LIBS_USER", "R_LIBS_SITE")
                if name in os.environ
            }
            result = subprocess.run(
                ["Rscript", "--vanilla", str(script)],
                env=environment, capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_adjacent_and_arbitrary_finite_doubles_roundtrip(self):
        self.run_r("c(1+.Machine$double.eps,1-.Machine$double.eps,1.2345678901234567,-1.2345678901234567)")

    def test_finite_range_extremes_do_not_round_to_infinity(self):
        self.run_r("c(.Machine$double.xmax,-.Machine$double.xmax,.Machine$double.xmin,-.Machine$double.xmin,5e-324,-5e-324)")

    def test_special_states_remain_explicit_and_rds_preserves_signed_zero(self):
        self.run_r(
            "c(NA_real_,NaN,Inf,-Inf,-0,0)",
            "stopifnot(identical(vapply(cells,function(cell)cell$state,character(1)),c('MISSING_NA','NAN','POSITIVE_INFINITY','NEGATIVE_INFINITY','PRESENT','PRESENT')))\n"
            "stopifnot(identical(writeBin(readRDS(outputs[[1]])$value,raw(),size=8L),writeBin(values,raw(),size=8L)))\n"
            "stopifnot(all(vapply(cells[1:4],function(cell)is.null(cell$value),logical(1))))\n",
        )


if __name__ == "__main__":
    unittest.main()
