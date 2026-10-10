Scoped official UCell adapter for Autonomics

Canonical repository: https://github.com/ZJ-2002/ucell-plugin
Renamed from cachexia-ucell-plugin on 2026-10-10 to reflect the generic
method. The repository rename does not alter the validated wrapper,
manifest plugin_name, node kind, image identity or frozen deployments.
The historical cachexia-ucell installation name remains for compatibility;
it denotes verification origin, not a disease-specific scoring algorithm.

This independent plugin calls UCell 2.16.0, not an approximate Python rank
score. It is an opt-in route and does not replace or certify the existing
single-cell/h5ad_ucell_score implementation. The two TSV inputs and four
output ports are specified in manifest.toml. All three method parameters
are required; no research threshold, mapping or null model is invented.

Status: source publication and bounded technical validation only.
Independent scientific approval, full-scale H5AD/donor inference, resident
daemon integration and G0 remain ungranted. The H5AD bridge is a separate
adapter; this repository itself accepts gene-by-cell TSV, not H5AD.

Image: ghcr.io/zj-2002/cachexia-ucell-official at the manifest digest.
At publication the GHCR package is PRIVATE; authorized credentials are
required. A public Git repository does not make its container public.
The registry manifest digest differs from the historical local manifest
after upload; the image configuration digest must remain
8509399c2da611964946f480595c552f2969888edb5c54dc9d05d74de6fe9f9b.
No frozen production plugin configuration is changed by this publication.

Install explicitly with plugin name cachexia-ucell, this repository URL,
and a full commit revision after deployment approval. The family has one
kind: cachexia_ucell_official. Reject missing/duplicate identities, invalid
parameters and undefined official scores; retain failure logs.

Build inputs: source-lock.json records official archives and hashes.
Run python scripts/download_sources.py --output /new/build/context; copy
Containerfile there, then build that context. This is a pinned-source
recipe, not a claim to reproduce image bytes across future build systems.

Checks:
  python -m unittest discover -s tests -p 'test_contract.py' -v
  Run tests/official_container_v2.R using the pinned image, mounting this
  repository read-only at /plugin and a writable tmpfs at /tmp. This
  compares the actual wrapper against a separate direct official call.
  It is not an independent human scientific review or a complete DAG.
  The first probe, official_container.R, is retained as a failed test
  design: it assumed insertion-order signatures although the wrapper
  emits sorted signature names. Version 2 explicitly checks that exact
  declared name set/order and aligns the independent official reference
  by those names, without changing numerical tolerance or wrapper code.

Historical bounded H5AD connected-route evidence is indexed in the main
Autonomics repository under docs/audits/cachexia-v4.1-2026-10-07 and
study_plugins/cachexia-ucell-h5ad. Those local run artifacts are not
claimed to be downloadable from this repository. Original sealed evidence
is not rewritten for publication.
