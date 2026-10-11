"""Mandatory actual-image refusal and publication counterexamples."""

import argparse
import json
import os
from pathlib import Path
import sys

import anndata as ad
import numpy as np

from qc_compare import digest
from test_qc_container import DEFAULTS, FAMILY, environment, execute, fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    arguments = parser.parse_args()
    arguments.evidence.mkdir(exist_ok=False)
    cases = [(name, name, fragment) for name, fragment in [
        ("negative", "finite nonnegative"), ("nan", "finite nonnegative"),
        ("infinity", "finite nonnegative"), ("complex", "finite nonnegative"),
        ("integer-overflow", "int64 QC accumulation"), ("float-overflow", "nonfinite QC sums"),
        ("integer-column-overflow", "int64 QC accumulation"), ("integer-row-overflow", "int64 QC accumulation"),
        ("inverted-gene-bounds", "min_genes exceeds max_genes"),
        ("inverted-cell-bounds", "min_cells exceeds max_cells"),
        ("missing-input-env", "AUTONOMICS_INPUT0"), ("missing-output-0", "AUTONOMICS_OUTPUT0"),
        ("missing-output-1", "AUTONOMICS_OUTPUT1"), ("missing-input-file", "readable H5AD"),
        ("duplicate-cell", "obs_names"), ("duplicate-gene", "var_names"),
        ("empty-cell-id", "obs_names"), ("empty-gene-id", "var_names"),
        ("no-X", "nonempty expression matrix"), ("zero-cell-axis", "nonempty expression matrix"),
        ("zero-gene-axis", "nonempty expression matrix"), ("malformed-h5ad", "file signature"),
        ("h5ad-exists", "refusing to overwrite"), ("report-exists", "refusing to overwrite"),
        ("output-directory", "refusing to overwrite"), ("dangling-output", "refusing to overwrite"),
        ("aliased-output", "paths must be distinct"), ("input-overwrite", "paths must be distinct"),
        ("second-link-failure", "injected second link failure")]]
    cases += [(name, (key, value), fragment) for name, key, value, fragment in [
        ("negative-min", "min_genes", -1, "nonnegative integer"),
        ("fractional-min", "min_genes", 1.7, "nonnegative integer"),
        ("boolean-min", "min_genes", True, "nonnegative integer"),
        ("negative-max", "max_cells", -1, "nonnegative integer"),
        ("nan-percentage", "max_pct_mt", "nan", "finite percentage"),
        ("infinite-percentage", "max_pct_rb", "inf", "finite percentage"),
        ("negative-percentage", "max_pct_mt", -1, "finite percentage"),
        ("large-percentage", "max_pct_rb", 101, "finite percentage"),
        ("invalid-regex", "mt_gene_pattern", "[", "valid regex"),
        ("empty-regex", "rb_gene_pattern", "", "nonempty regex"),
        ("empty-cell-filter", "min_genes", 99, "removed every cell"),
        ("empty-gene-filter", "min_cells", 99, "removed every gene")]]
    records = []
    for name, change, fragment in cases:
        directory = arguments.evidence / name
        directory.mkdir()
        fixture(directory)
        settings = DEFAULTS.copy()
        source = directory / "input.h5ad"
        data = ad.read_h5ad(source)
        if isinstance(change, tuple):
            settings[change[0]] = change[1]
        elif change in ["integer-column-overflow", "integer-row-overflow"]:
            data.X = np.zeros_like(data.X, dtype=np.int64)
            if change == "integer-column-overflow":
                data.X[:, 0] = 2**62
            else:
                data.X[0, :] = 2**62
        elif change == "inverted-gene-bounds":
            settings.update(min_genes=3, max_genes=1)
        elif change == "inverted-cell-bounds":
            settings.update(min_cells=3, max_cells=1)
        elif change in ["negative", "nan", "infinity", "complex", "integer-overflow", "float-overflow"]:
            data.X = data.X.astype(complex if change == "complex" else np.uint64 if change == "integer-overflow" else float)
            data.X[1, 2] = {"negative": -1, "nan": np.nan, "infinity": np.inf,
                           "complex": 1j, "integer-overflow": 2**63, "float-overflow": 1e308}[change]
            if change == "float-overflow":
                data.X[1, 3] = 1e308
        elif change in ["duplicate-cell", "empty-cell-id"]:
            data.obs_names = ["NA" if change == "duplicate-cell" else "", *data.obs_names[1:]]
        elif change in ["duplicate-gene", "empty-gene-id"]:
            data.var_names = ["G" if change == "duplicate-gene" else "", *data.var_names[1:]]
        elif change == "no-X":
            data.X = None
        elif change == "zero-cell-axis":
            data = data[:0, :].copy()
        elif change == "zero-gene-axis":
            data = data[:, :0].copy()
        data.write_h5ad(source)
        variables = environment(directory, settings)
        sentinel = None
        if change in ["h5ad-exists", "report-exists"]:
            sentinel = directory / ("output.h5ad" if change == "h5ad-exists" else "report.json")
            sentinel.write_bytes(b"original-result-must-not-change")
        elif change == "malformed-h5ad":
            source.write_bytes(b"not HDF5")
        elif change == "output-directory":
            (directory / "output.h5ad").mkdir()
        elif change == "dangling-output":
            (directory / "output.h5ad").symlink_to("missing.h5ad")
        elif change == "aliased-output":
            variables["AUTONOMICS_OUTPUT1"] = variables["AUTONOMICS_OUTPUT0"]
        elif change == "input-overwrite":
            variables["AUTONOMICS_OUTPUT0"] = str(source)
        elif change in ["missing-input-env", "missing-output-0", "missing-output-1"]:
            key = {"missing-input-env": "AUTONOMICS_INPUT0", "missing-output-0": "AUTONOMICS_OUTPUT0",
                   "missing-output-1": "AUTONOMICS_OUTPUT1"}[change]
            variables.pop(key)
        elif change == "missing-input-file":
            variables["AUTONOMICS_INPUT0"] = str(directory / "absent.h5ad")
        before = digest(source)
        command = [sys.executable, str(FAMILY / "scripts/qc_filter.py")]
        if change == "second-link-failure":
            code = "import os,runpy; original=os.link; calls=[]\ndef link(*args,**kwargs):\n calls.append(1)\n if len(calls)==2: raise OSError('injected second link failure')\n return original(*args,**kwargs)\nos.link=link\nrunpy.run_path(" + repr(str(FAMILY / "scripts/qc_filter.py")) + ",run_name='__main__')"
            command = [sys.executable, "-c", code]
        result = execute(command, directory, "declared-node-script", variables)
        assert result.returncode != 0 and fragment in result.stderr.decode(), result.stderr.decode()
        assert digest(source) == before
        for filename in [directory / "output.h5ad", directory / "report.json"]:
            if filename == sentinel:
                assert filename.read_bytes() == b"original-result-must-not-change"
            elif filename.is_file():
                raise AssertionError("Rejected computation published a normal artifact")
        assert not list(directory.glob(".qc-*"))
        records.append({"case": name, "specifically_refused": True, "expected_error": fragment,
                        "no_new_normal_artifacts": True, "input_unchanged": True, "G0": False})
        print(name, "PASS", flush=True)
    (arguments.evidence / "SUMMARY.json").write_text(json.dumps({"refusals": len(records), "records": records,
        "ordinary_publication_failure_injected": True, "crash_or_resume_verified": False, "G0": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
