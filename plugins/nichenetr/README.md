# nichenetr tier-① container node

Official-stack NicheNet ligand-activity node. The official R package runs
as-is; the driver does I/O translation only. Digest pins the official
algorithm AND the prior networks together.

| Pin | Value |
| --- | --- |
| Package | nichenetr **v2.2.0**, commit `f9906f3a51ddc09405a04ece9de375688e03facb` (2024-09-05; GitHub-only, no CRAN/Bioc release) |
| Base | `rocker/r-ver:4.4.1` (ubuntu 22.04 jammy) |
| CRAN deps | Posit PPM jammy **binary** snapshot `2024-10-01` (era-consistent: after the pin, before Bioc 3.20) |
| Bioc-only deps | ComplexHeatmap, rhdf5 (+Rhdf5lib) from **Bioc 3.20 source** — this PPM server exposes no `/bioc/` binaries path and its CRAN snapshots carry no Bioc packages |
| Priors | Zenodo record **7074291**, human nsga2r set; MD5-gated at build time |

## Node contract

`kind = "nichenetr_ligand_activity"` — see `manifest.toml`.

Inputs: expression h5ad (anndata; cells-x-genes or transposed, auto-detected)
+ a geneset file (one gene per line, first column taken if multi-column).
Params: `sender`/`receiver` (required, no defaults), `cluster_column`
(default `cluster`), `top_n_ligands` (30), `n_targets` (200), `pct` (0.10).

Outputs (workdir root): `nichenetr_ligand_activities.csv`
(test_ligand, auroc, aupr, aupr_corrected, pearson, rank),
`nichenetr_ligand_target_links.csv`, `nichenetr_ligand_receptor_links.csv`,
`nichenetr_top_ligands.csv`, `nichenetr_provenance.json`.

### Frozen pipeline (official manual path; matrix + metadata, no Seurat wrappers)

1. `convert_alias_to_symbols()` on gene names (skipping silently drops ~35
   ligand interactions known under aliases); alias rows are summed onto the
   official symbol
2. `get_expressed_genes(sender/receiver, pct = 0.10)`
3. background = receiver expressed genes ∩ prior targets
4. potential ligands = lr_network pairs with ligand expressed in the sender
   AND receptor expressed in the receiver
5. `predict_ligand_activities()` ranked by **aupr_corrected** (v2 convention,
   not the v1 pearson)
6. top-N ligands (default 30)
7. `get_weighted_ligand_target_links(n = 200)` per top ligand (official
   per-ligand idiom)
8. `get_weighted_ligand_receptor_links(..., weighted_networks$lr_sig)`

There is no nnls/PPR algorithm parameter on this path (the NSGA2R matrix is
read as baked) and no `prioritize_ligands` export upstream. Visualization
steps are not part of the pipeline. Human priors only in v1 (mouse not
baked). Deterministic: no RNG anywhere.

## Build

The vendor priors must already be in `vendor/` and MD5-verified — they are
never downloaded inside the build (see `vendor/download.log`; source: Zenodo
record 7074291):

```sh
cd vendor && md5sum -c zenodo_checksums.md5
cd .. && podman build --network host \
  --build-arg http_proxy=http://127.0.0.1:7890 \
  --build-arg https_proxy=http://127.0.0.1:7890 \
  --build-arg no_proxy=localhost,127.0.0.1 \
  -t nichenetr-official:v2.2.0-f9906f3a .
```

`install_packages.R` runs inside the build, writes
`/opt/autonomics/renv.lock`; export it and commit:

```sh
podman run --rm nichenetr-official:v2.2.0-f9906f3a cat /opt/autonomics/renv.lock > renv.lock.new
mv renv.lock.new renv.lock
```

## Offline e2e

```sh
fixtures/e2e_offline.sh nichenetr-official:v2.2.0-f9906f3a
```

The fixture signal is seeded from the official prior itself: an in-image R
step loads the baked ligand-target matrix, picks a ligand L whose top-50
prior targets give L rank 1 by aupr_corrected under the driver's exact
filtering, and the h5ad plants L in a sender cluster / its targets in a
receiver cluster. The acceptance asserts L lands in the top 3 — the
official prior plants it, the official method recovers it.

## License (GPL-3.0-only)

nichenetr is GPL-3 (grant in DESCRIPTION; upstream ships no LICENSE file).
The image carries the full GPL-3 text at `/usr/share/licenses/COPYING.GPLv3`
and the driver headers carry SPDX markers. This repository is the
Corresponding Source for the image: Dockerfile, install_packages.R,
renv.lock, and the pinned source tarball in
`vendor-src/nichenetr-f9906f3a….tar.gz` (sha256 in `vendor-src/`).
The Zenodo priors are distributed by their authors under their own terms
(Creative Commons, see the record); they are never re-hosted here —
`vendor/` is git-ignored, only the checksums are committed.
