"""Direct author-package reference, without importing the plugin implementation."""

import argparse
import csv
import json
from pathlib import Path
import warnings

import anndata as ad
import numpy as np
import pandas as pd
import scanpy as sc


def reference(directory: Path) -> None:
    request = json.loads((directory / "request.json").read_text())
    with (directory / "barcodes.tsv").open() as handle:
        barcodes = [line.rstrip("\n\r") for line in handle]
    with (directory / "features.tsv").open() as handle:
        feature_rows = list(csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE))
    separator = request.get("delimiter", "\t")
    with (directory / "metadata.tsv").open(newline="") as handle:
        metadata_rows = list(csv.reader(handle, delimiter=separator))
    observations = pd.DataFrame([row[1:] for row in metadata_rows[1:]],
        columns=metadata_rows[0][1:],
        index=pd.Index([row[0] for row in metadata_rows[1:]], name=metadata_rows[0][0])).loc[barcodes]
    variables = pd.DataFrame(feature_rows,
        columns=["gene_id", "gene_symbol", "feature_type"][:len(feature_rows[0])])
    variables.index = pd.Index(variables["gene_symbol"], name="var_name")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        expected = ad.AnnData(obs=observations, var=variables)
        expected.var_names_make_unique()
        if request["operation"] == "ingest":
            author_matrix = sc.read_mtx(directory / request.get("matrix_file", "matrix.mtx"), dtype="float64")
            expected.X = author_matrix.X.T.tocsr()
            if request.get("min_genes", 0):
                sc.pp.filter_cells(expected, min_genes=request["min_genes"])
            if request.get("min_cells", 0):
                sc.pp.filter_genes(expected, min_cells=request["min_cells"])
            if request.get("normalize_total", False):
                expected.layers["counts"] = expected.X.copy()
                sc.pp.normalize_total(expected, target_sum=1e4, exclude_highly_expressed=False,
                                      key_added=None, inplace=True)
                sc.pp.log1p(expected, base=None)
                raw_counts = expected.layers["counts"].toarray()
                totals = raw_counts.sum(axis=1)
                divisors = np.where(totals > 0, totals, 1.0)
                mathematical = np.log1p(raw_counts * (10000.0 / divisors)[:, None])
                np.testing.assert_allclose(expected.X.toarray(), mathematical, rtol=0, atol=1e-12)
    expected.write_h5ad(directory / "fresh-author-reference.h5ad", compression="lzf")
    (directory / "fresh-author-reference.json").write_text(json.dumps({
        "author_module_paths": {"anndata": ad.__file__, "scanpy": sc.__file__},
        "warnings": [f"{warning.category.__name__}: {warning.message}" for warning in caught],
        "rows": expected.n_obs, "columns": expected.n_vars,
        "mathematical_normalization_checked": bool(request.get("normalize_total")),
        "scientific_release": "NOT_GRANTED", "G0": False}, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    reference(parser.parse_args().directory)
