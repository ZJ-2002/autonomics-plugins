#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: test_deseq2_data_boundary.sh

Confirms that /work, /opt and /tmp carry no supplied pasilla acceptance fixture
and that /panels is absent. Official DESeq2 package example data are retained;
this check does not claim that the entire image contains no example datasets.

Environment:
  DESEQ2_IMAGE  Immutable image (default: manifest.toml reference)
EOF
}

root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
image=${DESEQ2_IMAGE:-$(python -c 'import sys,tomllib;print(tomllib.load(open(sys.argv[1],"rb"))["image"]["reference"])' "$root/manifest.toml")}
[[ "$image" =~ @sha256:[0-9a-f]{64}$ ]] || { echo 'Immutable image required' >&2; exit 1; }

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

command -v podman >/dev/null || {
  echo "missing required command: podman" >&2
  exit 1
}

podman run \
  --rm \
  --pull=never \
  --network=none \
  --read-only \
  --security-opt=no-new-privileges \
  --userns=keep-id \
  "--user=1000:1000" \
  "--tmpfs=/tmp:rw,nosuid,nodev" \
  --entrypoint sh \
  "$image" -c '
set -eu
test ! -d /panels
if find /work /opt /tmp -type f \
  \( -name "pasilla_gene_counts.tsv" \
  -o -name "pasilla_sample_metadata.tsv" \
  -o -name "pasilla_baseline.json" \) \
  | grep -q .; then
  echo "Execution directories unexpectedly contain supplied pasilla fixture data" >&2
  exit 1
fi
'

echo "Execution-directory data boundary validated; official package example data are not excluded."
