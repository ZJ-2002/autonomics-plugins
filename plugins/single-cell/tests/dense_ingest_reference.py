import json
import os
from pathlib import Path
import sys

import anndata as ad
import numpy as np
import pandas as pd
import scanpy as sc


directory = Path(sys.argv[1])
prefix = Path(os.environ["SC_DENSE_REFERENCE_LIBRARY"]).resolve()
for module in [ad, np, pd, sc]:
    assert Path(module.__file__).resolve().is_relative_to(prefix), module.__file__
oracle = json.loads((directory / "oracle.json").read_text())
options = oracle["options"]
cells, genes = oracle["cells"], oracle["genes"]
if not options.get("has_header", True):
    if options["orientation"] == "cells_by_genes":
        genes = [str(index) for index in range(1, len(genes) + 1)]
    else:
        cells = [str(index) for index in range(1, len(cells) + 1)]
data = ad.AnnData(X=np.array(oracle["matrix"], dtype=np.int64),
    obs=pd.DataFrame(index=pd.Index(cells, name="cell_id")),
    var=pd.DataFrame(index=pd.Index(genes, name="gene_symbol")))
for parameter, column in [("sample_label", "sample"), ("condition_label", "condition")]:
    if options.get(parameter):
        data.obs[column] = options[parameter]
data.layers["counts"] = data.X.copy()
if options.get("min_genes", 0):
    sc.pp.filter_cells(data, min_genes=options["min_genes"])
if options.get("min_cells", 0):
    sc.pp.filter_genes(data, min_cells=options["min_cells"])
data.write_h5ad(directory / "fresh-author.h5ad", compression="lzf")
(directory / "fresh-author.json").write_text(json.dumps({"modules": {module.__name__: module.__file__ for module in [ad, np, pd, sc]},
    "scope": "Separate official imports from independently installed inherited read-only prefix, not node import or a new package installation",
    "G0": False}, indent=2) + "\n")
