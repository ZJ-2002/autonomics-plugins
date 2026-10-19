import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


PROGRAM = Path(__file__).resolve().parents[1] / "staged-adapters/ieugwasr-official/scripts/official.R"


@unittest.skipUnless(shutil.which("Rscript"), "Rscript is required; skipped tests are not admission evidence")
class IeugwasrOfficialContractTests(unittest.TestCase):
    def run_r(self, body):
        with tempfile.TemporaryDirectory(prefix="ieugwasr-toy-contract-") as directory:
            script = Path(directory) / "test.R"
            script.write_text(
                "source(" + json.dumps(str(PROGRAM)) + ")\n"
                "setwd(" + json.dumps(directory) + ")\n"
                "must_fail <- function(expression) {\n"
                "  result <- tryCatch({force(expression); FALSE}, error=function(condition) TRUE)\n"
                "  stopifnot(isTRUE(result))\n}\n" + body,
                encoding="utf-8",
            )
            result = subprocess.run(
                ["Rscript", "--vanilla", str(script)],
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exact_author_arguments_and_complete_return_are_preserved(self):
        self.run_r('''
requests <- list(
 list(operation="associations", arguments=list(variants=list("rs1","rs2"),id="study",proxies=0,r2=0.8)),
 list(operation="phewas", arguments=list(variants="rs1",batch=list(),pval=0.01)),
 list(operation="phewas", arguments=list(variants="rs1",batch=list(1,2,3),pval=0.01)),
 list(operation="tophits", arguments=list(id="study",force_server=TRUE,kb=10000)),
 list(operation="variants_rsid", arguments=list(rsid="rs1")),
 list(operation="variants_chrpos", arguments=list(chrpos="1:2",radius=0)),
 list(operation="ld_clump_api",arguments=list(clump_kb=10000,clump_r2=0.001,clump_p=1,pop="EUR")),
 list(operation="gwasinfo",arguments=list())
)
dataset <- data.frame(rsid=c("rs2","rs1"), pval=c(0.1,0.2), extra=c("kept","kept"),row.names=c("b","a"))
for (request in requests) {
 captured <- NULL
 resolver <- function(operation) {
  stopifnot(identical(operation,request$operation))
  function(...) { captured <<- list(...); structure(dataset, toy_attribute="untouched") }
 }
 result <- invoke_official(request, if(request$operation=="ld_clump_api")dataset else NULL, resolver)
 expected <- validate_request(request)$arguments
 if(request$operation=="ld_clump_api")expected$dat <- dataset
 stopifnot(identical(captured,expected), identical(attr(result,"toy_attribute"),"untouched"))
}
''')

    def test_unknown_and_credential_arguments_are_rejected(self):
        self.run_r('''
for (field in c("opengwas_jwt","token","timeout","population","variant")) {
 arguments <- list(variants="rs1",id="study");arguments[[field]] <- "not-a-credential"
 must_fail(validate_request(list(operation="associations",arguments=arguments)))
}
must_fail(validate_request(list(operation="gwasinfo_search",arguments=list(keyword="x"))))
must_fail(validate_request(list(operation="tophits",arguments=list(id="study",preclumped=1))))
''')

    def test_typed_projection_preserves_special_values(self):
        self.run_r('''
result <- data.frame(number=c(1,NA,NaN,Inf,-Inf), integer=c(1L,NA,2L,3L,4L), text=c("NA","","x","y",NA), flag=c(TRUE,FALSE,NA,TRUE,FALSE))
projection <- typed_projection(result)
stopifnot(identical(vapply(projection$columns[[1]]$cells,function(cell)cell$state,character(1)),c("PRESENT","MISSING_NA","NAN","POSITIVE_INFINITY","NEGATIVE_INFINITY")))
stopifnot(identical(projection$columns[[2]]$storage_type,"integer"),identical(unlist(projection$row_names),rownames(result)))
stopifnot(identical(projection$columns[[3]]$cells[[1]]$value,"NA"))
''')

    def test_lossy_projection_is_rejected(self):
        self.run_r('''
must_fail(typed_projection(data.frame(factor=factor("x"))))
must_fail(typed_projection(data.frame(date=as.Date("2026-01-01"))))
result <- data.frame(id=1);result$nested <- list(list(value=1))
must_fail(typed_projection(result))
must_fail(typed_projection(NULL))
''')

    def test_complete_rds_roundtrip_and_four_ports(self):
        self.run_r('''
stopifnot(requireNamespace("jsonlite",quietly=TRUE))
result <- structure(data.frame(value=c(1,NA),row.names=c("second","first")),toy_metadata=list(order=c(2L,1L)))
outputs <- file.path(getwd(),paste0("out",0:3))
request <- list(operation="gwasinfo",arguments=list())
publish_ports(outputs,function(staged)write_official_products(request,NULL,staged,function(operation)function(...)result))
stopifnot(identical(readRDS(outputs[[1]]),result),all(file.exists(outputs)),file.info(outputs[[4]])$size>0)
projection <- jsonlite::read_json(outputs[[2]])
stopifnot(projection$rows==2,identical(unlist(projection$row_names),rownames(result)))
''')

    def test_projection_failure_publishes_no_ports(self):
        self.run_r('''
outputs <- file.path(getwd(),paste0("out",0:3))
request <- list(operation="gwasinfo",arguments=list())
must_fail(publish_ports(outputs,function(staged)write_official_products(request,NULL,staged,function(operation)function(...)data.frame(value=factor("x")))))
stopifnot(!any(file.exists(outputs)))
''')

    def test_official_error_is_not_converted_to_empty_success(self):
        self.run_r('''
request <- list(operation="variants_rsid",arguments=list(rsid="rs1"))
message <- tryCatch(invoke_official(request,resolver=function(operation)function(...)stop("author sentinel")),error=function(condition)conditionMessage(condition))
stopifnot(identical(message,"author sentinel"))
''')

    def test_existing_dangling_and_alias_destinations_are_refused(self):
        self.run_r('''
outputs <- file.path(getwd(),paste0("out",0:3))
writeLines("foreign",outputs[[1]])
must_fail(publish_ports(outputs,function(staged)stop("writer must not run")))
stopifnot(identical(readLines(outputs[[1]]),"foreign"));unlink(outputs[[1]])
stopifnot(file.symlink("missing",outputs[[2]]))
must_fail(publish_ports(outputs,function(staged)stop("writer must not run")))
stopifnot(nzchar(Sys.readlink(outputs[[2]])));unlink(outputs[[2]])
outputs[[2]] <- outputs[[1]]
must_fail(publish_ports(outputs,function(staged)stop("writer must not run")))
''')

    def test_late_foreign_output_is_not_overwritten(self):
        self.run_r('''
outputs <- file.path(getwd(),paste0("out",0:3))
must_fail(publish_ports(outputs,function(staged) {
 for (filename in staged)writeLines("owned",filename)
 writeLines("foreign",outputs[[3]])
}))
stopifnot(!file.exists(outputs[[1]]),!file.exists(outputs[[2]]),!file.exists(outputs[[4]]),identical(readLines(outputs[[3]]),"foreign"))
''')


if __name__ == "__main__":
    unittest.main()
