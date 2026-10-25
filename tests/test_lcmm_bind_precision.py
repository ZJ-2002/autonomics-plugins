import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROGRAM = Path(__file__).resolve().parents[1] / "research-adapters/cachexia-lcmm/scripts/lcmm.R"


class LcmmBindPrecisionTests(unittest.TestCase):
    def run_binding_block(self, params):
        self.assertIsNotNone(shutil.which("Rscript"), "Rscript is required; missing execution is not a pass")
        with tempfile.TemporaryDirectory(prefix="lcmm-bind-precision-") as directory:
            work = Path(directory)
            script = work / "check.R"
            request = {
                "schema_version": 1, "mode": "predict", "scope": "TECHNICAL_ONLY_NOT_G0",
                "input_role": "SYNTHETIC_TECHNICAL_INPUT", "scientific_qualification": "NOT_GRANTED",
                "analysis_role": "SYNTHETIC_TRAJECTORY_TECHNICAL_NOT_LANDMARK_PREDICTION",
                "test_id": "TOY_BIND_ONLY", "input0_sha256": "UPSTREAM_CONTENT_HASH",
                "input2_sha256": "UPSTREAM_CONTENT_HASH", "expected_row_ids": ["toy-row"],
                "max_input_bytes": 1024, "max_rows": 2, "params": params,
            }
            (work / "request.json").write_text(json.dumps(request, allow_nan=False))
            script.write_text(
                "source_lines <- readLines(" + json.dumps(str(PROGRAM)) + ",warn=FALSE)\n"
                "main_definition <- parse(text=source_lines)[[1L]]\n"
                "definitions <- as.list(main_definition[[3L]][[3L]])[-1L]\n"
                "environment <- new.env(parent=globalenv())\n"
                "wanted <- c('ROLE','require_value','exact','unique_json','text','strings','number','boolean','checksum','read_json','validate_request')\n"
                "for (definition in definitions) if (is.call(definition) && identical(definition[[1L]],as.name('<-')) && is.symbol(definition[[2L]]) && as.character(definition[[2L]]) %in% wanted) eval(definition,environment)\n"
                "stopifnot(all(vapply(wanted,exists,logical(1),envir=environment,inherits=FALSE)))\n"
                "start <- which(source_lines=='  if (mode == \"bind\") {')\n"
                "end <- which(source_lines=='    return(invisible(NULL))')\n"
                "stopifnot(length(start)==1L,length(end)==1L,end>start,source_lines[end+1L]=='  }')\n"
                "binder <- eval(parse(text=paste('function() {',paste(source_lines[start:(end+1L)],collapse='\\n'),'}')),environment)\n"
                "setwd(" + json.dumps(directory) + ")\n"
                "writeLines('toy-input-zero','input0');writeLines('toy-input-two','input2')\n"
                "environment$paths <- c('input0','request.json','input2')\n"
                "environment$mode <- 'bind'\n"
                "environment$request <- environment$read_json('request.json')\n"
                "environment$validate_request(environment$request,'predict')\n"
                "before <- environment$request\n"
                "input_hashes <- vapply(environment$paths,environment$checksum,character(1))\n"
                "Sys.setenv(AUTONOMICS_OUTPUT0='resolved.json',AUTONOMICS_OUTPUT1='audit.json',AUTONOMICS_OUTPUT2='bind.log')\n"
                "binder()\n"
                "after <- environment$read_json('resolved.json')\n"
                "expected <- before\n"
                "expected$input0_sha256 <- environment$checksum('input0')\n"
                "expected$input2_sha256 <- environment$checksum('input2')\n"
                "stopifnot(identical(after,expected))\n"
                "stopifnot(identical(input_hashes,vapply(environment$paths,environment$checksum,character(1))))\n"
                "audit <- environment$read_json('audit.json')\n"
                "stopifnot(isTRUE(audit$only_source_sha256_changed),identical(unlist(audit$changed_fields),c('input0_sha256','input2_sha256')),identical(audit$output0_sha256,environment$checksum('resolved.json')))\n",
                encoding="utf-8",
            )
            environment = {
                name: os.environ[name]
                for name in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "R_LIBS", "R_LIBS_USER", "R_LIBS_SITE")
                if name in os.environ
            }
            result = subprocess.run(
                ["Rscript", "--vanilla", str(script)], env=environment,
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_bind_preserves_adjacent_and_precise_nested_parameters(self):
        self.run_binding_block({"time_grid": [1.0000000000000002, 1.2345678901234567], "convB": 0.00010000000000000002})

    def test_bind_preserves_finite_extremes_without_overflow(self):
        self.run_binding_block({"values": [1.7976931348623157e308, -1.7976931348623157e308, 2.2250738585072014e-308, 5e-324]})

    def test_bind_preserves_non_numeric_types_nested_arrays_and_null(self):
        self.run_binding_block({"label": "1.2345678901234567", "enabled": False, "empty": [], "nullable": None, "nested": [{"integer": 3, "names": ["a", "b"]}]})


if __name__ == "__main__":
    unittest.main()
