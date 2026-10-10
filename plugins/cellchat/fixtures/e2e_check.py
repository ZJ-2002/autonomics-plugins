#!/usr/bin/env python3
"""Offline e2e acceptance checks for the CellChat tier-1 node.

Usage: python3 e2e_check.py <e2e-output-dir> [--variant full|secreted|raw-auto]

Verifies: exactly the 7 contract files, provenance content, and the planted
fixture signal (CXCL12 ligand up in Fibroblasts, CXCR4 receptor up in
T_cells => significant CXCL12-CXCR4 in the Fibroblasts->T_cells direction
and concentrated on the planted source/target pairs).

Variants: full (lognorm fixture, full DB), secreted (lognorm fixture,
db_scope=secreted => DB subset applied), raw-auto (integer-counts fixture,
normalized=auto => raw detected and official log1p applied in-container).
"""
import json
import os
import sys

import pandas as pd

CONTRACT = [
    "cellchat_lr_pairs.csv",
    "cellchat_pathway_probs.csv",
    "cellchat_net_count.csv",
    "cellchat_net_weight.csv",
    "cellchat_centrality.csv",
    "cellchat_object.rds",
    "cellchat_provenance.json",
]

# (ligand_source -> receptor_target) pairs planted in make_fixture.py
PLANTED_DIRECTIONS = [
    ("Fibroblasts", "T_cells"),      # TGFB1->TGFBR1/2, CXCL12->CXCR4, CCL2? no
    ("Macrophages", "T_cells"),      # IL6->IL6R/ST, CCL2->CCR2
    ("Fibroblasts", "Macrophages"),  # VEGFA->FLT1, EGF->EGFR
    ("Macrophages", "Macrophages"),  # MIF->CD74
]

def main():
    out = sys.argv[1]
    variant = "full" if "--variant" not in sys.argv else sys.argv[sys.argv.index("--variant") + 1]
    if variant not in ("full", "secreted", "raw-auto"):
        sys.exit(f"unknown variant {variant}")
    failures = []
    ok = lambda m: print(f"  PASS {m}")
    def check(cond, m):
        if cond: ok(m)
        else:
            failures.append(m); print(f"  FAIL {m}")

    print(f"e2e_check: {out} (variant={variant})")
    files = sorted(os.listdir(out))
    check(files == sorted(CONTRACT), f"exactly the 7 contract files (got {files})")

    prov = json.load(open(os.path.join(out, "cellchat_provenance.json")))
    check(prov["package_version"] == "2.2.0.9001", f"CellChat version pinned ({prov.get('package_version')})")
    check(prov["upstream"]["commit"] == "75253cd0c9e68410e6e721a6d3a0419a1d7e358f", "pinned commit in provenance")
    check(prov["presto"]["version"] == "1.1.0" and prov["presto"]["commit"] == "b5df6ee6097eb62522f2e557aa93ac21bab2d05f",
          "presto pinned in provenance")
    check(prov["upstream"]["source_tarball_sha256"] ==
          "52a90ce9f121acd58c9e5b2542956de0f3d81ac9b10906454847946f289e0739",
          "source tarball sha256 recorded")
    check(prov["cellchatdb"]["name"] == "CellChatDB.human", "DB name")
    check(set(prov["cellchatdb"]["versions"]) <= {"CellChatDB v1", "CellChatDB v2"}, "DB versions recorded")
    if variant == "secreted":
        check(prov["cellchatdb"]["interactions_after_scope_subset"] <
              prov["cellchatdb"]["interactions_before_scope_subset"], "secreted scope: DB subset applied")
    else:
        check(prov["cellchatdb"]["interactions_after_scope_subset"] ==
              prov["cellchatdb"]["interactions_before_scope_subset"], "full scope: no DB subset")
    p = prov["params"]
    expected_scope = "secreted" if variant == "secreted" else "full"
    check(p["species"] == "human" and p["db_scope"] == expected_scope, "params: species/db_scope")
    check(p["seed.use"] == 1 and p["type"] == "triMean" and p["raw.use"] is True, "params: frozen computeCommunProb")
    check(p["nboot"] == 100 and p["min.cells"] == 10 and p["pathway.thresh"] == 0.05, "params: nboot/min.cells/thresh")
    expected_norm = {
        "full": "auto_detected_lognorm_passed_through",
        "secreted": "auto_detected_lognorm_passed_through",
        "raw-auto": "auto_detected_raw_log1p_applied",
    }[variant]
    check(prov["normalization"]["decision"] == expected_norm,
          f"normalization decision ({prov['normalization'].get('decision')})")
    check(prov["future"]["workers"] == 4, "future workers recorded")
    check(prov["input"]["n_cells"] == 240 and prov["input"]["n_genes"] == 98, "input dims")
    check(prov["input"]["x_dense"] is False, "X stayed sparse")
    outs = prov["outputs"]
    check(set(outs) == set(CONTRACT) - {"cellchat_provenance.json"}, "provenance output list")
    check(all(int(outs[f]) == os.path.getsize(os.path.join(out, f)) for f in outs), "provenance sizes match")

    lr = pd.read_csv(os.path.join(out, "cellchat_lr_pairs.csv"))
    cols = set(lr.columns)
    need = {"source", "target", "interaction_name", "prob", "pval"}
    check(need <= cols, f"lr_pairs columns (got {sorted(cols)})")
    check((lr["pval"] < 0.05).all(), "all lr rows significant (official default thresh)")

    cx = lr[lr["interaction_name"].str.startswith("CXCL12") & (lr["interaction_name"].str.contains("CXCR4"))]
    fwd = cx[(cx["source"] == "Fibroblasts") & (cx["target"] == "T_cells")]
    check(len(fwd) == 1 and float(fwd.iloc[0]["pval"]) < 0.05,
          f"CXCL12_CXCR4 Fibroblasts->T_cells pval<0.05 (got {fwd.to_dict('records')})")
    rev = cx[(cx["source"] == "T_cells") & (cx["target"] == "Fibroblasts")]
    check(len(rev) == 0 or float(rev.iloc[0]["pval"]) >= 0.05 or float(rev.iloc[0]["prob"]) == 0.0,
          "reverse direction not significant")

    # significant rows concentrated on planted cell pairs
    pairs = set(zip(lr["source"], lr["target"]))
    check(pairs <= {(s, t) for s, t in PLANTED_DIRECTIONS} | {("T_cells", "T_cells")},
          f"significant pairs within planted directions (got {sorted(pairs)})")

    pw = pd.read_csv(os.path.join(out, "cellchat_pathway_probs.csv"))
    check(len(pw) > 0 and {"pathway_name", "prob", "pval"} <= set(pw.columns), "pathway probs non-empty")
    ncnt = pd.read_csv(os.path.join(out, "cellchat_net_count.csv"), index_col=0)
    check(ncnt.shape == (3, 3) and set(ncnt.index) == {"T_cells", "Macrophages", "Fibroblasts"},
          f"net_count 3x3 cluster matrix {ncnt.shape}")
    cen = pd.read_csv(os.path.join(out, "cellchat_centrality.csv"))
    check(set(cen.columns) == {"pathway", "measure", "cluster", "value"} and len(cen) > 0, "centrality long table")
    check({"outdeg", "indeg", "outdeg_unweighted", "betweenness", "hub"} <= set(cen["measure"]),
          "centrality measures present")
    check(os.path.getsize(os.path.join(out, "cellchat_object.rds")) > 1000, "cellchat object rds non-trivial")

    print(f"e2e_check: {'ALL GREEN' if not failures else f'{len(failures)} FAILURES'}")
    sys.exit(1 if failures else 0)

if __name__ == "__main__":
    main()
