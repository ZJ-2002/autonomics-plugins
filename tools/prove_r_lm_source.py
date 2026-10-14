"""Match the installed lm R functions against the primary R 4.6.1 release tag."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RELEASE_URL = "https://svn.r-project.org/R/tags/R-4-6-1/"
SOURCE_FILES = ["VERSION", "src/library/stats/R/lm.R", "src/library/stats/R/confint.R", "src/library/stats/R/vcov.R"]
FUNCTIONS = ["lm", "lm.fit", "lm.wfit", "summary.lm", "confint.lm", "vcov.lm", "vcov.summary.lm", ".vcov.aliased"]
SOURCE_SHA256 = {
    "VERSION": "16550af6f97b1dd87e9eae5809ab0345f4edd82cf28cc8fb08e8091d397455f3",
    "src/library/stats/R/lm.R": "e3eec3d9271025b40dde96858dbbf6d2e86c73cc1e441943e1f2c9669ea287f6",
    "src/library/stats/R/confint.R": "c1ed4e04b0c170b2a4398f6eca0595cca3828550b9b2e12466baf43e9d6fdbd4",
    "src/library/stats/R/vcov.R": "f423a5a899b293f6e7bbd31de8c1cd41ad6945845016d185c4073db6a67c0350",
}


def archived_sources(directory):
    lock = json.loads((directory / "source-lock.json").read_text())
    if lock.get("release_url") != RELEASE_URL or {row["path"] for row in lock["files"]} != set(SOURCE_FILES) or len(lock["files"]) != len(SOURCE_FILES):
        raise RuntimeError("Incomplete official-source reference lock")
    for row in lock["files"]:
        path = directory / row["path"]
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 512 * 1024:
            raise RuntimeError("Invalid archived source file")
        body = path.read_bytes()
        if (row["url"] != RELEASE_URL + row["path"] or row["received_url"] != row["url"] or row["status"] != 200
                or row["bytes"] != len(body) or row["sha256"] != SOURCE_SHA256[row["path"]]
                or hashlib.sha256(body).hexdigest() != row["sha256"]):
            raise RuntimeError("Archived author-source identity changed")
    return lock

R_COMPARE = r'''
root <- commandArgs(TRUE)[[1]]
parent <- Sys.getenv("EXPECTED_VALIDATION_CGROUP_PARENT")
actual <- readLines("/proc/self/cgroup",warn=FALSE)
stopifnot(length(parent)==1L,nzchar(parent),length(actual)==1L,startsWith(actual,"0::"),
  startsWith(substring(actual,4L),paste0(parent,"/")))
parent_memory <- readLines(file.path("/sys/fs/cgroup",parent,"memory.max"),warn=FALSE)
container_memory <- readLines(file.path("/sys/fs/cgroup",substring(actual,4L),"memory.max"),warn=FALSE)
stopifnot(identical(parent_memory,"2147483648"),identical(container_memory,"1073741824"))
stopifnot(as.character(getRversion())=="4.6.1",as.character(packageVersion("stats"))=="4.6.1")
lock <- jsonlite::fromJSON(file.path(root,"source-lock.json"),simplifyVector=FALSE)
for(record in lock$files) stopifnot(identical(record$sha256,digest::digest(file=file.path(root,record$path),algo="sha256",serialize=FALSE)))
stopifnot(trimws(readLines(file.path(root,"VERSION"),warn=FALSE)[[1]])=="4.6.1")
reference <- new.env(parent=asNamespace("stats"))
for(path in c("lm.R","confint.R","vcov.R")) sys.source(file.path(root,"src/library/stats/R",path),envir=reference,keep.source=FALSE)
required <- c("lm","lm.fit","lm.wfit","summary.lm","confint.lm","vcov.lm","vcov.summary.lm",".vcov.aliased")
answers <- list()
for(name in required) {
  official <- get(name,envir=reference,inherits=FALSE)
  installed <- get(name,envir=asNamespace("stats"),inherits=FALSE)
  same_formals <- identical(formals(official),formals(installed))
  same_body <- identical(body(official),body(installed))
  answers[[name]] <- list(formals_equal=same_formals,body_equal=same_body,
    installed_body_sha256=digest::digest(serialize(body(installed),NULL,version=3),algo="sha256",serialize=FALSE),
    official_body_sha256=digest::digest(serialize(body(official),NULL,version=3),algo="sha256",serialize=FALSE))
}
compiled <- list()
for(path in c(file.path(R.home("bin"),"exec/R"),list.files(system.file("libs",package="stats"),full.names=TRUE))) {
  if(file.exists(path) && !dir.exists(path)) compiled[[path]] <- digest::digest(file=path,algo="sha256",serialize=FALSE)
}
verified <- all(vapply(answers,function(answer) answer$formals_equal && answer$body_equal,logical(1)))
jsonlite::write_json(list(schema="OFFICIAL_R_RELEASE_FUNCTION_IDENTITY_V1",R_version=as.character(getRversion()),
  stats_version=as.character(packageVersion("stats")),release_url=lock$release_url,functions=answers,
  all_eight_function_formals_and_bodies_equal=verified,compiled_installed_files=compiled,
  recorded_service_parent=parent,container_cgroup=actual,
  recorded_service_memory_max=parent_memory,container_memory_max=container_memory,
  recorded_service_descendant_and_caps_verified=TRUE,
  compiled_binary_rebuild_or_signed_provenance_verified=FALSE,scientific_authorized=FALSE,g0_granted=FALSE),
  file.path(root,"identity.json"),auto_unbox=TRUE,pretty=TRUE)
writeLines(c(capture.output(print(R.version)),capture.output(sessionInfo())),file.path(root,"runtime.txt"))
stopifnot(verified)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-archive", type=Path)
    arguments = parser.parse_args()
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Use research_validation_session.py run for acceptance downloads")
    directory = Path(permanent) / "official-r-lm-source"
    directory.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__), directory / "driver.py")
    (directory / "comparison.R").write_text(R_COMPARE)
    if arguments.reference_archive:
        lock = archived_sources(arguments.reference_archive)
        for entry in lock["files"]:
            path = directory / entry["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(arguments.reference_archive / entry["path"], path)
        (directory / "source-lock.json").write_text(json.dumps(lock, indent=2) + "\n")
        (directory / "reference-reuse.json").write_text(json.dumps(dict(
            scope="REUSE_EXACT_PRIMARY_AUTHOR_SOURCE_BYTES_NOT_RETRYING_A_SCIENTIFIC_RESULT",
            reference=str(arguments.reference_archive), g0_granted=False), indent=2) + "\n")
    entries = []
    for relative in ([] if arguments.reference_archive else SOURCE_FILES):
        url = RELEASE_URL + relative
        request = Request(url, headers={"User-Agent": "autonomics-official-package-source-assurance/1.0"})
        try:
            with urlopen(request, timeout=45) as response:
                body = response.read(512 * 1024 + 1)
                if response.status != 200 or response.url != url or len(body) > 512 * 1024:
                    raise RuntimeError("Primary release source identity/bound failed")
                body.decode("utf-8")
                if hashlib.sha256(body).hexdigest() != SOURCE_SHA256[relative]:
                    raise RuntimeError("Primary release tag differs from the frozen software reference")
                metadata = dict(path=relative, url=url, received_url=response.url, status=response.status,
                                content_type=response.headers.get("Content-Type"), bytes=len(body),
                                sha256=hashlib.sha256(body).hexdigest())
        except Exception as error:
            (directory / "source-fetch-failure.json").write_text(json.dumps(dict(
                url=url, error_type=type(error).__name__, error=str(error), scientific_authorized=False), indent=2) + "\n")
            raise
        path = directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        entries.append(metadata)
        (directory / "source-lock.json").write_text(json.dumps(dict(
            release_url=RELEASE_URL, files=entries, scientific_authorized=False), indent=2) + "\n")
    manifest = tomllib.loads((ROOT / "plugins/r-stats-lm/manifest.toml").read_text())
    image = manifest["image"]["reference"]
    current = Path("/proc/self/cgroup").read_text().strip()
    if not current.startswith("0::/") or not current.endswith(".service/worker-native"):
        raise RuntimeError("Source proof requires the recorded delegated acceptance service")
    parent = current[3:].removesuffix("/worker-native")
    command = ["podman", "run", "--rm", "--pull=never", "--network=none", "--read-only",
               "--cpus=1", "--memory=1g", "--userns=keep-id", f"--user={os.getuid()}:{os.getgid()}",
               "--tmpfs=/tmp:rw,size=32m", "-v", f"{directory}:/work:rw", "--entrypoint=Rscript",
               "-e", "EXPECTED_VALIDATION_CGROUP_PARENT=" + parent,
               image, "--vanilla", "/work/comparison.R", "/work"]
    (directory / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    response = subprocess.run(command, capture_output=True, timeout=120)
    (directory / "stdout.txt").write_bytes(response.stdout)
    (directory / "stderr.txt").write_bytes(response.stderr)
    (directory / "execution.json").write_text(json.dumps(dict(exit=response.returncode, image=image, g0_granted=False)) + "\n")
    if response.returncode:
        raise RuntimeError("Official release-function identity failed; retain mismatch evidence")
    record = json.loads((directory / "identity.json").read_text())
    if set(record["functions"]) != set(FUNCTIONS) or not record["all_eight_function_formals_and_bodies_equal"]:
        raise RuntimeError("Incomplete actual official source comparison")
    print(json.dumps(dict(functions=len(FUNCTIONS), official_R_release_function_identity=True,
                         recorded_service_descendant_and_caps_verified=True,
                         compiled_binary_rebuild_or_signed_provenance_verified=False, g0_granted=False)))


if __name__ == "__main__":
    main()
