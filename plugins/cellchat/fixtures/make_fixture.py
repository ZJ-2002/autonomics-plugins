#!/usr/bin/env python3
"""Tiny fixture for the CellChat tier-1 node: 3 clusters, real CellChatDB
ligand/receptor genes planted with source-cluster ligand and target-cluster
receptor up-regulation, then normalized with the OFFICIAL CellChat formula
(log1p(x / cell_total * 1e4)) because CellChat consumes normalized data
(unlike CellPhoneDB, which consumes raw counts). Output: sparse-CSR h5ad.

Run inside any image with anndata/scipy (e.g. the cellphonedb plugin image):
  podman run --rm --network host -v <dir>:/out python3 make_fixture.py /out/fixture.h5ad
"""
import sys

import numpy as np
import pandas as pd
import scipy.sparse as sp
import anndata as ad

rng = np.random.default_rng(7)

# Real hgnc symbols present in CellChatDB.human.
LR_GENES = [
    "TGFB1", "TGFBR1", "TGFBR2", "IL6", "IL6R", "IL6ST",
    "CXCL12", "CXCR4", "MIF", "CD74", "CCL2", "CCR2",
    "FLT1", "VEGFA", "EGF", "EGFR", "WNT5A", "FZD5",
]
FILLER = [f"GENE{i:03d}" for i in range(80)]
genes = LR_GENES + FILLER

n_per = 80
clusters = ["T_cells", "Macrophages", "Fibroblasts"]
counts = rng.poisson(1.2, size=(n_per * len(clusters), len(genes))).astype(np.float32)

# Signal: ligand up in source cluster, receptor up in target cluster.
def up(gene, cluster, factor=14):
    ci = clusters.index(cluster)
    gi = genes.index(gene)
    counts[ci * n_per:(ci + 1) * n_per, gi] += rng.poisson(factor, size=n_per).astype(np.float32)

up("TGFB1", "Fibroblasts"); up("TGFBR1", "T_cells"); up("TGFBR2", "T_cells")
up("IL6", "Macrophages"); up("IL6R", "T_cells"); up("IL6ST", "T_cells")
up("CXCL12", "Fibroblasts"); up("CXCR4", "T_cells")
up("MIF", "Macrophages"); up("CD74", "Macrophages")
up("VEGFA", "Fibroblasts"); up("FLT1", "Macrophages")
up("EGF", "Fibroblasts"); up("EGFR", "Macrophages")
up("CCL2", "Macrophages"); up("CCR2", "T_cells")

# Official CellChat normalization: log1p(t(t(X)/colSums(X))*10000), kept
# sparse so the h5ad ships CSR (the driver reads X sparsely).
# --raw skips it and ships integer counts, exercising the driver's
# normalized=auto raw-detection branch (and normalized=raw).
raw = "--raw" in sys.argv
if raw:
    X = sp.csr_matrix(counts.astype(np.float32))
else:
    totals = counts.sum(axis=1)
    norm = np.log1p(counts / totals[:, None] * 10000.0)
    X = sp.csr_matrix(norm.astype(np.float32))

obs_cluster = [c for c in clusters for _ in range(n_per)]
adata = ad.AnnData(
    X=X,
    obs=pd.DataFrame({"cluster": pd.Categorical(obs_cluster, categories=clusters)}),
    var=pd.DataFrame(index=pd.Index(genes, dtype=str)),
)
adata.obs_names = [f"cell_{i:04d}" for i in range(adata.n_obs)]

out = sys.argv[1] if len(sys.argv) > 1 else "/workdir/fixture.h5ad"
adata.write_h5ad(out)
state = "raw integer counts" if raw else "log1p-normalized"
print(f"fixture: {adata.n_obs} cells x {adata.n_vars} genes, "
      f"X={type(X).__name__}, {state} -> {out}")
