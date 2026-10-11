#!/usr/bin/env bash
set -euo pipefail

plugin_root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
command -v podman >/dev/null
command -v python >/dev/null
: "${LIMMA_BOUNDARY_EVIDENCE:?Set a new evidence directory; missing evidence must not silently skip tests}"
if [[ -z ${LIMMA_BOUNDARY_IMAGE:-} ]]; then
  LIMMA_BOUNDARY_IMAGE=$(python -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1],"rb"))["image"]["reference"])' "$plugin_root/manifest.toml")
fi
[[ "$LIMMA_BOUNDARY_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]
export LIMMA_BOUNDARY_IMAGE LIMMA_BOUNDARY_EVIDENCE
export LIMMA_BOUNDARY_BAKED=1
podman run --rm --pull=never --network=none --entrypoint Rscript "$LIMMA_BOUNDARY_IMAGE" --vanilla -e '
  stopifnot(getRversion() == "4.5.3", packageVersion("limma") == "3.66.0",
    packageVersion("edgeR") == "4.8.2", packageVersion("statmod") == "1.5.2")
'
python -m unittest discover -s "$plugin_root/tests" -p 'test_limma_boundaries.py' -v
