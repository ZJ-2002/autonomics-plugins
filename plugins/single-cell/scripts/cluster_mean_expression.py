"""Descriptive cluster means using official Scanpy aggregation APIs."""

from __future__ import annotations

from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile
import warnings

import anndata as ad
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
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


def lexical(values, label: str, unique: bool) -> list[str]:
    result = list(values)
    if any(not isinstance(value, str) or not value or any(char in value for char in "\t\r\n\0") for value in result):
        raise ContractError(f"{label} must contain nonempty lexical strings without TAB/CR/LF/NUL")
    if unique and len(set(result)) != len(result):
        raise ContractError(f"{label} must be unique")
    return result


def parameters() -> dict:
    groupby = os.environ.get("SC_P_STR_GROUPBY", "")
    lexical([groupby], "groupby", True)
    normalize = os.environ.get("SC_P_STR_NORMALIZE", "cp10k").lower()
    if normalize not in {"cp10k", "none"}:
        raise ContractError("normalize must be cp10k or none")
    include = os.environ.get("SC_P_BOOL_INCLUDE_PERCENT_EXPRESSED", "true")
    if include not in {"true", "false"}:
        raise ContractError("include_percent_expressed must be true or false")
    encoded = os.environ.get("SC_P_R_ARRAY_GENES")
    if encoded is None or not encoded.startswith("c(") or not encoded.endswith(")"):
        raise ContractError("genes requires the lossless SC_P_R_ARRAY_GENES transport")
    try:
        genes = json.loads("[" + encoded[2:-1] + "]", parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except ValueError as error:
        raise ContractError("invalid lossless genes array") from error
    return {"groupby": groupby, "normalize": normalize, "include_percent_expressed": include == "true",
            "genes": lexical(genes, "genes", True)}


def group_labels(series: pd.Series) -> list[str]:
    if series.isna().any():
        raise ContractError("group labels must not be missing")
    identities = {}
    result = []
    for value in series:
        if not isinstance(value, (str, bool, int, float, np.integer, np.floating, np.bool_)):
            raise ContractError("group labels must be scalar strings or finite numbers/booleans")
        if isinstance(value, (float, np.floating)) and not np.isfinite(value):
            raise ContractError("group labels must be finite")
        label = str(value)
        lexical([label], "group labels", False)
        identity = (type(value).__name__, repr(value))
        if label in identities and identities[label] != identity:
            raise ContractError("distinct group label values collide after legacy string conversion")
        identities[label] = identity
        result.append(label)
    return result


def validated_matrix(matrix, normalize: str):
    if matrix is None:
        raise ContractError("chosen matrix source is absent")
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix)
    if values.dtype.kind not in "biuf" or not np.isfinite(values).all():
        raise ContractError("chosen matrix must contain finite real values")
    if values.dtype.kind in "iu" and any(abs(int(value)) > 2 ** 53 for value in values.ravel()):
        raise ContractError("integer matrix values must be in the exact float64 range")
    if normalize == "cp10k" and (values < 0).any():
        raise ContractError("cp10k requires nonnegative count-like values")
    if sparse.issparse(matrix):
        candidate = matrix.copy()
        candidate.check_format(full_check=True)
        if values.dtype.kind in "iu" and not candidate.has_canonical_format:
            coordinates = candidate.tocoo(copy=False)
            coordinate_totals = {}
            for row, column, value in zip(coordinates.row, coordinates.col, coordinates.data):
                key = (int(row), int(column))
                coordinate_totals[key] = coordinate_totals.get(key, 0) + int(value)
            if any(abs(value) > 2 ** 53 for value in coordinate_totals.values()):
                raise ContractError("integer coordinate sums must be in the exact float64 range")
        if values.dtype.kind == "b":
            candidate.sum_duplicates()
        candidate = candidate.astype(np.float64).tocsr()
        candidate.sum_duplicates()
        candidate.eliminate_zeros()
        if not np.isfinite(candidate.data).all():
            raise ContractError("canonicalized sparse matrix contains nonfinite values")
    else:
        candidate = np.asarray(matrix, dtype=np.float64).copy()
    return candidate


def aggregate(source: ad.AnnData, settings: dict) -> tuple[pd.DataFrame, dict]:
    if not source.n_obs or not source.n_vars:
        raise ContractError("H5AD must have nonempty observation and gene axes")
    cells = lexical(source.obs_names, "obs_names", True)
    background = lexical(source.var_names, "var_names", True)
    if source.obs.columns.has_duplicates or settings["groupby"] not in source.obs:
        raise ContractError("obs must have a unique named groupby column")
    labels = group_labels(source.obs[settings["groupby"]])
    genes = settings["genes"] or background
    known = set(background)
    missing = [gene for gene in genes if gene not in known]
    if missing:
        raise ContractError(f"requested genes are absent: {missing}")
    use_counts = settings["normalize"] == "cp10k" and "counts" in source.layers
    matrix_source = "layers/counts" if use_counts else "X"
    matrix = validated_matrix(source.layers["counts"] if use_counts else source.X, settings["normalize"])
    work = ad.AnnData(matrix, obs=pd.DataFrame({"cluster": pd.Categorical(labels, categories=sorted(set(labels)))}, index=cells),
                      var=pd.DataFrame(index=background))
    if settings["normalize"] == "cp10k":
        totals = np.asarray(work.X.sum(axis=1)).ravel()
        if not np.isfinite(totals).all() or (totals <= 0).any():
            raise ContractError("cp10k requires finite positive full-background cell totals")
        sc.pp.normalize_total(work, target_sum=10000, exclude_highly_expressed=False, key_added=None, inplace=True)
    work = work[:, genes].copy()
    combined = sc.get.aggregate(work, by="cluster", func=["mean", "count_nonzero"], axis="obs", dof=1)
    means = np.asarray(combined.layers["mean"])
    detected = np.asarray(combined.layers["count_nonzero"])
    if not np.isfinite(means).all() or not np.isfinite(detected).all():
        raise ContractError("official aggregation produced nonfinite results")
    group_counts = Counter(labels)
    rows = []
    for index, label in enumerate(combined.obs["cluster"].astype(str)):
        for position, gene in enumerate(genes):
            row = {"cluster": label, "gene": gene, "mean_expression": float(means[index, position])}
            if settings["include_percent_expressed"]:
                row["pct_expressed"] = float(detected[index, position] / group_counts[label] * 100)
            rows.append(row)
    table = pd.DataFrame.from_records(rows)
    report = {"schema_version": "2.0", "operation": "cluster_mean_expression", "parameters": settings,
              "input_cells": source.n_obs, "background_genes": source.n_vars, "selected_genes": genes,
              "output_rows": len(rows), "matrix_source": matrix_source,
              "normalization_background": "all_input_var_names_before_gene_selection",
              "group_cell_counts": dict(sorted(group_counts.items())), "ordered_cluster_labels": list(combined.obs["cluster"].astype(str)),
              "cell_ledger": [{"input_index": index, "cell_id": cell, "cluster": labels[index]} for index, cell in enumerate(cells)],
              "fraction_definition": "100 * count_nonzero_after_coordinate_coalescing / cells_in_cluster",
              "mean_definition": "cell-level arithmetic mean on chosen scale, not donor pseudobulk sum",
              "matrix_policy": "float64; canonical CSR; boolean duplicates coalesce in bool dtype; numeric duplicates sum; stored zeros removed",
              "raw_used": False, "study_input_scale_verified": False,
              "memory_policy": "whole AnnData materialized; full-size memory acceptance not established",
              "scientific_release": "NOT_GRANTED", "G0": False,
              "packages": {name: importlib.metadata.version(name) for name in ["scanpy", "anndata", "numpy", "scipy", "pandas", "pyarrow"]}}
    return table, report


def run() -> None:
    settings = parameters()
    source_path = required_path("AUTONOMICS_INPUT0")
    destination = required_path("AUTONOMICS_OUTPUT0")
    if not source_path.is_file():
        raise ContractError("input must be a readable H5AD file")
    if source_path.resolve() == destination.resolve():
        raise ContractError("input and output paths must be distinct")
    if os.path.lexists(destination):
        raise ContractError("refusing to overwrite existing output")
    destination.parent.mkdir(parents=True, exist_ok=True)
    checksum = digest(source_path)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        frame, report = aggregate(ad.read_h5ad(source_path), settings)
    if digest(source_path) != checksum:
        raise ContractError("input changed during aggregation")
    report["input_sha256"] = checksum
    report["warnings"] = [f"{warning.category.__name__}: {warning.message}" for warning in caught]
    table = pa.Table.from_pandas(frame, preserve_index=False)
    metadata = dict(table.schema.metadata or {})
    metadata[b"autonomics_cluster_mean_report"] = json.dumps(report, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    with tempfile.TemporaryDirectory(prefix=".cluster-mean-", dir=destination.parent) as temporary:
        staged = Path(temporary) / destination.name
        pq.write_table(table.replace_schema_metadata(metadata), staged)
        with staged.open("rb") as handle:
            os.fsync(handle.fileno())
        os.link(staged, destination)


def main() -> int:
    try:
        run()
    except ContractError as error:
        print(f"h5ad_cluster_mean_expression: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"h5ad_cluster_mean_expression: {error}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
