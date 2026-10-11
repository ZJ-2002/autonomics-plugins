"""Real declared-script execution compared with separately installed author wheels."""

import argparse
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

from qc_compare import compare


FAMILY = Path(__file__).resolve().parents[1]
DEFAULTS = {"min_genes": 0, "max_genes": 0, "min_cells": 0, "max_cells": 0,
            "max_pct_mt": 100., "max_pct_rb": 100., "mt_gene_pattern": "^MT-",
            "rb_gene_pattern": "^RPL|^RPS"}
BASE = np.array([[0, 0, 0, 0, 0, 0], [1, 2, 0, 0, 0, 0], [1, 0, 3, 0, 0, 0],
                 [0, 0, 0, 5, 0, 0], [1, 2, 3, 4, 0, 0], [1, 1, 1, 1, 2, 0]], dtype=float)


def fixture(directory, variant="dense"):
    values = BASE.copy()
    data = ad.AnnData(values, obs=pd.DataFrame({"donor": ["0001", "NA", "炎症", "01", "NA", "01"],
        "condition": pd.Categorical(["A", "B", "A", "B", "A", "B"])},
        index=["0001", "NA", "炎症", "cell D", "E", "F"]),
        var=pd.DataFrame({"feature_id": [f"id-{index}" for index in range(6)]},
                         index=["MT-A", "rplB", "G", "RPSC", "MT-D", "EMPTY"]))
    data.layers["counts"] = sparse.csr_matrix(values)
    data.layers["signed_derived_not_QC_source"] = values - 8
    data.obsm["coordinates"] = np.arange(12).reshape(6, 2)
    data.varm["loadings"] = np.arange(12).reshape(6, 2)
    data.obsp["graph"] = sparse.eye(6, format="csr")
    data.varp["graph"] = sparse.eye(6, format="csr")
    data.uns["frozen_history"] = {"scope": "SYNTHETIC_TECHNICAL_NOT_QUALIFIED_COHORT", "literal": "NA"}
    if variant in ["csr", "csc"]:
        data.X = getattr(sparse, variant + "_matrix")(values)
    elif variant in ["int32", "int64", "float32"]:
        data.X = values.astype(variant)
    elif variant == "explicit-zero":
        data.X = sparse.csr_matrix(([0., 1., 2., 1., 3.], ([1, 1, 1, 2, 2], [2, 0, 1, 0, 2])), shape=(6, 6))
    elif variant == "duplicate-coordinates":
        data.X = sparse.csr_matrix((np.array([1., 2., 1., 3.]), np.array([0, 0, 1, 2]),
                                    np.array([0, 2, 4, 4, 4, 4, 4])), shape=(6, 6))
    elif variant == "raw-wider":
        data.raw = data.copy()
        data = data[:, :4].copy()
    elif variant == "raw-narrower":
        data.raw = data[:, :2].copy()
    elif variant == "fractional":
        data.X = values / 4
    elif variant == "precision-16777217":
        data.X = values.astype(np.int64)
        data.X[1, 0] = 16777217
    elif variant == "large-int64":
        data.X = values.astype(np.int64)
        data.X[1, 0] = 2**53 + 1
    elif variant == "large-total-valid":
        data.X = np.zeros_like(values, dtype=np.int64)
        for index in range(3):
            data.X[index, index] = 2**62
    elif variant == "boolean-matrix":
        data.X = values.astype(bool)
    elif variant == "csr-all-zero":
        data.X = sparse.csr_matrix(data.shape, dtype=float)
    elif variant == "int32-duplicate-sum":
        data.X = sparse.csr_matrix((np.array([2**30, 2**30], dtype=np.int32), np.array([0, 0]),
                                    np.array([0, 2, 2, 2, 2, 2, 2])), shape=data.shape)
    elif variant == "all-zero":
        data.X = np.zeros_like(values)
    elif variant == "reordered":
        data = data[[5, 3, 1, 4, 2, 0], [4, 1, 5, 0, 3, 2]].copy()
    elif variant != "dense":
        raise AssertionError(variant)
    data.write_h5ad(directory / "input.h5ad")


def environment(directory, settings):
    result = dict(os.environ, AUTONOMICS_INPUT0=str(directory / "input.h5ad"),
                  AUTONOMICS_OUTPUT0=str(directory / "output.h5ad"),
                  AUTONOMICS_OUTPUT1=str(directory / "report.json"))
    for name, value in settings.items():
        kind = "INT" if name in ["min_genes", "max_genes", "min_cells", "max_cells"] else \
               "NUM" if name.startswith("max_pct_") else "STR"
        result["SC_P_" + kind + "_" + name.upper()] = str(value)
    return result


def execute(command, directory, label, variables):
    started = time.monotonic()
    result = subprocess.run(command, env=variables, capture_output=True, timeout=180)
    (directory / (label + ".stdout.txt")).write_bytes(result.stdout)
    (directory / (label + ".stderr.txt")).write_bytes(result.stderr)
    (directory / (label + ".execution.json")).write_text(json.dumps({"command": command,
        "exit": result.returncode, "seconds": time.monotonic() - started, "G0": False}, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--reference-library", type=Path, required=True)
    parser.add_argument("--pbmc3k-file", type=Path)
    arguments = parser.parse_args()
    arguments.evidence.mkdir(exist_ok=False)
    cases = [(f"min-g{genes}-c{cells}", "dense", {"min_genes": genes, "min_cells": cells})
             for genes, cells in itertools.product([0, 1, 2, 3], [0, 1, 2])]
    cases += [(variant, variant, {}) for variant in ["csr", "csc", "int32", "int64", "float32",
        "explicit-zero", "duplicate-coordinates", "raw-wider", "raw-narrower", "fractional",
        "precision-16777217", "large-int64", "large-total-valid", "all-zero", "reordered",
        "boolean-matrix", "csr-all-zero", "int32-duplicate-sum"]]
    cases += [(name, "dense", settings) for name, settings in [
        ("max-genes", {"max_genes": 2}), ("max-cells", {"max_cells": 2}),
        ("mt-limit", {"max_pct_mt": 35}), ("rb-limit", {"max_pct_rb": 20}),
        ("mt-zero-limit", {"max_pct_mt": 0}), ("rb-zero-limit", {"max_pct_rb": 0}),
        ("both-percentages", {"max_pct_mt": 35, "max_pct_rb": 50}),
        ("all-bounds", {"min_genes": 1, "max_genes": 5, "min_cells": 1, "max_cells": 3}),
        ("regex-no-match", {"mt_gene_pattern": "^NOT_PRESENT$", "rb_gene_pattern": "^NOT_PRESENT$"}),
        ("regex-custom", {"mt_gene_pattern": "^G$", "rb_gene_pattern": "^EMPTY$"})]]
    if arguments.pbmc3k_file:
        cases.append(("official-pbmc3k", "pbmc3k", {"min_genes": 200, "min_cells": 3}))
    records = []
    for name, variant, changes in cases:
        directory = arguments.evidence / name
        directory.mkdir()
        if variant == "pbmc3k":
            shutil.copyfile(arguments.pbmc3k_file, directory / "input.h5ad")
        else:
            fixture(directory, variant)
        settings = {**DEFAULTS, **changes}
        for key in ["max_pct_mt", "max_pct_rb"]:
            settings[key] = float(settings[key])
        (directory / "request.json").write_text(json.dumps(settings, indent=2) + "\n")
        author_env = dict(os.environ, PYTHONPATH=str(arguments.reference_library))
        author = execute([sys.executable, str(FAMILY / "tests/qc_reference.py"), str(directory)], directory,
                         "fresh-author", author_env)
        node = execute([sys.executable, str(FAMILY / "scripts/qc_filter.py")], directory, "declared-node-script",
                       environment(directory, settings))
        if author.returncode or node.returncode:
            raise AssertionError(author.stderr.decode() + node.stderr.decode())
        checked = compare(directory)
        (directory / "CHECKS.json").write_text(json.dumps(checked, indent=2) + "\n")
        records.append({"case": name, **checked})
        print(name, "PASS", flush=True)
    (arguments.evidence / "SUMMARY.json").write_text(json.dumps({"cases": len(records), "records": records,
        "complete_cases_compared": True, "scientific_release": "NOT_GRANTED", "G0": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
