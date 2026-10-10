Autonomics plugin monorepo — initial source migration

Engine: https://github.com/ZJ-2002/autonomics
Plugins: https://github.com/ZJ-2002/autonomics-plugins

plugins/ contains 26 independently installable plugin families.
research-adapters/ contains 48 opt-in research/reference adapters.
provenance/source-index.json records each original public repository,
published revision and imported file SHA256/Git blob identity.
shared-image-sources/ also preserves the two recipes from plugin-images;
its separate provenance file records the original published master revision.
These legacy recipes have mutable package/base inputs: preserving them is
not evidence of reproducible image rebuilding or newly accepted images.

This first commit is a byte-preserving SOURCE MIGRATION, not deployment or
scientific acceptance. Some selected sources were already published on fix/*
branches rather than their old default branch; the index states both revisions.
Original repositories and histories are retained, not deleted or archived.

The engine's git + rev + subdir installer is being validated separately.
Each family retains its own manifest, scripts, dependencies, image and panels.
Do not install all research adapters together: some intentionally overlap kinds.
An image reference is not a guarantee of anonymous pull access; the UCell
image currently requires authorized GHCR access. Local-only research images
and unresolved method/data contracts remain unresolved after migration.

No production plugins.toml, daemon, frozen study configuration, hypothesis
family, scientific sign-off or G0 status is changed by this migration.
Source consolidation does not certify any method or grant formal-study use.

Catalog management (Python 3.11+, standard library only)

  python -m tools.catalog check
  python -m tools.run_checks --output artifacts/catalog-checks.json
  python -m tools.catalog verify-import

release-lock.json records CURRENT family sources, image references and node
inventory. After intentional source changes, refresh it explicitly, review
the entire diff and update method-specific evidence before releasing:

  python -m tools.catalog refresh

source-index.json is the initial migration baseline; do not rewrite historical
origin records merely because a current source has changed. verify-import is
a migration check, not a perpetual requirement to keep the code unchanged.
Catalog checks do not execute any R/Python method or supply certification.
CI runs every required catalog test and fails for missing, extra, skipped or
failed cases, a zero-test run or a changed release-lock. Existing method tests
are kept within each family, not silently counted as having executed by CI.

Generate an explicitly selected, proposed installation profile:

  python -m tools.catalog profile --rev <full-40-hex-commit> \
    --families ucell single-cell --output proposed-plugins.toml

The output must be a NEW file. It does not replace ~/.autonomics/plugins.toml.
The engine needs git+rev+subdir support before this profile can be loaded.
Keep individual plugin image pins and acceptance boundaries; the monorepo
does not require a giant combined image or force every family to be enabled.

New source changes should be made here and accompanied by their current
release-lock and method-specific evidence. Old repositories remain available
for frozen pins/history; any necessary backport must be explicit and recorded,
not an independently evolving second source of truth. Do not edit the engine's
shared pinned checkout. Use a local path source for development.

Deployment boundary: isolated native installation/loading evidence and
reviewable proposed profiles are separate from production cutover. The frozen
production configuration and running daemon have NOT been migrated.
