#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
#
# Offline end-to-end acceptance for the nichenetr tier-1 image.
#
#   fixtures/e2e_offline.sh <image[:tag]> [run-dir]
#
# 1. make_fixture.R runs INSIDE the image: picks ligand L whose top-50 prior
#    targets rank it 1 by aupr_corrected under the driver's exact filtering,
#    and writes fixture_spec.json / geneset.txt / expected.json.
# 2. make_fixture.py (host venv with anndata) builds the planted h5ad.
# 3. The driver runs with --network none and NO mounts other than inputs and
#    the output workdir: exit code 0, exactly 5 outputs, L in the top 3 by
#    aupr_corrected, provenance verified field by field.
set -euo pipefail

IMAGE="${1:?usage: e2e_offline.sh <image[:tag]> [run-dir]}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN="$(dirname "$HERE")"
RUN="${2:-$HERE/e2e-run}"
VENV="${NNET_FIXTURE_VENV:-/tmp/nnet-fixture-venv}"

rm -rf "$RUN"
mkdir -p "$RUN/inputs" "$RUN/out"
FIX="$RUN/inputs"

cp "$HERE/make_fixture.R" "$FIX/make_fixture.R"
echo "== e2e[1/4] fixture R half (in-image, seeds signal from the prior)"
podman run --rm --pull=never --entrypoint Rscript -v "$FIX":/io:Z "$IMAGE" \
  /io/make_fixture.R 2>&1 | tee "$RUN/fixture-R.log"
test -s "$FIX/fixture_spec.json"
test -s "$FIX/geneset.txt"
test -s "$FIX/expected.json"

echo "== e2e[2/4] fixture python half (host venv + anndata)"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q anndata scipy
fi
"$VENV/bin/python" "$HERE/make_fixture.py" "$FIX/fixture_spec.json" \
  "$FIX/fixture.h5ad" 2>&1 | tee "$RUN/fixture-py.log"

echo "== e2e[3/4] driver, network isolated"
set +e
podman run --rm --pull=never --network none \
  -v "$FIX":/inputs:ro,Z -v "$RUN/out":/workdir:Z \
  -e AUTONOMICS_INPUT0=/inputs/fixture.h5ad \
  -e AUTONOMICS_INPUT1=/inputs/geneset.txt \
  -e AUTONOMICS_WORKDIR=/workdir \
  -e NNET_SENDER=Sender -e NNET_RECEIVER=Receiver \
  -e NNET_CLUSTER_COLUMN=cluster \
  -e NNET_TOP_N_LIGANDS=30 -e NNET_N_TARGETS=200 -e NNET_PCT=0.1 \
  --entrypoint Rscript "$IMAGE" /opt/autonomics/driver.R >"$RUN/driver.log" 2>&1
rc=$?
set -e
echo "driver exit code: $rc (log: $RUN/driver.log)"
tail -20 "$RUN/driver.log"
test "$rc" -eq 0

echo "== e2e[4/4] assertions"
python3 - "$RUN" "$PLUGIN" <<'PY' 2>&1 | tee "$RUN/assert.log"
import json, sys

run, plugin = sys.argv[1], sys.argv[2]
out = f"{run}/out"
import pandas as pd

failures = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not cond:
        failures.append(name)

import os
files = sorted(os.listdir(out))
check("exactly 5 outputs",
      files == ["nichenetr_ligand_activities.csv",
                "nichenetr_ligand_receptor_links.csv",
                "nichenetr_ligand_target_links.csv",
                "nichenetr_provenance.json",
                "nichenetr_top_ligands.csv"],
      f"got {files}")

expected = json.load(open(f"{run}/inputs/expected.json"))
act = pd.read_csv(f"{out}/nichenetr_ligand_activities.csv")
cols = list(act.columns)
check("activities columns",
      cols == ["test_ligand", "auroc", "aupr", "aupr_corrected", "pearson",
               "rank"], f"got {cols}")
row = act[act.test_ligand == expected["ligand"]]
rank = int(row["rank"].iloc[0]) if len(row) else None
check(f"ligand {expected['ligand']} rank<= {expected['expect_rank_le']}",
      rank is not None and rank <= expected["expect_rank_le"],
      f"rank={rank} aupr_corrected={float(row['aupr_corrected'].iloc[0]) if len(row) else None}")

top = pd.read_csv(f"{out}/nichenetr_top_ligands.csv")
check("top ligands <= 30 rows", 0 < len(top) <= 30, f"{len(top)} rows")

lt = pd.read_csv(f"{out}/nichenetr_ligand_target_links.csv")
lr = pd.read_csv(f"{out}/nichenetr_ligand_receptor_links.csv")
check("ligand-target links non-empty", len(lt) > 0, f"{len(lt)} rows")
check("ligand-receptor links non-empty", len(lr) > 0, f"{len(lr)} rows")
check("planted ligand in receptor links",
      len(lr[lr["from"] == expected["ligand"]]) > 0,
      f"{len(lr[lr['from'] == expected['ligand']])} pairs")

prov = json.load(open(f"{out}/nichenetr_provenance.json"))
check("provenance package_version",
      prov["package_version"] == "2.2.0", prov["package_version"])
check("provenance commit",
      prov["nichenetr_commit"] == "f9906f3a51ddc09405a04ece9de375688e03facb",
      prov["nichenetr_commit"])
vendor_md5 = {}
for line in open(f"{plugin}/vendor/zenodo_checksums.md5"):
    h, f = line.split()
    vendor_md5[f] = h
prior_md5 = {p["file"]: p["md5"] for p in prov["priors"]}
check("provenance prior MD5s match vendor checksums",
      prior_md5 == vendor_md5, f"{prior_md5}")
check("provenance params echo",
      prov["params"]["sender"] == "Sender"
      and prov["params"]["receiver"] == "Receiver"
      and prov["params"]["top_n_ligands"] == 30
      and prov["params"]["n_targets"] == 200
      and prov["params"]["pct"] == 0.1
      and prov["params"]["ranking_metric"] == "aupr_corrected",
      json.dumps(prov["params"]))
check("provenance geneset source",
      prov["geneset_source"] == "geneset.txt", prov["geneset_source"])
check("provenance outputs list matches files",
      sorted(prov["outputs"]) == files, str(prov["outputs"]))

if failures:
    print(f"ASSERTIONS FAILED: {failures}")
    sys.exit(1)
print("ALL ASSERTIONS PASSED")
PY

echo "e2e: ALL GREEN (run dir: $RUN)"
