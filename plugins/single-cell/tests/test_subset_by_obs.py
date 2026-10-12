"""Whole-container author slicing comparison and lexical selection counterexamples."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import anndata as ad
import h5py
import numpy as np
import pandas as pd
from scipy import sparse

from qc_compare import compare_value, digest


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
    data.raw = ad.AnnData(sparse.csr_matrix(np.arange(42, dtype=np.float32).reshape(6, 7)),
                         obs=obs.copy(), var=pd.DataFrame(index=[f"raw{index}" for index in range(7)]))
    return data


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
    with h5py.File(directory / "output.h5ad") as actual, h5py.File(directory / "fresh-author.h5ad") as reference:
        names, expected_names = [], []
        actual.visit(names.append)
        reference.visit(expected_names.append)
        assert names == expected_names
        for name in ["/", *names]:
            assert set(actual[name].attrs) == set(reference[name].attrs)
            for key in reference[name].attrs:
                np.testing.assert_array_equal(actual[name].attrs[key], reference[name].attrs[key])
            if isinstance(reference[name], h5py.Dataset):
                assert actual[name].dtype == reference[name].dtype
                if reference[name].dtype.kind in "fc":
                    np.testing.assert_allclose(actual[name][()], reference[name][()], atol=1e-12, rtol=0, equal_nan=True)
                else:
                    np.testing.assert_array_equal(actual[name][()], reference[name][()])
    settings = json.loads((directory / "request.json").read_text())
    report = json.loads((directory / "report.json").read_text())
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
    return {"whole_container_checks": int(checked), "selected_cell_ids": report["selected_cell_ids"], "G0": False}


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


def main():
    root = Path(sys.argv[1])
    root.mkdir()
    mode = sys.argv[2]
    records = {"original": original_failures, "positive": positives, "boundary": boundaries}[mode](root)
    (root / "SUMMARY.json").write_text(json.dumps({"mode": mode, "cases": len(records), "records": records,
                                                  "whole_current_engine": False, "resident_daemon": False, "G0": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
