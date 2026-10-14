"""Actual declared-port/whole-author-log parity using the published pristine runtime."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "ghcr.io/zj-2002/ldsc@sha256:e98d2a89b0412384bbec1369250d935868a919f8a164c4ce55b282ac13495767"
REFERENCE = "80cfad43df464152bc4c7561829a4b7c"
REFERENCE_SEAL = "51ae58efb47e8cdbc18e7957211fea977b90d04fed27066b0a47b899a77f61d3"


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def normalize_log(text, substitutions):
    lines = []
    for line in text.splitlines():
        if line.startswith(("Beginning analysis at ", "Analysis finished at ", "Total time elapsed: ")):
            continue
        for old, new in substitutions:
            line = line.replace(old, new)
        lines.append(line)
    return "\n".join(lines)


def check_author_failure(actual_log, author_log, author_stderr, actual_exit, author_exit):
    if (actual_exit != 1 or author_exit != actual_exit or "KeyError: 'AGAC'" not in author_stderr
            or "traceback.format_exc" not in author_stderr
            or "/opt/cachexia-official-ldsc/ldscore/sumstats.py" not in author_stderr):
        raise RuntimeError("Exact known author allele/exception-formatting failure required")
    position = 0
    for line in author_stderr.splitlines():
        if not line:
            continue
        found = actual_log.find(line, position)
        if found < 0:
            raise RuntimeError("Complete ordered independent author diagnostics were not retained")
        position = found + len(line)
    if not actual_log.endswith(author_log):
        raise RuntimeError("Official failure log suffix was not retained")


def check_positive_log(actual, oracle, substitutions, method, mode):
    required = ["Total Observed scale h2:"] if method == "h2" else [
        "Summary of Genetic Correlation Results", "Genetic Covariance"]
    if not actual.strip() or not oracle.strip() or any(marker not in oracle for marker in required):
        raise RuntimeError("Nonempty complete official inference output required")
    if method == "rg" and mode != "nonpositive_h2" and "Genetic Correlation:" not in oracle:
        raise RuntimeError("Actual author genetic-correlation estimate required")
    if normalize_log(actual, substitutions) != normalize_log(oracle, substitutions):
        raise RuntimeError("Whole official output differs beyond declared path/timing identity")


def checked_reference(archive):
    if archive.name != REFERENCE or digest(archive / "artifacts/MANIFEST.json") != REFERENCE_SEAL:
        raise RuntimeError("Exact sealed published-runtime reference required")
    document = json.loads((archive / "artifacts/MANIFEST.json").read_text())
    paths = {path.relative_to(archive / "artifacts").as_posix() for path in (archive / "artifacts").rglob("*")
             if path.is_file() and path.name != "MANIFEST.json"}
    if paths != set(document["files"]):
        raise RuntimeError("Complete reference membership differs")
    for name, identity in document["files"].items():
        path = archive / "artifacts" / name
        if path.is_symlink() or path.stat().st_size != identity["bytes"] or digest(path) != identity["sha256"]:
            raise RuntimeError("Actual sealed reference artifact differs")
    source = archive / "artifacts/permanent/ldsc-pristine-published-method"
    result = json.loads((source / "RESULT.json").read_text())
    if result["status"] != "PASS" or result["image"] != IMAGE or len(result["cases"]) != 5:
        raise RuntimeError("Complete actual author-state reference differs")
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-archive", required=True, type=Path)
    arguments = parser.parse_args()
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Use managed validation")
    output = Path(permanent) / "ldsc-canonical-published-entrypoints"
    output.mkdir(mode=0o700)
    (output / "driver.py").write_bytes(Path(__file__).read_bytes())
    reference = checked_reference(arguments.reference_archive)
    panels = output / "synthetic-panels"
    shutil.copytree(reference / "panels", panels)
    source = output / "source"
    source.mkdir()
    family = ROOT / "plugins/ldsc"
    for name in ["manifest.toml", "scripts/h2.sh", "scripts/rg.sh"]:
        destination = source / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(family / name, destination)
    manifest = tomllib.loads((source / "manifest.toml").read_text())
    if manifest["image"]["reference"] != IMAGE:
        raise RuntimeError("Actual author runtime identity differs")
    cases = [
        ("h2-plain", "h2", False, 20, None, None, "observed"),
        ("h2-gzip", "h2", True, 200, None, None, "observed"),
        ("h2-constrained", "h2", False, 20, "1.0", "100", "observed"),
        ("rg-plain", "rg", False, 20, None, None, "observed"),
        ("rg-gzip", "rg", True, 200, None, "100", "observed"),
        ("rg-nonpositive-h2", "rg", False, 20, None, None, "nonpositive_h2"),
        ("rg-invalid-allele-author-failure", "rg", False, 20, None, None, "invalid"),
    ]
    answers = []
    for name, method, compressed, blocks, intercept, cutoff, mode in cases:
        case = output / name
        case.mkdir()
        original = reference / ("rg-nonpositive_h2" if mode == "nonpositive_h2" else "rg-observed")
        inputs = []
        references = []
        for index in range(1 if method == "h2" else 2):
            payload = (original / ("input-"+str(index))).read_bytes()
            if mode == "invalid" and index == 1:
                rows = list(csv.DictReader(io.StringIO(payload.decode()), delimiter="\t"))
                rows[0]["A2"] = "C"
                buffer = io.StringIO()
                writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
                payload = buffer.getvalue().encode()
            path = case / (f"input-{index}.sumstats.gz" if compressed else f"input-{index}.tsv")
            path.write_bytes(gzip.compress(payload, mtime=0) if compressed else payload)
            inputs.append("/work/"+path.name)
            direct = case / ".reference_" / f"input-{index}.tsv" if compressed else case / f"other-{index}.tsv"
            direct.parent.mkdir(exist_ok=True)
            direct.write_bytes(payload)
            references.append("/work/"+str(direct.relative_to(case)))
        node = next(node for node in manifest["nodes"] if node["kind"] == "ldsc_"+method)
        declared = node["ports"]["outputs"][0]["path"]
        environment = dict(AUTONOMICS_WORKDIR="/work", AUTONOMICS_INPUT0=inputs[0],
                           AUTONOMICS_OUTPUT0="/work/"+declared, LDSC_N_BLOCKS=str(blocks),
                           LDSC_RG_N_BLOCKS=str(blocks), OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", LC_ALL="C")
        if method == "rg": environment["AUTONOMICS_INPUT1"] = inputs[1]
        if intercept is not None: environment["LDSC_INTERCEPT_H2"] = intercept
        if cutoff is not None: environment["LDSC_CHISQ_MAX" if method == "h2" else "LDSC_RG_CHISQ_MAX"] = cutoff
        base = ["podman", "run", "--rm", "--pull=never", "--network=none", "--read-only", "--cpus=1", "--memory=1g",
                "--tmpfs=/tmp:rw,size=32m", "-v", str(case)+":/work:rw", "-v", str(panels)+":/panels:ro"]
        command = base + ["-v", str(source / "scripts" / (method+".sh"))+":/entrypoint.sh:ro", "--entrypoint=/bin/sh"]
        for key, value in environment.items(): command += ["-e", key+"="+value]
        with (case / "wrapper.stdout").open("wb") as stdout, (case / "wrapper.stderr").open("wb") as stderr:
            observed = subprocess.run(command+[IMAGE, "/entrypoint.sh"], stdout=stdout, stderr=stderr, timeout=180)
        direct_args = ["--"+method, references[0] if method == "h2" else ",".join(references),
                       "--ref-ld-chr", "/panels/ref_ld/LDscore.", "--w-ld-chr", "/panels/w_ld/weights.hm3_noMHC.",
                       "--n-blocks", str(blocks)]
        if intercept is not None: direct_args += ["--intercept-h2", intercept]
        if cutoff is not None: direct_args += ["--chisq-max", cutoff]
        direct_args += ["--out", "/work/direct_cli"]
        reference_command = base + ["-e", "OPENBLAS_NUM_THREADS=1", "-e", "OMP_NUM_THREADS=1", "--entrypoint=python", IMAGE,
                                    "/opt/cachexia-official-ldsc/ldsc.py"] + direct_args
        with (case / "direct.stdout").open("wb") as stdout, (case / "direct.stderr").open("wb") as stderr:
            independent = subprocess.run(reference_command, stdout=stdout, stderr=stderr, timeout=180)
        if mode != "invalid" and (independent.returncode or observed.returncode):
            raise RuntimeError("Actual author or canonical entrypoint failed: "+name)
        if mode == "invalid":
            reference_error=(case / "direct.stderr").read_text()
            check_author_failure((case / declared).read_text(),(case / "direct_cli.log").read_text(),
                                 reference_error,observed.returncode,independent.returncode)
        actual = (case / declared).read_text()
        oracle = (case / "direct_cli.log").read_text() or (case / "direct.stdout").read_text()
        substitutions = [("/work/.autonomics/ldsc_"+method, "<OUTPUT>"), ("/work/direct_cli", "<OUTPUT>")]
        for index in range(len(inputs)):
            actual_input = f"/work/.autonomics/input-{index}.tsv" if compressed else inputs[index]
            substitutions += [(actual_input, f"<INPUT{index}>"), (references[index], f"<INPUT{index}>")]
        if mode != "invalid":
            check_positive_log(actual, oracle, substitutions, method, mode)
            if (case / "wrapper.stderr").read_bytes() != (case / "direct.stderr").read_bytes():
                raise RuntimeError("Complete independent author warnings differ: "+name)
        if compressed:
            for index, source_path in enumerate(references):
                materialized = case / ".autonomics" / f"input-{index}.tsv"
                if digest(materialized) != digest(case / source_path.removeprefix("/work/")):
                    raise RuntimeError("Actual complete gzip materialization differs")
        answers.append(dict(case=name, kind=node["kind"], wrapper_exit=observed.returncode,
                            independent_author_exit=independent.returncode, declared_port=declared,
                            whole_author_log_equal_except_paths_and_three_timing_lines=mode!="invalid",
                            ordered_complete_failure_diagnostics_preserved=mode=="invalid",
                            complete_log_bytes=len(actual.encode()), true_author_failure_not_fallback=mode=="invalid"))
        (output / "cases-completed.json").write_text(json.dumps(answers, indent=2)+"\n")
    report = dict(status="CANONICAL_AUTHOR_CLI_AND_DECLARED_LOG_PORTS_PROVEN_SCOPED_NOT_DAG",
                  image=IMAGE, cases=answers, original_reference_seal=REFERENCE_SEAL,
                  input_origin="SYNTHETIC_TECHNICAL_ONLY", all22_synthetic_panel_files_used=True,
                  h2_script_sha256=digest(source / "scripts/h2.sh"), rg_script_sha256=digest(source / "scripts/rg.sh"),
                  actual_research_panels_qualified=False, full_precision_family_P_from_logs=False,
                  current_engine_DAG_verified=False, daemon_deployed=False, formal_authorized=False, g0_granted=False)
    (output / "verification.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
