import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import anndata as ad
import h5py
import numpy as np

from qc_compare import compare_value


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/dense_ingest.py"
VALUES = [[1, 0, 3], [0, 2, 4], [2, 0, 0], [0, 0, 0]]
CELLS = ["001", "NA", "cell,comma", "cell四"]
GENES = ["007", "NULL", "gene三"]


def compare_h5ad(reference_path, actual_path):
    expected = ad.read_h5ad(reference_path)
    actual = ad.read_h5ad(actual_path)
    assert actual.shape == expected.shape
    finite = compare_value(actual.X, expected.X) + compare_value(actual.obs, expected.obs) + compare_value(actual.var, expected.var)
    for name in ["layers", "obsm", "varm", "obsp", "varp", "uns"]:
        finite += compare_value(dict(getattr(actual, name)), dict(getattr(expected, name)))
    assert actual.raw is None and expected.raw is None
    with h5py.File(reference_path) as reference, h5py.File(actual_path) as produced:
        expected_names, actual_names = [], []
        reference.visit(expected_names.append)
        produced.visit(actual_names.append)
        assert expected_names == actual_names
        for name in [""] + expected_names:
            left, right = produced[name] if name else produced, reference[name] if name else reference
            assert type(left) == type(right) and set(left.attrs) == set(right.attrs)
            for key in right.attrs:
                np.testing.assert_array_equal(left.attrs[key], right.attrs[key])
            if isinstance(right, h5py.Dataset):
                assert left.shape == right.shape and left.dtype == right.dtype and left.compression == right.compression
                np.testing.assert_array_equal(left[()], right[()])
    return {"shape": list(actual.shape), "finite_values": int(finite), "whole_HDF5_exact": True}


def write_fixture(directory, options, matrix=None, cells=None, genes=None, compressed=False):
    matrix = VALUES if matrix is None else matrix
    cells = CELLS if cells is None else cells
    genes = GENES if genes is None else genes
    rows = matrix if options["orientation"] == "cells_by_genes" else list(map(list, zip(*matrix)))
    row_ids, column_ids = (cells, genes) if options["orientation"] == "cells_by_genes" else (genes, cells)
    path = directory / ("input.tsv.gz" if compressed else "input.tsv")
    opener = gzip.open if compressed else open
    with opener(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=options.get("write_delimiter", "\t"))
        if options.get("has_header", True):
            writer.writerow(["axis"] + column_ids)
        for name, row in zip(row_ids, rows):
            writer.writerow([name] + row)
    return path, matrix, cells, genes


def author_reference(directory, options, matrix, cells, genes):
    prefix = os.environ["SC_DENSE_REFERENCE_LIBRARY"]
    (directory / "oracle.json").write_text(json.dumps({"options": options, "matrix": matrix, "cells": cells, "genes": genes}) + "\n")
    result = subprocess.run([sys.executable, str(Path(__file__).with_name("dense_ingest_reference.py")), str(directory)],
        env=dict(os.environ, PYTHONPATH=prefix), capture_output=True)
    (directory / "fresh-author.stdout.txt").write_bytes(result.stdout)
    (directory / "fresh-author.stderr.txt").write_bytes(result.stderr)
    assert result.returncode == 0, result.stderr.decode()
    return ad.read_h5ad(directory / "fresh-author.h5ad")


def run(root, name, options, *, error=None, matrix=None, cells=None, genes=None,
        compressed=False, raw=None, mode=None, inject=False):
    directory = root / name
    directory.mkdir()
    source, matrix, cells, genes = write_fixture(directory, options, matrix, cells, genes, compressed)
    if raw is not None:
        source.write_text(raw)
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    output, report_path = directory / "output.h5ad", directory / "report.json"
    if mode == "sentinel":
        output.write_text("IMMUTABLE SENTINEL")
    elif mode == "dangling":
        output.symlink_to("absent.h5ad")
    elif mode == "alias":
        report_path = output
    elif mode == "input":
        output = source
    environment = dict(os.environ, AUTONOMICS_INPUT0=str(source), AUTONOMICS_OUTPUT0=str(output), AUTONOMICS_OUTPUT1=str(report_path),
        SC_P_STR_ORIENTATION=options["orientation"], SC_P_STR_DELIMITER=options.get("delimiter", "tab"),
        SC_P_BOOL_HAS_HEADER=str(options.get("has_header", True)).lower(),
        SC_P_INT_MIN_GENES=str(options.get("min_genes", 0)), SC_P_INT_MIN_CELLS=str(options.get("min_cells", 0)),
        SC_P_STR_SAMPLE_LABEL=options.get("sample_label", ""), SC_P_STR_CONDITION_LABEL=options.get("condition_label", ""))
    command = [sys.executable, str(SCRIPT)]
    if inject:
        command = [sys.executable, "-c", "import os,runpy,sys;original=os.link;calls=0\ndef link(source,destination):\n global calls\n calls+=1\n if calls==2:raise OSError('INJECTED_SECOND_LINK_FAILURE')\n return original(source,destination)\nos.link=link\nrunpy.run_path(sys.argv[1],run_name='__main__')", str(SCRIPT)]
    result = subprocess.run(command, env=environment, capture_output=True)
    (directory / "stdout.txt").write_bytes(result.stdout)
    (directory / "stderr.txt").write_bytes(result.stderr)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_sha
    if error:
        assert result.returncode != 0 and error in result.stderr.decode(), (name, result.stderr.decode())
        if mode == "sentinel":
            assert output.read_text() == "IMMUTABLE SENTINEL"
        elif mode == "dangling":
            assert output.is_symlink() and os.readlink(output) == "absent.h5ad"
        elif mode != "input":
            assert not output.exists()
        if report_path != output:
            assert not report_path.exists()
        assert not list(directory.glob(".dense-ingest-*"))
        return {"case": name, "specific_refusal": error, "exit": result.returncode}
    assert result.returncode == 0, (name, result.stderr.decode())
    expected = author_reference(directory, options, matrix, cells, genes)
    comparison = compare_h5ad(directory / "fresh-author.h5ad", output)
    actual = ad.read_h5ad(output)
    assert actual.X.dtype == np.int64 and np.array_equal(actual.X, expected.X)
    assert np.array_equal(actual.X, actual.layers["counts"])
    report = json.loads(report_path.read_text())
    assert report["input_sha256"] == source_sha and report["output_cell_ids"] == expected.obs_names.tolist()
    assert report["output_gene_ids"] == expected.var_names.tolist()
    assert report["output_cells"] == expected.n_obs and report["output_genes"] == expected.n_vars
    assert report["headerless_synthetic_column_ids"] == (not options.get("has_header", True))
    original_cells, original_genes = list(cells), list(genes)
    if not options.get("has_header", True):
        if options["orientation"] == "cells_by_genes":
            original_genes = [str(index) for index in range(1, len(genes) + 1)]
        else:
            original_cells = [str(index) for index in range(1, len(cells) + 1)]
    assert report["input_cells"] == len(cells) and report["input_genes"] == len(genes)
    assert report["input_cell_ids"] == original_cells and report["input_gene_ids"] == original_genes
    assert report["excluded_cell_ids"] == [value for value in original_cells if value not in set(expected.obs_names)]
    assert report["excluded_gene_ids"] == [value for value in original_genes if value not in set(expected.var_names)]
    for key, default in [("orientation", None), ("delimiter", "tab"), ("has_header", True),
            ("min_genes", 0), ("min_cells", 0), ("sample_label", None), ("condition_label", None)]:
        assert report[key] == options.get(key, default)
    assert set(report["input_cell_ids"]) == set(report["output_cell_ids"]) | set(report["excluded_cell_ids"])
    assert set(report["input_gene_ids"]) == set(report["output_gene_ids"]) | set(report["excluded_gene_ids"])
    assert not report["G0"] and not report["scientific_input_qualification"]
    return {"case": name, "whole_official_AnnData_Scanpy_and_HDF5_exact": True,
        "comparison": comparison, "exit": 0, "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}


def main(root):
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for orientation in ["genes_by_cells", "cells_by_genes"]:
        for label, delimiter, written in [("tab", "tab", "\t"), ("comma", "comma", ","),
                ("semicolon", "semicolon", ";"), ("pipe", "pipe", "|"), ("custom", "^", "^"),
                ("auto", "auto", "\t"), ("auto-custom", "auto", "^")]:
            records.append(run(root, orientation + "-" + label,
                {"orientation": orientation, "delimiter": delimiter, "write_delimiter": written}))
        records.append(run(root, orientation + "-gz", {"orientation": orientation}, compressed=True))
        records.append(run(root, orientation + "-headerless", {"orientation": orientation, "has_header": False}))
    records.append(run(root, "official-sequential-filters", {"orientation": "cells_by_genes", "min_genes": 2, "min_cells": 2,
        "sample_label": "donor冻", "condition_label": "conditionA"}))
    records.append(run(root, "exact-int64-above-double", {"orientation": "cells_by_genes"},
        matrix=[[9007199254740993, 0, 2], [0, 2, 4], [2, 0, 0], [0, 0, 0]]))
    options = {"orientation": "cells_by_genes"}
    for name, token, error in [("negative", "-1", "nonnegative integers"), ("fractional", "0.5", "nonnegative integers"),
            ("nan", "NaN", "nonnegative integers"), ("infinite", "Inf", "nonnegative integers"),
            ("out-of-range", "9223372036854775808", "int64 storage range"), ("non-numeric", "oops", "nonnumeric count")]:
        records.append(run(root, name, options, matrix=[[token, 0, 3], *VALUES[1:]], error=error))
    records.append(run(root, "duplicate-header", options, genes=["g1", "g1", "g3"], error="must be unique"))
    records.append(run(root, "duplicate-row", options, cells=["c1", "c1", "c3", "c4"], error="must be unique"))
    records.append(run(root, "empty-header", options, genes=["", "g2", "g3"], error="nonempty literal"))
    records.append(run(root, "empty-row", options, cells=["", "c2", "c3", "c4"], error="nonempty literal"))
    records.append(run(root, "row-field-loss", options, raw="cell\tg1\tg2\nc1\t1\n", error="declared column count"))
    records.append(run(root, "only-header", options, raw="cell\tg1\tg2\n", error="nonempty literal"))
    records.append(run(root, "all-filtered", {**options, "min_genes": 5}, error="removed every"))
    records.append(run(root, "invalid-orientation", {"orientation": "automatic"}, error="orientation must"))
    records.append(run(root, "negative-threshold", {**options, "min_genes": -1}, error="nonnegative integer"))
    records.append(run(root, "invalid-boolean", {**options, "has_header": "yes"}, error="true or false"))
    for mode, error in [("sentinel", "refusing overwrite"), ("dangling", "refusing overwrite"),
            ("alias", "must be distinct"), ("input", "refusing overwrite")]:
        records.append(run(root, "output-" + mode, options, mode=mode, error=error))
    records.append(run(root, "ordinary-rollback", options, inject=True, error="INJECTED_SECOND_LINK_FAILURE"))
    records.append(run(root, "underscore-notation", options, matrix=[["1_000", 0, 3], *VALUES[1:]], error="nonnumeric count notation"))
    report = {"cases": len(records), "records": records,
        "script_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(), "G0": False,
        "reference": "Separate inherited verified official prefix imports of AnnData(int64 fixture) plus Scanpy cells-before-genes; whole HDF5 exact comparison, no node/parser import"}
    (root / "SUMMARY.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
