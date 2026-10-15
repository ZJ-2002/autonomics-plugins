"""Compare every package-owned R function with the frozen official host package."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.prove_frozen_a_harmonisation import IMAGE, STUDY, digest, inspected_backend, require, resource_admission, write

HOST_DESCRIPTION_SHA = '693abf30cec91e706d2f29acfc255542c7059f4760479c1132f28274f6e1a5b5'
CONTAINER_DESCRIPTION_SHA = '911b67c8ea5bdc0985f51db6c98ff7016e829216043fe816fb5d462314aae531'
COMMIT = 'd4df21929fdabeb2f89686ffaad0db5f56973d64'
FUNCTION_IDENTITY_R = '''namespace_function_identity <- function() {
 namespace <- asNamespace("TwoSampleMR")
 names <- sort(ls(namespace,all.names=TRUE),method="radix")
 names <- names[vapply(names,function(name) is.function(get(name,envir=namespace,inherits=FALSE)),logical(1))]
 hashes <- vapply(names,function(name) {
  fun <- get(name,envir=namespace,inherits=FALSE)
  lines <- c(paste0("name=",name),"FORMALS",deparse(formals(fun),width.cutoff=500L),
             "BODY",deparse(body(fun),width.cutoff=500L))
  digest::digest(charToRaw(paste(lines,collapse="\\n")),algo="sha256",serialize=FALSE)
 },"")
 aggregate <- digest::digest(charToRaw(paste(paste(names(hashes),hashes,sep="\\t"),collapse="\\n")),algo="sha256",serialize=FALSE)
 list(function_count=length(hashes),aggregate_sha256=aggregate,functions=as.list(hashes))
}
'''


def package_files(package):
    return {path.relative_to(package).as_posix(): digest(path) for path in package.rglob('*') if path.is_file()}


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed identity proof required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'frozen-a-package-identity'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    library = STUDY / '04_SOFTWARE/R_library'
    package = library / 'TwoSampleMR'
    require(digest(package / 'DESCRIPTION') == HOST_DESCRIPTION_SHA, 'Exact frozen official host package required')
    before = package_files(package)
    program = FUNCTION_IDENTITY_R + '''arguments<-commandArgs(TRUE)
if(nzchar(arguments[1])) .libPaths(c(arguments[1],.libPaths()))
stopifnot(as.character(getRversion())=="4.6.1",as.character(packageVersion("TwoSampleMR"))=="0.7.11")
description<-packageDescription("TwoSampleMR")
record<-list(R=as.character(getRversion()),TwoSampleMR=as.character(packageVersion("TwoSampleMR")),
 package_description_sha256=digest::digest(file=system.file("DESCRIPTION",package="TwoSampleMR"),algo="sha256",serialize=FALSE),
 observed_RemoteSha=description$RemoteSha,observed_GithubSHA1=description$GithubSHA1,
 function_identity=namespace_function_identity())
jsonlite::write_json(record,arguments[2],pretty=TRUE,auto_unbox=TRUE,null="null",digits=17)
'''
    script = output / 'package-identity.R'
    script.write_text(program)
    resource_admission(output)
    prefix = inspected_backend(output)
    host_command = ['Rscript', '--vanilla', str(script), str(library), str(output / 'host.json')]
    command = [*prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1',
        '--memory=1g', '--pids-limit=64', '--userns=keep-id', '--user=' + str(os.getuid()) + ':' + str(os.getgid()),
        '--tmpfs=/tmp:rw,size=64m', '-v', str(output) + ':/work:rw', '--entrypoint=Rscript', IMAGE,
        '--vanilla', '/work/package-identity.R', '', '/work/container.json']
    for label, current in [('host', host_command), ('container', command)]:
        write(output / (label + '-command.json'), current)
        result = subprocess.run(current, capture_output=True, text=True, timeout=120)
        (output / (label + '.stdout.log')).write_text(result.stdout)
        (output / (label + '.stderr.log')).write_text(result.stderr)
        require(result.returncode == 0, 'Actual package function identity process failed: ' + label)
    host = json.loads((output / 'host.json').read_text())
    container = json.loads((output / 'container.json').read_text())
    require(host['package_description_sha256'] == HOST_DESCRIPTION_SHA and host['observed_RemoteSha'] == COMMIT and
        host['observed_GithubSHA1'] == COMMIT, 'Frozen host must retain actual official source metadata')
    require(container['package_description_sha256'] == CONTAINER_DESCRIPTION_SHA and
        container['observed_RemoteSha'] is None and container['observed_GithubSHA1'] is None,
        'Container metadata observation must not be fabricated')
    require(host['function_identity']['function_count'] > 0 and host['function_identity'] == container['function_identity'],
        'Full package-owned function inventory/formals/bodies differ')
    require(before == package_files(package), 'Frozen host package bytes changed')
    write(output / 'verification.json', dict(status='FULL_PACKAGE_OWNED_R_FUNCTION_IDENTITY_MATCH_NOT_WHOLE_ENVIRONMENT_CERTIFICATION',
        canonical_host_package_files_unchanged=True, canonical_host_package_files=len(before),
        observed_host_RemoteSha=host['observed_RemoteSha'], observed_container_RemoteSha=None,
        canonical_host_description_sha256=HOST_DESCRIPTION_SHA, container_description_sha256=CONTAINER_DESCRIPTION_SHA,
        official_source_commit_supported_by_host_metadata=COMMIT,
        function_identity=host['function_identity'], exact_image=IMAGE,
        R='4.6.1', TwoSampleMR='0.7.11', method_fitted=False, production_restarted=False,
        scientific_release_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
