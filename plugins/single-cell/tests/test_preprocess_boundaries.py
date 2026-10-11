"""Actual baked-runner refusal and ordinary publication-rollback tests."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from test_preprocess_container import execute


MATRIX = "%%MatrixMarket matrix coordinate integer general\n2 2 2\n1 1 1\n2 2 2\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    options = parser.parse_args()
    options.evidence.mkdir(exist_ok=False)
    cases = [
        ("negative-integer", "matrix.mtx", MATRIX.replace("1 1 1\n", "1 1 -1\n"), "negative expression"),
        ("integer-decimal", "matrix.mtx", MATRIX.replace("1 1 1\n", "1 1 1.5\n"), "non-integer value"),
        ("integer-range", "matrix.mtx", MATRIX.replace("1 1 1\n", "1 1 9007199254740993\n"), "exact float64 range"),
        ("integer-sum-range", "matrix.mtx", MATRIX.replace("1 1 1\n", "1 1 9007199254740992\n"), "exact float64 range"),
        ("negative-real", "matrix.mtx", MATRIX.replace("integer", "real").replace("1 1 1\n", "1 1 -1\n"), "finite and nonnegative"),
        *[("real-" + value, "matrix.mtx", MATRIX.replace("integer", "real").replace("1 1 1\n", "1 1 " + value + "\n"), "finite and nonnegative")
          for value in ["NaN", "Inf", "-Inf", "1e400"]],
        ("real-text", "matrix.mtx", MATRIX.replace("integer", "real").replace("1 1 1\n", "1 1 word\n"), "invalid real"),
        ("matrix-banner-prefix", "matrix.mtx", MATRIX.replace("%%MatrixMarket", "%%MatrixMarketFake"), "not a MatrixMarket"),
        *[("matrix-field-" + field, "matrix.mtx", MATRIX.replace("integer", field), "unsupported MatrixMarket") for field in ["double", "complex", "pattern"]],
        ("matrix-symmetric", "matrix.mtx", MATRIX.replace("general", "symmetric"), "unsupported MatrixMarket"),
        ("matrix-array", "matrix.mtx", MATRIX.replace("coordinate", "array"), "expected MatrixMarket"),
        ("matrix-axis-zero", "matrix.mtx", MATRIX.replace("2 2 2", "0 2 2"), "axes must be nonempty"),
        ("matrix-coordinate-zero", "matrix.mtx", MATRIX.replace("1 1 1\n", "0 1 1\n"), "outside declared axes"),
        ("matrix-coordinate-large", "matrix.mtx", MATRIX.replace("1 1 1\n", "3 1 1\n"), "outside declared axes"),
        ("matrix-too-few", "matrix.mtx", MATRIX.replace("2 2 2\n", "2 2 3\n", 1), "coordinate count"),
        ("matrix-too-many", "matrix.mtx", MATRIX.replace("2 2 2\n", "2 2 1\n", 1), "more coordinates"),
        ("matrix-ragged", "matrix.mtx", MATRIX.replace("1 1 1\n", "1 1 1 EXTRA\n"), "malformed coordinate"),
        ("barcode-extra", "barcodes.tsv", "A\twrong\nB\twrong\n", "exactly one column"),
        ("barcode-duplicate", "barcodes.tsv", "A\nA\n", "duplicate cell IDs"),
        ("barcode-empty", "barcodes.tsv", "A\n\n", "blank rows"),
        ("barcode-padded", "barcodes.tsv", "A \nB\n", "identifier is empty"),
        ("barcode-NUL", "barcodes.tsv", "A\0\nB\n", "contains NUL"),
        ("feature-ragged", "features.tsv", "001\tG1\n002\tG2\tGene Expression\n", "inconsistent column"),
        ("feature-duplicate-id", "features.tsv", "001\tG1\n001\tG2\n", "duplicate gene IDs"),
        ("feature-empty-symbol", "features.tsv", "001\t\n002\tG2\n", "identifier is empty"),
        ("feature-four-columns", "features.tsv", "001\tG1\ttype\textra\n002\tG2\ttype\textra\n", "two or three columns"),
        ("metadata-duplicate-header", "metadata.tsv", "cell_id\tdonor\tdonor\nA\tx\ty\nB\tx\ty\n", "duplicate column headers"),
        ("metadata-ragged", "metadata.tsv", "cell_id\tdonor\nA\tx\textra\nB\ty\n", "inconsistent column"),
        ("metadata-duplicate-cell", "metadata.tsv", "cell_id\tdonor\nA\tx\nA\ty\n", "duplicate cell IDs"),
        ("metadata-mismatch", "metadata.tsv", "cell_id\tdonor\nA\tx\nC\ty\n", "do not align"),
        ("metadata-NUL", "metadata.tsv", "cell_id\tdonor\nA\tx\0\nB\ty\n", "contains NUL"),
        ("metadata-no-data", "metadata.tsv", "cell_id\nA\nB\n", "at least one data column"),
        ("metadata-path-header", "metadata.tsv", "cell_id\tdonor/id\nA\tx\nB\ty\n", "HDF5 path separator"),
        ("output-existing", None, None, "overwrite existing output"),
        ("output-directory", None, None, "overwrite existing output"),
        ("output-dangling-link", None, None, "overwrite existing output"),
        ("outputs-same", None, None, "output paths collide"),
        ("output-input", None, None, "output paths collide"),
        ("invalid-separator", None, None, "metadata_separator"),
        ("invalid-operation", None, None, "unsupported operation"),
        ("negative-filter", None, None, "nonnegative integer"),
        ("fraction-filter", None, None, "nonnegative integer"),
        ("invalid-normalize", None, None, "must be a boolean"),
        ("inspect-filter", None, None, "require operation `ingest`"),
        ("all-cells-filtered", None, None, "no cells or genes remain"),
        ("all-genes-filtered", None, None, "no cells or genes remain"),
        ("ordinary-publication-rollback", None, None, "injected second publication error"),
    ]
    records = []
    for name, mutated, content, fragment in cases:
        directory = options.evidence / name
        directory.mkdir()
        inputs = {"matrix.mtx": MATRIX, "barcodes.tsv": "A\nB\n", "features.tsv": "001\tG1\n002\tG2\n",
                  "metadata.tsv": "cell_id\tdonor\nA\tx\nB\ty\n"}
        if mutated:
            inputs[mutated] = content
        for filename, payload in inputs.items():
            (directory / filename).write_text(payload)
        environment = dict(os.environ, AUTONOMICS_INPUT0=str(directory / "matrix.mtx"),
            AUTONOMICS_INPUT1=str(directory / "barcodes.tsv"), AUTONOMICS_INPUT2=str(directory / "features.tsv"),
            AUTONOMICS_INPUT3=str(directory / "metadata.tsv"), AUTONOMICS_OUTPUT0=str(directory / "report.json"),
            AUTONOMICS_OUTPUT1=str(directory / "output.h5ad"), AUTONOMICS_SINGLE_CELL_OPERATION="ingest",
            AUTONOMICS_SINGLE_CELL_METADATA_SEP="auto", AUTONOMICS_SINGLE_CELL_MIN_GENES="0",
            AUTONOMICS_SINGLE_CELL_MIN_CELLS="0", AUTONOMICS_SINGLE_CELL_NORMALIZE_TOTAL="false")
        protected = None
        if name == "output-existing":
            protected = directory / "output.h5ad"
            protected.write_bytes(b"old-evidence")
        if name == "output-directory":
            (directory / "report.json").mkdir()
        if name == "output-dangling-link":
            (directory / "output.h5ad").symlink_to(directory / "absent.h5ad")
        overrides = {
            "outputs-same": {"AUTONOMICS_OUTPUT0": str(directory / "output.h5ad")},
            "output-input": {"AUTONOMICS_OUTPUT1": str(directory / "matrix.mtx")},
            "invalid-separator": {"AUTONOMICS_SINGLE_CELL_METADATA_SEP": "spaces"},
            "invalid-operation": {"AUTONOMICS_SINGLE_CELL_OPERATION": "auto"},
            "negative-filter": {"AUTONOMICS_SINGLE_CELL_MIN_GENES": "-1"},
            "fraction-filter": {"AUTONOMICS_SINGLE_CELL_MIN_GENES": "1.5"},
            "invalid-normalize": {"AUTONOMICS_SINGLE_CELL_NORMALIZE_TOTAL": "maybe"},
            "inspect-filter": {"AUTONOMICS_SINGLE_CELL_OPERATION": "inspect", "AUTONOMICS_SINGLE_CELL_MIN_GENES": "1"},
            "all-cells-filtered": {"AUTONOMICS_SINGLE_CELL_MIN_GENES": "10"},
            "all-genes-filtered": {"AUTONOMICS_SINGLE_CELL_MIN_CELLS": "10"},
        }
        environment.update(overrides.get(name, {}))
        command = [sys.executable, "/opt/autonomics/preprocess.py"]
        if name == "ordinary-publication-rollback":
            program = "import sys,os;sys.path.insert(0,'/opt/autonomics');import preprocess;original=os.link\n" \
                      "def injected(source,destination):\n" \
                      " if str(destination).endswith('report.json'):raise OSError('injected second publication error')\n" \
                      " return original(source,destination)\n" \
                      "os.link=injected;raise SystemExit(preprocess.main())"
            command = [sys.executable, "-c", program]
        result = execute(command, directory, "baked-runner", environment)
        if result.returncode == 0 or fragment not in result.stderr.decode():
            raise AssertionError(name + " was not specifically refused: " + result.stderr.decode())
        if (directory / "report.json").is_file():
            raise AssertionError("Failed run published a normal JSON report")
        if (directory / "output.h5ad").is_file() and name != "output-existing":
            raise AssertionError("Failed run published an H5AD")
        if protected and protected.read_bytes() != b"old-evidence":
            raise AssertionError("Old evidence overwritten")
        if list(directory.glob(".preprocess-*")):
            raise AssertionError("Ordinary failure retained private staging directories")
        records.append({"case": name, "specific_refusal": fragment, "exit": result.returncode,
                        "normal_outputs_not_published": True, "G0": False})
        print(name, "PASS", flush=True)
    (options.evidence / "SUMMARY.json").write_text(json.dumps({"cases": len(records), "records": records,
        "scope": "actual baked runner; ordinary injected error is not a crash/recovery/concurrency test",
        "scientific_release": "NOT_GRANTED", "G0": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
