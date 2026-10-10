#!/usr/bin/env bash
# WO-R-02 parity gate: replay the three seed1 canonical edges (XM, XY, MY)
# through scripts/mrlap.sh and compare every 17-field summary value against
# the frozen WOE4_mrlap_summary_seed1.tsv.
#
#   default          host R mode: uses the canonical host library
#                    (MRlap 0.0.3.3 / GenomicSEM 0.0.5 / TwoSampleMR 0.7.11
#                    exactly as the seed1 acceptance environment)
#   MRLAP_CONTAINER=1  container mode: runs inside MRLAP_IMAGE with the
#                    LD assets bind-mounted at /panels/ldsc_assets
#                    (tolerance stays at 1e-12; container BLAS may move
#                    the last bits — a failure there is information, not
#                    a reason to loosen the gate silently)
set -euo pipefail
root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
FEEDS=${MRLAP_FEEDS:-/home/zj-normal/.autonomics/data/artifacts/gwas_iv_audit/exec/mrlap_feeds}
ASSETS=${MRLAP_LDSC_ASSETS:-/home/zj-normal/tools/genetics/ldsc_assets}
REF=${MRLAP_REF:-/home/zj-normal/Work/autonomics/results/cachexia-v4/acceptance-mrlap-seed1-20261006/exec/WOE4_mrlap_summary_seed1.tsv}
IMAGE=${MRLAP_IMAGE:-localhost/mrlap-official:0.0.3.3}
RLIBS=${R_LIBS_USER:-/home/zj-normal/R/library}
work=$(mktemp -d /tmp/mrlap-parity.XXXXXX)
trap 'rm -rf "$work"' EXIT

# edge: exposure outcome ivlist labels
edges=(
  "X.tsv M.tsv x39_ivs.txt BMFF Monocyte"
  "X.tsv Y7526.tsv x39_ivs.txt BMFF GripStrength"
  "M.tsv Y7526.tsv m475_ivs.txt Monocyte GripStrength"
)

run_edge() { # $1=idx(0-based)
  local i=$1
  local out=$work/edge_$i
  mkdir -p "$out"
  read -r exp outc iv le lo <<< "${edges[$i]}"
  if [[ "${MRLAP_CONTAINER:-0}" == 1 ]]; then
    podman run --rm --network=none \
      -v "$FEEDS":/work/feeds:ro \
      -v "$ASSETS":/panels/ldsc_assets:ro \
      -v "$root/scripts/mrlap.sh":/work/mrlap.sh:ro \
      -v "$out":/work/run \
      -e AUTONOMICS_INPUT0=/work/feeds/$exp \
      -e AUTONOMICS_INPUT1=/work/feeds/$outc \
      -e AUTONOMICS_INPUT2=/work/feeds/$iv \
      -e AUTONOMICS_OUTPUT0=/work/run/summary.tsv \
      -e AUTONOMICS_OUTPUT1=/work/run/mrlap.RDS \
      -e AUTONOMICS_OUTPUT2=/work/run/mrlap.txt \
      -e AUTONOMICS_OUTPUT3=/work/run/mrlap.log \
      -e MRLAP_EXPOSURE="$le" -e MRLAP_OUTCOME="$lo" -e MRLAP_SEED=1 \
      --entrypoint Rscript "$IMAGE" /work/mrlap.sh > "$out/stdout.log" 2>&1
  else
    env R_LIBS_USER="$RLIBS" \
      AUTONOMICS_INPUT0="$FEEDS/$exp" AUTONOMICS_INPUT1="$FEEDS/$outc" \
      AUTONOMICS_INPUT2="$FEEDS/$iv" \
      AUTONOMICS_OUTPUT0="$out/summary.tsv" AUTONOMICS_OUTPUT1="$out/mrlap.RDS" \
      AUTONOMICS_OUTPUT2="$out/mrlap.txt" AUTONOMICS_OUTPUT3="$out/mrlap.log" \
      MRLAP_EXPOSURE="$le" MRLAP_OUTCOME="$lo" MRLAP_SEED=1 \
      MRLAP_LD_PATH="$ASSETS/eur_w_ld_chr" MRLAP_HM3_PATH="$ASSETS/w_hm3.noMHC.snplist" \
      Rscript --vanilla "$root/scripts/mrlap.sh" > "$out/stdout.log" 2>&1
  fi
  echo "[done] edge $i ($le->$lo)"
}

run_edge 0; run_edge 1; run_edge 2

python3 - "$REF" "$work" <<'PYEOF'
import sys, csv
ref_path, work = sys.argv[1], sys.argv[2]
with open(ref_path) as f:
    ref = list(csv.DictReader(f, delimiter="\t"))
FIELDS = [k for k in ref[0].keys() if k != "edge"]
TOL = 1e-12
bad = 0
for i, row in enumerate(ref):
    with open(f"{work}/edge_{i}/summary.tsv") as f:
        got = list(csv.DictReader(f, delimiter="\t"))[0]
    for fld in FIELDS:
        a, b = row[fld], got[fld]
        if a == "NA" or b == "NA":
            ok = (a == b)
        else:
            try:
                ok = abs(float(a) - float(b)) <= TOL
            except ValueError:
                ok = a == b
        if not ok:
            print(f"FAIL edge{i} {fld}: ref={a} got={b}")
            bad += 1
print("PARITY PASS" if bad == 0 else f"PARITY FAIL ({bad} field(s))")
sys.exit(1 if bad else 0)
PYEOF
