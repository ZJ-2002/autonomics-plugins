#!/usr/bin/env python3
"""Fixture generator, python half.

Reads fixture_spec.json emitted by make_fixture.R (which picked ligand L and
its top-50 prior targets FROM THE OFFICIAL PRIOR) and builds a standard
anndata H5AD:

  Sender     cluster: ligand L strongly expressed + low-level background
  Receiver   cluster: geneset genes + low-level background + one L receptor
  Bystander  cluster: low-level background only

Deterministic (fixed seed). Output: standard cells-x-genes float32 CSR h5ad.
"""
import json
import sys

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

SPEC = sys.argv[1] if len(sys.argv) > 1 else "/io/fixture_spec.json"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/io/fixture.h5ad"

with open(SPEC) as fh:
    spec = json.load(fh)

ligand = spec["ligand"]
receptor = spec["receptor"]
geneset = list(spec["geneset"])
background = list(spec["background"])
n_per = int(spec["n_cells_per_cluster"])

clusters = [
    spec["sender_cluster"],
    spec["receiver_cluster"],
    spec["bystander_cluster"],
]

genes = sorted({ligand, receptor, *geneset, *background} | {
    f"FILLER{i:03d}" for i in range(60)
})
gidx = {g: i for i, g in enumerate(genes)}

rng = np.random.default_rng(11)
counts = rng.poisson(0.0, size=(n_per * len(clusters), len(genes))).astype(np.float32)


def plant(gene, cluster, lam):
    ci = clusters.index(cluster)
    counts[ci * n_per:(ci + 1) * n_per, gidx[gene]] += rng.poisson(
        lam, size=n_per).astype(np.float32)


for g in background:
    plant(g, clusters[0], 0.5)   # sender: ambient background
    plant(g, clusters[1], 0.5)   # receiver: ambient background
    plant(g, clusters[2], 0.5)   # bystander: ambient background
plant(ligand, clusters[0], 8.0)          # sender: the ligand
for g in geneset:
    plant(g, clusters[1], 4.0)           # receiver: L's prior targets
plant(receptor, clusters[1], 3.0)        # receiver: one L receptor

obs = pd.DataFrame(
    {"cluster": pd.Categorical(
        [c for c in clusters for _ in range(n_per)], categories=clusters)},
    index=[f"cell_{i:04d}" for i in range(n_per * len(clusters))],
)
adata = ad.AnnData(
    X=sparse.csr_matrix(counts),
    obs=obs,
    var=pd.DataFrame(index=genes),
)
adata.write_h5ad(OUT)
print(f"fixture: {adata.n_obs} cells x {adata.n_vars} genes -> {OUT}")
print(f"fixture: ligand={ligand} receptor={receptor} "
      f"geneset={len(geneset)} background={len(background)}")
