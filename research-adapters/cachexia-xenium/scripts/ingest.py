"""Frozen 10x CSC ingestion without cell/feature identity or integer count loss."""

import contextlib
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

KEYS = {"schema_version", "scope", "test_id", "input_sha256", "cells_format", "x_col", "y_col", "barcode_col", "cell_id_col", "expected_cell_ids", "expected_matrix_barcodes", "expected_features", "expected_shape", "xoa_profile", "row_unit", "coordinate_unit", "quantitative_feature_type", "count_column_namespace", "duplicate_sparse_policy", "row_chunk", "max_dense_bytes", "max_nnz", "max_input_bytes", "metadata_policy", "source_pair_attestation"}
NAMES = ["gene_counts.parquet", "cells.parquet", "features.parquet", "xenium.log", "all_feature_counts.parquet", "audit.json", "request_ledger.tsv", "source_matrix.h5", "source_cells.bin"]
TYPES = {"Gene Expression", "Negative Control Codeword", "Negative Control Probe", "Genomic Control", "Unassigned Codeword", "Deprecated Codeword"}
MAX_COUNT = (1 << 64) - 1


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(filename):
    checksum = hashlib.sha256()
    with open(filename, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def lexical(value):
    return isinstance(value, str) and bool(value.strip()) and not any(char in value for char in ["\t", "\r", "\n", "\x00"])


def recover_test_id(raw):
    decoder, identifiers = json.JSONDecoder(), []
    cursor = len(raw) - len(raw.lstrip())
    if not raw[cursor:].startswith("{"):
        return None
    cursor += 1
    try:
        while True:
            while raw[cursor].isspace():
                cursor += 1
            if raw[cursor] == "}":
                break
            key, cursor = decoder.raw_decode(raw, cursor)
            if not isinstance(key, str):
                break
            while raw[cursor].isspace():
                cursor += 1
            if raw[cursor] != ":":
                break
            cursor += 1
            while raw[cursor].isspace():
                cursor += 1
            value, cursor = decoder.raw_decode(raw, cursor)
            if key == "test_id":
                identifiers.append(value)
            while raw[cursor].isspace():
                cursor += 1
            if raw[cursor] != ",":
                break
            cursor += 1
    except (ValueError, IndexError):
        pass
    return identifiers[0] if len(identifiers) == 1 and (identifiers[0] is None or isinstance(identifiers[0], str)) else None


def unique(values, name):
    require(isinstance(values, list) and bool(values) and all(lexical(value) for value in values) and len(set(values)) == len(values), "Distinct nonempty lexical " + name + " required")


def decode_json(filename):
    def pairs(items):
        answer = {}
        for key, value in items:
            require(key not in answer, "Duplicate JSON key: " + key)
            answer[key] = value
        return answer
    return json.loads(Path(filename).read_text(), object_pairs_hook=pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON constant")))


def validate(request):
    require(isinstance(request, dict) and set(request) == KEYS, "Exact frozen request keys required")
    require(type(request["schema_version"]) is int and request["schema_version"] == 1 and request["scope"] == "TECHNICAL_XENIUM_FORMAT_NOT_G0", "Unknown frozen schema/scope")
    require(lexical(request["test_id"]), "Frozen test_id required")
    require(type(request["input_sha256"]) is list and len(request["input_sha256"]) == 2 and all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in request["input_sha256"]), "Two frozen input SHA256 values required")
    require(request["cells_format"] in ["parquet", "csv", "csv.gz", "tsv"], "Unsupported cells format")
    for field in ["x_col", "y_col", "barcode_col", "cell_id_col"]:
        require(lexical(request[field]), "Frozen column identity required: " + field)
    require(request["x_col"] != request["y_col"] and not ({request["x_col"], request["y_col"]} & {request["barcode_col"], request["cell_id_col"]}), "Coordinate/identity columns must differ")
    unique(request["expected_cell_ids"], "cell universe")
    unique(request["expected_matrix_barcodes"], "matrix barcode universe")
    features = request["expected_features"]
    require(isinstance(features, list) and bool(features) and all(isinstance(feature, dict) and set(feature) == {"id", "name", "feature_type"} and all(lexical(value) for value in feature.values()) for feature in features), "Complete ordered frozen features required")
    require(request["xoa_profile"] in ["XOA3.2", "XOA4.0"], "Supported official XOA profile required")
    types = TYPES | ({"Protein Expression"} if request["xoa_profile"] == "XOA4.0" else set())
    require(all(feature["feature_type"] in types for feature in features), "Unsupported official feature_type for frozen profile")
    require(type(request["expected_shape"]) is list and all(type(value) is int for value in request["expected_shape"]) and request["expected_shape"] == [len(features), len(request["expected_matrix_barcodes"])] and len(request["expected_cell_ids"]) == len(request["expected_matrix_barcodes"]), "Frozen matrix dimensions differ")
    expected = {"row_unit": "CELL_NOT_DONOR_INFERENCE", "coordinate_unit": "MICROMETER_XOA_NATIVE_NO_TRANSFORM", "quantitative_feature_type": "Gene Expression", "count_column_namespace": "ORIGINAL_FEATURE_POSITION_F_PREFIX", "duplicate_sparse_policy": "SUM_EXACT_UINT64", "metadata_policy": "PRESERVE_ALL_TYPED_COLUMNS_NO_INFERENCE", "source_pair_attestation": "FROZEN_INPUT_PAIR_NOT_SCIENTIFIC_COHORT_QUALIFICATION"}
    require(all(request[key] == value for key, value in expected.items()), "Unsupported scientific/interface policy")
    for field in ["row_chunk", "max_dense_bytes", "max_nnz", "max_input_bytes"]:
        require(type(request[field]) is int and request[field] > 0, "Positive frozen resource bound required: " + field)


def text_dataset(group, name, expected_length):
    import h5py
    require(name in group and isinstance(group[name], h5py.Dataset) and group[name].ndim == 1 and len(group[name]) == expected_length and h5py.check_string_dtype(group[name].dtype) is not None, "One-dimensional HDF5 string dataset required: " + name)
    values = group[name].asstr(encoding="utf-8", errors="strict")[...].tolist()
    require(all(lexical(value) for value in values), "Nonempty lexical HDF5 identity required: " + name)
    return values


def read_cells(filename, request):
    import pyarrow as pa
    import pyarrow.parquet as pq
    if request["cells_format"] == "parquet":
        table = pq.read_table(filename)
    else:
        opener = gzip.open if request["cells_format"] == "csv.gz" else open
        with opener(filename, "rt", newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle, delimiter="\t" if request["cells_format"] == "tsv" else ",")
            header = next(reader)
            require(header and len(header) == len(set(header)) and all(lexical(name) for name in header), "Duplicate or empty cells columns")
            rows = list(reader)
        require(all(len(row) == len(header) for row in rows), "Ragged cells record")
        table = pa.Table.from_arrays([pa.array([row[position] for row in rows], type=pa.string()) for position in range(len(header))], names=header)
    require(table.num_rows > 0 and len(table.column_names) == len(set(table.column_names)) and all(lexical(name) for name in table.column_names), "Nonempty cells table with distinct columns required")
    for field in ["x_col", "y_col", "barcode_col", "cell_id_col"]:
        require(request[field] in table.column_names, "Missing cells column: " + request[field])
    for field in ["barcode_col", "cell_id_col"]:
        column = table.column(request[field])
        require(pa.types.is_string(column.type) or pa.types.is_large_string(column.type), "Cell/barcode identities must have lexical string types")
        unique(column.to_pylist(), field)
    for field in ["x_col", "y_col"]:
        column = table.column(request[field])
        if request["cells_format"] == "parquet":
            require(pa.types.is_integer(column.type) or pa.types.is_floating(column.type) or pa.types.is_decimal(column.type), "Coordinates must be numeric")
        require(all(value is not None and value != "" and not isinstance(value, bool) and math.isfinite(float(value)) for value in column.to_pylist()), "Coordinates must be finite and nonmissing")
    require(table.column(request["cell_id_col"]).to_pylist() == request["expected_cell_ids"], "Frozen cells order/universe differs")
    return table


def matrix(filename, request):
    import h5py
    import numpy as np
    import scipy.sparse as sp
    with h5py.File(filename, "r") as handle:
        require("matrix" in handle and isinstance(handle["matrix"], h5py.Group), "H5 has no matrix group")
        group = handle["matrix"]
        arrays = {}
        for name in ["shape", "data", "indices", "indptr"]:
            require(name in group and isinstance(group[name], h5py.Dataset) and group[name].ndim == 1 and group[name].dtype.kind in "ui", "One-dimensional integer CSC dataset required: " + name)
            expected_length = {"shape": 2, "data": None, "indices": len(arrays.get("data", [])), "indptr": request["expected_shape"][1] + 1}[name]
            require(expected_length is None or len(group[name]) == expected_length, "CSC dataset length differs: " + name)
            require(name != "data" or len(group[name]) <= request["max_nnz"], "Frozen max_nnz exceeded")
            arrays[name] = group[name][...]
        shape = [int(value) for value in arrays["shape"]]
        require(shape == request["expected_shape"] and len(shape) == 2 and all(value > 0 for value in shape), "Frozen CSC shape differs")
        features, cells = shape
        barcodes = text_dataset(group, "barcodes", cells)
        unique(barcodes, "matrix barcodes")
        require(barcodes == request["expected_matrix_barcodes"], "Frozen matrix barcode order differs")
        require("features" in group and isinstance(group["features"], h5py.Group), "H5 feature metadata group required")
        names = {name: text_dataset(group["features"], name, features) for name in ["id", "name", "feature_type"]}
        records = [dict(zip(names, row)) for row in zip(*names.values())]
        require(records == request["expected_features"], "Full ordered feature metadata differs")
        data, indices, pointers = [arrays[name] for name in ["data", "indices", "indptr"]]
        require(len(data) == len(indices) and len(pointers) == cells + 1 and len(pointers) > 0 and int(pointers[0]) == 0 and int(pointers[-1]) == len(data), "CSC data/indices/indptr lengths or endpoints differ")
        require(all(0 <= int(value) <= len(data) for value in pointers) and all(int(left) <= int(right) for left, right in zip(pointers, pointers[1:])), "CSC indptr must be monotone and in range")
        require(all(0 <= int(value) < features for value in indices), "CSC feature index out of range")
        require(all(0 <= int(value) <= MAX_COUNT for value in data), "CSC counts must be nonnegative uint64-representable integers")
        total = sum(int(value) for value in data)
        require(total <= MAX_COUNT, "Exact count sum exceeds uint64 output domain")
        decoded = sp.csc_matrix((data.astype(np.uint64), indices.astype(np.int64), pointers.astype(np.int64)), shape=tuple(shape))
        decoded.sum_duplicates()
        decoded.sort_indices()
        return decoded.T.tocsr(), barcodes, records, total, len(data) - decoded.nnz


def write_counts(counts, cell_ids, positions, filename, request):
    import pyarrow as pa
    import pyarrow.parquet as pq
    require(request["row_chunk"] * max(1, len(positions)) * 8 <= request["max_dense_bytes"], "Frozen dense chunk exceeds max_dense_bytes")
    schema = pa.schema([pa.field("cell_id", pa.string(), False)] + [pa.field("f" + str(position), pa.uint64(), False) for position in positions])
    with pq.ParquetWriter(filename, schema) as writer:
        for start in range(0, counts.shape[0], request["row_chunk"]):
            block = counts[start:start + request["row_chunk"], positions].toarray()
            columns = [pa.array(cell_ids[start:start + len(block)], type=pa.string())] + [pa.array(block[:, position], type=pa.uint64()) for position in range(len(positions))]
            writer.write_table(pa.Table.from_arrays(columns, schema=schema))


def calculate(inputs, request, folder):
    import pyarrow as pa
    import pyarrow.parquet as pq
    require(all(path.stat().st_size <= request["max_input_bytes"] for path in inputs), "Frozen max_input_bytes exceeded")
    require([digest(filename) for filename in inputs] == request["input_sha256"], "Frozen input content differs")
    cells = read_cells(inputs[1], request)
    counts, barcodes, features, total, duplicate_positions = matrix(inputs[0], request)
    cell_barcodes = cells.column(request["barcode_col"]).to_pylist()
    require(set(cell_barcodes) == set(barcodes), "H5/cells barcode universes differ")
    order = {value: position for position, value in enumerate(barcodes)}
    reordered = [order[value] for value in cell_barcodes]
    counts = counts[reordered]
    target = [position for position, feature in enumerate(features) if feature["feature_type"] == "Gene Expression"]
    cell_ids = cells.column(request["cell_id_col"]).to_pylist()
    write_counts(counts, cell_ids, target, folder / NAMES[0], request)
    write_counts(counts, cell_ids, list(range(len(features))), folder / NAMES[4], request)
    pq.write_table(cells, folder / NAMES[1])
    rows = []
    for position, feature in enumerate(features):
        column = counts[:, position]
        rows.append({"feature_position": position, "count_column": "f" + str(position), "feature_id": feature["id"], "feature_name": feature["name"], "feature_type": feature["feature_type"], "quantitative_gene_eligible": position in target, "total_counts": int(column.sum()), "n_cells": int((column > 0).sum())})
    schema = pa.schema([("feature_position", pa.uint64()), ("count_column", pa.string()), ("feature_id", pa.string()), ("feature_name", pa.string()), ("feature_type", pa.string()), ("quantitative_gene_eligible", pa.bool_()), ("total_counts", pa.uint64()), ("n_cells", pa.uint64())])
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), folder / NAMES[2])
    for filename, output in zip(inputs, NAMES[7:]):
        shutil.copy2(filename, folder / output)
    require([digest(filename) for filename in inputs] == request["input_sha256"], "Inputs changed during ingestion")
    print("Full CSC counts preserved; controls/protein excluded only from separate Gene Expression view.")
    return {"cells": len(cell_ids), "features": len(features), "gene_features": len(target), "all_feature_total_counts": total, "duplicate_sparse_entries_summed": duplicate_positions, "reordered_rows": sum(position != value for position, value in enumerate(reordered)), "original_metadata_schema": str(cells.schema), "official_segmentation_or_requantification_granted": False}


def json_file(filename, value):
    Path(filename).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def ledger(filename, test_id, status, error=""):
    with open(filename, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["test_id", "status", "error", "scientific_release"])
        writer.writerow([test_id or "UNKNOWN_UNRECOVERABLE_ID", status, error, "NOT_GRANTED"])


def main():
    inputs = [Path(os.environ["AUTONOMICS_INPUT" + str(position)]) for position in range(3)]
    outputs = [Path(os.environ.get("AUTONOMICS_OUTPUT" + str(position), "/work/" + name)) for position, name in enumerate(NAMES)]
    audit = {"status": "BLOCKED", "test_id": None, "G0_granted": False, "scientific_release_granted": False, "resident_deployment_granted": False, "statistical_official_layer": "NOT_APPLICABLE"}
    temporary, safe, published = None, False, []
    try:
        parent = outputs[0].parent
        require(parent.is_dir() and not parent.is_symlink() and len(set(outputs)) == len(outputs) and all(path.is_absolute() and path.parent == parent and path.name == name and not path.exists() and not path.is_symlink() for path, name in zip(outputs, NAMES)), "Unsafe or preexisting output paths")
        safe = True
        raw_text = inputs[2].read_text()
        audit["test_id"] = recover_test_id(raw_text)
        json_file(outputs[5], dict(audit, status="STARTED_NOT_VERIFIED"))
        request = decode_json(inputs[2])
        validate(request)
        temporary = Path(tempfile.mkdtemp(prefix="xenium-publication-", dir=parent))
        with (temporary / NAMES[3]).open("w") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            details = calculate(inputs[:2], request, temporary)
        ledger(temporary / NAMES[6], request["test_id"], "TECHNICAL_PASS_NOT_SCIENTIFIC")
        audit.update(details, status="TECHNICAL_PASS_NOT_SCIENTIFIC", request=request, request_sha256=digest(inputs[2]), input_sha256=[digest(filename) for filename in inputs], output_sha256={str(position): digest(temporary / NAMES[position]) for position in range(len(NAMES)) if position != 5})
        json_file(temporary / NAMES[5], audit)
        for position, name in enumerate(NAMES):
            (temporary / name).replace(outputs[position])
            published.append(outputs[position])
    except Exception as error:
        audit.update(status="BLOCKED", error=str(error))
        audit.pop("output_sha256", None)
        if safe:
            for filename in published:
                filename.unlink()
            json_file(outputs[5], audit)
            ledger(outputs[6], audit["test_id"], "BLOCKED", str(error))
            outputs[3].write_text(str(error) + "\n")
        else:
            print(json.dumps(audit), file=sys.stderr)
        print(str(error), file=sys.stderr)
        return 1
    finally:
        if temporary is not None:
            shutil.rmtree(temporary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
