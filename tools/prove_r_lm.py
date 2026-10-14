"""Managed official-package linear-regression proof, never a scientific release."""

import argparse
import copy
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / "plugins/r-stats-lm"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def fixtures():
    rows = [{"row_id": identity, "y": outcome, "x": predictor}
            for identity, outcome, predictor in zip(
                ["0001", "1e03", "NA", "D3", "D4", "D5", "D6", "D7"],
                [2.1, 2.9, 5.4, 6.3, 7.8, 8.7, 11.2, 11.8], range(8), strict=True)]
    contract = dict(schema_version=1, scope="TECHNICAL_ONLY_NOT_G0", analysis_id="toy",
                    input_sha256="UNBOUND", response="y", columns={"y": {"type": "numeric"}, "x": {"type": "numeric"}},
                    terms=[["x"]], intercept=True, weights=None, offset=None,
                    qr_tolerance=1e-7, conf_level=.95)
    cases = []

    def add(name, transform=None, formula="y ~ x", error=None, mutation=None):
        data, method = copy.deepcopy(rows), copy.deepcopy(contract)
        if transform:
            transform(data, method)
        cases.append(dict(name=name, rows=data, contract=method, oracle_formula=formula,
                          expected_error=error, input_mutation=mutation))

    add("simple")
    add("no-intercept", lambda data, method: method.update(intercept=False), "y ~ 0 + x")
    add("reordered", lambda data, method: data.reverse())
    add("scaled-response", lambda data, method: [row.update(y=row["y"] * 1000) for row in data])
    add("shifted-predictor", lambda data, method: [row.update(x=row["x"] + 10) for row in data])

    def second(data, method):
        for index, row in enumerate(data):
            row["z"] = [3, 0, 4, 1, 2, 5, 1, 4][index]
        method["columns"]["z"] = {"type": "numeric"}
        method["terms"].append(["z"])

    add("two-covariates", second, "y ~ x + z")
    def interaction(data, method):
        second(data, method)
        method["terms"].append(["x", "z"])
    add("numeric-interaction", interaction, "y ~ x + z + x:z")

    def factor(data, method):
        for index, row in enumerate(data):
            row["group"] = "control" if index % 2 == 0 else "case"
        method["columns"]["group"] = {"type": "factor", "levels": ["control", "case"]}
        method["terms"].append(["group"])

    add("factor-reference", factor, "y ~ x + group")
    def reverse_reference(data, method):
        factor(data, method)
        method["columns"]["group"]["levels"].reverse()
    add("factor-reversed-reference", reverse_reference, "y ~ x + group")
    def factor_interaction(data, method):
        factor(data, method)
        method["terms"].append(["x", "group"])
    add("factor-interaction", factor_interaction, "y ~ x + group + x:group")

    def weighted(data, method):
        for index, row in enumerate(data):
            row["precision"] = [1, 3, 2, 1, 4, 2, 1, 3][index]
        method["columns"]["precision"] = {"type": "numeric"}
        method["weights"] = "precision"

    add("weighted", weighted)
    def zero_weight(data, method):
        weighted(data, method)
        data[1]["precision"] = 0
    add("zero-weight-row-retained", zero_weight)
    def offset(data, method):
        for index, row in enumerate(data):
            row["baseline"] = (index % 3) * .2
        method["columns"]["baseline"] = {"type": "numeric"}
        method["offset"] = "baseline"
    add("offset", offset)
    def weighted_offset(data, method):
        weighted(data, method)
        offset(data, method)
    add("weighted-offset", weighted_offset)
    add("constant-response", lambda data, method: [row.update(y=3) for row in data])
    def intercept_only(data, method):
        for row in data:
            del row["x"]
        del method["columns"]["x"]
        method["terms"] = []
    add("intercept-only", intercept_only, "y ~ 1")
    add("confidence-level-90", lambda data, method: method.update(conf_level=.9))

    add("wrong-hash", error="input SHA256 mismatch", mutation="hash")
    add("unknown-key", lambda data, method: method.update(unknown=True), error="lm contract fields differ")
    add("missing-key", lambda data, method: method.pop("weights"), error="lm contract fields differ")
    add("duplicate-json-key", error="lm contract fields differ", mutation="duplicate-json")
    add("missing-response", lambda data, method: data[0].update(y="NA"), error="finite numeric model values")
    add("nonfinite-predictor", lambda data, method: data[0].update(x="Inf"), error="finite numeric model values")
    add("numeric-whitespace", lambda data, method: data[0].update(x=" 2"), error="finite numeric model values")
    add("duplicate-row", lambda data, method: data[1].update(row_id=data[0]["row_id"]), error="unique nonempty row identities")
    add("ragged", error="unique header and rectangular TSV", mutation="ragged")
    add("wrong-header", error="input column order differs", mutation="header")
    add("embedded-NUL", error="embedded NUL forbidden", mutation="nul")
    add("untrusted-formula", lambda data, method: method.update(terms=[["system('false')"]]), error="term must contain column symbols")
    add("unknown-variable", lambda data, method: method.update(terms=[["missing"]]), error="invalid interaction variables")
    add("named-term-object", lambda data, method: method.update(terms=[{"hidden": "x"}]), error="term must contain column symbols")
    add("named-terms-object", lambda data, method: method.update(terms={"hidden": ["x"]}), error="explicit ordered term list")
    add("named-factor-levels", lambda data, method: (factor(data, method), method["columns"]["group"].update(levels={"hidden": "control", "other": "case"})), error="explicit factor levels required")
    add("unknown-factor", lambda data, method: (factor(data, method), data[0].update(group="other")), error="factor levels are unknown")
    add("absent-factor-reference", lambda data, method: (factor(data, method), method["columns"]["group"].update(levels=["absent", "control", "case"])), error="factor levels are unknown")
    add("unknown-factor-field", lambda data, method: (factor(data, method), method["columns"]["group"].update(ordered=True)), error="factor column fields differ")
    add("duplicate-terms", lambda data, method: method["terms"].append(["x"]), error="unique nonempty model")
    add("reversed-duplicate-interaction", lambda data, method: (interaction(data, method), method["terms"].append(["z", "x"])), error="unique nonempty model")
    add("rank-deficient", lambda data, method: (second(data, method), [row.update(z=row["x"] * 2) for row in data]), error="singular fit encountered")
    add("no-residual-df", lambda data, method: data.__delitem__(slice(2, None)), error="positive residual df")
    add("negative-weight", lambda data, method: (weighted(data, method), data[0].update(precision=-1)), error="nonnegative weights")
    add("all-zero-weights", lambda data, method: (weighted(data, method), [row.update(precision=0) for row in data]), error="nonnegative weights")
    add("invalid-intercept", lambda data, method: method.update(intercept="false"), error="explicit intercept boolean")
    add("invalid-QR-tolerance", lambda data, method: method.update(qr_tolerance=0), error="QR tolerance outside")
    add("invalid-CI", lambda data, method: method.update(conf_level=1), error="confidence level outside")
    add("unused-column", lambda data, method: (second(data, method), method.update(terms=[["x"]])), error="unused columns forbidden")
    return cases


R_PROOF = r'''
args <- commandArgs(TRUE)
root <- args[[1]]
script <- args[[2]]
cases <- jsonlite::fromJSON(file.path(root, "cases.json"), simplifyVector=FALSE)
compare <- function(actual, expected) {
  stopifnot(identical(dim(actual), dim(expected)), identical(names(actual), names(expected)),
    identical(is.na(actual), is.na(expected)), identical(is.nan(actual), is.nan(expected)),
    identical(is.infinite(actual), is.infinite(expected)))
  if (is.numeric(actual)) {
    finite <- is.finite(expected)
    stopifnot(all(abs(actual[finite]-expected[finite]) <= 1e-10+1e-8*abs(expected[finite])))
    stopifnot(identical(actual[is.infinite(expected)], expected[is.infinite(expected)]))
  } else stopifnot(identical(actual,expected))
}
answers <- list()
for (case in cases) {
  directory <- file.path(root, case$name)
  outputs <- file.path(directory,c("coefficients.tsv","observations.tsv","model.RDS","model.log","audit.json"))
  env <- c(AUTONOMICS_INPUT0=file.path(directory,"input.tsv"), AUTONOMICS_INPUT1=file.path(directory,"contract.json"))
  names(outputs) <- paste0("AUTONOMICS_OUTPUT",0:4)
  do.call(Sys.setenv,as.list(c(env,outputs)))
  result <- suppressWarnings(system2("Rscript",c("--vanilla",shQuote(script)),
    stdout=file.path(directory,"node.stdout"),stderr=file.path(directory,"node.stderr")))
  if (!is.null(case$expected_error)) {
    stopifnot(result==2L,!any(file.exists(outputs)),
      any(grepl(case$expected_error,readLines(file.path(directory,"node.stderr")),fixed=TRUE)),
      !any(startsWith(list.files(directory,all.files=TRUE),".r-stats-lm-")))
    answers[[case$name]] <- list(expected_refusal=TRUE,exit=result)
    next
  }
  stopifnot(result==0L,all(file.exists(outputs)),all(file.info(outputs)$size>0))
  observed <- readRDS(outputs[[3]])
  data <- read.delim(file.path(directory,"input.tsv"),colClasses="character",check.names=FALSE,na.strings=NULL)
  contract <- case$contract
  for (name in names(contract$columns)) {
    definition <- contract$columns[[name]]
    data[[name]] <- if (definition$type=="numeric") as.numeric(data[[name]]) else factor(data[[name]],levels=unlist(definition$levels))
  }
  reference_arguments <- list(formula=stats::as.formula(case$oracle_formula),data=data,
    method="qr",na.action=stats::na.fail,singular.ok=FALSE,x=TRUE,y=TRUE,model=TRUE,tol=1e-7)
  if (!is.null(contract$weights)) reference_arguments$weights <- data[[contract$weights]]
  if (!is.null(contract$offset)) reference_arguments$offset <- data[[contract$offset]]
  references <- list()
  for (name in names(contract$columns)) if(contract$columns[[name]]$type=="factor") {
    references[[name]] <- stats::contr.treatment(unlist(contract$columns[[name]]$levels),base=1L)
  }
  if(length(references)) reference_arguments$contrasts <- references
  reference <- do.call(stats::lm,reference_arguments)
  summary_reference <- suppressWarnings(summary(reference))
  compare(stats::coef(observed$fit),stats::coef(reference))
  compare(observed$summary$coefficients,summary_reference$coefficients)
  compare(observed$fit$x,reference$x)
  compare(observed$covariance,stats::vcov(reference))
  compare(stats::fitted(observed$fit),stats::fitted(reference))
  compare(stats::residuals(observed$fit),stats::residuals(reference))
  compare(observed$summary$r.squared,summary_reference$r.squared)
  actual <- read.delim(outputs[[1]],check.names=FALSE)
  expected <- summary_reference$coefficients
  interval <- stats::confint(reference,level=contract$conf_level)
  stopifnot(identical(actual$term,rownames(expected)))
  for (index in seq_len(4L)) compare(actual[[index+1L]],unname(expected[,index]))
  compare(actual$conf_low,unname(interval[,1L]))
  compare(actual$conf_high,unname(interval[,2L]))
  for (column in names(actual)[2:7]) {
    expected_kind <- vapply(actual[[column]],function(value) {
      if(is.nan(value)) "NAN" else if(is.na(value)) "MISSING" else if(is.infinite(value)) {
        if(value<0) "NEG_INF" else "POS_INF"
      } else "FINITE"
    },character(1))
    stopifnot(identical(actual[[paste0(column,"_kind")]],expected_kind))
  }
  observations <- read.delim(outputs[[2]],colClasses=c("character","numeric","numeric","numeric"),na.strings=NULL)
  stopifnot(identical(observations$row_id,data$row_id))
  compare(observations$fitted,unname(stats::fitted(reference)))
  compare(observations$residual,unname(stats::residuals(reference)))
  audit <- jsonlite::fromJSON(outputs[[5]])
  stopifnot(identical(audit$input_sha256,digest::digest(file=env[[1]],algo="sha256",serialize=FALSE)),
    identical(audit$contract_sha256,digest::digest(file=env[[2]],algo="sha256",serialize=FALSE)),
    audit$input_rows==nrow(data),audit$nobs==stats::nobs(reference),audit$residual_df==reference$df.residual,
    identical(audit$formal_authorized,FALSE),identical(audit$g0_granted,FALSE))
  for(index in 1:4) stopifnot(identical(audit$outputs$sha256[index],digest::digest(file=outputs[[index]],algo="sha256",serialize=FALSE)))
  saveRDS(list(fit=reference,summary=summary_reference,arguments=reference_arguments),file.path(directory,"independent-reference.RDS"),version=3)
  jsonlite::write_json(reference_arguments$formula |> deparse(),file.path(directory,"independent-formula.json"),pretty=TRUE)
  old_hashes <- vapply(outputs,function(path) digest::digest(file=path,algo="sha256",serialize=FALSE),character(1))
  rerun <- suppressWarnings(system2("Rscript",c("--vanilla",shQuote(script)),
    stdout=file.path(directory,"rerun.stdout"),stderr=file.path(directory,"rerun.stderr")))
  stopifnot(rerun==2L,identical(old_hashes,vapply(outputs,function(path) digest::digest(file=path,algo="sha256",serialize=FALSE),character(1))))
  answers[[case$name]] <- list(expected_refusal=FALSE,exit=result,coefficient_rows=nrow(actual),
    nobs=stats::nobs(reference),all_input_rows_retained=TRUE,no_clobber_rerun_verified=TRUE)
}
jsonlite::write_json(list(schema="OFFICIAL_R_LM_METHOD_PROOF_V1",cases=answers,
  R_version=as.character(getRversion()),stats_version=as.character(packageVersion("stats")),
  absolute_tolerance=1e-10,relative_tolerance=1e-8,independent_reference_script=TRUE,
  native_DAG_verified=FALSE,production_deployed=FALSE,g0_granted=FALSE),
  file.path(root,"verification.json"),auto_unbox=TRUE,pretty=TRUE)
writeLines(c(capture.output(sessionInfo()),capture.output(print(formals(stats::lm))),
  capture.output(print(body(stats::lm)))),file.path(root,"official-runtime.txt"))
'''


R_DAG_READBACK = r'''
root <- commandArgs(TRUE)[[1]]
records <- jsonlite::fromJSON(file.path(root,"dag-evidence.json"),simplifyVector=FALSE)$cases
compare <- function(actual,expected) {
  stopifnot(identical(is.na(actual),is.na(expected)),identical(is.nan(actual),is.nan(expected)),
    identical(is.infinite(actual),is.infinite(expected)))
  finite <- is.finite(expected)
  stopifnot(all(abs(actual[finite]-expected[finite]) <= 1e-10+1e-8*abs(expected[finite])))
  stopifnot(identical(actual[is.infinite(expected)],expected[is.infinite(expected)]))
}
checked <- list()
for(record in records) {
  if(record$expected_refusal) next
  source <- file.path(root,record$name)
  official <- readRDS(file.path(source,"independent-reference.RDS"))
  model <- readRDS(file.path(root,record$output_paths[[3]]))
  stopifnot(identical(names(coef(model$fit)),names(coef(official$fit))),
    identical(model$row_id,official$arguments$data$row_id),model$fit$rank==official$fit$rank,
    model$fit$df.residual==official$fit$df.residual)
  compare(coef(model$fit),coef(official$fit))
  compare(model$summary$coefficients,official$summary$coefficients)
  compare(model$covariance,vcov(official$fit))
  actual <- read.delim(file.path(root,record$materialized_path),check.names=FALSE)
  direct <- read.delim(file.path(source,"coefficients.tsv"),check.names=FALSE)
  stopifnot(identical(names(actual),names(direct)),identical(actual$term,direct$term))
  for(column in names(actual)[2:7]) compare(actual[[column]],direct[[column]])
  for(column in names(actual)[8:13]) stopifnot(identical(actual[[column]],direct[[column]]))
  observations <- read.delim(file.path(root,record$output_paths[[2]]),colClasses=c("character","numeric","numeric","numeric"),na.strings=NULL)
  stopifnot(identical(observations$row_id,official$arguments$data$row_id))
  compare(observations$fitted,unname(fitted(official$fit)))
  compare(observations$residual,unname(residuals(official$fit)))
  checked[[record$name]] <- list(coefficient_rows=nrow(actual),materialized_re_read=TRUE,complete_rds_compared=TRUE)
}
jsonlite::write_json(list(cases=checked,R_version=as.character(getRversion()),
  current_daemon_verified=FALSE,scientific_authorized=FALSE,g0_granted=FALSE),
  file.path(root,"dag-readback.json"),auto_unbox=TRUE,pretty=TRUE)
'''


def run_dags(directory, source, cases, runner, build_path):
    build = json.loads(build_path.read_text())
    if digest(runner) != build["executable_sha256"]:
        raise RuntimeError("Runner differs from its preserved build identity")
    shutil.copyfile(build_path, directory / "historical-runner-build.json")
    (directory / "historical-runner-reference.json").write_text(json.dumps(dict(
        executable=str(runner), executable_sha256=digest(runner),
        scope="EXISTING_HASH_BOUND_HARNESS_NOT_CURRENT_DAEMON_NOT_CURRENT_MAIN"), indent=2) + "\n")
    isolated_data = directory / "isolated-inputs/data_sets"
    isolated_data.mkdir(parents=True)
    panels = directory / "unused-panels"
    panels.mkdir()
    node = tomllib.loads((source / "manifest.toml").read_text())["nodes"][0]
    records = []
    dag_root = directory / "dags"
    dag_root.mkdir()
    for case in cases:
        work = dag_root / case["name"]
        work.mkdir()
        shutil.copyfile(directory / case["name"] / "input.tsv", work / "input.tsv")
        shutil.copyfile(directory / case["name"] / "contract.json", work / "contract.json")
        nodes = [dict(id="observations", kind="file_reference", spec=dict(path="vfs:///input.tsv", format="tsv")),
                 dict(id="contract", kind="file_reference", spec=dict(path="vfs:///contract.json", format="json")),
                 dict(id="analysis", kind=node["kind"], plugin_manifest=str(source / "manifest.toml"), spec={}),
                 dict(id="read", kind="file_to_dataframe", spec=dict(format="tsv")),
                 dict(id="write", kind="dataframe_to_file", spec=dict(path="vfs:///materialized.tsv", format="tsv"))]
        edges = [dict(from_port=first_port, to_port=second_port, **{"from": first, "to": second})
                 for first, second, first_port, second_port in
                 [("observations", "analysis", 0, 0), ("contract", "analysis", 0, 1), ("analysis", "read", 0, 0), ("read", "write", 0, 0)]]
        job = dict(run_root=str(work), data_root=str(isolated_data.parent), panel_root=str(panels),
                   report_file="dag-report.json", max_concurrency=1, nodes=nodes, edges=edges)
        (work / "job.json").write_text(json.dumps(job, indent=2) + "\n")
        response = subprocess.run([str(runner), str(work / "job.json")], capture_output=True, timeout=180)
        (work / "stdout.txt").write_bytes(response.stdout)
        (work / "stderr.txt").write_bytes(response.stderr)
        (work / "execution.json").write_text(json.dumps(dict(exit_code=response.returncode)) + "\n")
        report = json.loads((work / "dag-report.json").read_text())
        first = report["first_run"]
        negative = case["expected_error"] is not None
        record = dict(name=case["name"], expected_refusal=negative, nodes=5, edges=4,
                      engine_source_revision=report["engine_source_revision"], output_paths=[])
        analysis = next(entry for entry in first["nodes"] if entry["id"] == "analysis")
        if negative:
            serialized = json.dumps(first)
            if not first["errors"] or (work / "materialized.tsv").exists() or case["expected_error"] not in serialized:
                raise RuntimeError("Expected DAG refusal/diagnostic did not propagate: " + case["name"])
            if any(path.name in {entry["path"] for entry in node["ports"]["outputs"]} for path in (work / "artifacts").rglob("*") if path.is_file()):
                raise RuntimeError("Rejected DAG published statistical output")
        else:
            if response.returncode or first["errors"] or analysis["status"] != "success":
                raise RuntimeError("Positive official-package DAG failed: " + case["name"])
            assignments = analysis["port_assignments"]
            if set(assignments) != {str(index) for index in range(5)}:
                raise RuntimeError("DAG declaration/port mismatch")
            for index, definition in enumerate(node["ports"]["outputs"]):
                entry = assignments[str(index)]
                if not entry["path"].startswith("vfs:///"):
                    raise RuntimeError("Unexpected VFS output")
                path = work / entry["path"].removeprefix("vfs:///")
                if not path.resolve().is_relative_to(work) or path.name != definition["path"] or entry["format"] != definition["format"]:
                    raise RuntimeError("Port identity/format differs")
                if digest(path) != entry["fingerprint"]["content_hash"].removeprefix("sha256:"):
                    raise RuntimeError("Published port content hash differs")
                record["output_paths"].append(str(path.relative_to(directory)))
            record["materialized_path"] = str((work / "materialized.tsv").relative_to(directory))
        records.append(record)
        (directory / "dag-evidence.json").write_text(json.dumps(dict(
            schema="OFFICIAL_R_LM_ISOLATED_DAG_V1", cases=records,
            scope="HISTORICAL_HASH_BOUND_HARNESS_NOT_CURRENT_DAEMON", g0_granted=False), indent=2) + "\n")
    (directory / "dag-readback.R").write_text(R_DAG_READBACK)
    result = subprocess.run(["Rscript", "--vanilla", str(directory / "dag-readback.R"), str(directory)], capture_output=True, timeout=120)
    (directory / "dag-readback.stdout").write_bytes(result.stdout)
    (directory / "dag-readback.stderr").write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError("Official DAG readback failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", type=Path)
    parser.add_argument("--runner-build", type=Path)
    arguments = parser.parse_args()
    if bool(arguments.runner) != bool(arguments.runner_build):
        parser.error("runner and runner-build must be provided together")
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Use the engine's managed research_validation_session.py run entry")
    directory = Path(permanent) / "official-r-lm"
    directory.mkdir(mode=0o700)
    source = directory / "source"
    source.mkdir()
    for path in FAMILY.rglob("*"):
        if path.is_file():
            target = source / path.relative_to(FAMILY)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    shutil.copyfile(Path(__file__), source / "prove_r_lm.py")
    manifest = tomllib.loads((source / "manifest.toml").read_text())
    image = manifest["image"]["reference"]
    (directory / "source-identity.json").write_text(json.dumps({
        "files": {str(path.relative_to(source)): digest(path) for path in source.rglob("*") if path.is_file()},
        "image": image, "scientific_authorized": False}, indent=2) + "\n")
    cases = fixtures()
    for case in cases:
        work = directory / case["name"]
        work.mkdir()
        with (work / "input.tsv").open("w") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(case["rows"][0]), delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE)
            writer.writeheader()
            writer.writerows(case["rows"])
        path = work / "input.tsv"
        mutation = case["input_mutation"]
        if mutation == "ragged":
            path.write_text(path.read_text() + "extra\trow\n")
        elif mutation == "header":
            path.write_text(path.read_text().replace("row_id\ty\tx", "row_id\tx\ty", 1))
        elif mutation == "nul":
            path.write_bytes(path.read_bytes() + b"\x00")
        case["contract"]["input_sha256"] = "0" * 64 if mutation == "hash" else digest(path)
        content = json.dumps(case["contract"], indent=2)
        if mutation == "duplicate-json":
            content = content.replace('"scope":', '"schema_version": 1, "scope":', 1)
        (work / "contract.json").write_text(content + "\n")
    (directory / "cases.json").write_text(json.dumps(cases, indent=2) + "\n")
    (directory / "predeclared-comparison.json").write_text(json.dumps(dict(
        absolute_tolerance=1e-10, relative_tolerance=1e-8, exact_identity_and_nonfinite_kinds=True,
        required_cases=[case["name"] for case in cases], method_scope="TECHNICAL_ONLY_NOT_G0"), indent=2) + "\n")
    (directory / "reference-and-readback.R").write_text(R_PROOF)
    inspected = subprocess.run(["podman", "image", "inspect", image], capture_output=True, timeout=60)
    (directory / "image-inspect.json").write_bytes(inspected.stdout)
    (directory / "image-inspect.stderr").write_bytes(inspected.stderr)
    if inspected.returncode:
        raise RuntimeError("Pinned image not available; no rebuild or alternative estimator")
    command = ["podman", "run", "--rm", "--pull=never", "--network=none", "--read-only",
               "--userns=keep-id", f"--user={os.getuid()}:{os.getgid()}", "--cpus=1", "--memory=2g",
               "--tmpfs=/tmp:rw,size=64m", "-v", f"{directory}:/work:rw",
               "-e", "OPENBLAS_NUM_THREADS=1", "-e", "OMP_NUM_THREADS=1",
               "--entrypoint=Rscript", image, "--vanilla", "/work/reference-and-readback.R", "/work", "/work/source/scripts/lm.R"]
    (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    completed = subprocess.run(command, capture_output=True, timeout=600)
    (directory / "stdout.txt").write_bytes(completed.stdout)
    (directory / "stderr.txt").write_bytes(completed.stderr)
    (directory / "execution.json").write_text(json.dumps(dict(exit_code=completed.returncode, scientific_authorized=False)) + "\n")
    if completed.returncode:
        raise RuntimeError("Official lm proof failed; preserve diagnostics, do not certify")
    report = json.loads((directory / "verification.json").read_text())
    if set(report["cases"]) != {case["name"] for case in cases}:
        raise RuntimeError("Missing required cases")
    if arguments.runner:
        run_dags(directory, source, cases, arguments.runner, arguments.runner_build)
    before = json.loads((directory / "source-identity.json").read_text())["files"]
    if before != {str(path.relative_to(source)): digest(path) for path in source.rglob("*") if path.is_file()}:
        raise RuntimeError("Proof source changed during execution")
    print(json.dumps(dict(cases=len(cases), positive=sum(case["expected_error"] is None for case in cases),
                         native_DAG_verified=arguments.runner is not None,
                         current_daemon_verified=False, production_deployed=False, g0_granted=False)))


if __name__ == "__main__":
    main()
