"""Requalify the unchanged official methods and repaired output ownership boundary."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
SEAL = "bc5e5f3a7755d808ce200fb6d801005a3d30bf0ac625a1ade9dacbe9953230cb"
OLD_SCRIPT = "c1d37ca8a73e46ac6c7b509abea5bae10f4d978fe75b91932aaa377825c78d5c"
R_COMMIT = "1d95a4c60b0be6766490b1a621610b98a4bf5765"


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024**2), b""):
            result.update(block)
    return result.hexdigest()


def content_identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink, value.st_uid,
            value.st_gid, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def sealed_files(root):
    if digest(root / "proof-seal.json") != SEAL:
        raise RuntimeError("Exact historical reference seal required")
    records = json.loads((root / "proof-seal.json").read_bytes())["artifacts"]
    names = [record["path"] for record in records]
    if len(names) != len(set(names)):
        raise RuntimeError("Duplicate historical seal entries")
    for record in records:
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("Historical reference path escapes scope")
        path = root / relative
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise RuntimeError("Historical source identity contains redirected paths")
        before = path.stat()
        if (before.st_size != record["size_bytes"] or digest(path) != record["sha256"]
                or content_identity(path.stat()) != content_identity(before)):
            raise RuntimeError("Historical sealed artifact differs: " + record["path"])
    return records


R_DRIVER = r'''
root <- "/work"
stopifnot(as.character(getRversion()) == "4.5.1", as.character(packageVersion("stats")) == "4.5.1")
source_environment <- new.env(parent=emptyenv())
for (filename in list.files(file.path(root,"official-source"), pattern="\\.R$", full.names=TRUE)) {
  for (expression in parse(filename)) {
    if (is.call(expression) && identical(expression[[1]],as.name("<-")) && is.symbol(expression[[2]]) &&
        is.call(expression[[3]]) && identical(expression[[3]][[1]],as.name("function"))) {
      source_environment[[as.character(expression[[2]])]] <- expression[[3]]
    }
  }
}
selected <- c("t.test.default","cor.test.default","var.test.default","wilcox.test.default","prop.test","p.adjust")
for (name in selected) {
  official <- eval(source_environment[[name]],baseenv())
  installed <- get(name,asNamespace("stats"))
  stopifnot(identical(deparse(body(official)),deparse(body(installed))),
            identical(deparse(formals(official)),deparse(formals(installed))))
}
sha <- function(path) substr(system2("sha256sum", shQuote(path),stdout=TRUE)[[1]],1,64)
run <- function(directory, script, operation, label) {
  Sys.setenv(STATISTICS_OPERATION=operation,
    AUTONOMICS_INPUT0=file.path(directory,"input0.tsv"),
    AUTONOMICS_INPUT1=file.path(directory,"input1.tsv"))
  outputs <- file.path(directory,"outputs",c("statistics.tsv","parameters.tsv","statistics.RDS","statistics.log","audit.tsv"))
  environment <- as.list(setNames(outputs,paste0("AUTONOMICS_OUTPUT",0:4)))
  do.call(Sys.setenv,environment)
  status <- suppressWarnings(system2("Rscript",c("--vanilla",shQuote(script)),
    stdout=file.path(directory,paste0(label,".stdout")),stderr=file.path(directory,paste0(label,".stderr"))))
  list(status=status,outputs=outputs)
}
cases <- read.delim(file.path(root,"cases.tsv"),colClasses="character",check.names=FALSE,na.strings=NULL)
answers <- list()
for (index in seq_len(nrow(cases))) {
  record <- cases[index,]
  directory <- file.path(root,"cases",record$id)
  observed <- run(directory,file.path(root,"statistics.R"),record$operation,"first")
  if (record$negative == "true") {
    stopifnot(observed$status != 0L, !any(file.exists(observed$outputs[1:3])),
              file.exists(observed$outputs[4]),file.info(observed$outputs[4])$size>0,
              file.exists(observed$outputs[5]))
    audit <- read.delim(observed$outputs[5],colClasses="character",na.strings=NULL)
    stopifnot(audit$value[audit$key=="status"] == "BLOCKED")
    answers[[index]] <- data.frame(id=record$id,operation=record$operation,negative=TRUE,
      first_exit=observed$status,complete_object_compared=FALSE,no_clobber_repeat=FALSE)
    next
  }
  stopifnot(observed$status==0L,all(file.exists(observed$outputs)))
  fixture <- dget(file.path(directory,"reference-fixture.R"))
  warnings <- character()
  expected <- withCallingHandlers(do.call(get(fixture$function_name,asNamespace("stats")),fixture$args),
    warning=function(condition) {
      warnings <<- c(warnings,conditionMessage(condition))
      invokeRestart("muffleWarning")
    })
  actual <- readRDS(observed$outputs[3])
  stopifnot(isTRUE(all.equal(actual$fit,expected,tolerance=1e-12,check.attributes=TRUE)),
    isTRUE(all.equal(actual$arguments[sort(names(actual$arguments))],fixture$args[sort(names(fixture$args))],tolerance=1e-12)),
    identical(actual$row_id,fixture$row_ids),identical(actual$warnings,warnings))
  saveRDS(list(fit=expected,arguments=fixture$args,warnings=warnings),file.path(directory,"independent-reference.RDS"),version=3)
  before <- vapply(observed$outputs,sha,character(1))
  repeated <- run(directory,file.path(root,"statistics.R"),record$operation,"repeat")
  stopifnot(repeated$status!=0L,identical(before,vapply(observed$outputs,sha,character(1))))
  answers[[index]] <- data.frame(id=record$id,operation=record$operation,negative=FALSE,
    first_exit=observed$status,complete_object_compared=TRUE,no_clobber_repeat=TRUE)
}
write.table(do.call(rbind,answers),file.path(root,"method-checks.tsv"),sep="\t",row.names=FALSE,quote=FALSE)
fixture <- file.path(root,"cases","adjust-BH")
guard_results <- list()
for (index in 0:4) {
  directory <- file.path(root,"guards",paste0("port-",index))
  dir.create(file.path(directory,"outputs"),recursive=TRUE)
  file.copy(file.path(fixture,c("input0.tsv","input1.tsv")),directory)
  target <- file.path(directory,"outputs",c("statistics.tsv","parameters.tsv","statistics.RDS","statistics.log","audit.tsv"))[index+1]
  writeLines("permanent sentinel: do not overwrite",target)
  before <- sha(target)
  result <- run(directory,file.path(root,"statistics.R"),"adjust","guard")
  stopifnot(result$status!=0L,identical(before,sha(target)),sum(file.exists(result$outputs))==1L)
  guard_results[[index+1]] <- data.frame(port=index,exit=result$status,sentinel_unchanged=TRUE)
}
directory <- file.path(root,"guards","old-script-counterexample")
dir.create(file.path(directory,"outputs"),recursive=TRUE)
file.copy(file.path(fixture,c("input0.tsv","input1.tsv")),directory)
target <- file.path(directory,"outputs/statistics.tsv")
writeLines("permanent sentinel: do not overwrite",target)
before <- sha(target)
old <- run(directory,file.path(root,"old-statistics.R"),"adjust","old")
stopifnot(old$status==0L,!identical(before,sha(target)))
write.table(do.call(rbind,guard_results),file.path(root,"guard-checks.tsv"),sep="\t",row.names=FALSE,quote=FALSE)
writeLines(c("original_overwrite_counterexample_reproduced=true","selected_official_functions=6",
 "new_method_calls_are_not_current_engine_DAGs","formal_authorized=false","g0_granted=false"),file.path(root,"runtime-scope.txt"))
writeLines(capture.output(sessionInfo()),file.path(root,"official-runtime.txt"))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    arguments = parser.parse_args()
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Use the managed validation session")
    output = Path(permanent) / "official-r-stats-publication"
    output.mkdir(mode=0o700)
    (output / "driver.py").write_bytes(Path(__file__).read_bytes())
    records = sealed_files(arguments.reference)
    old_root = arguments.reference / "official-R-stats-v2"
    old_script = old_root / "source/cachexia-r-stats/scripts/statistics.R"
    if digest(old_script) != OLD_SCRIPT:
        raise RuntimeError("Original method entry identity differs")
    current = ROOT / "research-adapters/cachexia-r-stats"
    shutil.copyfile(old_script, output / "old-statistics.R")
    shutil.copyfile(current / "scripts/statistics.R", output / "statistics.R")
    manifest = tomllib.loads((current / "manifest.toml").read_text())
    summary = json.loads((old_root / "summary.json").read_bytes())
    cases = summary["checks"]
    if len(cases) != 164 or len({(record["operation"], record["name"]) for record in cases}) != 164:
        raise RuntimeError("Complete historical method case inventory differs")
    official = arguments.reference / "official-source"
    locks = json.loads((official / "source-lock.json").read_bytes())
    source = output / "official-source"
    source.mkdir()
    for record in locks:
        if record["commit"] != R_COMMIT or digest(official / record["file"]) != record["sha256"]:
            raise RuntimeError("Author release source identity differs")
        shutil.copyfile(official / record["file"], source / record["file"])
    with (output / "cases.tsv").open("x") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "operation", "negative"], delimiter="\t")
        writer.writeheader()
        for record in cases:
            identifier = record["operation"] + "-" + record["name"]
            directory = output / "cases" / identifier
            directory.mkdir(parents=True)
            for name in ["input0.tsv", "input1.tsv"] + ([] if record["negative"] else ["reference-fixture.R"]):
                shutil.copyfile(old_root / identifier / name, directory / name)
            writer.writerow(dict(id=identifier, operation=record["operation"], negative=str(record["negative"]).lower()))
    (output / "reference-and-guards.R").write_text(R_DRIVER)
    image = manifest["image"]["reference"]
    if image != "ghcr.io/auto-nomics/autonomics/coloc@sha256:a2afe7aa83ae6f1ecb9573317aa022af4db0870771378c7fe90d295d70057322":
        raise RuntimeError("Original author-package image identity differs")
    command = ["podman", "run", "--rm", "--pull=never", "--network=none", "--read-only",
               "--userns=keep-id", f"--user={os.getuid()}:{os.getgid()}", "--cpus=1", "--memory=1g",
               "--tmpfs=/tmp:rw,size=64m", "-e", "OPENBLAS_NUM_THREADS=1", "-e", "OMP_NUM_THREADS=1",
               "-v", f"{output}:/work:rw", "--entrypoint=Rscript", image, "--vanilla", "/work/reference-and-guards.R"]
    with (output / "container.stdout").open("wb") as stdout, (output / "container.stderr").open("wb") as stderr:
        completed = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=1200)
    if completed.returncode:
        raise RuntimeError("Official method/publication requalification failed; preserve this run")
    with (output / "method-checks.tsv").open() as handle:
        observed = list(csv.DictReader(handle, delimiter="\t"))
    if len(observed) != 164 or {record["id"] for record in observed} != {record["operation"]+"-"+record["name"] for record in cases}:
        raise RuntimeError("Actual method execution coverage differs")
    positive = sum(record["negative"] == "FALSE" for record in observed)
    negative = sum(record["negative"] == "TRUE" for record in observed)
    if (positive, negative) != (122, 42):
        raise RuntimeError("Actual method positive/refusal inventory differs")
    report = dict(status="OFFICIAL_METHOD_AND_NO_CLOBBER_BOUNDARY_REQUALIFIED_NOT_CURRENT_DAG",
                  image=image, reference_seal_sha256=SEAL, old_reference_files_rehashed=len(records),
                  old_reference_bytes_rehashed=sum(record["size_bytes"] for record in records),
                  old_script_sha256=OLD_SCRIPT, current_script_sha256=digest(current / "scripts/statistics.R"),
                  staged_script_sha256=digest(output / "statistics.R"), positive_cases=positive, refusal_cases=negative,
                  positive_full_object_rereads=positive, no_clobber_positive_repeats=positive,
                  single_port_sentinel_guards=5, original_overwrite_counterexample_reproduced=True,
                  reference_scope="UNCHANGED_VECTOR_METHODS_AND_EXPLICIT_PARAMETERS",
                  historical_DAG_evidence_retained_not_relabelled=True, current_engine_DAG_verified=False,
                  daemon_deployed=False, official_function_bodies_reverified=6, new_function_slots=0,
                  frozen_study_changed=False, formal_authorized=False, g0_granted=False)
    if report["current_script_sha256"] != report["staged_script_sha256"]:
        raise RuntimeError("Current method entry changed during proof")
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
