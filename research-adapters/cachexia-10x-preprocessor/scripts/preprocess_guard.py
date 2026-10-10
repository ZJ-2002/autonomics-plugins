"""Lossless raw-count boundary around the pinned official-API ingestion pipeline."""

from contextlib import contextmanager
import csv
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys
import warnings


UPSTREAM_SHA256 = "ec93eb735eb6567c1d74d1295273948697276018e996370cf0334a2750f73d7e"
VERSIONS = {"scanpy": "1.11.3", "anndata": "0.11.4", "numpy": "2.1.3",
            "scipy": "1.14.1", "pandas": "2.2.3"}
MAX_EXACT = (1 << 53) - 1


class ContractError(RuntimeError):
    pass


def open_text(filename):
    filename = Path(filename)
    if filename.name.lower().endswith(".gz"):
        return gzip.open(filename, "rt", encoding="utf-8", newline="")
    return filename.open(encoding="utf-8", newline="")


def rows(filename, delimiter):
    with open_text(filename) as handle:
        values = list(csv.reader(handle, delimiter=delimiter, strict=True))
    if not values:
        raise ContractError("Companion table is empty")
    return values


def identifier(value):
    if not value or value.strip() != value or any(ord(character) < 32 for character in value):
        raise ContractError("Identifiers must be nonempty, unpadded lexical strings")
    return value


def barcodes(filename):
    values = rows(filename, "\t")
    if any(len(row) != 1 for row in values):
        raise ContractError("Barcode rows must contain exactly one field")
    ids = [identifier(row[0]) for row in values]
    if len(set(ids)) != len(ids):
        raise ContractError("Duplicate barcode IDs")
    return ids


def features(filename):
    values = rows(filename, "\t")
    width = len(values[0])
    if width not in (2, 3) or any(len(row) != width for row in values):
        raise ContractError("Feature rows must uniformly contain two or three fields")
    for row in values:
        identifier(row[0])
        identifier(row[1])
        if width == 3:
            identifier(row[2])
    if len({row[0] for row in values}) != len(values):
        raise ContractError("Duplicate feature IDs")
    return values


def metadata(filename, ordered_barcodes, delimiter):
    values = rows(filename, delimiter)
    header, records = values[0], values[1:]
    if len(header) < 2 or not records or any(len(row) != len(header) for row in records):
        raise ContractError("Metadata requires a rectangular header, cell ID and at least one value column")
    for value in header:
        identifier(value)
    if len(set(header)) != len(header):
        raise ContractError("Duplicate metadata column names")
    ids = [identifier(row[0]) for row in records]
    if len(set(ids)) != len(ids):
        raise ContractError("Duplicate metadata cell IDs")
    if set(ids) != set(ordered_barcodes):
        raise ContractError("Metadata cell IDs do not align with barcodes")
    by_id = {row[0]: row for row in records}
    return header, [by_id[cell_id] for cell_id in ordered_barcodes], ids == ordered_barcodes


def count_body(filename, expected_genes, expected_cells):
    with open_text(filename) as handle:
        banner = handle.readline().split()
        if banner not in (["%%MatrixMarket", "matrix", "coordinate", "integer", "general"],
                          ["%%MatrixMarket", "matrix", "coordinate", "real", "general"]):
            raise ContractError("Raw-count ingest requires a general integer/real coordinate MatrixMarket matrix")
        dimensions = next((line.split() for line in handle if line.strip() and not line.lstrip().startswith("%")), None)
        try:
            genes, cells, entries = map(int, dimensions or [])
        except ValueError as error:
            raise ContractError("Malformed matrix dimensions") from error
        if genes != expected_genes or cells != expected_cells or genes <= 0 or cells <= 0 or entries < 0:
            raise ContractError("Matrix dimensions do not match companion axes")
        totals = [0] * cells
        observed = 0
        for line in handle:
            if not line.strip() or line.lstrip().startswith("%"):
                continue
            tokens = line.split()
            if len(tokens) != 3:
                raise ContractError("Each matrix entry must have row, column and count")
            try:
                gene, cell = int(tokens[0]), int(tokens[1])
                count = Decimal(tokens[2])
            except (ValueError, InvalidOperation) as error:
                raise ContractError("Malformed matrix entry") from error
            if not 1 <= gene <= genes or not 1 <= cell <= cells:
                raise ContractError("Matrix coordinate is outside its axes")
            if not count.is_finite() or count < 0 or count != count.to_integral_value() or count > MAX_EXACT:
                raise ContractError("Ingest requires finite, nonnegative, exactly representable integer counts")
            totals[cell - 1] += int(count)
            if totals[cell - 1] > MAX_EXACT:
                raise ContractError("Cell library total exceeds exact Float64 integer range")
            observed += 1
        if observed != entries:
            raise ContractError("Matrix stored-entry count differs from its declared NNZ")
    return {"stored_entries_checked": observed, "exact_cell_totals": totals,
            "input_profile": "RAW_INTEGER_COUNTS_FLOAT64_EXACT", "body_verified": True}


def load_upstream(filename):
    filename = Path(filename)
    if hashlib.sha256(filename.read_bytes()).hexdigest() != UPSTREAM_SHA256:
        raise ContractError("Pinned baked preprocess.py source identity differs")
    spec = importlib.util.spec_from_file_location("cachexia_pinned_preprocess", filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def separator(filename):
    configured = os.environ.get("AUTONOMICS_SINGLE_CELL_METADATA_SEP", "auto").lower()
    if configured in ("tab", "comma"):
        return "\t" if configured == "tab" else ","
    if configured != "auto":
        raise ContractError("Unknown metadata separator")
    with open_text(filename) as handle:
        return "\t" if "\t" in handle.readline() else ","


@contextmanager
def guarded_readers(upstream, operation):
    original = {name: getattr(upstream, name) for name in ("read_barcodes", "read_features", "read_metadata", "_file_probe")}
    def read_barcodes(filename):
        return upstream.pd.DataFrame({"cell_barcode": barcodes(filename)}, dtype=str)
    def read_features(filename):
        values = features(filename)
        return upstream.pd.DataFrame(values, columns=["gene_id", "gene_symbol", "feature_type"][:len(values[0])], dtype=str)
    def read_metadata(filename, barcode_frame):
        header, records, preserved = metadata(filename, list(barcode_frame["cell_barcode"]), separator(filename))
        frame = upstream.pd.DataFrame(records, columns=header, dtype=str).set_index(header[0])
        return frame, preserved
    def probe(filename):
        with Path(filename).open("rb") as handle:
            preview = handle.read(512)
        return {"bytes": Path(filename).stat().st_size,
                "preview": preview.decode("utf-8", errors="replace").splitlines()[:3],
                "preview_line_count": preview.count(b"\n"), "probe_bytes_read": len(preview)}
    upstream.read_barcodes, upstream.read_features, upstream.read_metadata, upstream._file_probe = read_barcodes, read_features, read_metadata, probe
    scanpy = None
    try:
        if operation == "ingest":
            import scanpy
            original_read = scanpy.read_mtx
            scanpy.read_mtx = lambda filename: original_read(filename, dtype="float64")
        yield
    finally:
        for name, value in original.items():
            setattr(upstream, name, value)
        if scanpy is not None:
            scanpy.read_mtx = original_read


def run(upstream):
    actual = {name: importlib.metadata.version(name) for name in VERSIONS}
    if actual != VERSIONS:
        raise ContractError("Frozen method package versions differ")
    operation = os.environ.get("AUTONOMICS_SINGLE_CELL_OPERATION", "inspect").lower()
    report_path = upstream.required_path(upstream.REPORT_ENV)
    h5ad_path = upstream.required_path(upstream.H5AD_ENV)
    if report_path.resolve() == h5ad_path.resolve() or report_path.exists() or h5ad_path.exists():
        raise ContractError("Outputs must be distinct fresh paths, never stale evidence")
    matrix_path = upstream.required_path(upstream.MATRIX_ENV)
    barcode_ids = barcodes(upstream.required_path(upstream.BARCODES_ENV))
    feature_rows = features(upstream.required_path(upstream.FEATURES_ENV))
    body = count_body(matrix_path, len(feature_rows), len(barcode_ids)) if operation == "ingest" else {
        "body_verified": False, "input_profile": "HEADER_ONLY_NOT_ANALYSABLE_EXPRESSION"}
    with warnings.catch_warnings(record=True) as caught, guarded_readers(upstream, operation):
        warnings.simplefilter("always")
        report, report_path, h5ad_path = upstream._run()
    report["boundary_validation"] = body
    report["warnings"] = [f"{warning.category.__name__}: {warning.message}" for warning in caught]
    report["outputs"] = [{"name": h5ad_path.name, "sha256": upstream._sha256(h5ad_path), "bytes": h5ad_path.stat().st_size}]
    report["scope"] = "RAW_10X_INSPECT_OR_INGEST_NOT_COMPLETE_SINGLECELL_PREPROCESSING"
    report["scientific_release_granted"] = report["g0_granted"] = False
    report["method_packages"] = actual
    report["preprocess_source_sha256"] = UPSTREAM_SHA256
    upstream.write_report(report_path, report)


def main():
    try:
        run(load_upstream("/opt/autonomics/preprocess.py"))
    except Exception as error:
        print(f"cachexia_10x_preprocessor: {type(error).__name__}: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
