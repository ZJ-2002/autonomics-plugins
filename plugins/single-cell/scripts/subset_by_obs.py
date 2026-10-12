"""Strict lexical cell or group selection using official AnnData slicing."""

from __future__ import annotations

from contextlib import ExitStack
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


class ContractError(RuntimeError):
    pass


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def path_from_env(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        raise ContractError(f"missing required environment variable: {name}")
    return Path(value)


def lexical(values, label: str, unique: bool) -> list[str]:
    result = list(values)
    if any(not isinstance(value, str) or not value or any(char in value for char in "\t\r\n")
           for value in result):
        raise ContractError(f"{label} must contain nonempty lexical strings, without missing values or TAB/CR/LF")
    if unique and len(set(result)) != len(result):
        raise ContractError(f"{label} must contain unique identifiers")
    return result


def subset(source: ad.AnnData, selection: pd.DataFrame, join_column: str) -> tuple[ad.AnnData, dict]:
    if not source.n_obs or not source.n_vars:
        raise ContractError("H5AD must have nonempty observation and variable axes")
    cell_ids = lexical(source.obs_names, "obs_names", True)
    lexical(source.var_names, "var_names", True)
    if source.obs.columns.has_duplicates or selection.columns.has_duplicates:
        raise ContractError("obs and selection column names must be unique")
    if join_column not in selection.columns:
        raise ContractError(f"selection Parquet has no `{join_column}` column")
    requested = lexical(selection[join_column], "selection IDs", True)
    if not requested:
        raise ContractError("selection must contain at least one identifier")
    if join_column == "cell_id":
        obs_values = cell_ids
    elif join_column in source.obs.columns:
        obs_values = lexical(source.obs[join_column], f"obs `{join_column}`", False)
    else:
        raise ContractError(f"H5AD obs has no `{join_column}` column")
    observed = set(obs_values)
    unknown = [value for value in requested if value not in observed]
    if unknown:
        raise ContractError(f"selection contains unknown identifiers: {unknown}")
    keep = np.asarray(pd.Index(obs_values).isin(requested), dtype=bool)
    result = source[keep].to_memory() if source.isbacked else source[keep].copy()
    prior_params = "subset_params" in source.uns
    result.uns["subset_params"] = {"join_column": join_column, "requested_cells": len(requested)}
    available_counts = Counter(obs_values)
    counts = {value: available_counts[value] for value in requested}
    report = {"schema_version": "2.0", "operation": "subset_by_obs", "join_column": join_column,
              "selection_semantics": "obs_names" if join_column == "cell_id" else "obs_group_membership",
              "input_cells": source.n_obs, "output_cells": result.n_obs,
              "input_genes": source.n_vars, "output_genes": result.n_vars,
              "requested_unique_cells": len(requested), "requested_unique_values": len(requested),
              "matched_unique_values": len(requested), "missing_cells": 0, "missing_values": [],
              "requested_values": requested, "matched_cells_per_value": counts,
              "selection_order": "input_H5AD_observation_order_not_request_order",
              "selected_cell_ids": list(result.obs_names),
              "cell_ledger": [{"input_index": index, "cell_id": cell_id, "join_value": obs_values[index],
                               "retained": bool(keep[index])} for index, cell_id in enumerate(cell_ids)],
              "preexisting_subset_params_overwritten": prior_params,
              "preexisting_derived_artifacts_recomputed": False,
              "matrix_policy": "slice only; no normalization, mapping, QC, or scale selection",
              "memory_policy": "load whole AnnData; full-scale memory acceptance not established",
              "donor_eligibility": "NOT_VERIFIED", "scientific_release": "NOT_GRANTED", "G0": False,
              "packages": {name: importlib.metadata.version(name) for name in ["anndata", "numpy", "pandas", "pyarrow", "h5py"]}}
    return result, report


def publish(data: ad.AnnData, report: dict, outputs: list[Path]) -> None:
    published = []
    with ExitStack() as stack:
        directories = [Path(stack.enter_context(tempfile.TemporaryDirectory(prefix=".subset-", dir=path.parent)))
                       for path in outputs]
        staged = [directories[0] / "output.h5ad", directories[1] / "report.json"]
        data.write_h5ad(staged[0], compression="lzf")
        report["outputs"] = [{"port": 0, "name": outputs[0].name, "sha256": digest(staged[0]),
                              "bytes": staged[0].stat().st_size}]
        report["report_hash_policy"] = "port_1_hash_recorded_externally_not_recursively"
        staged[1].write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n")
        for path in staged:
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
        try:
            for temporary, destination in zip(staged, outputs):
                status = temporary.stat()
                os.link(temporary, destination)
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
    join_column = os.environ.get("SC_P_STR_JOIN_COLUMN", "cell_id")
    lexical([join_column], "join_column", True)
    inputs = [path_from_env("AUTONOMICS_INPUT0"), path_from_env("AUTONOMICS_INPUT1")]
    outputs = [path_from_env("AUTONOMICS_OUTPUT0"), path_from_env("AUTONOMICS_OUTPUT1")]
    if not all(path.is_file() for path in inputs):
        raise ContractError("inputs must be readable H5AD and Parquet files")
    if len({path.resolve() for path in inputs + outputs}) != 4:
        raise ContractError("input and output paths must be distinct")
    for path in outputs:
        if os.path.lexists(path):
            raise ContractError(f"refusing to overwrite existing output: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    checksums = [digest(path) for path in inputs]
    selection = pd.read_parquet(inputs[1], engine="pyarrow")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        source = ad.read_h5ad(inputs[0])
        result, report = subset(source, selection, join_column)
    if [digest(path) for path in inputs] != checksums:
        raise ContractError("input changed during selection")
    report["input_sha256"] = checksums[0]
    report["selection_sha256"] = checksums[1]
    report["warnings"] = [f"{warning.category.__name__}: {warning.message}" for warning in caught]
    publish(result, report, outputs)


def main() -> int:
    try:
        run()
    except ContractError as error:
        print(f"h5ad_subset_by_obs: {error}", file=sys.stderr)
        return 2
    except Exception as error:
        print(f"h5ad_subset_by_obs: {error}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
