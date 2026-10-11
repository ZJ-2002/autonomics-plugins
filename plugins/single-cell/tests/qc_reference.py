"""Independent explicit author-package QC recipe; never imports the node."""

import json
from pathlib import Path
import re
import sys
import warnings

import anndata as ad
import numpy as np
import scanpy as sc
from scipy import sparse


def reference(directory: Path) -> None:
    assert sc.__version__ == "1.11.3" and ad.__version__ == "0.11.4"
    settings = json.loads((directory / "request.json").read_text())
    data = ad.read_h5ad(directory / "input.h5ad")
    if data.X.dtype.kind in "biu":
        data.X = data.X.astype(np.int64)
    if sparse.issparse(data.X):
        data.X = sparse.csr_matrix(data.X)
        data.X.sum_duplicates()
        data.X.eliminate_zeros()
    for label in ["mt", "rb"]:
        data.var[label] = data.var_names.str.contains(settings[label + "_gene_pattern"], case=False, regex=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sc.pp.calculate_qc_metrics(data, qc_vars=["mt", "rb"], expr_type="counts", var_type="genes",
                                  percent_top=None, log1p=False, layer=None, use_raw=False, inplace=True)
        cells, _ = sc.pp.filter_cells(data.X, min_genes=settings["min_genes"], inplace=False)
        if settings["max_genes"]:
            upper, _ = sc.pp.filter_cells(data.X, max_genes=settings["max_genes"], inplace=False)
            cells &= upper
        for label in ["mt", "rb"]:
            if settings["max_pct_" + label] < 100:
                cells &= data.obs["pct_counts_" + label].le(settings["max_pct_" + label]).to_numpy()
        data = data[cells, :].copy()
        genes, counts = sc.pp.filter_genes(data.X, min_cells=settings["min_cells"], inplace=False)
        if settings["max_cells"]:
            upper, _ = sc.pp.filter_genes(data.X, max_cells=settings["max_cells"], inplace=False)
            genes &= upper
        data.var["n_cells"] = counts
        data = data[:, genes].copy()
    data.uns["qc_params"] = settings
    data.write_h5ad(directory / "fresh-author.h5ad", compression="lzf")
    (directory / "fresh-author.json").write_text(json.dumps({
        "module_paths": {"scanpy": sc.__file__, "anndata": ad.__file__},
        "official_versions": {"scanpy": sc.__version__, "anndata": ad.__version__},
        "warnings": [str(warning.message) for warning in caught],
        "shape": list(data.shape), "independent_node_imports": False, "G0": False}, indent=2) + "\n")


if __name__ == "__main__":
    reference(Path(sys.argv[1]))
