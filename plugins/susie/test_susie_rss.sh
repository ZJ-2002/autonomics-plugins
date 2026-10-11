#!/usr/bin/env bash
set -euo pipefail

root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
command -v python3 >/dev/null
command -v podman >/dev/null
: "${SUSIE_TEST_EVIDENCE:?Set a new absolute evidence directory}"
: "${SUSIE_REFERENCE_LIBRARY:?Set the separately installed pinned author package library}"
[[ "$SUSIE_TEST_EVIDENCE" = /* && "$SUSIE_REFERENCE_LIBRARY" = /* ]]
[[ -f "$SUSIE_REFERENCE_LIBRARY/susieR/DESCRIPTION" ]]
podman image exists ghcr.io/zj-2002/susie@sha256:b1df377e428e6166cd8ac65ac3e131c46c3bb68f172969c0e0f910751792d87e
python3 "$root/tests/test_contract.py"
