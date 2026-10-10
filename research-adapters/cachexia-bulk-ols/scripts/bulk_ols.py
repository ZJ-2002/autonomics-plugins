import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys


def read_table(path):
    with Path(path).open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        columns = reader.fieldnames
        if not columns or len(set(columns)) != len(columns):
            raise ValueError("empty or duplicate columns")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError("malformed TSV row")
    return columns, rows


def prepare(matrix_columns, matrix_rows, metadata, request):
    if request.get("expression_scale") != "log2_normalized":
        raise ValueError("only declared log2_normalized bulk expression is supported; not counts")
    lock = request["contrast_lock"]
    if lock.get("design_formula") != "expression ~ condition":
        raise ValueError("only frozen expression ~ condition is supported")
    if not lock.get("contrast_id") or not lock.get("exposure_status"):
        raise ValueError("contrast identity and exposure history are required")
    if not request.get("unit_column"):
        raise ValueError("independent-unit column must be declared")
    unit_column = request["unit_column"]
    samples = [row["sample_id"] for row in metadata]
    units = [row[unit_column] for row in metadata]
    if (not samples or any(not value for value in samples + units)
            or len(set(samples)) != len(samples) or len(set(units)) != len(units)):
        raise ValueError("duplicate or empty sample/independent-unit identity; repeated data need a different model")
    if len(matrix_columns) < 2 or set(matrix_columns[1:]) != set(samples):
        raise ValueError("matrix and metadata sample identities must match exactly")
    case, control = request["case_condition"], request["control_condition"]
    if not case or not control or case == control:
        raise ValueError("case/control identities must be distinct")
    frozen_sizes = re.fullmatch(r"(\d+) case / (\d+) control \(donors; no pairing, no pooling\)",
                                lock["independent_units_per_arm"])
    if frozen_sizes is None:
        raise ValueError("frozen independent arm counts/qualification are not supported or not filled")
    cases = [row for row in metadata if row["condition"] == case]
    controls = [row for row in metadata if row["condition"] == control]
    if (len(cases), len(controls)) != tuple(map(int, frozen_sizes.groups())):
        raise ValueError("observed arms differ from frozen arm counts")
    if min(len(cases), len(controls)) < 3 or len(cases) + len(controls) <= 2:
        raise ValueError("insufficient independent units or residual degrees of freedom")
    genes = request["genes"]
    if not isinstance(genes, list) or not genes or any(not isinstance(gene, str) or not gene for gene in genes) or len(set(genes)) != len(genes):
        raise ValueError("selected gene IDs must be nonempty, unique strings")
    gene_column = matrix_columns[0]
    index = {}
    for row in matrix_rows:
        gene = row[gene_column]
        if not gene or gene in index:
            raise ValueError("empty or duplicate matrix gene ID")
        index[gene] = row
    if set(genes) - set(index):
        raise ValueError("selected gene is absent; mapping/coverage is not silently repaired")
    selected = [row for row in metadata if row["condition"] in (case, control)]
    prepared = []
    for gene in genes:
        for sample in selected:
            value = float(index[gene][sample["sample_id"]])
            if not math.isfinite(value):
                raise ValueError("selected expression is missing or nonfinite; no automatic donor deletion")
            prepared.append({"gene": gene, "sample": sample["sample_id"],
                             "condition": int(sample["condition"] == case), "expression": value})
    audit = {"contrast_id": lock["contrast_id"], "expression_scale": request["expression_scale"],
             "exposure_status": lock["exposure_status"], "design_formula": lock["design_formula"],
             "case": case, "control": control, "case_n": len(cases), "control_n": len(controls),
             "unit_column": unit_column, "unit_identity_is_user_attestation_not_biological_validation": True,
             "condition_coding": "control=0 case=1", "genes": genes,
             "residual_df_per_gene": len(selected) - 2, "status": "PREPARED",
             "scientific_release": False, "g0_granted": False}
    return prepared, audit


def main():
    outputs = [Path(os.environ[f"AUTONOMICS_OUTPUT{port}"]) for port in range(3)]
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        inputs = [Path(os.environ[f"AUTONOMICS_INPUT{port}"]) for port in range(3)]
        columns, matrix = read_table(inputs[0])
        _, metadata = read_table(inputs[1])
        prepared, audit = prepare(columns, matrix, metadata, json.loads(inputs[2].read_text()))
        audit["input_sha256"] = [hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs]
        with outputs[0].open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["gene", "sample", "condition", "expression"], delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(prepared)
        outputs[1].write_text(json.dumps(audit, indent=2) + "\n")
        outputs[2].write_text("PREPARED; normalized donor-level condition-only model; no scientific release\n")
        return 0
    except (ValueError, KeyError, TypeError, OSError) as error:
        outputs[0].unlink(missing_ok=True)
        outputs[1].write_text(json.dumps({"status": "BLOCKED", "error": str(error), "g0_granted": False}, indent=2) + "\n")
        outputs[2].write_text(f"BLOCKED: {error}\n")
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
