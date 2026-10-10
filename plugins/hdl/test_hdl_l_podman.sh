#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: test_hdl_l_podman.sh

Builds the official HDL-L image and runs the rootless-Podman smoke baseline.
No registry, cluster, or full 1.8 GiB UKB panel is required.

Environment:
  AUTONOMICS_HDL_IMAGE   Local OCI tag (default: localhost/atc/hdl:1.4.3)
  AUTONOMICS_PODMAN_PROGRAM
                         Podman executable (default: podman)
  AUTONOMICS_REPO_ROOT   Autonomics workspace holding the nodes-io
                         integration tests (default:
                         /mnt/projects/autonomics_projects/autonomics)
  BUILD_IMAGE=0          Skip image build
  RUN_TEST=0             Skip the Rust integration test
EOF
}

# root is the hdl plugin directory (this script was moved here from the
# legacy containers/hdl-l/ tree alongside the Dockerfile).
root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# The Rust integration tests still live in the autonomics workspace until
# the hdl_l/hdl_l_scan wrappers are deleted there.
repo_root=${AUTONOMICS_REPO_ROOT:-/mnt/projects/autonomics_projects/autonomics}
image=${AUTONOMICS_HDL_IMAGE:-localhost/atc/hdl:1.4.3}
build_image=${BUILD_IMAGE:-1}
run_test=${RUN_TEST:-1}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

need() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "missing required command: $1" >&2
    exit 1
  }
}

need cargo
need podman

if [[ "$build_image" == 1 ]]; then
  podman build -f "$root/Dockerfile" -t "$image" \
    "$root"
fi

version_output=$(podman run --rm "$image" -e '
  cat(
    "HDL", as.character(packageVersion("HDL")),
    "data.table", as.character(packageVersion("data.table")),
    "dplyr", as.character(packageVersion("dplyr")),
    "\n"
  )
')
if ! grep -q 'HDL 1.4.3 data.table 1.18.4 dplyr 1.2.1' \
  <<<"$version_output"; then
  echo "unexpected HDL image versions: $version_output" >&2
  exit 1
fi

if [[ "$run_test" == 1 ]]; then
  export AUTONOMICS_HDL_IMAGE=$image
  export AUTONOMICS_PODMAN_PROGRAM=${AUTONOMICS_PODMAN_PROGRAM:-podman}
  (cd "$repo_root" && cargo test -p nodes-io --test container_file_flow \
    real_official_hdl_l_runs_in_podman_with_local_panel \
    -- --ignored --nocapture)
fi

echo "HDL-L official Podman smoke completed successfully."
