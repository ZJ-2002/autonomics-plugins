"""Run every sealed official statistics case through a fixed current-engine typed DAG."""

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_SESSION = "6c469b6c101c472ba60a8b5df077d780"
REFERENCE_MANIFEST = "dca66ac064d61286b5aa1519247113aa40ee720aaa64dc6a76e0c63de0b1f536"
METHOD_SHA = "1ef00d41e6cb1b5a4870b5018dcfe28329bb0e9156d65e5fbfc6362aa4ef7d51"
METHODS = dict(t="cachexia_r_t_test", cor="cachexia_r_cor_test", var="cachexia_r_var_test",
               wilcox="cachexia_r_wilcox_test", prop="cachexia_r_prop_test", adjust="cachexia_r_p_adjust")
NUMERIC = ["statistic", "p_value", "dof1", "dof2", "estimate1", "estimate2", "null_value", "stderr",
           "conf_low", "conf_high", "achieved_conf_level"]
COLUMNS = ["test_id", *NUMERIC[:8], "conf_low", "conf_high", "conf_low_type", "conf_high_type",
           "achieved_conf_level", "alternative", "method", "status"]
ADJUST = ["test_id", "p_value", "p_adj", "reject", "family_n", "method", "status"]


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024**2), b""):
            value.update(block)
    return value.hexdigest()


def table(path):
    with path.open() as source:
        return list(csv.DictReader(source, delimiter="\t"))


def reference(archive):
    if archive.name != REFERENCE_SESSION or digest(archive / "artifacts/MANIFEST.json") != REFERENCE_MANIFEST:
        raise RuntimeError("Exact sealed independent method reference required")
    manifest = json.loads((archive / "artifacts/MANIFEST.json").read_bytes())
    paths = {path.relative_to(archive / "artifacts").as_posix() for path in (archive / "artifacts").rglob("*")
             if path.is_file() and path.name != "MANIFEST.json"}
    if paths != set(manifest["files"]) or manifest["session"] != REFERENCE_SESSION:
        raise RuntimeError("Independent reference membership differs")
    for name, identity in manifest["files"].items():
        path = archive / "artifacts" / name
        if path.is_symlink() or path.stat().st_size != identity["bytes"] or digest(path) != identity["sha256"]:
            raise RuntimeError("Independent reference artifact identity differs")
    packet = archive / "artifacts/permanent/official-r-stats-publication"
    if digest(packet / "statistics.R") != METHOD_SHA:
        raise RuntimeError("Independent method entry differs")
    checks = table(packet / "method-checks.tsv")
    cases = table(packet / "cases.tsv")
    if len(cases) != 164 or len({case["id"] for case in cases}) != 164 or {case["id"] for case in cases} != {case["id"] for case in checks}:
        raise RuntimeError("Complete fixed official-method case inventory differs")
    return packet, cases


def make_job(work, source, case, ids):
    operation = case["operation"]
    if operation not in METHODS or len(ids) != len(set(ids)) or any(not re.fullmatch(r"[A-Za-z0-9_.:+-]+", identity) for identity in ids):
        raise RuntimeError("Explicit method and lexical unique output identities required")
    columns = ADJUST if operation == "adjust" else COLUMNS
    numeric = {"p_value", "p_adj", "family_n"} if operation == "adjust" else set(NUMERIC)
    expressions = []
    for column in columns:
        if column in numeric or column == "reject":
            datatype = "BOOLEAN" if column == "reject" else "DOUBLE"
            expressions.append(f'CAST(NULLIF("{column}", \'NA\') AS {datatype}) AS "{column}"')
        else:
            expressions.append(f'"{column}" AS "{column}"')
    query = "SELECT " + ", ".join(expressions) + " FROM input"
    if ids:
        query += ' ORDER BY CASE "test_id" ' + " ".join(f"WHEN '{identity}' THEN {index}" for index, identity in enumerate(ids)) + f" ELSE {len(ids)} END"
    nodes = [
        dict(id="input0", kind="file_reference", spec=dict(path="vfs:///input0.tsv", format="tsv")),
        dict(id="input1", kind="file_reference", spec=dict(path="vfs:///input1.tsv", format="tsv")),
        dict(id="analysis", kind=METHODS[operation], spec={}),
        dict(id="raw_read", kind="file_to_dataframe", spec=dict(format="tsv",
             csv_schema=[dict(name=column, data_type="utf8", nullable=True) for column in columns])),
        dict(id="raw_write", kind="dataframe_to_file", spec=dict(path="vfs:///raw.parquet", format="parquet")),
        dict(id="typed", kind="datafusion_sql", spec=dict(sql=query, output_path="vfs:///typed.parquet")),
        dict(id="typed_read", kind="file_to_dataframe", spec=dict(format="parquet")),
        dict(id="sink", kind="dataframe_to_file", spec=dict(path="vfs:///materialized.tsv", format="tsv")),
    ]
    edges = [("input0", "analysis", 0, 0), ("input1", "analysis", 0, 1),
             ("analysis", "raw_read", 0, 0), ("raw_read", "raw_write", 0, 0),
             ("raw_write", "typed", 0, 0), ("typed", "typed_read", 0, 0), ("typed_read", "sink", 0, 0)]
    return dict(scope="TECHNICAL_ONLY_NOT_G0", run_root=str(work), plugin_manifest=str(source / "manifest.toml"),
                nodes=nodes, edges=[dict(**{"from": first, "to": second}, from_port=first_port, to_port=second_port)
                                    for first, second, first_port, second_port in edges])


def compare_rows(actual, expected, operation):
    if actual and ("test_id" not in actual[0] or set(actual[0]) != set(expected[0])):
        raise RuntimeError("Declared materialized column names differ; do not normalize qualified headers")
    if len(actual) != len(expected) or [row["test_id"] for row in actual] != [row["test_id"] for row in expected]:
        raise RuntimeError("Complete ordered materialized output identities differ")
    numeric = {"p_value", "p_adj", "family_n"} if operation == "adjust" else set(NUMERIC)
    for observed, oracle in zip(actual, expected, strict=True):
        if observed.keys() != oracle.keys():
            raise RuntimeError("Declared output column inventory differs")
        for key, value in oracle.items():
            candidate = observed[key]
            if key in numeric:
                if value == "NA":
                    if candidate not in {"", "NA"}:
                        raise RuntimeError("Official missing numeric output was replaced")
                elif not math.isfinite(float(candidate)) or abs(float(candidate)-float(value)) > 1e-12:
                    raise RuntimeError("Materialized official numerical output differs")
            elif key == "reject":
                normalized = candidate.upper() if candidate else "NA"
                if normalized != value:
                    raise RuntimeError("Typed reject/NULL output differs")
            elif candidate != value:
                raise RuntimeError("Literal result identity or semantic value differs")


def check_report(work, definition, case, report, commit, expected_message):
    if (report.get("engine_source_revision") != commit or report.get("input_hashing") != "ContentRequired"
            or report.get("scope") != "TECHNICAL_ONLY_NOT_G0" or report.get("max_concurrency") != 1
            or report.get("incremental") is not False or report.get("g0_granted") is not False):
        raise RuntimeError("Exact current engine identity or technical discipline differs")
    first = report["first_run"]
    if len(first["nodes"]) != 8 or {node["id"] for node in first["nodes"]} != {
            "input0", "input1", "analysis", "raw_read", "raw_write", "typed", "typed_read", "sink"}:
        raise RuntimeError("Actual complete eight-node DAG inventory differs")
    analysis = next(record for record in first["nodes"] if record["id"] == "analysis")
    scratch = Path(os.environ["TMPDIR"]) / "official-r-stats-container-workspaces" / work.name
    record = dict(id=case["id"], operation=case["operation"], negative=case["negative"] == "true",
                  nodes=8, edges=7, output_paths=[])
    if record["negative"]:
        if not first["errors"] or (work / "materialized.tsv").exists() or analysis["status"] != "failed":
            raise RuntimeError("Expected invalid method was not blocked")
        if any(list(scratch.rglob(name)) for name in ["statistics.tsv", "parameters.tsv", "statistics.RDS"]):
            raise RuntimeError("Blocked method retained analytical output")
        diagnostics = list(scratch.rglob("audit.tsv"))
        if len(diagnostics) != 1:
            raise RuntimeError("Exactly one owned failure diagnostic required")
        path = diagnostics[0]
        if path.is_symlink() or not path.resolve().is_relative_to(scratch):
            raise RuntimeError("Failure diagnostic escaped owned work")
        facts = {row["key"]: row["value"] for row in table(path)}
        if facts.get("status") != "BLOCKED" or facts.get("message") != expected_message:
            raise RuntimeError("Actual refusal reason differs from sealed case")
        owned = work / "failure-diagnostics"
        owned.mkdir()
        for name in ["audit.tsv", "statistics.log"]:
            source = path.parent / name
            if source.is_symlink() or not source.stat().st_size:
                raise RuntimeError("Required actual failure diagnostic missing")
            shutil.copyfile(source, owned / name)
            if digest(owned / name) != digest(source):
                raise RuntimeError("Diagnostic preservation differs")
        record["failure_diagnostics_preserved_not_success_ports"] = True
        return record
    if first["errors"] or any(node["status"] != "success" for node in first["nodes"]) or not (work / "materialized.tsv").is_file():
        raise RuntimeError("Positive complete current DAG failed")
    assignments = analysis["port_assignments"]
    if set(assignments) != {str(index) for index in range(5)}:
        raise RuntimeError("All declared output ports required")
    published_root = work / definition["artifact_prefix"].removeprefix("/")
    for index, port in enumerate(definition["ports"]["outputs"]):
        assigned = assignments[str(index)]
        live = Path(assigned["path"])
        matches = list(published_root.glob("*/" + port["path"]))
        if (not live.is_absolute() or live.is_symlink() or not live.resolve().is_relative_to(scratch)
                or len(matches) != 1 or matches[0].is_symlink() or live.name != port["path"]
                or assigned["format"] != port["format"] or digest(live) != digest(matches[0])
                or live.stat().st_size != assigned["fingerprint"]["size"]):
            raise RuntimeError("Actual live output and unique published copy differ")
        declared = assigned["fingerprint"].get("content_hash")
        if declared is not None and digest(live) != declared.removeprefix("sha256:"):
            raise RuntimeError("Declared output content identity differs")
        record["output_paths"].append(str(matches[0]))
    columns = next(node for node in first["nodes"] if node["id"] == "typed_read")["output_schema"]["columns"]
    numeric = {"p_value", "p_adj", "family_n"} if case["operation"] == "adjust" else set(NUMERIC)
    if any(columns[name] != "Float64" for name in numeric) or columns["test_id"] not in {"Utf8", "Utf8View", "LargeUtf8"}:
        raise RuntimeError("Typed numeric/lexical output schema differs")
    if case["operation"] == "adjust" and columns["reject"] != "Boolean":
        raise RuntimeError("Reject column is not typed Boolean")
    record["typed_output_schema"] = columns
    return record


R_READBACK = r'''
root <- "/work"
stopifnot(as.character(getRversion())=="4.5.1")
records <- read.delim(file.path(root,"readback.tsv"),colClasses="character",na.strings=NULL)
for (index in seq_len(nrow(records))) {
  actual <- readRDS(records$actual[index])
  expected <- readRDS(records$reference[index])
  input <- read.delim(records$input[index],colClasses="character",na.strings=NULL,check.names=FALSE)
  stopifnot(isTRUE(all.equal(actual$fit,expected$fit,tolerance=1e-12,check.attributes=TRUE)),
    isTRUE(all.equal(actual$arguments[sort(names(actual$arguments))],expected$arguments[sort(names(expected$arguments))],tolerance=1e-12)),
    identical(actual$warnings,expected$warnings),identical(actual$row_id,input$row_id))
}
writeLines(paste0("complete_RDS_objects_reread=",nrow(records)),file.path(root,"complete-RDS-readback.txt"))
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--build-record", required=True, type=Path)
    parser.add_argument("--engine-commit", required=True)
    parser.add_argument("--reference-archive", required=True, type=Path)
    arguments = parser.parse_args()
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent or not re.fullmatch(r"[0-9a-f]{40}", arguments.engine_commit):
        raise RuntimeError("Managed session and exact compiled engine commit required")
    packet, cases = reference(arguments.reference_archive)
    build = json.loads(arguments.build_record.read_text())
    if (build["engine_commit"] != arguments.engine_commit or build.get("source_unchanged") is not True
            or build.get("actual_build_exit") != 0 or digest(arguments.runner) != build["executable_sha256"]):
        raise RuntimeError("Exact current compiler executable binding differs")
    output = Path(permanent) / "current-official-r-stats-dag"
    output.mkdir(mode=0o700)
    (output / "driver.py").write_bytes(Path(__file__).read_bytes())
    source = output / "source"
    shutil.copytree(ROOT / "research-adapters/cachexia-r-stats", source)
    if digest(source / "scripts/statistics.R") != METHOD_SHA:
        raise RuntimeError("Current guarded method differs from independent reference")
    manifest = tomllib.loads((source / "manifest.toml").read_text())
    by_kind = {node["kind"]: node for node in manifest["nodes"]}
    if set(by_kind) != set(METHODS.values()):
        raise RuntimeError("Actual complete official factory set differs")
    runner = Path(os.environ["TMPDIR"]) / "official_r_stats_dag"
    shutil.copyfile(arguments.runner, runner)
    runner.chmod(0o700)
    if digest(runner) != build["executable_sha256"]:
        raise RuntimeError("Temporary executable differs")
    records = []
    with (output / "readback.tsv").open("x") as handle:
        writer = csv.DictWriter(handle, fieldnames=["actual", "reference", "input"], delimiter="\t")
        writer.writeheader()
        for case in cases:
            work = output / case["id"]
            work.mkdir()
            old = packet / "cases" / case["id"]
            for name in ["input0.tsv", "input1.tsv"]:
                shutil.copyfile(old / name, work / name)
            negative = case["negative"] == "true"
            expected = [] if negative else table(old / "outputs/statistics.tsv")
            message = dict((row["key"], row["value"]) for row in table(old / "outputs/audit.tsv")).get("message") if negative else None
            job = make_job(work, source, case, [row["test_id"] for row in expected])
            (work / "job.json").write_text(json.dumps(job, indent=2) + "\n")
            with (work / "dag.stdout").open("wb") as stdout, (work / "dag.stderr").open("wb") as stderr:
                executed = subprocess.run([str(runner), str(work / "job.json")], stdout=stdout, stderr=stderr, timeout=300)
            if executed.returncode:
                raise RuntimeError("Current engine CLI failed; never substitute an old executable")
            report = json.loads((work / "dag-report.json").read_text())
            record = check_report(work, by_kind[METHODS[case["operation"]]], case, report, arguments.engine_commit, message)
            if not negative:
                compare_rows(table(work / "materialized.tsv"), expected, case["operation"])
                reference_path = work / "independent-reference.RDS"
                shutil.copyfile(old / "independent-reference.RDS", reference_path)
                writer.writerow(dict(actual=record["output_paths"][2].replace(str(output), "/work", 1),
                                     reference=str(reference_path).replace(str(output), "/work", 1),
                                     input=str(work / "input0.tsv").replace(str(output), "/work", 1)))
            records.append(record)
            (output / "cases-completed.json").write_text(json.dumps(records, indent=2) + "\n")
    (output / "complete-readback.R").write_text(R_READBACK)
    command = ["podman", "run", "--rm", "--pull=never", "--network=none", "--read-only", "--memory=1g",
               "--userns=keep-id", f"--user={os.getuid()}:{os.getgid()}", "--tmpfs=/tmp:rw,size=64m",
               "-v", f"{output}:/work:rw", "--entrypoint=Rscript", manifest["image"]["reference"],
               "--vanilla", "/work/complete-readback.R"]
    with (output / "readback.stdout").open("wb") as stdout, (output / "readback.stderr").open("wb") as stderr:
        reread = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=300)
    if reread.returncode or len(records) != 164:
        raise RuntimeError("Complete current-DAG independent RDS readback failed")
    report = dict(engine_commit=arguments.engine_commit, executable_sha256=build["executable_sha256"],
                  plugin_manifest_sha256=digest(source / "manifest.toml"), method_sha256=METHOD_SHA,
                  positive_DAGs=sum(not record["negative"] for record in records),
                  expected_refused_DAGs=sum(record["negative"] for record in records),
                  nodes_per_DAG=8, edges_per_DAG=7, typed_null_and_literal_identity_readback=True,
                  reference_recomputed=False, current_daemon_verified=False, source_hashes_not_forged=True,
                  formal_authorized=False, new_whole_node_certificates=0, g0_granted=False)
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
