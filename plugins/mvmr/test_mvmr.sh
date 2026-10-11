#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  printf '%s\n' 'Runs actual MVMR wrapper contract tests against the cached manifest digest.' \
    'No network, image build, scientific admission or production deployment.'
  exit 0
fi
command -v podman >/dev/null
command -v python >/dev/null
image=$(python - "$root/manifest.toml" <<'PY'
import pathlib
import sys
import tomllib
print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text())['image']['reference'])
PY
)
podman image exists "$image"
export MVMR_TEST_IMAGE="$image"
python "$root/tests/test_contract.py" -v
