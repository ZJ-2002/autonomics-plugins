"""Exact count-table ingestion with explicit AnnData axes and Scanpy filters."""

import csv
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import tempfile

import anndata as ad
import numpy as np
import pandas as pd


class ContractError(RuntimeError):
    pass


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def parameters():
    orientation = os.environ.get("SC_P_STR_ORIENTATION", "").lower()
    if orientation not in {"genes_by_cells", "cells_by_genes"}:
        raise ContractError("orientation must be genes_by_cells or cells_by_genes")
    has_header = os.environ.get("SC_P_BOOL_HAS_HEADER", "true")
    if has_header not in {"true", "false"}:
        raise ContractError("has_header must be true or false")
    result = {"orientation": orientation, "has_header": has_header == "true",
        "delimiter": os.environ.get("SC_P_STR_DELIMITER", "auto")}
    for name in ["min_genes", "min_cells"]:
        value = os.environ.get("SC_P_INT_" + name.upper(), "0")
        if not re.fullmatch(r"[0-9]+", value):
            raise ContractError(f"{name} must be a nonnegative integer")
        result[name] = int(value)
    for name in ["sample_label", "condition_label"]:
        value = os.environ.get("SC_P_STR_" + name.upper(), "")
        if value and (not value.strip() or any(character in value for character in "\t\r\n")):
            raise ContractError(f"{name} must be nonblank and cannot contain tab/newline characters")
        result[name] = value or None
    return result


def separator(specification, sample):
    aliases = {"tab": "\t", "\\t": "\t", "comma": ",", "semicolon": ";", "pipe": "|"}
    normalized = specification.lower()
    if normalized == "auto":
        try:
            return csv.Sniffer().sniff(sample).delimiter
        except csv.Error as error:
            raise ContractError("cannot infer delimiter; provide an explicit delimiter") from error
    value = aliases.get(normalized, specification)
    if len(value) != 1 or value in "\r\n\0" or value == chr(34):
        raise ContractError("delimiter must be auto, tab, comma, semicolon, pipe or one valid character")
    return value


def identifiers(values, label):
    if not values or any(not value.strip() or any(character in value for character in "\t\r\n\0") for value in values):
        raise ContractError(f"{label} must be nonempty literal identifiers without control characters")
    if len(set(values)) != len(values):
        raise ContractError(f"{label} must be unique; duplicate identifiers are not renamed")


def read_matrix(path, options):
    opener = gzip.open if path.name.lower().endswith(".gz") else open
    row_ids = []
    rows = []
    column_ids = None
    blank_records = 0
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        selected_separator = separator(options["delimiter"], handle.read(65536))
        handle.seek(0)
        reader = csv.reader(handle, delimiter=selected_separator, strict=True)
        for record in reader:
            if not record:
                blank_records += 1
                continue
            if column_ids is None:
                if len(record) < 2:
                    raise ContractError("matrix requires an identifier column and at least one numeric column")
                column_ids = record[1:] if options["has_header"] else [str(index) for index in range(1, len(record))]
                identifiers(column_ids, "column identifiers")
                if options["has_header"]:
                    continue
            if len(record) != len(column_ids) + 1:
                raise ContractError("matrix rows must have exactly the declared column count")
            row_ids.append(record[0])
            values = []
            for token in record[1:]:
                try:
                    value = Decimal(token)
                except InvalidOperation as error:
                    raise ContractError("matrix contains a nonnumeric count") from error
                if not value.is_finite() or value < 0 or value != value.to_integral_value():
                    raise ContractError("count matrix must contain finite nonnegative integers")
                if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", token.strip()):
                    raise ContractError("matrix contains a nonnumeric count notation")
                if value > int(np.iinfo(np.int64).max):
                    raise ContractError("count exceeds the exact int64 storage range")
                values.append(int(value))
            rows.append(values)
    identifiers(row_ids, "row identifiers")
    matrix = np.array(rows, dtype=np.int64)
    if options["orientation"] == "genes_by_cells":
        matrix = matrix.T.copy()
        cell_ids, gene_ids = column_ids, row_ids
    else:
        cell_ids, gene_ids = row_ids, column_ids
    return matrix, cell_ids, gene_ids, selected_separator, blank_records


def paths():
    values = [os.environ.get(name) for name in ["AUTONOMICS_INPUT0", "AUTONOMICS_OUTPUT0", "AUTONOMICS_OUTPUT1"]]
    if not all(values):
        raise ContractError("input and both declared output ports are required")
    source, output, report = [Path(value).absolute() for value in values]
    if not source.is_file():
        raise ContractError("input port must name a readable count-table file")
    if output.resolve() == report.resolve():
        raise ContractError("output paths must be distinct")
    for path in [output, report]:
        if os.path.lexists(path):
            raise ContractError(f"output already exists; refusing overwrite: {path}")
        if not path.parent.is_dir():
            raise ContractError(f"output parent does not exist: {path.parent}")
    return source, output, report


def publish(data, report, destinations):
    staged = []
    published = []
    try:
        for path in destinations:
            descriptor, name = tempfile.mkstemp(prefix=".dense-ingest-", dir=path.parent)
            os.close(descriptor)
            staged.append(Path(name))
        data.write_h5ad(staged[0], compression="lzf")
        staged[1].write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        for path in staged:
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
        for temporary, destination in zip(staged, destinations):
            os.link(temporary, destination)
            published.append((destination, temporary.stat().st_dev, temporary.stat().st_ino))
    except BaseException:
        for destination, device, inode in published:
            try:
                current = destination.lstat()
                if current.st_dev == device and current.st_ino == inode:
                    destination.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for path in staged:
            path.unlink(missing_ok=True)


def run():
    options = parameters()
    source, output_path, report_path = paths()
    input_sha = digest(source)
    matrix, cell_ids, gene_ids, selected_separator, blank_records = read_matrix(source, options)
    data = ad.AnnData(X=matrix, obs=pd.DataFrame(index=pd.Index(cell_ids, name="cell_id")),
        var=pd.DataFrame(index=pd.Index(gene_ids, name="gene_symbol")))
    for parameter, column in [("sample_label", "sample"), ("condition_label", "condition")]:
        if options[parameter] is not None:
            data.obs[column] = options[parameter]
    data.layers["counts"] = data.X.copy()
    if options["min_genes"] or options["min_cells"]:
        import scanpy as sc

    if options["min_genes"]:
        sc.pp.filter_cells(data, min_genes=options["min_genes"])
    if options["min_cells"]:
        sc.pp.filter_genes(data, min_cells=options["min_cells"])
    if not data.n_obs or not data.n_vars:
        raise ContractError("dense ingest filters removed every cell or gene")
    if digest(source) != input_sha:
        raise ContractError("input changed during dense ingestion")
    retained_cells = set(data.obs_names)
    retained_genes = set(data.var_names)
    report = {"schema_version": "2.0", "operation": "dense_ingest", **options,
        "input_cells": len(cell_ids), "input_genes": len(gene_ids),
        "output_cells": data.n_obs, "output_genes": data.n_vars,
        "input_sha256": input_sha, "resolved_delimiter": selected_separator,
        "input_cell_ids": cell_ids, "input_gene_ids": gene_ids,
        "output_cell_ids": data.obs_names.tolist(), "output_gene_ids": data.var_names.tolist(),
        "excluded_cell_ids": [value for value in cell_ids if value not in retained_cells],
        "excluded_gene_ids": [value for value in gene_ids if value not in retained_genes],
        "headerless_synthetic_column_ids": not options["has_header"], "ignored_blank_records": blank_records,
        "numeric_storage": "int64 exact; no normalization, species mapping or ID repair",
        "gene_identifier_semantics": "Literal input IDs; gene_symbol index name is not symbol validation",
        "versions": {name: importlib.metadata.version(name) for name in ["anndata", "scanpy", "numpy", "pandas"]},
        "scientific_input_qualification": False, "G0": False,
        "publication": "No overwrite; ordinary inode-specific rollback, not multi-file crash atomicity or persistent resume"}
    publish(data, report, [output_path, report_path])


def main():
    try:
        run()
    except (ContractError, csv.Error, OSError, UnicodeError, ValueError) as error:
        print(f"dense_ingest: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
