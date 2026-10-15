"""Run with research_validation_session.py; all required evidence is permanent."""
import json
import os
from pathlib import Path
import subprocess
import tomllib
from generate_toy import generate, sha

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
DEST = Path(os.environ["AUTONOMICS_VALIDATION_PERMANENT"]) / "v432-a-method"
DEST.mkdir()
manifest = tomllib.loads((PLUGIN / "manifest.toml").read_text())
image = manifest["image"]["reference"]
names = ["input.tsv","config.json","certificate.json","lock.tsv","proof.json"]


def run(inputs, outputs, script, arguments=(), expect_success=True):
    outputs.mkdir()
    command = ["podman","run","--rm","--pull=never","--network=none",
               "--userns=keep-id",f"--user={os.getuid()}:{os.getgid()}",
               "--security-opt=no-new-privileges","--cpus=2","--memory=2g",
               "-v",f"{PLUGIN}:/plugin:ro","-v",f"{inputs}:/inputs:ro","-v",f"{outputs}:/outputs:rw"]
    for i,name in enumerate(names):
        command += ["-e",f"AUTONOMICS_INPUT{i}=/inputs/{name}"]
    for i in range(9):
        command += ["-e",f"AUTONOMICS_OUTPUT{i}=/outputs/output{i}"]
    command += ["--entrypoint=Rscript",image,"--vanilla",script,*arguments]
    result = subprocess.run(command, capture_output=True, text=True)
    (outputs / "stdout.txt").write_text(result.stdout)
    (outputs / "stderr.txt").write_text(result.stderr)
    if expect_success != (result.returncode == 0):
        raise RuntimeError(f"unexpected status {result.returncode}: {result.stderr}")
    return result.returncode


for label,noise in [("under",.001),("over",.5)]:
    inputs = DEST / label / "inputs"
    generate(inputs, noise)
    outputs = DEST / label / "outputs"
    run(inputs,outputs,"/plugin/scripts/mr.R")
    # Verification reads the adapter output through a dedicated read-only mount.
    command = ["podman","run","--rm","--pull=never","--network=none",
      "--userns=keep-id",f"--user={os.getuid()}:{os.getgid()}",
      "-v",f"{PLUGIN}:/plugin:ro","-v",f"{inputs}:/inputs:ro","-v",f"{outputs}:/outputs:rw",
      "--entrypoint=Rscript",image,"--vanilla","/plugin/tests/verify.R","/inputs","/outputs",label]
    result = subprocess.run(command,capture_output=True,text=True)
    (outputs/"verify-stdout.txt").write_text(result.stdout)
    (outputs/"verify-stderr.txt").write_text(result.stderr)
    if result.returncode: raise RuntimeError(result.stderr)

failures = {}
for label in ["input-byte-mismatch","primary-source-mismatch","version-lock-mismatch","unqualified-row",
              "method-mismatch","seed-mismatch","certificate-role-mismatch"]:
    inputs = DEST / label / "inputs"
    generate(inputs,.001)
    if label in ["input-byte-mismatch","unqualified-row"]:
        path = inputs/"input.tsv"
        path.write_text(path.read_text().replace("QUALIFIED","NOT_QUALIFIED",1))
    elif label in ["primary-source-mismatch","method-mismatch","seed-mismatch"]:
        path = inputs/"config.json"
        cfg = json.loads(path.read_text())
        if label == "primary-source-mismatch": cfg["primary_p_source"]="EXPLORATORY_P"
        elif label == "method-mismatch": cfg["methods"]=["mr_ivw_fe"]
        else: cfg["seed"]=1
        path.write_text(json.dumps(cfg))
    elif label == "certificate-role-mismatch":
        path = inputs/"certificate.json"
        cert = json.loads(path.read_text()); cert["A"]["role"]="CONFIRMATORY"
        path.write_text(json.dumps(cert))
    else:
        path = inputs/"lock.tsv"; path.write_text(path.read_text().replace("0.7.11","0.7.9"))
    if label != "input-byte-mismatch":
        cfg = json.loads((inputs/"config.json").read_text())
        cfg["program_sha256"]=sha(inputs/"input.tsv")
        (inputs/"config.json").write_text(json.dumps(cfg))
        proof = json.loads((inputs/"proof.json").read_text())
        proof["input_sha256"]=[sha(inputs/name) for name in names[:4]]
        (inputs/"proof.json").write_text(json.dumps(proof))
    failures[label]=run(inputs,DEST/label/"outputs","/plugin/scripts/mr.R",expect_success=False)

inspection = subprocess.run(["podman","image","inspect",image],capture_output=True,text=True,check=True)
(DEST/"image-inspect.json").write_text(inspection.stdout)
summary = dict(scope="SYNTHETIC_METHOD_TEST",image=image,
  source_sha256={str(path.relative_to(PLUGIN)):sha(path) for path in PLUGIN.rglob("*") if path.is_file()},
  underdispersion_and_overdispersion=True,official_complete_sequence_parity=True,
  rejected_contracts=failures,scientific_authorization_granted=False,g0_granted=False)
(DEST/"SUMMARY.json").write_text(json.dumps(summary,indent=2)+"\n")
print(json.dumps(summary,indent=2))
