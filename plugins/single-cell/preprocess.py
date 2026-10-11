#!/usr/bin/env python3
"""Validate and ingest 10x-style MatrixMarket inputs into AnnData."""

from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import sys
import tempfile
import warnings
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

import anndata as ad
import numpy as np
import pandas as pd


MATRIX_ENV = "AUTONOMICS_INPUT0"
BARCODES_ENV = "AUTONOMICS_INPUT1"
FEATURES_ENV = "AUTONOMICS_INPUT2"
METADATA_ENV = "AUTONOMICS_INPUT3"
REPORT_ENV = "AUTONOMICS_OUTPUT0"
H5AD_ENV = "AUTONOMICS_OUTPUT1"
EXACT_INTEGER_LIMIT = 2**53


class ContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class MatrixHeader:
    field: str
    rows: int
    columns: int
    nonzero: int


def required_path(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise ContractError(f"missing required environment variable: {name}")
    return Path(value)


def _check_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise ContractError(f"{label} file does not exist: {path}")
    if not path.is_file():
        raise ContractError(f"{label} is not a regular file: {path}")
    if path.stat().st_size == 0:
        raise ContractError(f"{label} file is empty (0 bytes): {path}")


def _file_probe(path: Path) -> dict[str, object]:
    with path.open("rb") as handle:
        preview = handle.read(512)
    return {"bytes": path.stat().st_size,
            "preview": preview.decode("utf-8", errors="replace").splitlines()[:3],
            "preview_line_count": preview.count(b"\n"), "preview_limit_bytes": 512}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def open_text(path: Path) -> TextIO:
    if path.name.lower().endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("rt", encoding="utf-8", newline="")


def _dimensions(handle: TextIO, path: Path) -> list[str]:
    for line in handle:
        if line.lstrip().startswith("%") or not line.strip():
            continue
        return line.split()
    raise ContractError(f"{path.name}: missing MatrixMarket dimensions")


def parse_matrix_header(path: Path) -> MatrixHeader:
    with open_text(path) as handle:
        parts = handle.readline().strip().split()
        if not parts or parts[0].lower() != "%%matrixmarket":
            raise ContractError(f"{path.name}: not a MatrixMarket file")
        if len(parts) != 5:
            raise ContractError(f"{path.name}: malformed MatrixMarket banner")
        parts = [part.lower() for part in parts]
        if parts[1:3] != ["matrix", "coordinate"]:
            raise ContractError(f"{path.name}: expected MatrixMarket coordinate matrix")
        if parts[3] not in {"integer", "real"} or parts[4] != "general":
            raise ContractError(f"{path.name}: unsupported MatrixMarket field or symmetry")
        dimensions = _dimensions(handle, path)
        if len(dimensions) != 3 or any(not re.fullmatch(r"[0-9]+", value) for value in dimensions):
            raise ContractError(f"{path.name}: malformed MatrixMarket dimensions")
        values = tuple(int(value) for value in dimensions)
        if values[0] < 1 or values[1] < 1:
            raise ContractError(f"{path.name}: matrix axes must be nonempty")
        return MatrixHeader(parts[3], values[0], values[1], values[2])


def validate_matrix_body(path: Path, header: MatrixHeader) -> dict[str, object]:
    entries = 0
    integer_mass = 0
    with open_text(path) as handle:
        handle.readline()
        _dimensions(handle, path)
        for line_number, line in enumerate(handle, start=1):
            if not line.strip() or line.lstrip().startswith("%"):
                continue
            fields = line.split()
            if len(fields) != 3 or any(not re.fullmatch(r"[0-9]+", value) for value in fields[:2]):
                raise ContractError(f"{path.name}: malformed coordinate at body line {line_number}")
            row_index, column_index = (int(value) for value in fields[:2])
            if not 1 <= row_index <= header.rows or not 1 <= column_index <= header.columns:
                raise ContractError(f"{path.name}: coordinate outside declared axes")
            if header.field == "integer":
                if not re.fullmatch(r"[+-]?[0-9]+", fields[2]):
                    raise ContractError(f"{path.name}: non-integer value in integer field")
                value = int(fields[2])
                if value < 0:
                    raise ContractError(f"{path.name}: negative expression value")
                integer_mass += value
                if integer_mass > EXACT_INTEGER_LIMIT:
                    raise ContractError(f"{path.name}: integer mass exceeds exact float64 range")
            else:
                try:
                    value = float(fields[2])
                except ValueError as error:
                    raise ContractError(f"{path.name}: invalid real expression value") from error
                if not math.isfinite(value) or value < 0:
                    raise ContractError(f"{path.name}: expression values must be finite and nonnegative")
                if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", fields[2]):
                    raise ContractError(f"{path.name}: invalid real expression syntax")
            entries += 1
            if entries > header.nonzero:
                raise ContractError(f"{path.name}: more coordinates than declared")
    if entries != header.nonzero:
        raise ContractError(f"{path.name}: coordinate count does not match declared count")
    return {"coordinate_entries_validated": entries,
            "integer_mass": integer_mass if header.field == "integer" else None,
            "integer_exactness_guard": "total_nonnegative_mass_le_2^53" if header.field == "integer" else None}


def _identifier(value: str, label: str) -> None:
    if not value or value != value.strip() or any(ord(char) < 32 for char in value):
        raise ContractError(f"{label}: identifier is empty, padded or contains control characters")


def _table_rows(path: Path, delimiter: str, quoted: bool = False) -> list[list[str]]:
    try:
        with open_text(path) as handle:
            rows = list(csv.reader(handle, delimiter=delimiter, strict=True,
                                   quoting=csv.QUOTE_MINIMAL if quoted else csv.QUOTE_NONE))
    except (csv.Error, UnicodeError) as error:
        raise ContractError(f"{path.name}: table parse failed: {error}; {_file_probe(path)}") from error
    if not rows or any(not row for row in rows):
        raise ContractError(f"{path.name}: table is empty or has blank rows")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ContractError(f"{path.name}: table rows have inconsistent column counts")
    if any("\0" in value for row in rows for value in row):
        raise ContractError(f"{path.name}: table contains NUL")
    return rows


def read_barcodes(path: Path) -> pd.DataFrame:
    rows = _table_rows(path, "\t")
    if len(rows[0]) != 1:
        raise ContractError(f"{path.name}: barcode table must have exactly one column")
    identifiers = [row[0] for row in rows]
    for identifier in identifiers:
        _identifier(identifier, path.name)
    if len(set(identifiers)) != len(identifiers):
        raise ContractError(f"{path.name}: barcode file contains duplicate cell IDs")
    return pd.DataFrame({"cell_barcode": identifiers})


def read_features(path: Path) -> pd.DataFrame:
    rows = _table_rows(path, "\t")
    width = len(rows[0])
    if width not in {2, 3}:
        raise ContractError(f"{path.name}: feature table must have two or three columns")
    for row in rows:
        for identifier in row:
            _identifier(identifier, path.name)
    frame = pd.DataFrame(rows, columns=["gene_id", "gene_symbol", "feature_type"][:width])
    if frame["gene_id"].duplicated().any():
        raise ContractError(f"{path.name}: feature file contains duplicate gene IDs")
    return frame


def _detect_separator(path: Path) -> str:
    mode = os.environ.get("AUTONOMICS_SINGLE_CELL_METADATA_SEP", "auto").lower()
    if mode not in {"auto", "tab", "comma"}:
        raise ContractError("metadata_separator must be auto, tab or comma")
    if mode != "auto":
        return "\t" if mode == "tab" else ","
    with open_text(path) as handle:
        first_line = handle.readline()
    return "\t" if "\t" in first_line else ","


def read_metadata(path: Path, barcodes: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    rows = _table_rows(path, _detect_separator(path), quoted=True)
    headings = rows[0]
    if len(headings) < 2 or len(rows) < 2:
        raise ContractError(f"{path.name}: metadata needs a cell ID and at least one data column")
    for heading in headings:
        _identifier(heading, path.name)
        if "/" in heading:
            raise ContractError(f"{path.name}: metadata header contains an HDF5 path separator")
    if len(set(headings)) != len(headings):
        raise ContractError(f"{path.name}: metadata has duplicate column headers")
    identifiers = [row[0] for row in rows[1:]]
    for identifier in identifiers:
        _identifier(identifier, path.name)
    if len(set(identifiers)) != len(identifiers):
        raise ContractError(f"{path.name}: metadata file contains duplicate cell IDs")
    barcode_ids = barcodes["cell_barcode"].tolist()
    if set(identifiers) != set(barcode_ids):
        raise ContractError("cell IDs do not align between metadata and barcodes")
    frame = pd.DataFrame([row[1:] for row in rows[1:]], columns=headings[1:],
                         index=pd.Index(identifiers, name=headings[0]))
    return frame.loc[barcode_ids].copy(), identifiers == barcode_ids


def make_adata(metadata: pd.DataFrame, features: pd.DataFrame) -> ad.AnnData:
    variables = features.copy()
    variables.index = pd.Index(features["gene_symbol"], name="var_name")
    adata = ad.AnnData(obs=metadata.copy(), var=variables)
    adata.var_names_make_unique()
    return adata


def parse_nonnegative_int(name: str, default: str = "0") -> int:
    value = os.environ.get(name, default)
    if not re.fullmatch(r"[0-9]+", value):
        raise ContractError(f"{name} must be a nonnegative integer")
    return int(value)


def parse_bool(name: str, default: str = "false") -> bool:
    value = os.environ.get(name, default).lower()
    if value in {"1", "true", "yes"}:
        return True
    if value in {"0", "false", "no"}:
        return False
    raise ContractError(f"{name} must be a boolean")


def _validate_outputs(inputs: list[Path], outputs: list[Path]) -> None:
    resolved_inputs = {path.resolve() for path in inputs}
    resolved_outputs = [path.resolve() for path in outputs]
    if len(set(resolved_outputs)) != len(outputs) or resolved_inputs.intersection(resolved_outputs):
        raise ContractError("output paths collide with each other or with an input")
    for path in outputs:
        if os.path.lexists(path):
            raise ContractError(f"refusing to overwrite existing output: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)


def _run() -> tuple[ad.AnnData, dict[str, object], Path, Path]:
    inputs = [required_path(name) for name in [MATRIX_ENV, BARCODES_ENV, FEATURES_ENV, METADATA_ENV]]
    matrix_path, barcodes_path, features_path, metadata_path = inputs
    report_path, h5ad_path = [required_path(name) for name in [REPORT_ENV, H5AD_ENV]]
    _validate_outputs(inputs, [report_path, h5ad_path])
    for path, label in zip(inputs, ["matrix", "barcode", "feature", "metadata"], strict=True):
        _check_exists(path, label)
    operation = os.environ.get("AUTONOMICS_SINGLE_CELL_OPERATION", "inspect").lower()
    if operation not in {"inspect", "ingest"}:
        raise ContractError(f"unsupported operation `{operation}`")
    min_genes = parse_nonnegative_int("AUTONOMICS_SINGLE_CELL_MIN_GENES")
    min_cells = parse_nonnegative_int("AUTONOMICS_SINGLE_CELL_MIN_CELLS")
    normalize = parse_bool("AUTONOMICS_SINGLE_CELL_NORMALIZE_TOTAL")
    if operation == "inspect" and (min_genes > 0 or min_cells > 0 or normalize):
        raise ContractError("filtering and normalization require operation `ingest`")
    header = parse_matrix_header(matrix_path)
    barcodes = read_barcodes(barcodes_path)
    features = read_features(features_path)
    metadata, metadata_order_preserved = read_metadata(metadata_path, barcodes)
    if header.columns != len(barcodes) or header.rows != len(features):
        raise ContractError("matrix dimensions do not match barcode and feature tables")
    adata = make_adata(metadata, features)
    original_cells = adata.obs_names.tolist()
    original_variables = adata.var_names.tolist()
    report: dict[str, object] = {
        "schema_version": "2.0", "operation": operation,
        "scientific_release": "NOT_GRANTED", "G0": False,
        "analysis_eligibility": "METADATA_ONLY_NOT_ANALYZABLE",
        "tool_versions": {"python": platform.python_version(),
                          **{package: importlib.metadata.version(package)
                             for package in ["pandas", "anndata", "scanpy", "numpy", "scipy", "h5py"]}},
        "inputs": [{"name": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size} for path in inputs],
        "matrix": {"format": "matrix_market_coordinate", "field": header.field,
                   "genes": header.rows, "cells": header.columns, "nonzero": header.nonzero,
                   "gzip": matrix_path.name.lower().endswith(".gz"), "expression_loaded": False,
                   "body_validated": False, "read_dtype": "float64" if operation == "ingest" else None,
                   "feature_type_filter": "none_all_features_retained",
                   "input_scale_qualification": "NOT_GRANTED_BY_INGESTION"},
        "alignment": {"cells": len(barcodes), "genes": len(features), "metadata_rows": len(metadata),
                      "cell_ids_aligned": True, "cell_id_order_preserved": metadata_order_preserved},
        "qc": {"min_genes": min_genes, "min_cells": min_cells, "normalize_total": normalize,
               "filter_order": "cells_then_genes", "target_sum": 10000.0 if normalize else None,
               "exclude_highly_expressed": False if normalize else None,
               "log1p_base": None, "zero_count_cells": None},
    }
    if operation == "ingest":
        import scanpy as sc

        report["matrix"].update(validate_matrix_body(matrix_path, header))
        raw_matrix = sc.read_mtx(matrix_path, dtype="float64")
        if raw_matrix.shape != (header.rows, header.columns):
            raise ContractError("loaded matrix shape does not match header")
        adata.X = raw_matrix.X.T.tocsr()
        if not np.isfinite(adata.X.data).all() or (adata.X.data < 0).any():
            raise ContractError("loaded expression values must be finite and nonnegative")
        report["matrix"].update({"expression_loaded": True, "body_validated": True,
                                 "canonical_sparse_nonzero": int(adata.X.nnz)})
        if min_genes > 0:
            sc.pp.filter_cells(adata, min_genes=min_genes)
        if min_cells > 0:
            sc.pp.filter_genes(adata, min_cells=min_cells)
        if not adata.n_obs or not adata.n_vars:
            raise ContractError("no cells or genes remain after filtering")
        library_sizes = np.asarray(adata.X.sum(axis=1)).ravel()
        if not np.isfinite(library_sizes).all():
            raise ContractError("cell totals exceed finite float64 range")
        report["qc"]["zero_count_cells"] = int(np.count_nonzero(library_sizes == 0))
        if normalize:
            adata.layers["counts"] = adata.X.copy()
            sc.pp.normalize_total(adata, target_sum=1e4, exclude_highly_expressed=False,
                                  key_added=None, inplace=True)
            sc.pp.log1p(adata, base=None)
        if not np.isfinite(adata.X.data).all():
            raise ContractError("nonfinite expression values after preprocessing")
        report["analysis_eligibility"] = "COMPUTED_TECHNICAL_ONLY_REQUIRES_STUDY_QUALIFICATION"
    retained_cells = set(adata.obs_names)
    retained_variables = set(adata.var_names)
    report["cell_ledger"] = [{"input_index": index, "cell_barcode": identifier,
                               "retained": identifier in retained_cells,
                               "reason": "RETAINED" if identifier in retained_cells else "FILTER_MIN_GENES"}
                              for index, identifier in enumerate(original_cells)]
    report["feature_ledger"] = [{"input_index": index, "gene_id": features.iloc[index]["gene_id"],
                                  "gene_symbol_original": features.iloc[index]["gene_symbol"],
                                  "var_name": identifier, "retained": identifier in retained_variables,
                                  "reason": "RETAINED" if identifier in retained_variables else "FILTER_MIN_CELLS"}
                                 for index, identifier in enumerate(original_variables)]
    report["matrix"].update({"output_genes": adata.n_vars, "output_cells": adata.n_obs})
    return adata, report, report_path, h5ad_path


def _publish(adata: ad.AnnData, report: dict[str, object], report_path: Path, h5ad_path: Path) -> None:
    published: list[tuple[Path, tuple[int, int]]] = []
    with ExitStack() as stack:
        report_directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=".preprocess-", dir=report_path.parent)))
        h5ad_directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=".preprocess-", dir=h5ad_path.parent)))
        staged_h5ad = h5ad_directory / "output.h5ad"
        staged_report = report_directory / "report.json"
        adata.write_h5ad(staged_h5ad, compression="lzf")
        report["outputs"] = [{"port": 1, "name": h5ad_path.name, "sha256": _sha256(staged_h5ad),
                              "bytes": staged_h5ad.stat().st_size}]
        report["report_hash_policy"] = "port_0_hash_is_recorded_externally_not_recursively_in_its_own_content"
        with staged_report.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False, ensure_ascii=False)
            handle.write("\n")
        for staged_path in [staged_h5ad, staged_report]:
            with staged_path.open("rb") as handle:
                os.fsync(handle.fileno())
        try:
            for staged_path, destination in [(staged_h5ad, h5ad_path), (staged_report, report_path)]:
                identity = staged_path.stat()
                os.link(staged_path, destination)
                published.append((destination, (identity.st_dev, identity.st_ino)))
        except OSError:
            for destination, identity in reversed(published):
                try:
                    current = destination.lstat()
                    if (current.st_dev, current.st_ino) == identity:
                        destination.unlink()
                except FileNotFoundError:
                    pass
            raise


def run() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        adata, report, report_path, h5ad_path = _run()
    report["warnings"] = [f"{warning.category.__name__}: {warning.message}" for warning in caught]
    _publish(adata, report, report_path, h5ad_path)


def main() -> int:
    try:
        run()
    except ContractError as error:
        print(f"single_cell_preprocessor: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, UnicodeError) as error:
        print(f"single_cell_preprocessor: {error}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
