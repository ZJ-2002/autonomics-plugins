"""Current compiled engine / official lm DAG proof using sealed independent oracles."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import tomllib

from tools.prove_r_lm import R_DAG_READBACK, fixtures

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_SESSION = "372140b7eea947c698b1544a68888604"
REFERENCE_MANIFEST_SHA256 = "0e69d1cdc664bc73a5091fa5c4741ad1ff68f3a3242807eaaf28c8aee6973d9b"
REFERENCE_METHOD_SHA256 = "86da2e2eb1e684db72a5cd6d149e48f0c6025182b148722a2c8a73a15a090d70"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def verify_reference(archive):
    manifest_path = archive / "artifacts/MANIFEST.json"
    if digest(manifest_path) != REFERENCE_MANIFEST_SHA256:
        raise RuntimeError("Reference archive manifest identity changed")
    manifest = json.loads(manifest_path.read_text())
    if manifest["session"] != REFERENCE_SESSION:
        raise RuntimeError("Wrong independent reference session")
    prefix = "permanent/official-r-lm/"
    records = {name: value for name, value in manifest["files"].items() if name.startswith(prefix)}
    if not records:
        raise RuntimeError("Empty independent reference packet")
    for name, identity in records.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("Escaping reference artifact")
        path = archive / "artifacts" / relative
        if path.is_symlink() or not path.is_file() or digest(path) != identity["sha256"] or path.stat().st_size != identity["bytes"]:
            raise RuntimeError("Independent reference bytes changed")
    packet = archive / "artifacts/permanent/official-r-lm"
    if digest(packet / "source/scripts/lm.R") != REFERENCE_METHOD_SHA256:
        raise RuntimeError("Reference method identity changed")
    cases = json.loads((packet / "cases.json").read_text())
    expected = fixtures()
    if [case["name"] for case in cases] != [case["name"] for case in expected]:
        raise RuntimeError("Fixed complete case denominator changed")
    verification = json.loads((packet / "verification.json").read_text())
    if set(verification["cases"]) != {case["name"] for case in cases}:
        raise RuntimeError("Independent oracle execution incomplete")
    for case in cases:
        required = ["input.tsv", "contract.json"]
        if case["expected_error"] is None:
            required += ["independent-reference.RDS", "coefficients.tsv"]
        for filename in required:
            if prefix + case["name"] + "/" + filename not in records:
                raise RuntimeError("Required reference file not sealed")
    return packet, cases


def make_job(work, source):
    return dict(scope="TECHNICAL_ONLY_NOT_G0", run_root=str(work),
                plugin_manifest=str(source / "manifest.toml"), nodes=[
        dict(id="observations", kind="file_reference", spec=dict(path="vfs:///input.tsv", format="tsv")),
        dict(id="contract", kind="file_reference", spec=dict(path="vfs:///contract.json", format="json")),
        dict(id="analysis", kind="r_stats_lm", spec={}),
        dict(id="read", kind="file_to_dataframe", spec=dict(format="tsv")),
        dict(id="write", kind="dataframe_to_file", spec=dict(path="vfs:///materialized.tsv", format="tsv")),
    ], edges=[dict(from_port=first_port, to_port=second_port, **{"from": first, "to": second})
              for first, second, first_port, second_port in [
        ("observations", "analysis", 0, 0), ("contract", "analysis", 0, 1),
        ("analysis", "read", 0, 0), ("read", "write", 0, 0),
    ]])


def check_report(directory, work, report, definition, case, commit):
    if report.get("engine_source_revision") != commit or report.get("input_hashing") != "ContentRequired":
        raise RuntimeError("Current compiled engine identity or content-hash policy differs")
    if (report.get("scope") != "TECHNICAL_ONLY_NOT_G0" or report.get("max_concurrency") != 1
            or report.get("incremental") is not False or report.get("g0_granted") is not False):
        raise RuntimeError("Synthetic execution discipline changed")
    first = report["first_run"]
    negative = case["expected_error"] is not None
    record = dict(name=case["name"], expected_refusal=negative, nodes=5, edges=4,
                  engine_source_revision=commit, output_paths=[])
    analysis = next(entry for entry in first["nodes"] if entry["id"] == "analysis")
    if negative:
        if not first["errors"] or (work / "materialized.tsv").exists() or case["expected_error"] not in json.dumps(first):
            raise RuntimeError("Expected refusal did not propagate with its actual diagnostic")
        if any(path.name in {entry["path"] for entry in definition["ports"]["outputs"]}
               for path in (work / "artifacts").rglob("*") if path.is_file()):
            raise RuntimeError("Failed current DAG published analytical output")
        return record
    if first["errors"] or analysis["status"] != "success":
        raise RuntimeError("Positive current DAG failed")
    assigned = analysis["port_assignments"]
    if set(assigned) != {str(index) for index in range(5)}:
        raise RuntimeError("Five actual output ports required")
    for index, port in enumerate(definition["ports"]["outputs"]):
        entry = assigned[str(index)]
        if not entry["path"].startswith("vfs:///"):
            raise RuntimeError("Unexpected current VFS port")
        path = work / entry["path"].removeprefix("vfs:///")
        if not path.resolve().is_relative_to(work) or path.name != port["path"] or entry["format"] != port["format"]:
            raise RuntimeError("Declared current port identity differs")
        if digest(path) != entry["fingerprint"]["content_hash"].removeprefix("sha256:"):
            raise RuntimeError("Current published port fingerprint changed")
        record["output_paths"].append(str(path.relative_to(directory)))
    record["materialized_path"] = str((work / "materialized.tsv").relative_to(directory))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--build-record", required=True, type=Path)
    parser.add_argument("--engine-commit", required=True)
    parser.add_argument("--reference-archive", required=True, type=Path)
    arguments = parser.parse_args()
    if not re.fullmatch("[0-9a-f]{40}", arguments.engine_commit):
        parser.error("actual exact compiled engine commit required")
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Use research_validation_session.py run")
    packet, cases = verify_reference(arguments.reference_archive)
    build = json.loads(arguments.build_record.read_text())
    if build["engine_commit"] != arguments.engine_commit or digest(arguments.runner) != build["executable_sha256"]:
        raise RuntimeError("Current executable differs from its build evidence")
    directory = Path(permanent) / "current-official-lm-dag"
    directory.mkdir(mode=0o700)
    source = directory / "source"
    shutil.copytree(ROOT / "plugins/r-stats-lm", source)
    if digest(source / "scripts/lm.R") != REFERENCE_METHOD_SHA256:
        raise RuntimeError("Method changed; sealed reference cannot authorize it")
    shutil.copyfile(Path(__file__), source / "current-driver.py")
    shutil.copyfile(ROOT / "tools/prove_r_lm.py", source / "original-fixture-and-readback-driver.py")
    shutil.copyfile(arguments.build_record, directory / "build-record.json")
    source_identities = {str(path.relative_to(source)): digest(path) for path in source.rglob("*") if path.is_file()}
    (directory / "source-identity.json").write_text(json.dumps(source_identities, indent=2) + "\n")
    (directory / "predeclared.json").write_text(json.dumps(dict(
        original_function_id="FUNC_linear_regression", cases=[case["name"] for case in cases],
        absolute_tolerance=1e-10, relative_tolerance=1e-8, exact_names_masks_and_hashes=True,
        reference_manifest_sha256=REFERENCE_MANIFEST_SHA256, reference_recomputed=False,
        current_daemon_verified=False, g0_granted=False), indent=2) + "\n")
    definition = tomllib.loads((source / "manifest.toml").read_text())["nodes"][0]
    dag_root = directory / "dags"
    dag_root.mkdir()
    records = []
    for case in cases:
        reference = directory / case["name"]
        reference.mkdir()
        for name in ["input.tsv", "contract.json"] + ([] if case["expected_error"] else ["coefficients.tsv", "independent-reference.RDS"]):
            shutil.copyfile(packet / case["name"] / name, reference / name)
        work = dag_root / case["name"]
        work.mkdir()
        for name in ["input.tsv", "contract.json"]:
            shutil.copyfile(reference / name, work / name)
        job = make_job(work, source)
        (work / "job.json").write_text(json.dumps(job, indent=2) + "\n")
        started = time.monotonic()
        completed = subprocess.run([str(arguments.runner), str(work / "job.json")], capture_output=True, timeout=180)
        (work / "stdout.log").write_bytes(completed.stdout)
        (work / "stderr.log").write_bytes(completed.stderr)
        (work / "execution.json").write_text(json.dumps(dict(exit=completed.returncode, elapsed=time.monotonic()-started)) + "\n")
        if completed.returncode:
            raise RuntimeError("Current engine harness did not finish its report: " + case["name"])
        report = json.loads((work / "dag-report.json").read_text())
        records.append(check_report(directory, work, report, definition, case, arguments.engine_commit))
        (directory / "dag-evidence.json").write_text(json.dumps(dict(
            schema="CURRENT_COMMITTED_ENGINE_OFFICIAL_LM_DAG_V1", cases=records,
            engine_commit=arguments.engine_commit, current_daemon_verified=False,
            scientific_authorized=False, g0_granted=False), indent=2) + "\n")
    (directory / "dag-readback.R").write_text(R_DAG_READBACK)
    readback = subprocess.run(["Rscript", "--vanilla", str(directory / "dag-readback.R"), str(directory)], capture_output=True, timeout=120)
    (directory / "dag-readback.stdout").write_bytes(readback.stdout)
    (directory / "dag-readback.stderr").write_bytes(readback.stderr)
    if readback.returncode:
        raise RuntimeError("Materialized current outputs do not match sealed independent official references")
    if source_identities != {str(path.relative_to(source)): digest(path) for path in source.rglob("*") if path.is_file()}:
        raise RuntimeError("Proof source mutated during current execution")
    print(json.dumps(dict(current_engine_commit=arguments.engine_commit, current_engine_dags=len(records),
                         independent_reference_recomputed=False, current_daemon_verified=False, g0_granted=False)))


if __name__ == "__main__":
    main()
