"""Whole AnnData and strict QC-report comparison, with declared tolerances."""

import hashlib
import json
import re
from pathlib import Path

import anndata as ad
import h5py
import numpy as np
import pandas as pd
from scipy import sparse


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def compare_value(actual, expected):
    if isinstance(expected, dict):
        assert set(actual) == set(expected)
        return sum(compare_value(actual[name], expected[name]) for name in expected)
    if isinstance(expected, pd.DataFrame):
        pd.testing.assert_frame_equal(actual, expected, check_exact=False, atol=1e-12, rtol=0)
        return sum(np.isfinite(expected[column].to_numpy()).sum() for column in expected.select_dtypes(include="number"))
    if sparse.issparse(expected):
        assert sparse.issparse(actual) and actual.format == expected.format and actual.dtype == expected.dtype
        np.testing.assert_array_equal(actual.indptr, expected.indptr)
        np.testing.assert_array_equal(actual.indices, expected.indices)
        np.testing.assert_allclose(actual.data, expected.data, atol=1e-12, rtol=0, equal_nan=True)
        return int(np.isfinite(expected.data).sum())
    if isinstance(expected, (np.ndarray, np.generic)):
        assert np.asarray(actual).dtype == np.asarray(expected).dtype
        if np.asarray(expected).dtype.kind in "fciub":
            np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=0, equal_nan=True)
            return int(np.isfinite(expected).sum())
        np.testing.assert_array_equal(actual, expected)
        return 0
    assert actual == expected
    return 0


def compare(directory):
    actual = ad.read_h5ad(directory / "output.h5ad")
    expected = ad.read_h5ad(directory / "fresh-author.h5ad")
    assert actual.shape == expected.shape and actual.n_obs > 0 and actual.n_vars > 0
    finite = compare_value(actual.X, expected.X)
    finite += compare_value(actual.obs, expected.obs) + compare_value(actual.var, expected.var)
    for name in ["layers", "obsm", "varm", "obsp", "varp", "uns"]:
        finite += compare_value(dict(getattr(actual, name)), dict(getattr(expected, name)))
    assert (actual.raw is None) == (expected.raw is None)
    if expected.raw is not None:
        finite += compare_value(actual.raw.X, expected.raw.X)
        finite += compare_value(actual.raw.var, expected.raw.var)
        finite += compare_value(dict(actual.raw.varm), dict(expected.raw.varm))
    with h5py.File(directory / "output.h5ad") as produced, h5py.File(directory / "fresh-author.h5ad") as reference:
        actual_names, expected_names = [], []
        produced.visit(actual_names.append)
        reference.visit(expected_names.append)
        assert actual_names == expected_names
        for name in ["/", *expected_names]:
            for attribute in reference[name].attrs:
                np.testing.assert_array_equal(produced[name].attrs[attribute], reference[name].attrs[attribute])
            assert set(produced[name].attrs) == set(reference[name].attrs)
            if isinstance(reference[name], h5py.Dataset):
                assert produced[name].dtype == reference[name].dtype
                if reference[name].dtype.kind in "fciub":
                    np.testing.assert_allclose(produced[name][()], reference[name][()], atol=1e-12, rtol=0, equal_nan=True)
                else:
                    np.testing.assert_array_equal(produced[name][()], reference[name][()])
    report = json.loads((directory / "report.json").read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    settings = json.loads((directory / "request.json").read_text())
    source = ad.read_h5ad(directory / "input.h5ad")
    assert report["filters"] == settings and report["input_sha256"] == digest(directory / "input.h5ad")
    assert report["input_cells"] == source.n_obs and report["input_genes"] == source.n_vars
    assert report["output_cells"] == actual.n_obs and report["output_genes"] == actual.n_vars
    assert report["filter_order"] == ["calculate_qc_metrics_on_input_X", "filter_cells", "filter_genes_on_retained_cells"]
    assert report["scientific_release"] == "NOT_GRANTED" and report["G0"] is False
    assert report["outputs"] == [{"port": 0, "name": "output.h5ad", "sha256": digest(directory / "output.h5ad"),
                                  "bytes": (directory / "output.h5ad").stat().st_size}]
    assert len(report["cell_ledger"]) == source.n_obs and len(report["gene_ledger"]) == source.n_vars
    assert [item["cell_id"] for item in report["cell_ledger"] if item["retained"]] == list(expected.obs_names)
    assert [item["gene_id"] for item in report["gene_ledger"] if item["retained"]] == list(expected.var_names)
    mathematical_source = source.X.astype(np.int64) if source.X.dtype.kind in "biu" else source.X
    if sparse.issparse(mathematical_source):
        counts = mathematical_source.toarray()
    else:
        counts = np.asarray(mathematical_source)
    retained_cells = [item["input_index"] for item in report["cell_ledger"] if item["retained"]]
    np.testing.assert_array_equal([item["n_cells_after_cell_filter"] for item in report["gene_ledger"]],
                                  (counts[retained_cells, :] > 0).sum(axis=0))
    totals = counts.sum(axis=1)
    assert report["undefined_percentage_cells"] == list(source.obs_names[totals == 0])
    independent_metrics = {"n_genes_by_counts": (counts > 0).sum(axis=1), "total_counts": totals}
    for label in ["mt", "rb"]:
        flags = np.array([bool(re.search(settings[label + "_gene_pattern"], str(name), re.IGNORECASE))
                          for name in source.var_names])
        with np.errstate(divide="ignore", invalid="ignore"):
            independent_metrics["pct_counts_" + label] = counts[:, flags].sum(axis=1) / totals * 100
    assert set(report["metrics"]) == set(independent_metrics)
    for name, values in independent_metrics.items():
        finite_values = values[np.isfinite(values)]
        expected_summary = dict(zip(["min", "p25", "median", "p75", "max"],
                                    np.percentile(finite_values, [0, 25, 50, 75, 100]).tolist())) \
            if finite_values.size else dict.fromkeys(["min", "p25", "median", "p75", "max"])
        assert set(report["metrics"][name]) == set(expected_summary)
        for key, value in expected_summary.items():
            if value is None:
                assert report["metrics"][name][key] is None
            else:
                np.testing.assert_allclose(report["metrics"][name][key], value, atol=1e-12, rtol=0)
    for item in report["cell_ledger"]:
        assert item["retained"] == (not item["failed_filters"])
        assert item["percentage_defined"] == bool(totals[item["input_index"]] > 0)
    for item in report["gene_ledger"]:
        assert item["retained"] == (not item["failed_filters"])
    assert report["schema_version"] == "2.0" and report["operation"] == "qc_filter"
    assert report["matrix_source"] == "X; never silently switches to raw or a counts layer"
    assert report["integer_matrix_policy"] == "promote to int64; each row and column sum must fit int64"
    assert report["sparse_matrix_policy"] == "CSR, sum_duplicates, eliminate_zeros before official QC"
    assert report["input_scale_and_donor_eligibility"] == "NOT_VERIFIED"
    assert report["preexisting_derived_artifacts_recomputed"] is False
    assert report["report_hash_policy"] == "port_1_hash_recorded_externally_not_recursively"
    return {"pass": True, "shape": list(actual.shape), "finite_values_checked": int(finite),
            "all_AnnData_components_and_HDF5_datasets_checked": True,
            "full_axis_ledger_and_hash_checked": True, "absolute_tolerance": 1e-12,
            "relative_tolerance": 0, "official_undefined_masks_preserved": True, "G0": False}
