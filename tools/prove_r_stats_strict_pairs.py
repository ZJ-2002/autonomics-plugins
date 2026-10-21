import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SYSTEM = ROOT.parent / 'autonomics'
BASE = 'd27814469edd3651ff94b100ba9159c630f0d298'
BASE_SHA = 'aeaf7ea6073029eb4c3450303c332bf15e2f8077b704f6fd958ce6e1ba5acec5'
IMAGE = 'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d'
ADAPTER_SHA = 'd73e8270a18cae934de5b8ca9584575b7b734e692e59066875cd36e995349194'


R_DRIVER = r'''
root <- commandArgs(TRUE)[1]
stopifnot(as.character(getRversion()) == "4.6.1", as.character(packageVersion("stats")) == "4.6.1")
write_tsv <- function(value, filename) write.table(value, filename, sep="\t", row.names=FALSE, quote=FALSE, na="NA")
checksum <- function(filename) substr(system2("sha256sum", shQuote(filename), stdout=TRUE), 1L, 64L)
complete <- data.frame(row_id=c("P001","P002","P003"), x=c(1,4,8), y=c(0,2,3))
incomplete <- data.frame(row_id=c("P001","P002","P003","P004"), x=c(1,4,8,12), y=c(0,NA_real_,3,7))
expected <- function(data) do.call(stats::t.test, list(x=data$x,y=data$y,paired=TRUE,
  alternative="two.sided",conf.level=0.95,mu=0,var.equal=FALSE))
references <- list(complete=expected(complete), incomplete=expected(incomplete))
dir.create(file.path(root,"references"))
saveRDS(references, file.path(root,"references","direct-official-htest-objects.RDS"), version=3)
cases <- list(
 list(name="official-complete",data=complete,policy="official",mode="paired",success=TRUE,reference="complete"),
 list(name="official-incomplete-control",data=incomplete,policy="official",mode="paired",success=TRUE,reference="incomplete"),
 list(name="strict-complete",data=complete,policy="strict_complete_pairs",mode="paired",ids="P001,P002,P003",success=TRUE,reference="complete"),
 list(name="strict-incomplete",data=incomplete,policy="strict_complete_pairs",mode="paired",ids="P001,P002,P003,P004",success=FALSE,reason="Incomplete frozen pair; no official test executed"),
 list(name="strict-whole-pair-absent",data=complete[1:2,,drop=FALSE],policy="strict_complete_pairs",mode="paired",ids="P001,P002,P003",success=FALSE,reason="Paired row identities differ from the explicit frozen contract"),
 list(name="strict-axis-reordered",data=complete[c(3,1,2),,drop=FALSE],policy="strict_complete_pairs",mode="paired",ids="P001,P002,P003",success=FALSE,reason="Paired row identities differ from the explicit frozen contract"),
 list(name="strict-trailing-comma",data=complete,policy="strict_complete_pairs",mode="paired",ids="P001,P002,P003,",success=FALSE,reason="Expected pair identities must use canonical comma-separated syntax"),
 list(name="strict-nonpaired",data=complete,policy="strict_complete_pairs",mode="wide",ids="P001,P002,P003",success=FALSE,reason="Strict complete-pair policy requires a paired t-test"),
 list(name="strict-no-expected-axis",data=complete,policy="strict_complete_pairs",mode="paired",success=FALSE,reason="Missing frozen method key: expected_row_ids"),
 list(name="strict-duplicate-expected-axis",data=complete,policy="strict_complete_pairs",mode="paired",ids="P001,P001,P003",success=FALSE,reason="Unique lexical identities required")
)
answers <- list()
for (phase in c("before","after")) {
 for (case in cases) {
  directory <- file.path(root,phase,case$name)
  dir.create(directory,recursive=TRUE)
  input <- file.path(directory,"input.tsv")
  contract_file <- file.path(directory,"contract.tsv")
  write_tsv(case$data,input)
  contract <- c(operation="t",scope="TECHNICAL_ONLY_NOT_G0",test_id=case$name,
    input_sha256=checksum(input),missing_policy=case$policy,mode=case$mode,mu="0",
    alternative="two.sided",var_equal="false",conf_level="0.95")
  if (!is.null(case$ids)) contract <- c(contract,expected_row_ids=case$ids)
  write_tsv(data.frame(key=names(contract),value=unname(contract)),contract_file)
  ports <- file.path(directory,c("statistics.tsv","parameters.tsv","statistics.RDS","statistics.log","audit.tsv"))
  variables <- c(AUTONOMICS_INPUT0=input,AUTONOMICS_INPUT1=contract_file,
    AUTONOMICS_INPUT_COUNT="2",AUTONOMICS_OUTPUT_COUNT="5",STATISTICS_OPERATION="t",
    setNames(ports,paste0("AUTONOMICS_OUTPUT",0:4)))
  do.call(Sys.setenv,as.list(variables))
  status <- suppressWarnings(system2("Rscript",c("--vanilla",shQuote(file.path(root,paste0(phase,".R")))),
    stdout=file.path(directory,"entry.stdout"),stderr=file.path(directory,"entry.stderr")))
  log <- if (file.exists(ports[4])) paste(readLines(ports[4],warn=FALSE),collapse="\n") else ""
  full_fit_match <- FALSE
  if (case$success) {
    behavior <- identical(status,0L) && all(file.exists(ports))
    if (behavior) {
      actual <- readRDS(ports[3])
      full_fit_match <- identical(actual$fit,references[[case$reference]])
      behavior <- full_fit_match && identical(actual$row_id,as.character(case$data$row_id))
    }
  } else {
    behavior <- identical(status,1L) && !any(file.exists(ports[1:3])) &&
      file.exists(ports[4]) && file.exists(ports[5]) && grepl(case$reason,log,fixed=TRUE)
    if (behavior) {
      audit <- read.delim(ports[5],colClasses="character",na.strings=NULL)
      behavior <- identical(audit$value[audit$key=="status"],"BLOCKED")
    }
  }
  answers[[length(answers)+1L]] <- data.frame(phase=phase,name=case$name,actual_exit=status,
    expected_success=case$success,behavior_matches_requested_contract=behavior,
    complete_author_htest_object_identical=full_fit_match)
 }
}
write_tsv(do.call(rbind,answers),file.path(root,"checks.tsv"))
write_tsv(data.frame(key=c("R_version","stats_version","scope"),
  value=c(as.character(getRversion()),as.character(packageVersion("stats")),"SYNTHETIC_CONTRACT_ONLY_NOT_G0")),
  file.path(root,"namespace.tsv"))
'''


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('AUTONOMICS_PODMAN_PROGRAM'), 'Managed validation session required')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    output = permanent / 'r-stats-strict-pair-contract'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    work = Path(os.environ['TMPDIR']) / 'r-stats-pair-contract'
    work.mkdir(mode=0o700)
    current_name = ROOT / 'plugins/r-stats/scripts/statistics.R'
    current = current_name.read_bytes()
    original = subprocess.check_output(['git', '-C', str(ROOT), 'show', BASE + ':plugins/r-stats/scripts/statistics.R'], timeout=30)
    require(sha(original) == BASE_SHA, 'Exact original published official-policy source required')
    test_file = ROOT / 'tests/test_r_stats_current_r.py'
    specification = importlib.util.spec_from_file_location('pair_delta', test_file)
    pair_delta = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(pair_delta)
    require(pair_delta.original_policy_source(current.decode()).encode() == original,
            'Changes beyond the declared intake-policy delta invalidate reference reuse')
    (work / 'before.R').write_bytes(original)
    (work / 'after.R').write_bytes(current)
    (work / 'controls.R').write_text(R_DRIVER)
    (output / 'source-before.R').write_bytes(original)
    (output / 'source-after.R').write_bytes(current)
    (output / 'controls.R').write_text(R_DRIVER)
    (output / 'source-delta-unit-tests.py').write_bytes(test_file.read_bytes())
    state = Path.home() / '.autonomics'
    profile = json.loads((state / 'qualified-image-store.json').read_text())
    require(IMAGE in profile['images'], 'Use an already operator-qualified exact image')
    delegate = Path(os.environ['AUTONOMICS_PODMAN_PROGRAM'])
    profile['images'] = [IMAGE]
    profile['delegate'] = dict(path=str(delegate), sha256=sha(delegate.read_bytes()))
    profile_file = output / 'managed-readonly-image-profile.json'
    profile_file.write_text(json.dumps(profile,indent=2)+'\n')
    profile_file.chmod(0o600)
    adapter = Path.home() / '.local/lib/autonomics/qualified-podman' / ADAPTER_SHA / 'podman'
    require(sha(adapter.read_bytes()) == ADAPTER_SHA, 'Qualified adapter source identity changed')
    primary = profile['primary']
    backend = ['--root',primary['graphroot'],'--runroot',primary['runroot'],
        '--tmpdir',str(Path(primary['runroot'])/'libpod-tmp'),'--storage-driver',primary['driver'],'--cgroup-manager=cgroupfs']
    prefix = [str(adapter),*backend]
    environment = dict(os.environ,AUTONOMICS_QUALIFIED_IMAGE_STORE_PROFILE=str(profile_file))
    inspected = subprocess.run([*prefix,'image','inspect','--format','{"Id":{{json .ID}},"Digest":{{json .Digest}},"RepoDigests":{{json .RepoDigests}}}',IMAGE],
        capture_output=True,env=environment,timeout=60)
    (output/'image-inspect-exit.json').write_text(json.dumps(dict(actual_exit=inspected.returncode))+'\n')
    require(inspected.returncode == 0,'Existing exact R image unavailable; do not pull or build a replacement')
    image = json.loads(inspected.stdout)
    require(image['Id'].removeprefix('sha256:')=='294152508a320bf7bbefa9ba53a095a121535cc3643e79a842950609843ea84c'
            and (image['Digest']==IMAGE.split('@',1)[1] or IMAGE in image['RepoDigests']), 'Original R image configuration/digest changed')
    (output/'filtered-image-identity.json').write_text(json.dumps(image,indent=2)+'\n')
    command = [*prefix,'run','--rm','--pull=never','--network=none','--read-only','--cpus=1','--memory=512m','--pids-limit=128',
        '--tmpfs=/tmp:rw,nosuid,nodev,size=64m','--workdir=/proof','--userns=keep-id','--user='+str(os.getuid())+':'+str(os.getgid()),
        '-e','OPENBLAS_NUM_THREADS=1','-e','OMP_NUM_THREADS=1','-e','TMPDIR=/tmp','-e','R_PROFILE_USER=/dev/null','-e','R_ENVIRON_USER=/dev/null',
        '-v',str(work)+':/proof:rw','--entrypoint=Rscript',IMAGE,'--vanilla','/proof/controls.R','/proof']
    try:
        completed = subprocess.run(command,capture_output=True,env=environment,timeout=180)
        (output/'container.stdout').write_bytes(completed.stdout)
        (output/'container.stderr').write_bytes(completed.stderr)
        (output/'container-exit.json').write_text(json.dumps(dict(actual_exit=completed.returncode))+'\n')
    finally:
        sys.path.insert(0,str(ROOT))
        from tools.prove_frozen_a_family_runtime import stopped
        stopped([str(delegate),'--storage-opt','additionalimagestore='+profile['additional']['path'],*backend],permanent,output,1)
        for child in ('checks.tsv','namespace.tsv','references','before','after'):
            source = work/child
            if source.is_dir(): shutil.copytree(source,output/child)
            elif source.is_file(): shutil.copyfile(source,output/child)
    require(completed.returncode==0,'Actual fixed-image contract driver failed; preserve all outputs')
    with (output/'checks.tsv').open() as handle:
        checks=list(csv.DictReader(handle,delimiter='\t'))
    before=[row for row in checks if row['phase']=='before']
    after=[row for row in checks if row['phase']=='after']
    require(len(before)==len(after)==10 and len({row['name'] for row in before})==10,
            'Every frozen contract case must actually execute in both source phases')
    gaps=[row['name'] for row in before if row['behavior_matches_requested_contract']!='TRUE']
    require(len(gaps)==8 and all(row['behavior_matches_requested_contract']=='TRUE' for row in after),
            'Baseline absence and candidate complete-pair contract behavior are not established')
    require(all(row['complete_author_htest_object_identical']=='TRUE' for row in checks if row['expected_success']=='TRUE' and row['actual_exit']=='0'),
            'Every successful complete htest must exactly match the direct official package call')
    require(current_name.read_bytes()==current,'Candidate source changed during proof')
    report=dict(candidate_pair_contract_verified=True,base_source_commit=BASE,base_source_sha256=BASE_SHA,
        candidate_source_sha256=sha(current),image=IMAGE,actual_containers=1,actual_entrypoint_cases=20,
        original_scope_control_cases=2,baseline_requested_extension_gaps=gaps,candidate_cases_passed=10,
        candidate_successful_complete_author_objects=3,candidate_specific_refusals=7,
        original_official_missing_policy_preserved=True,only_declared_intake_delta=True,
        existing_168_case_suite_repeated=False,new_image_builds=0,image_pulls=0,
        new_full_scheduler_DAGs=0,resident_deployed=False,new_software_admissions=0,
        signature_or_donor_or20_test_freezes_selected=False,scientific_release_granted=False,g0_granted=False)
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__=='__main__':
    main()
