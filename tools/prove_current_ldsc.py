"""Replay sealed author cases through an explicit synthetic-panel LDSC DAG."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prove_ldsc_entrypoints import check_author_failure, check_positive_log, normalize_log

ROOT = Path(__file__).resolve().parents[1]
REFERENCES = {
    "inference": ("d75e5074142c4003b63c55cccb0472ff", "0c6341b5e372542a25d4e4f27bdd7038f9b481284ed06e2f4883f9b9dbc1fe4f", "ldsc-canonical-published-entrypoints"),
    "munge": ("f59bb9f484d840c7a1560b91e29bc5b5", "ca9fb84b75c6d0da2bac659cf53f698d8119ae19dfcef1e095fa30dd5074f620", "ldsc-actual-declared-munge-ports"),
}
PANEL_IDS = {"ref_ld": "autonomics-technical/ldsc-synthetic-ref", "w_ld": "autonomics-technical/ldsc-synthetic-weight"}
TABLE_COLUMNS = ["p1", "p2", "rg", "se", "z", "p", "h2_obs", "h2_obs_se", "h2_int", "h2_int_se", "gcov_int", "gcov_int_se"]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def reference(archives, name):
    identity, expected, packet = REFERENCES[name]
    artifacts = archives / identity / "artifacts"
    if digest(artifacts / "MANIFEST.json") != expected:
        raise RuntimeError("Exact sealed independent author archive required")
    manifest = json.loads((artifacts / "MANIFEST.json").read_text())
    actual = {path.relative_to(artifacts).as_posix() for path in artifacts.rglob("*") if path.is_file() and path.name != "MANIFEST.json"}
    if actual != set(manifest["files"]):
        raise RuntimeError("Independent archive membership differs")
    for name, record in manifest["files"].items():
        path = artifacts / name
        if path.is_symlink() or path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
            raise RuntimeError("Independent reference content differs")
    return artifacts / "permanent" / packet


def normalize_engine_log(text, substitutions):
    rows = normalize_log(text, substitutions).splitlines()
    in_summary = False
    result = []
    for row in rows:
        if row == "Summary of Genetic Correlation Results":
            in_summary = True
        fields = row.split()
        if in_summary and (fields == TABLE_COLUMNS or fields[:2] == ["<INPUT0>", "<INPUT1>"]):
            if len(fields) != len(TABLE_COLUMNS):
                raise RuntimeError("Complete twelve-column author rg summary required")
            row = " ".join(fields)
        result.append(row)
    return "\n".join(result)


def panels(work, original):
    records = []
    hashes = {}
    for binding, identity in PANEL_IDS.items():
        destination = work / "synthetic-panels" / binding
        shutil.copytree(original / binding, destination)
        files = [dict(path=path.relative_to(destination).as_posix(), size=path.stat().st_size, sha256="sha256:"+digest(path))
                 for path in sorted(destination.rglob("*")) if path.is_file()]
        content_digest = "sha256:"+hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        manifest = dict(schema_version=1, id=identity, version="synthetic-technical-v1", digest=content_digest, files=files)
        write(destination / "manifest.json", manifest)
        prefix = "/synthetic-panels/"+binding
        hashes[prefix] = digest(destination / "manifest.json")
        records.append(dict(ident=identity, desc="SYNTHETIC TECHNICAL FIXTURE; NOT A RESEARCH PANEL", vpath=prefix, source=prefix, digest=content_digest))
    return records, hashes


def check_ports(work, definition, analysis, scratch):
    assignments = analysis["port_assignments"]
    if set(assignments) != {str(index) for index in range(len(definition["ports"]["outputs"]))}:
        raise RuntimeError("Complete actual declared output inventory required")
    result = []
    for index, port in enumerate(definition["ports"]["outputs"]):
        value = assignments[str(index)]
        live = Path(value["path"])
        published = list((work / definition["artifact_prefix"].removeprefix("/")).glob("*/"+port["path"]))
        if (live.is_symlink() or not live.resolve().is_relative_to(scratch) or len(published) != 1
                or published[0].is_symlink() or live.name != port["path"] or not live.stat().st_size
                or value["format"] != port["format"] or value["fingerprint"]["size"] != live.stat().st_size
                or digest(live) != digest(published[0])):
            raise RuntimeError("Owned live output and actual published port differ")
        content_hash = value["fingerprint"].get("content_hash")
        if content_hash is not None and content_hash.removeprefix("sha256:") != digest(live):
            raise RuntimeError("Declared output content hash differs")
        result.append(published[0])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner", required=True, type=Path)
    parser.add_argument("--build-record", required=True, type=Path)
    parser.add_argument("--archives", required=True, type=Path)
    arguments = parser.parse_args()
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Managed validation required")
    build = json.loads(arguments.build_record.read_text())
    if build["actual_build_exit"] != 0 or digest(arguments.runner) != build["executable_sha256"]:
        raise RuntimeError("Exact successful current compiler executable required")
    inference = reference(arguments.archives, "inference")
    munging = reference(arguments.archives, "munge")
    output = Path(permanent) / "current-ldsc-dag"
    output.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__), output / "driver.py")
    shutil.copyfile(arguments.build_record, output / "build-record.json")
    family = output / "source"
    family.mkdir()
    shutil.copyfile(ROOT / "plugins/ldsc/manifest.toml", family / "manifest.toml")
    (family / "scripts").mkdir()
    for method in ["h2", "rg", "munge"]:
        shutil.copyfile(ROOT / "plugins/ldsc/scripts" / (method+".sh"), family / "scripts" / (method+".sh"))
    manifest = tomllib.loads((family / "manifest.toml").read_text())
    inventory = json.loads((inference / "verification.json").read_text())["cases"]
    cases = [(record["case"], record["kind"], inference / record["case"]) for record in inventory]
    cases += [("munge-"+name, "ldsc_munge", munging / name) for name in ["plain", "gzip"]]
    results = []
    for name, kind, oracle_root in cases:
        work = output / name
        work.mkdir()
        bundles, panel_hashes = panels(work, inference / "synthetic-panels")
        method = kind.removeprefix("ldsc_")
        negative = "invalid-allele" in name
        inputs = ([oracle_root / ("original GWAS.tsv.gz" if name.endswith("gzip") else "original GWAS.tsv")]
                  if method == "munge" else sorted(oracle_root.glob("input-*")))
        spec = {}
        if method == "munge":
            spec = dict(snp="original_variant", n_col="original_sample_size", a1="original_effect_allele", a2="original_other_allele",
                        p="original_P", frq="original_MAF", info="original_INFO", signed_sumstats="original_signed_Z,0", n_min=5000)
        else:
            spec["n_blocks"] = 200 if name.endswith("gzip") else 20
            if name == "h2-constrained":
                spec.update(intercept_h2=1.0, chisq_max=100)
            if name == "rg-gzip":
                spec["chisq_max"] = 100
        nodes = []
        edges = []
        substitutions = [("/work/.autonomics/ldsc_"+method, "<OUTPUT>"), ("/work/direct_cli", "<OUTPUT>")]
        for index, path in enumerate(inputs):
            destination = work / path.name
            shutil.copyfile(path, destination)
            nodes.append(dict(id="input"+str(index), kind="file_reference", spec=dict(path="vfs:///"+path.name, format="tsv")))
            edges.append(dict(from_port=0, to_port=index, **{"from": "input"+str(index), "to": "analysis"}))
            compressed = path.name.endswith(".gz")
            actual_path = f"/work/.autonomics/input-{index}.tsv" if compressed else f"/work/.autonomics/inputs/input-{index}.tsv"
            direct_path = f"/work/.reference_/input-{index}.tsv" if compressed else f"/work/other-{index}.tsv"
            substitutions.extend([(actual_path, f"<INPUT{index}>"), (direct_path, f"<INPUT{index}>")])
        nodes.append(dict(id="analysis", kind=kind, spec=spec))
        job = dict(scope="SYNTHETIC_LDSC_DAG_NOT_G0", run_root=str(work), plugin_manifest=str(family / "manifest.toml"),
                   plugin_manifest_sha256=digest(family / "manifest.toml"), script_sha256={"scripts/"+path.name: digest(path) for path in (family / "scripts").iterdir()},
                   bundles=bundles, panel_manifest_sha256=panel_hashes, nodes=nodes, edges=edges)
        write(work / "job.json", job)
        with (work / "runner.stdout").open("wb") as stdout, (work / "runner.stderr").open("wb") as stderr:
            process = subprocess.run([str(arguments.runner), str(work / "job.json")], stdout=stdout, stderr=stderr, timeout=300)
        if process.returncode:
            raise RuntimeError("Current engine runner failed; no historical substitute: "+name)
        report = json.loads((work / "dag-report.json").read_text())
        if (report["engine_source_revision"] != build["engine_commit"] or report["scope"] != job["scope"]
                or report["input_hashing"] != "ContentRequired" or report["max_concurrency"] != 1
                or report["incremental"] is not False or report["g0_granted"] is not False
                or report["original_manifest_sha256"] != job["plugin_manifest_sha256"]
                or report["panel_bindings_are_explicit_synthetic_overrides"] is not True):
            raise RuntimeError("Actual engine identity or synthetic discipline differs")
        first = report["first_run"]
        if {row["id"] for row in first["nodes"]} != {node["id"] for node in nodes}:
            raise RuntimeError("Actual complete DAG node inventory differs")
        analysis = next(row for row in first["nodes"] if row["id"] == "analysis")
        expected_image = manifest["image"]["reference"]
        if analysis["execution"]["image"] != expected_image:
            raise RuntimeError("Actual DAG dispatched a different image")
        execution_evidence = work / "execution-evidence"
        execution_evidence.mkdir()
        for label in ["stdout_log", "stderr_log", "task_manifest"]:
            source = Path(analysis["execution"][label]["path"])
            if source.is_symlink() or not source.is_file():
                raise RuntimeError("Actual execution evidence missing")
            destination = execution_evidence / source.name
            shutil.copyfile(source, destination)
            if digest(source) != digest(destination):
                raise RuntimeError("Execution evidence preservation differs")
        scratch = Path(os.environ["TMPDIR"]) / "official-ldsc-container-workspaces" / name
        definition = next(row for row in manifest["nodes"] if row["kind"] == kind)
        if negative:
            if not first["errors"] or analysis["status"] != "failed" or list((work / "artifacts").rglob("ldsc_rg.log")):
                raise RuntimeError("Real author failure became a successful published result")
            diagnostics = [path for path in scratch.rglob("ldsc_rg.log") if path.parent.name != ".autonomics"]
            if len(diagnostics) != 1 or diagnostics[0].is_symlink():
                raise RuntimeError("Unique actual owned failed log required")
            check_author_failure(diagnostics[0].read_text(), (oracle_root / "direct_cli.log").read_text(),
                                 (oracle_root / "direct.stderr").read_text(), analysis["execution"]["exit_code"], 1)
            shutil.copyfile(diagnostics[0], work / "preserved-failure.log")
        else:
            if first["errors"] or any(row["status"] != "success" for row in first["nodes"]):
                raise RuntimeError("Positive actual DAG failed: "+name)
            ports = check_ports(work, definition, analysis, scratch)
            if method == "munge":
                with gzip.open(ports[0], "rb") as stream:
                    actual = stream.read()
                with gzip.open(oracle_root / "direct.sumstats.gz", "rb") as stream:
                    expected = stream.read()
                if actual != expected:
                    raise RuntimeError("Complete official munged rows differ")
            else:
                actual = ports[0].read_text()
                expected = (oracle_root / "direct_cli.log").read_text() or (oracle_root / "direct.stdout").read_text()
                mode = "nonpositive_h2" if name == "rg-nonpositive-h2" else "observed"
                check_positive_log(actual, actual, [], method, mode)
                if normalize_engine_log(actual, substitutions) != normalize_engine_log(expected, substitutions):
                    raise RuntimeError("Complete materialized author inference output differs: "+name)
        results.append(dict(case=name, kind=kind, nodes=len(nodes), edges=len(edges), outcome="AUTHOR_FAILURE_PRESERVED" if negative else "FULL_AUTHOR_OUTPUT_MATCHED",
                            synthetic_panel_bindings=True, published_ports=0 if negative else len(ports)))
        (output / "completed-cases.json").write_text(json.dumps(results, indent=2)+"\n")
    write(output / "verification.json", dict(status="CURRENT_CANONICAL_LDSC_DAG_PROVEN_SYNTHETIC_SCOPED", engine_commit=build["engine_commit"],
          executable_sha256=build["executable_sha256"], cases=results, source_manifest_sha256=digest(family / "manifest.toml"),
          independent_reference_recomputed=False, actual_research_panels_qualified=False, daemon_deployed=False, formal_authorized=False, g0_granted=False))
    print(json.dumps(dict(cases=len(results), positive=sum(row["outcome"]=="FULL_AUTHOR_OUTPUT_MATCHED" for row in results), g0_granted=False)))


if __name__ == "__main__":
    main()
