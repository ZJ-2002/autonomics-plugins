"""Preserved real-runner cases compared with separately installed official packages."""

import argparse
import csv
import gzip
import hashlib
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import anndata as ad
import h5py
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.io import mmwrite


ROOT = Path(__file__).resolve().parents[1]
BASE = np.array([[0, 0, 0, 0, 0, 0], [1, 0, 2, 0, 0, 0],
                 [3, 4, 0, 0, 0, 1], [1, 2, 3, 4, 0, 0],
                 [5, 2, 1, 4, 0, 0], [1, 1, 1, 1, 0, 0]], dtype=np.int64)


def digest(filename: Path) -> str:
    with filename.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def execute(command: list[str], directory: Path, label: str, environment: dict[str, str]) -> subprocess.CompletedProcess:
    started = time.monotonic()
    result = subprocess.run(command, env=environment, capture_output=True, timeout=120)
    (directory / (label + ".stdout.txt")).write_bytes(result.stdout)
    (directory / (label + ".stderr.txt")).write_bytes(result.stderr)
    (directory / (label + ".execution.json")).write_text(json.dumps({"command": command,
        "exit": result.returncode, "seconds": time.monotonic() - started, "G0": False}, indent=2) + "\n")
    return result


def fixture(directory: Path, request: dict) -> None:
    directory.mkdir(exist_ok=False)
    values = BASE.copy()
    if request.get("precision"):
        values[1, 0] = 16777217
    field = "real" if request.get("real") else "integer"
    if request.get("real"):
        values = values.astype(float) / 4
    mmwrite(directory / "matrix.mtx", sparse.coo_matrix(values.T), field=field, symmetry="general")
    barcodes = ["0001", "NA", "Inf", "炎症", "cell E", "cell-F"]
    (directory / "barcodes.tsv").write_text("\n".join(barcodes) + "\n")
    symbols = ["G0", "G1", "G2", "G3", "G4", "G5"]
    if request.get("duplicate_symbols"):
        symbols[:3] = ["G", "G", "G-1"]
    width = 2 if request.get("two_features") else 3
    features = [[f"000{index}", symbol, "Gene Expression" if index < 5 else "Antibody Capture"][:width]
                for index, symbol in enumerate(symbols)]
    with (directory / "features.tsv").open("w") as handle:
        csv.writer(handle, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE).writerows(features)
    rows = [[barcode, "donor A" if index % 2 == 0 else "NA", "" if index == 0 else "with, comma"]
            for index, barcode in enumerate(barcodes)]
    if request.get("reorder"):
        rows.reverse()
    with (directory / "metadata.tsv").open("w", newline="") as handle:
        csv.writer(handle, delimiter=request.get("delimiter", "\t"), lineterminator="\n").writerows(
            [["cell_id", "donor", "note"], *rows])
    if request.get("gzip"):
        with gzip.open(directory / "matrix.mtx.gz", "wb") as handle:
            handle.write((directory / "matrix.mtx").read_bytes())
        request["matrix_file"] = "matrix.mtx.gz"
    if request.get("duplicate_coordinates"):
        filename = directory / "matrix.mtx"
        lines = filename.read_text().splitlines()
        dimensions_index = next(index for index, line in enumerate(lines) if not line.startswith("%"))
        dimensions = lines[dimensions_index].split()
        dimensions[2] = str(int(dimensions[2]) + 1)
        lines[dimensions_index] = " ".join(dimensions)
        lines.append(lines[-1])
        filename.write_text("\n".join(lines) + "\n")
    (directory / "request.json").write_text(json.dumps(request, indent=2) + "\n")


def environment_for(directory: Path, request: dict) -> dict[str, str]:
    return dict(os.environ, AUTONOMICS_INPUT0=str(directory / request.get("matrix_file", "matrix.mtx")),
        AUTONOMICS_INPUT1=str(directory / "barcodes.tsv"), AUTONOMICS_INPUT2=str(directory / "features.tsv"),
        AUTONOMICS_INPUT3=str(directory / "metadata.tsv"), AUTONOMICS_OUTPUT0=str(directory / "report.json"),
        AUTONOMICS_OUTPUT1=str(directory / "output.h5ad"), AUTONOMICS_SINGLE_CELL_OPERATION=request["operation"],
        AUTONOMICS_SINGLE_CELL_MIN_GENES=str(request.get("min_genes", 0)),
        AUTONOMICS_SINGLE_CELL_MIN_CELLS=str(request.get("min_cells", 0)),
        AUTONOMICS_SINGLE_CELL_NORMALIZE_TOTAL=str(request.get("normalize_total", False)).lower(),
        AUTONOMICS_SINGLE_CELL_METADATA_SEP=request.get("metadata_separator", "auto"))


def compare(directory: Path) -> dict:
    result = ad.read_h5ad(directory / "output.h5ad")
    reference = ad.read_h5ad(directory / "fresh-author-reference.h5ad")
    pd.testing.assert_frame_equal(result.obs, reference.obs, check_exact=True)
    pd.testing.assert_frame_equal(result.var, reference.var, check_exact=True)
    finite_fields = 0
    matrices = [(result.X, reference.X), *[(result.layers[key], reference.layers[key]) for key in reference.layers]]
    for actual, expected in matrices:
        if expected is None:
            if actual is not None:
                raise AssertionError("Metadata-only reference acquired expression values")
            continue
        if actual.dtype != expected.dtype or type(actual) is not type(expected):
            raise AssertionError("Matrix dtype or sparse encoding differs")
        np.testing.assert_array_equal(actual.indptr, expected.indptr)
        np.testing.assert_array_equal(actual.indices, expected.indices)
        np.testing.assert_allclose(actual.data, expected.data, rtol=0, atol=1e-12)
        if not np.isfinite(actual.data).all():
            raise AssertionError("Unexpected nonfinite matrix")
        finite_fields += actual.data.size
    if result.uns != reference.uns or result.raw is not None or reference.raw is not None:
        raise AssertionError("AnnData uns/raw differs")
    for attribute in ["obsm", "varm", "obsp", "varp", "layers"]:
        if set(getattr(result, attribute)) != set(getattr(reference, attribute)):
            raise AssertionError("AnnData container keys differ: " + attribute)
    with h5py.File(directory / "output.h5ad") as actual, h5py.File(directory / "fresh-author-reference.h5ad") as expected:
        actual_keys = []
        expected_keys = []
        actual.visit(actual_keys.append)
        expected.visit(expected_keys.append)
        if actual_keys != expected_keys:
            raise AssertionError("H5AD storage object paths differ")
        for key in ["/", *actual_keys]:
            actual_attrs = dict(actual[key].attrs)
            expected_attrs = dict(expected[key].attrs)
            if set(actual_attrs) != set(expected_attrs):
                raise AssertionError("H5AD attribute keys differ")
            for attribute in actual_attrs:
                np.testing.assert_array_equal(actual_attrs[attribute], expected_attrs[attribute])
    report = json.loads((directory / "report.json").read_text())
    request = json.loads((directory / "request.json").read_text())
    if report["G0"] or report["scientific_release"] != "NOT_GRANTED" or report["schema_version"] != "2.0":
        raise AssertionError("Technical/scientific separation differs")
    if report["operation"] != request["operation"] or report["matrix"]["expression_loaded"] != (request["operation"] == "ingest"):
        raise AssertionError("Operation semantics differ")
    input_cells = (directory / "barcodes.tsv").read_text().splitlines()
    input_features = list(csv.reader((directory / "features.tsv").read_text().splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE))
    if len(report["cell_ledger"]) != len(input_cells) or len(report["feature_ledger"]) != len(input_features):
        raise AssertionError("Full input-axis ledger incomplete")
    for index, entry in enumerate(report["cell_ledger"]):
        if entry["input_index"] != index or entry["cell_barcode"] != input_cells[index] or entry["retained"] != (entry["cell_barcode"] in result.obs_names):
            raise AssertionError("Cell retention ledger differs")
    for index, entry in enumerate(report["feature_ledger"]):
        if entry["input_index"] != index or entry["gene_id"] != input_features[index][0] or entry["gene_symbol_original"] != input_features[index][1] or entry["retained"] != (entry["var_name"] in result.var_names):
            raise AssertionError("Feature retention ledger differs")
    for entry, filename in zip(report["inputs"], [request.get("matrix_file", "matrix.mtx"), "barcodes.tsv", "features.tsv", "metadata.tsv"], strict=True):
        if entry["sha256"] != digest(directory / filename):
            raise AssertionError("Input identity differs")
    outputs = report["outputs"]
    if len(outputs) != 1 or outputs[0]["port"] != 1 or outputs[0]["sha256"] != digest(directory / "output.h5ad"):
        raise AssertionError("H5AD output identity or self-hash policy differs")
    return {"finite_matrix_values": int(finite_fields), "full_frames_exact": True,
            "sparse_indices_and_storage_attributes_exact": True, "complete_axis_ledgers": True,
            "full_AnnData_container_keys": True, "absolute_tolerance": 1e-12, "relative_tolerance": 0,
            "output_sha256": digest(directory / "output.h5ad"), "report_sha256": digest(directory / "report.json"),
            "scientific_release": "NOT_GRANTED", "G0": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--reference-library", type=Path, required=True)
    parser.add_argument("--benchmark-case", type=Path)
    options = parser.parse_args()
    options.evidence.mkdir(exist_ok=False)
    cases = [{"name": f"ingest-g{genes}-c{cells}-n{int(normalize)}", "operation": "ingest",
              "min_genes": genes, "min_cells": cells, "normalize_total": normalize}
             for genes, cells, normalize in itertools.product([0, 1, 2, 3], [0, 1, 2], [False, True])]
    cases += [{"name": name, "operation": "inspect" if name.startswith("inspect") else "ingest", **changes}
              for name, changes in [
                  ("inspect-default", {}), ("inspect-comma", {"delimiter": ","}),
                  ("precision-16777217", {"precision": True}),
                  ("real-values", {"real": True, "normalize_total": True}),
                  ("gzip-input", {"gzip": True, "normalize_total": True}),
                  ("two-feature-columns", {"two_features": True}),
                  ("duplicate-symbols", {"duplicate_symbols": True}),
                  ("metadata-reordered", {"reorder": True}),
                  ("metadata-comma", {"delimiter": ",", "metadata_separator": "comma"}),
                  ("duplicate-coordinates", {"duplicate_coordinates": True})]]
    records = []
    if options.benchmark_case:
        cases.append({"name": "official-pbmc3k", "benchmark_case": True,
                      **json.loads((options.benchmark_case / "request.json").read_text())})
    for request in cases:
        directory = options.evidence / request["name"]
        if request.get("benchmark_case"):
            directory.mkdir()
            for filename in [request.get("matrix_file", "matrix.mtx"), "barcodes.tsv", "features.tsv", "metadata.tsv", "request.json"]:
                shutil.copyfile(options.benchmark_case / filename, directory / filename)
        else:
            fixture(directory, request)
        environment = environment_for(directory, request)
        author_environment = dict(environment, PYTHONPATH=str(options.reference_library))
        author = execute([sys.executable, str(ROOT / "tests/preprocess_reference.py"), str(directory)],
                         directory, "fresh-author", author_environment)
        runner = execute([sys.executable, "/opt/autonomics/preprocess.py"], directory, "baked-runner", environment)
        if author.returncode or runner.returncode:
            raise AssertionError("Reference or runner failed: " + author.stderr.decode() + runner.stderr.decode())
        checked = compare(directory)
        (directory / "CHECKS.json").write_text(json.dumps(checked, indent=2) + "\n")
        records.append({"case": request["name"], **checked})
        print(request["name"], "PASS", flush=True)
    (options.evidence / "SUMMARY.json").write_text(json.dumps({"cases": len(records), "records": records,
        "finite_matrix_values": sum(record["finite_matrix_values"] for record in records),
        "reference": "fresh separately installed author packages; shared frozen numeric runtime",
        "production_deployed": False, "G0": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
