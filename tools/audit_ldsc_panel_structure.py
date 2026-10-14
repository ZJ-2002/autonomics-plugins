"""Inspect content-verified LDSC panel structure without selecting a study panel."""

import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import shutil


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_scores(path, chromosome):
    positions = {}
    with gzip.open(path, "rt", encoding="ascii") as stream:
        if stream.readline().split() != ["CHR", "SNP", "BP", "L2"]:
            raise RuntimeError("Exact basic LDSC score header required")
        for line in stream:
            fields = line.split()
            if (len(fields) != 4 or fields[0] != str(chromosome) or not fields[1]
                    or not fields[2].isdigit() or int(fields[2]) <= 0
                    or not math.isfinite(float(fields[3])) or fields[1] in positions):
                raise RuntimeError("Malformed, nonfinite or duplicate LDSC score row")
            positions[fields[1]] = int(fields[2])
            if len(positions) > 250000:
                raise RuntimeError("Chromosome exceeds admitted audit size")
    if not positions:
        raise RuntimeError("Empty chromosome score table")
    return positions


def compare_axes(reference, weight):
    shared = reference.keys() & weight.keys()
    if not shared:
        raise RuntimeError("Reference and weight panels have no common SNP")
    conflicts = [identifier for identifier in shared if reference[identifier] != weight[identifier]]
    if conflicts:
        raise RuntimeError("Same SNP has conflicting reference/weight coordinates")
    return dict(shared=len(shared), reference_only=len(reference.keys()-weight.keys()), weight_only=len(weight.keys()-reference.keys()))


def main():
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Managed validation required")
    archive = Path.home()/".local/state/autonomics/validation-archives/66c189d36d4144fe805ec617b8314244/artifacts"
    if digest(archive/"MANIFEST.json") != "b1034169ef0230f4c7ca66da2abe55e2611113a6617ff11ea2d8ecd24a65b6c2":
        raise RuntimeError("Exact complete panel-payload archive required")
    manifest = json.loads((archive/"MANIFEST.json").read_text())
    actual = {path.relative_to(archive).as_posix() for path in archive.rglob("*") if path.is_file() and path.name != "MANIFEST.json"}
    if actual != set(manifest["files"]):
        raise RuntimeError("Exact sealed payload membership required")
    for name, identity in manifest["files"].items():
        path = archive/name
        if path.is_symlink() or path.stat().st_size != identity["bytes"] or digest(path) != identity["sha256"]:
            raise RuntimeError("Actual sealed payload changed")
    source = archive/"permanent/ldsc-declared-panel-payloads"
    output = Path(permanent)/"ldsc-declared-panel-structure"
    output.mkdir()
    shutil.copyfile(Path(__file__),output/"driver.py")
    rows = []
    reference_ids = set()
    weight_ids = set()
    for chromosome in range(1,23):
        reference = read_scores(source/"ref_ld"/f"LDscore.{chromosome}.l2.ldscore.gz",chromosome)
        weight = read_scores(source/"w_ld"/f"weights.hm3_noMHC.{chromosome}.l2.ldscore.gz",chromosome)
        if reference_ids.intersection(reference) or weight_ids.intersection(weight):
            raise RuntimeError("Duplicate SNP identifier across chromosomes")
        reference_ids.update(reference)
        weight_ids.update(weight)
        counts = {}
        for suffix in ["M","M_5_50"]:
            fields = (source/"ref_ld"/f"LDscore.{chromosome}.l2.{suffix}").read_text().split()
            if len(fields) != 1 or not fields[0].isdigit() or int(fields[0]) <= 0:
                raise RuntimeError("Exact positive single-annotation M count required")
            counts[suffix] = int(fields[0])
        if counts["M_5_50"] > counts["M"]:
            raise RuntimeError("M_5_50 exceeds all-frequency M")
        rows.append(dict(chromosome=chromosome,reference_rows=len(reference),weight_rows=len(weight),**counts,**compare_axes(reference,weight)))
    report = dict(status="ALL_22_CHROMOSOME_SCHEMAS_COUNTS_AND_SHARED_COORDINATES_VERIFIED",chromosomes=rows,
                  reference_rows=len(reference_ids),weight_rows=len(weight_ids),source_archive_manifest_sha256=digest(archive/"MANIFEST.json"),
                  SNPs_filtered_or_reordered=False,author_distribution_origin_independently_proven=False,
                  production_cache_or_frozen_binding_changed=False,real_data_DAG_verified=False,g0_granted=False)
    with (output/"verification.json").open("x") as stream:
        json.dump(report,stream,indent=2)
    print(json.dumps(dict(chromosomes=len(rows),reference_rows=len(reference_ids),weight_rows=len(weight_ids),g0_granted=False)))


if __name__ == "__main__":
    main()
