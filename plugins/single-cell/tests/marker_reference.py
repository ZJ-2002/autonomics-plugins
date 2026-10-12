from collections import Counter
from decimal import Decimal, localcontext
import json
import os
from pathlib import Path
import sys

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse


root = Path(sys.argv[1])
prefix = Path(os.environ["MARKER_REFERENCE_LIBRARY"]).resolve()
for module in [ad, np, pd]:
    assert Path(module.__file__).resolve().is_relative_to(prefix)
request = json.loads((root / "request.json").read_text())
data = ad.read_h5ad(root / "input.h5ad")
raw = data.X
exact = [[Decimal(0) for column in range(data.n_vars)] for row in range(data.n_obs)]
if sparse.issparse(raw):
    coordinates = raw.tocoo(copy=False)
    for row, column, value in zip(coordinates.row, coordinates.col, coordinates.data):
        scalar = Decimal(int(value)) if raw.dtype.kind in "biu" else Decimal.from_float(float(value))
        exact[int(row)][int(column)] += scalar
else:
    for row in range(data.n_obs):
        for column in range(data.n_vars):
            value = raw[row, column]
            exact[row][column] = Decimal(int(value)) if raw.dtype.kind in "biu" else Decimal.from_float(float(value))
names = list(request["marker_sets"])
positions = {str(gene): index for index, gene in enumerate(data.var_names)}
scores = []
precise_scores = []
with localcontext() as context:
    context.prec = 100
    for row in exact:
        if request["normalize"] == "log_cp10k":
            total = sum(row, Decimal(0))
            row = [(Decimal(1) + value / total * 10000).ln() if total else Decimal(0) for value in row]
        precise = [sum((row[positions[gene]] for gene in request["marker_sets"][name] if gene in positions), Decimal(0)) /
            sum(gene in positions for gene in request["marker_sets"][name]) for name in names]
        precise_scores.append(precise)
        scores.append([float(value) for value in precise])
labels, selected, margins, fallbacks = [], [], [], []
clusters = {}
groups = data.obs[request["groupby"]].astype(str).tolist() if request.get("groupby") else None
for row in range(data.n_obs):
    own = scores[row]
    if groups is None:
        decision = own
    else:
        members = [index for index, group in enumerate(groups) if group == groups[row]]
        with localcontext() as context:
            context.prec = 100
            decision = [float(sum((precise_scores[index][column] for index in members), Decimal(0)) / len(members)) for column in range(len(names))]
    chosen = max(range(len(names)), key=lambda column: decision[column])
    fallback = decision[chosen] <= request["min_score"]
    label = request["unknown_label"] if fallback else names[chosen]
    labels.append(label)
    selected.append(max(own) if fallback else own[chosen])
    alternatives = [value for index, value in enumerate(decision) if index != chosen]
    margins.append(decision[chosen] - max(alternatives) if alternatives else decision[chosen])
    fallbacks.append(fallback)
    if groups is not None:
        clusters[groups[row]] = {"label": label, "n_cells": groups.count(groups[row]), "scores": decision}
data.obs["marker_label"] = np.array(labels)
data.obs["marker_score"] = np.array(selected, dtype=np.float64)
data.obs["marker_margin"] = np.array(margins, dtype=np.float64)
data.uns["marker_annotate_params"] = {"normalize": request["normalize"], "groupby": request.get("groupby"),
    "min_score": float(request["min_score"]), "unknown_label": request["unknown_label"]}
data.write_h5ad(root / "reference.h5ad", compression="lzf")
(root / "reference.json").write_text(json.dumps({"labels": labels, "selected_scores": selected,
    "margins": margins, "fallback_count": sum(fallbacks), "cluster_scores": clusters,
    "label_counts": dict(Counter(labels)), "candidate_scores": scores,
    "module_paths": {module.__name__: module.__file__ for module in [ad, np, pd]},
    "reference_kind": "Independent Decimal100 arithmetic and official AnnData container preservation; not an official classifier", "G0": False}, indent=2) + "\n")

