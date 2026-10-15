"""Whole-container author slicing comparison and lexical selection counterexamples."""

import importlib.util
import importlib.metadata
import ast
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
from unittest.mock import patch

import anndata as ad
import h5py
import numpy as np
import pandas as pd
from scipy import sparse

from qc_compare import assert_array_contract, assert_hdf5_object_contract, compare_value, digest


SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("subset_node", SOURCE / "scripts/subset_by_obs.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture(form="dense"):
    values = np.arange(30, dtype=np.float64).reshape(6, 5)
    if form in ["csr", "csc"]:
        values = getattr(sparse, form + "_matrix")(values)
    obs = pd.DataFrame({"donor": pd.Categorical(["d1", "d1", "d2", "d2", "d3", "d3"]),
                        "cell_id": ["ignored"] * 6, "number": np.arange(6)},
                       index=["001", "1", "α", "四", "cell5", "cell6"])
    data = ad.AnnData(values, obs=obs, var=pd.DataFrame({"code": np.arange(5)}, index=[f"g{index}" for index in range(5)]))
    data.layers["counts"] = sparse.csr_matrix(np.arange(30, dtype=np.int32).reshape(6, 5))
    data.obsm["spatial"] = np.arange(12, dtype=float).reshape(6, 2)
    data.varm["weights"] = np.arange(10, dtype=float).reshape(5, 2)
    data.obsp["graph"] = sparse.csr_matrix(np.arange(36, dtype=float).reshape(6, 6))
    data.varp["graph"] = sparse.csc_matrix(np.arange(25, dtype=float).reshape(5, 5))
    data.uns["nested"] = {"key": np.array([1, 2, 3]), "description": "unchanged"}
    raw = ad.AnnData(sparse.csr_matrix(np.arange(42, dtype=np.float32).reshape(6, 7)),
                    obs=obs.copy(), var=pd.DataFrame(index=[f"raw{index}" for index in range(7)]))
    raw.varm["raw_weights"] = np.arange(14, dtype=np.float64).reshape(7, 2)
    data.raw = raw
    return data


def strict_report_json(text):
    def reject_constant(value):
        raise ValueError(f"non-standard report number: {value}")

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate report key: {key}")
            result[key] = value
        return result

    return json.loads(text, parse_constant=reject_constant, object_pairs_hook=unique_object)


def validate_subset_report(report, settings, cell_ids, obs_values, gene_count, output_name,
                           output_bytes, output_sha256, input_sha256, selection_sha256,
                           prior_params, packages):
    requested = settings["requested"]
    join_column = settings["join_column"]
    selected = [index for index, value in enumerate(obs_values) if value in requested]
    expected = {"schema_version": "2.0", "operation": "subset_by_obs", "join_column": join_column,
        "selection_semantics": "obs_names" if join_column == "cell_id" else "obs_group_membership",
        "input_cells": len(cell_ids), "output_cells": len(selected), "input_genes": gene_count,
        "output_genes": gene_count, "requested_unique_cells": len(requested),
        "requested_unique_values": len(requested), "matched_unique_values": len(requested),
        "missing_cells": 0, "missing_values": [], "requested_values": requested,
        "matched_cells_per_value": {value: obs_values.count(value) for value in requested},
        "selection_order": "input_H5AD_observation_order_not_request_order",
        "selected_cell_ids": [cell_ids[index] for index in selected],
        "cell_ledger": [{"input_index": index, "cell_id": cell_id, "join_value": obs_values[index],
                         "retained": index in selected} for index, cell_id in enumerate(cell_ids)],
        "preexisting_subset_params_overwritten": prior_params,
        "preexisting_derived_artifacts_recomputed": False,
        "matrix_policy": "slice only; no normalization, mapping, QC, or scale selection",
        "memory_policy": "load whole AnnData; full-scale memory acceptance not established",
        "donor_eligibility": "NOT_VERIFIED", "scientific_release": "NOT_GRANTED", "G0": False,
        "packages": packages, "input_sha256": input_sha256, "selection_sha256": selection_sha256,
        "outputs": [{"port": 0, "name": output_name, "sha256": output_sha256, "bytes": output_bytes}],
        "report_hash_policy": "port_1_hash_recorded_externally_not_recursively"}
    assert isinstance(report, dict) and set(report) == set(expected) | {"warnings"}
    assert isinstance(report["warnings"], list) and all(isinstance(value, str) for value in report["warnings"])
    for field, value in expected.items():
        assert report[field] == value, field
    for field in ["input_cells", "output_cells", "input_genes", "output_genes", "requested_unique_cells",
                  "requested_unique_values", "matched_unique_values", "missing_cells"]:
        assert type(report[field]) is int
    assert all(type(value) is int for value in report["matched_cells_per_value"].values())
    assert type(report["outputs"][0]["port"]) is int and type(report["outputs"][0]["bytes"]) is int
    assert report["preexisting_subset_params_overwritten"] is prior_params
    assert report["preexisting_derived_artifacts_recomputed"] is False and report["G0"] is False
    for row in report["cell_ledger"]:
        assert type(row["input_index"]) is int and type(row["retained"]) is bool
    return len(expected["cell_ledger"])


def compare(directory):
    produced = ad.read_h5ad(directory / "output.h5ad")
    expected = ad.read_h5ad(directory / "fresh-author.h5ad")
    assert produced.shape == expected.shape
    checked = compare_value(produced.X, expected.X) if expected.X is not None else 0
    if expected.X is None:
        assert produced.X is None
    for slot in ["obs", "var"]:
        checked += compare_value(getattr(produced, slot), getattr(expected, slot))
    for slot in ["layers", "obsm", "varm", "obsp", "varp", "uns"]:
        checked += compare_value(dict(getattr(produced, slot)), dict(getattr(expected, slot)))
    assert (produced.raw is None) == (expected.raw is None)
    if expected.raw is not None:
        checked += compare_value(produced.raw.X, expected.raw.X)
        checked += compare_value(produced.raw.var, expected.raw.var)
        checked += compare_value(dict(produced.raw.varm), dict(expected.raw.varm))
    datasets = 0
    with h5py.File(directory / "output.h5ad") as actual, h5py.File(directory / "fresh-author.h5ad") as reference:
        names, expected_names = [], []
        actual.visit(names.append)
        reference.visit(expected_names.append)
        assert names == expected_names
        for name in ["/", *names]:
            assert_hdf5_object_contract(actual[name], reference[name])
            assert set(actual[name].attrs) == set(reference[name].attrs)
            for key in reference[name].attrs:
                actual_attribute, expected_attribute = assert_array_contract(actual[name].attrs[key], reference[name].attrs[key])
                np.testing.assert_array_equal(actual_attribute, expected_attribute)
            if isinstance(reference[name], h5py.Dataset):
                datasets += 1
                assert actual[name].dtype == reference[name].dtype
                if reference[name].dtype.kind in "fc":
                    np.testing.assert_allclose(actual[name][()], reference[name][()], atol=1e-12, rtol=0, equal_nan=True)
                else:
                    np.testing.assert_array_equal(actual[name][()], reference[name][()])
    settings = json.loads((directory / "request.json").read_text())
    report = strict_report_json((directory / "report.json").read_text())
    original = ad.read_h5ad(directory / "input.h5ad")
    assert report["requested_values"] == settings["requested"]
    observed = list(original.obs_names) if settings["join_column"] == "cell_id" else list(original.obs[settings["join_column"]])
    selected_indices = [index for index, value in enumerate(observed) if value in settings["requested"]]
    assert report["selected_cell_ids"] == [str(original.obs_names[index]) for index in selected_indices]
    assert report["output_cells"] == len(selected_indices) and report["input_cells"] == original.n_obs
    assert report["matched_cells_per_value"] == {value: observed.count(value) for value in settings["requested"]}
    assert report["missing_cells"] == 0 and report["missing_values"] == []
    assert report["input_sha256"] == digest(directory / "input.h5ad")
    assert report["selection_sha256"] == digest(directory / "selection.parquet")
    assert report["outputs"][0]["sha256"] == digest(directory / "output.h5ad")
    assert report["scientific_release"] == "NOT_GRANTED" and report["G0"] is False
    assert [item["input_index"] for item in report["cell_ledger"] if item["retained"]] == selected_indices
    ledger_rows = validate_subset_report(report, settings, list(original.obs_names), observed, original.n_vars,
        "output.h5ad", (directory / "output.h5ad").stat().st_size, digest(directory / "output.h5ad"),
        digest(directory / "input.h5ad"), digest(directory / "selection.parquet"),
        "subset_params" in original.uns,
        {name: importlib.metadata.version(name) for name in ["anndata", "numpy", "pandas", "pyarrow", "h5py"]})
    assert checked > 0 and datasets > 0
    return {"whole_container_checks": int(checked), "hdf5_datasets_checked": datasets,
            "complete_cell_ledger_rows_checked": ledger_rows, "full_report_checked": True,
            "selected_cell_ids": report["selected_cell_ids"], "G0": False}


def execute(directory, original=False, overrides=None):
    settings = json.loads((directory / "request.json").read_text())
    variables = dict(os.environ, AUTONOMICS_INPUT0=str(directory / "input.h5ad"),
                     AUTONOMICS_INPUT1=str(directory / "selection.parquet"),
                     AUTONOMICS_OUTPUT0=str(directory / "output.h5ad"),
                     AUTONOMICS_OUTPUT1=str(directory / "report.json"),
                     SC_P_STR_JOIN_COLUMN=settings["join_column"], AUTONOMICS_SINGLE_CELL_WORKFLOW="subset_by_obs",
                     AUTONOMICS_SINGLE_CELL_PARAMS=str(directory / "params.json"))
    variables.update(overrides or {})
    if original:
        (directory / "params.json").write_text(json.dumps({"join_column": settings["join_column"]}))
    script = str(SOURCE / "scripts/run_workflow.py") if original else str(SOURCE / "scripts/subset_by_obs.py")
    result = subprocess.run([sys.executable, script], env=variables, capture_output=True, timeout=120)
    (directory / "stdout.txt").write_bytes(result.stdout)
    (directory / "stderr.txt").write_bytes(result.stderr)
    (directory / "execution.json").write_text(json.dumps({"exit": result.returncode, "script": script}, indent=2) + "\n")
    return result


def prepare(root, name, data, requested, join_column="cell_id"):
    directory = root / name
    directory.mkdir()
    data.write_h5ad(directory / "input.h5ad")
    pd.DataFrame({join_column: requested}).to_parquet(directory / "selection.parquet", index=False)
    (directory / "request.json").write_text(json.dumps({"requested": requested, "join_column": join_column}))
    return directory


def original_failures(root):
    records = []
    for name, requested, column in [("unknown-partial", ["001", "absent"], "cell_id"),
                                    ("duplicate-request", ["001", "001"], "cell_id"),
                                    ("negative-missing-group", ["d1"], "donor")]:
        directory = prepare(root, name, fixture(), requested, column)
        result = execute(directory, original=True)
        assert result.returncode == 0, result.stderr.decode()
        report = json.loads((directory / "report.json").read_text())
        if name == "unknown-partial":
            assert report["missing_cells"] == 1 and report["output_cells"] == 1
        elif name == "duplicate-request":
            assert report["requested_unique_cells"] == 1
        else:
            assert report["missing_cells"] == -1
        records.append({"case": name, "actual_original_exit": 0, "report": report, "G0": False})
    return records


def positives(root):
    cases = []
    for form in ["dense", "csr", "csc"]:
        cases.append((form, fixture(form), ["四", "001"], "cell_id"))
    cases += [("group-many-to-one", fixture(), ["d3", "d1"], "donor"),
              ("all-cells", fixture(), list(fixture().obs_names)[::-1], "cell_id"),
              ("lexical-numeric", fixture(), ["1"], "cell_id"),
              ("single-cell", fixture(), ["α"], "cell_id")]
    stale = fixture()
    stale.uns["subset_params"] = {"join_column": "old", "requested_cells": 999}
    cases.append(("prior-params", stale, ["α", "cell6"], "cell_id"))
    no_raw = fixture()
    no_raw.raw = None
    cases.append(("no-raw", no_raw, ["四"], "cell_id"))
    no_matrix = fixture()
    no_matrix.X = None
    cases.append(("no-X", no_matrix, ["001", "cell5"], "cell_id"))
    nonfinite = fixture()
    nonfinite.X[0, 0], nonfinite.X[0, 1], nonfinite.X[4, 3] = np.nan, np.inf, -np.inf
    cases.append(("nonfinite-X", nonfinite, ["001", "cell5"], "cell_id"))
    records = []
    for name, data, requested, column in cases:
        directory = prepare(root, name, data, requested, column)
        source = ad.read_h5ad(directory / "input.h5ad")
        values = source.obs_names if column == "cell_id" else source.obs[column]
        expected = source[pd.Index(values).isin(requested)].copy()
        expected.uns["subset_params"] = {"join_column": column, "requested_cells": len(requested)}
        expected.write_h5ad(directory / "fresh-author.h5ad", compression="lzf")
        result = execute(directory)
        assert result.returncode == 0, result.stderr.decode()
        records.append({"case": name, **compare(directory)})
        print(name, "PASS", flush=True)
    return records


def boundaries(root):
    cases = [("unknown", fixture(), ["absent"], "cell_id", "unknown identifiers"),
             ("unknown-partial", fixture(), ["001", "absent"], "cell_id", "unknown identifiers"),
             ("unknown-group", fixture(), ["d1", "absent"], "donor", "unknown identifiers"),
             ("duplicate-request", fixture(), ["001", "001"], "cell_id", "unique identifiers"),
             ("duplicate-group", fixture(), ["d1", "d1"], "donor", "unique identifiers"),
             ("empty-request", fixture(), [], "cell_id", "at least one"),
             ("null-request", fixture(), [None], "cell_id", "lexical strings"),
             ("integer-request", fixture(), [1], "cell_id", "lexical strings"),
             ("empty-string", fixture(), [""], "cell_id", "lexical strings"),
             ("tab-request", fixture(), ["bad\tvalue"], "cell_id", "lexical strings"),
             ("numeric-group", fixture(), ["1"], "number", "lexical strings"),
             ("absent-column", fixture(), ["x"], "missing", "obs has no")]
    duplicated = fixture()
    duplicated.obs_names = ["same"] * 6
    cases.append(("duplicate-obs", duplicated, ["same"], "cell_id", "unique identifiers"))
    duplicated_vars = fixture()
    duplicated_vars.var_names = ["same"] * 5
    cases.append(("duplicate-var", duplicated_vars, ["001"], "cell_id", "unique identifiers"))
    bad_group = fixture()
    bad_group.obs["bad"] = ["x", "x", None, "y", "z", "z"]
    cases.append(("missing-group", bad_group, ["x"], "bad", "lexical strings"))
    cases += [("zero-cells", fixture()[:0].copy(), ["001"], "cell_id", "nonempty"),
              ("zero-genes", fixture()[:, :0].copy(), ["001"], "cell_id", "nonempty")]
    records = []
    for name, data, requested, column, fragment in cases:
        directory = prepare(root, name, data, requested, column)
        result = execute(directory)
        assert result.returncode == 2 and fragment in result.stderr.decode(), result.stderr.decode()
        assert not (directory / "output.h5ad").exists() and not (directory / "report.json").exists()
        records.append({"case": name, "specific_refusal": fragment, "exit": result.returncode})
        print(name, "REFUSED", flush=True)
    extra = [("missing-selection-column", "selection Parquet has no"),
             ("corrupt-selection", "Parquet"), ("existing-h5ad", "refusing to overwrite"),
             ("existing-report", "refusing to overwrite"), ("aliased-outputs", "paths must be distinct"),
             ("input-overwrite", "paths must be distinct")]
    for name, fragment in extra:
        directory = prepare(root, name, fixture(), ["001"])
        overrides = {}
        sentinel = None
        if name == "missing-selection-column":
            pd.DataFrame({"wrong": ["001"]}).to_parquet(directory / "selection.parquet", index=False)
        elif name == "corrupt-selection":
            (directory / "selection.parquet").write_bytes(b"not parquet")
        elif name in ["existing-h5ad", "existing-report"]:
            sentinel = directory / ("output.h5ad" if name == "existing-h5ad" else "report.json")
            sentinel.write_bytes(b"preserve existing sentinel")
        elif name == "aliased-outputs":
            overrides["AUTONOMICS_OUTPUT1"] = str(directory / "output.h5ad")
        elif name == "input-overwrite":
            overrides["AUTONOMICS_OUTPUT0"] = str(directory / "input.h5ad")
        before = digest(directory / "input.h5ad")
        result = execute(directory, overrides=overrides)
        assert result.returncode != 0 and fragment in result.stderr.decode(), result.stderr.decode()
        assert digest(directory / "input.h5ad") == before
        if sentinel:
            assert sentinel.read_bytes() == b"preserve existing sentinel"
        for filename in ["output.h5ad", "report.json"]:
            candidate = directory / filename
            if candidate != sentinel:
                assert not candidate.exists()
        records.append({"case": name, "specific_refusal": fragment, "exit": result.returncode})
    directory = root / "ordinary-second-link-failure"
    directory.mkdir()
    real_link = os.link
    calls = []

    def fail_second(source, destination):
        calls.append(str(destination))
        if len(calls) == 2:
            raise OSError("injected second link failure")
        return real_link(source, destination)

    with patch.object(module.os, "link", side_effect=fail_second):
        try:
            module.publish(fixture(), {}, [directory / "output.h5ad", directory / "report.json"])
        except OSError as error:
            assert "injected second link" in str(error)
        else:
            raise AssertionError("injected publication failure not observed")
    assert len(calls) == 2 and not list(directory.iterdir())
    records.append({"case": directory.name, "ordinary_rollback": True, "crash_atomicity_claimed": False})
    return records


def old_comparisons(directory):
    expected = {"qc_compare.py": "d2d30324793dc33b5e438be8269a8fe7f9021d54d637a88d3aa3dd8f78d1b109",
                "test_subset_by_obs.py": "c88766868a9c747ac1dd8b3308956603923dde877023af20e48a1a0e24cdcf81"}
    namespace = dict(ad=ad, np=np, pd=pd, sparse=sparse, h5py=h5py, json=json)
    for name, functions in [("qc_compare.py", {"digest", "compare_value"}),
                             ("test_subset_by_obs.py", {"compare"})]:
        path = directory / name
        assert path.is_file() and not path.is_symlink() and digest(path) == expected[name]
        tree = ast.parse(path.read_text())
        selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in functions]
        assert {node.name for node in selected} == functions
        fragment = ast.Module(body=selected, type_ignores=[])
        ast.fix_missing_locations(fragment)
        exec(compile(fragment, str(path), "exec"), namespace)
    namespace["hashlib"] = __import__("hashlib")
    return namespace["compare"], namespace["compare_value"], expected


def comparison_observation(compare_function, value):
    try:
        compare_function(value)
    except (AssertionError, ValueError) as error:
        return {"accepted": False, "refusal_type": type(error).__name__, "diagnostic": str(error)}
    return {"accepted": True, "refusal_type": None, "diagnostic": None}


def mutants(root, positive=None, baseline=Path("/source/baseline-tests")):
    positive = root.parent / "positive" if positive is None else positive
    original_compare, original_value, baseline_hashes = old_comparisons(baseline)
    source = positive / "dense"
    assert compare(source)["whole_container_checks"] > 0
    assert original_compare(source)["whole_container_checks"] > 0
    records = []
    for name in ["wrong-X", "missing-raw", "reordered-cells", "missing-obsp", "raw-varm", "missing-unselected-ledger",
                 "wrong-output-bytes", "extra-output-port", "false-donor-eligibility", "nonfinite-report"]:
        directory = root / name
        directory.mkdir()
        for filename in ["input.h5ad", "output.h5ad", "fresh-author.h5ad", "selection.parquet", "request.json", "report.json"]:
            shutil.copyfile(source / filename, directory / filename)
        report = strict_report_json((directory / "report.json").read_text())
        if name in {"wrong-X", "missing-raw", "reordered-cells", "missing-obsp", "raw-varm"}:
            data = ad.read_h5ad(directory / "output.h5ad")
            if name == "wrong-X":
                data.X[0, 0] += 1
            elif name == "missing-raw":
                data.raw = None
            elif name == "reordered-cells":
                data = data[::-1].copy()
            elif name == "missing-obsp":
                del data.obsp["graph"]
            else:
                data.raw.varm["raw_weights"][0, 0] += 1
            data.write_h5ad(directory / "output.h5ad", compression="lzf")
            report["outputs"][0]["sha256"] = digest(directory / "output.h5ad")
            report["outputs"][0]["bytes"] = (directory / "output.h5ad").stat().st_size
        elif name == "missing-unselected-ledger":
            report["cell_ledger"] = [row for row in report["cell_ledger"] if row["retained"]]
        elif name == "wrong-output-bytes":
            report["outputs"][0]["bytes"] += 1
        elif name == "extra-output-port":
            report["outputs"].append({"port": 1, "name": "report.json", "sha256": "0" * 64, "bytes": 1})
        elif name == "false-donor-eligibility":
            report["donor_eligibility"] = "VERIFIED"
        else:
            report["warnings"] = [float("nan")]
        (directory / "report.json").write_text(json.dumps(report, allow_nan=True) + "\n")
        old = comparison_observation(original_compare, directory)
        current = comparison_observation(compare, directory)
        assert current["accepted"] is False
        assert old["accepted"] is (name not in {"wrong-X", "missing-raw", "reordered-cells", "missing-obsp", "raw-varm"})
        records.append({"case": name, "comparison_scope": "WHOLE_CURRENT_FIXTURE_AND_REPORT",
                        "old_comparison": old, "current_comparison": current,
                        "baseline_source_sha256": baseline_hashes, "G0": False})
    for name, actual, expected in [
            ("shared-scalar-broadcast", np.array(1., dtype=np.float64), np.ones(2, dtype=np.float64)),
            ("shared-sparse-shape", sparse.csr_matrix(([1.], ([0], [0])), shape=(1, 3)),
             sparse.csr_matrix(([1.], ([0], [0])), shape=(1, 2)))]:
        old = comparison_observation(lambda value: original_value(*value), (actual, expected))
        current = comparison_observation(lambda value: compare_value(*value), (actual, expected))
        assert old["accepted"] is True and current["accepted"] is False
        records.append({"case": name, "comparison_scope": "SHARED_COMPARE_VALUE_ONLY",
                        "old_comparison": old, "current_comparison": current,
                        "old_whole_object_comparison_executed": False, "G0": False})
    assert len(records) == 12
    return records


def main():
    root = Path(sys.argv[1])
    root.mkdir()
    mode = sys.argv[2]
    records = {"original": original_failures, "positive": positives, "boundary": boundaries, "mutants": mutants}[mode](root)
    (root / "SUMMARY.json").write_text(json.dumps({"mode": mode, "cases": len(records), "records": records,
                                                  "whole_current_engine": False, "resident_daemon": False, "G0": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
