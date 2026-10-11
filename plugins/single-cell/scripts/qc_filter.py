"""Count-based H5AD QC using explicit Scanpy 1.11.3 API calls."""

from __future__ import annotations

from contextlib import ExitStack
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import warnings

import anndata as ad
import numpy as np
import scanpy as sc
from scipy import sparse


class ContractError(RuntimeError):
    pass


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def required_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise ContractError(f"missing required environment variable: {name}")
    return Path(value)


def parameters() -> dict:
    result = {}
    for name in ["min_genes", "max_genes", "min_cells", "max_cells"]:
        text = os.environ.get("SC_P_INT_" + name.upper(), "0")
        if not re.fullmatch(r"[0-9]+", text):
            raise ContractError(f"{name} must be a nonnegative integer")
        result[name] = int(text)
    for lower, upper in [("min_genes", "max_genes"), ("min_cells", "max_cells")]:
        if result[upper] and result[lower] > result[upper]:
            raise ContractError(f"{lower} exceeds {upper}")
    for name in ["max_pct_mt", "max_pct_rb"]:
        try:
            value = float(os.environ.get("SC_P_NUM_" + name.upper(), "100"))
        except ValueError as error:
            raise ContractError(f"{name} must be a finite percentage") from error
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ContractError(f"{name} must be a finite percentage between 0 and 100")
        result[name] = value
    for name, default in [("mt_gene_pattern", "^MT-"), ("rb_gene_pattern", "^RPL|^RPS")]:
        value = os.environ.get("SC_P_STR_" + name.upper(), default)
        if not value.strip():
            raise ContractError(f"{name} must be a nonempty regex")
        try:
            re.compile(value, re.IGNORECASE)
        except re.error as error:
            raise ContractError(f"{name} is not a valid regex: {error}") from error
        result[name] = value
    return result


def validate_matrix(data: ad.AnnData) -> None:
    if data.n_obs == 0 or data.n_vars == 0 or data.X is None:
        raise ContractError("input must contain a nonempty expression matrix X")
    for label, names in [("obs_names", data.obs_names), ("var_names", data.var_names)]:
        if names.has_duplicates or any(not str(name) for name in names):
            raise ContractError(f"{label} must contain unique nonempty identifiers")
    for label, frame in [("obs", data.obs), ("var", data.var)]:
        if frame.columns.has_duplicates:
            raise ContractError(f"{label} column names must be unique")
    values = data.X.data if sparse.issparse(data.X) else np.asarray(data.X)
    if values.dtype.kind not in "biuf" or not np.isfinite(values).all() or (values < 0).any():
        raise ContractError("X must contain finite nonnegative real expression values")
    if values.dtype.kind in "biu":
        if sparse.issparse(data.X):
            coordinates = data.X.tocoo(copy=False)
            row_totals = [0] * data.n_obs
            column_totals = [0] * data.n_vars
            for row, column, value in zip(coordinates.row, coordinates.col, coordinates.data):
                row_totals[int(row)] += int(value)
                column_totals[int(column)] += int(value)
        else:
            row_totals = np.sum(data.X, axis=1, dtype=object)
            column_totals = np.sum(data.X, axis=0, dtype=object)
        if max(row_totals) > np.iinfo(np.int64).max or max(column_totals) > np.iinfo(np.int64).max:
            raise ContractError("integer row or gene sum exceeds the exact int64 QC accumulation range")
        data.X = data.X.astype(np.int64)
    if sparse.issparse(data.X):
        data.X = sparse.csr_matrix(data.X)
        data.X.sum_duplicates()
        data.X.eliminate_zeros()
    totals = np.asarray(data.X.sum(axis=1)).ravel()
    gene_totals = np.asarray(data.X.sum(axis=0)).ravel()
    if not np.isfinite(totals).all() or not np.isfinite(gene_totals).all():
        raise ContractError("nonfinite QC sums: expression values overflow their accumulation dtype")


def percentile_summary(values: np.ndarray) -> dict:
    finite = values[np.isfinite(values)]
    labels = ["min", "p25", "median", "p75", "max"]
    return dict(zip(labels, np.percentile(finite, [0, 25, 50, 75, 100]).tolist())) if finite.size else dict.fromkeys(labels)


def run_qc(data: ad.AnnData, settings: dict) -> tuple[ad.AnnData, dict]:
    validate_matrix(data)
    original_cells = list(data.obs_names)
    original_genes = list(data.var_names)
    for label in ["mt", "rb"]:
        pattern = re.compile(settings[label + "_gene_pattern"], re.IGNORECASE)
        data.var[label] = [bool(pattern.search(str(name))) for name in original_genes]
    sc.pp.calculate_qc_metrics(data, expr_type="counts", var_type="genes", qc_vars=["mt", "rb"],
                              percent_top=None, layer=None, use_raw=False, log1p=False, inplace=True)
    minimum, detected = sc.pp.filter_cells(data.X, min_genes=settings["min_genes"], inplace=False)
    maximum = (detected <= settings["max_genes"]) if settings["max_genes"] else np.ones(data.n_obs, dtype=bool)
    checks = {"MIN_GENES": minimum, "MAX_GENES": maximum}
    for label in ["mt", "rb"]:
        values = data.obs["pct_counts_" + label].to_numpy()
        checks["MAX_PCT_" + label.upper()] = (np.isfinite(values) & (values <= settings["max_pct_" + label])) \
            if settings["max_pct_" + label] < 100 else np.ones(data.n_obs, dtype=bool)
    keep_cells = np.logical_and.reduce(list(checks.values()))
    metrics = {name: data.obs[name].to_numpy().copy()
               for name in ["n_genes_by_counts", "total_counts", "pct_counts_mt", "pct_counts_rb"]}
    cell_ledger = [{"input_index": index, "cell_id": name, "retained": bool(keep_cells[index]),
                    "failed_filters": [label for label, mask in checks.items() if not mask[index]],
                    "percentage_defined": bool(metrics["total_counts"][index] > 0)}
                   for index, name in enumerate(original_cells)]
    data = data[keep_cells, :].copy()
    if not data.n_obs:
        raise ContractError("QC filters removed every cell")
    keep_genes, gene_counts = sc.pp.filter_genes(data.X, min_cells=settings["min_cells"], inplace=False)
    if settings["max_cells"]:
        keep_genes &= gene_counts <= settings["max_cells"]
    gene_ledger = [{"input_index": index, "gene_id": name, "retained": bool(keep_genes[index]),
                    "n_cells_after_cell_filter": int(gene_counts[index]),
                    "failed_filters": (["MIN_CELLS"] if gene_counts[index] < settings["min_cells"] else []) +
                    (["MAX_CELLS"] if settings["max_cells"] and gene_counts[index] > settings["max_cells"] else [])}
                   for index, name in enumerate(original_genes)]
    data.var["n_cells"] = gene_counts
    data = data[:, keep_genes].copy()
    if not data.n_vars:
        raise ContractError("QC filters removed every gene")
    data.uns["qc_params"] = settings
    report = {"schema_version": "2.0", "operation": "qc_filter", "filters": settings,
              "filter_order": ["calculate_qc_metrics_on_input_X", "filter_cells", "filter_genes_on_retained_cells"],
              "input_cells": len(original_cells), "output_cells": data.n_obs,
              "input_genes": len(original_genes), "output_genes": data.n_vars,
              "metrics": {name: percentile_summary(values) for name, values in metrics.items()},
              "undefined_percentage_cells": [name for index, name in enumerate(original_cells)
                                             if metrics["total_counts"][index] == 0],
              "cell_ledger": cell_ledger, "gene_ledger": gene_ledger,
              "percentage_100_policy": "disables_percentage_filter; undefined values remain NaN in H5AD",
              "matrix_source": "X; never silently switches to raw or a counts layer",
              "integer_matrix_policy": "promote to int64; each row and column sum must fit int64",
              "sparse_matrix_policy": "CSR, sum_duplicates, eliminate_zeros before official QC",
              "input_scale_and_donor_eligibility": "NOT_VERIFIED",
              "preexisting_derived_artifacts_recomputed": False,
              "scientific_release": "NOT_GRANTED", "G0": False,
              "packages": {name: importlib.metadata.version(name) for name in ["scanpy", "anndata", "numpy", "scipy"]}}
    return data, report


def publish(data: ad.AnnData, report: dict, h5ad_path: Path, report_path: Path) -> None:
    published = []
    with ExitStack() as stack:
        h5ad_directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=".qc-", dir=h5ad_path.parent)))
        report_directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=".qc-", dir=report_path.parent)))
        staged_h5ad = h5ad_directory / "output.h5ad"
        staged_report = report_directory / "report.json"
        data.write_h5ad(staged_h5ad, compression="lzf")
        report["outputs"] = [{"port": 0, "name": h5ad_path.name, "sha256": digest(staged_h5ad),
                              "bytes": staged_h5ad.stat().st_size}]
        report["report_hash_policy"] = "port_1_hash_recorded_externally_not_recursively"
        staged_report.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
        for path in [staged_h5ad, staged_report]:
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
        try:
            for staged, destination in [(staged_h5ad, h5ad_path), (staged_report, report_path)]:
                status = staged.stat()
                os.link(staged, destination)
                published.append((destination, (status.st_dev, status.st_ino)))
        except OSError:
            for destination, expected in reversed(published):
                try:
                    status = destination.lstat()
                    if (status.st_dev, status.st_ino) == expected:
                        destination.unlink()
                except FileNotFoundError:
                    pass
            raise


def run() -> None:
    settings = parameters()
    input_path = required_path("AUTONOMICS_INPUT0")
    h5ad_path = required_path("AUTONOMICS_OUTPUT0")
    report_path = required_path("AUTONOMICS_OUTPUT1")
    if not input_path.is_file():
        raise ContractError("input must be a readable H5AD file")
    if len({path.resolve() for path in [input_path, h5ad_path, report_path]}) != 3:
        raise ContractError("input and output paths must be distinct")
    for path in [h5ad_path, report_path]:
        if os.path.lexists(path):
            raise ContractError(f"refusing to overwrite existing output: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    checksum = digest(input_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data, report = run_qc(ad.read_h5ad(input_path), settings)
    if digest(input_path) != checksum:
        raise ContractError("input changed during QC")
    report["input_sha256"] = checksum
    report["warnings"] = [f"{warning.category.__name__}: {warning.message}" for warning in caught]
    publish(data, report, h5ad_path, report_path)


def main() -> int:
    try:
        run()
    except ContractError as error:
        print(f"h5ad_qc_filter: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"h5ad_qc_filter: {error}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
