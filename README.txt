Autonomics plugin monorepo — initial source migration

Engine: https://github.com/ZJ-2002/autonomics
Plugins: https://github.com/ZJ-2002/autonomics-plugins

plugins/ contains 26 independently installable plugin families.
research-adapters/ contains 48 opt-in research/reference adapters.
provenance/source-index.json records each original public repository,
published revision and imported file SHA256/Git blob identity.

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

Next: catalog validation/CI, isolated native installation/loading evidence,
and reviewable proposed profiles. Production cutover is not automatic.
