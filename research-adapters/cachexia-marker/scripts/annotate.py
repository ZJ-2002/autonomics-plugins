import contextlib
import csv
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import warnings


KEYS = {"schema_version", "scope", "test_id", "input_sha256", "row_unit", "species", "matrix_gene_id_type", "marker_gene_id_type", "matrix_layer", "expression_scale", "normalize", "normalization_target", "expected_cell_ids", "expected_gene_ids", "marker_sets", "groupby", "expected_group_ids", "expected_group_counts", "min_score", "unknown_label", "tie_policy", "duplicate_member_policy", "missing_member_policy", "annotation_basis"}
MARKER_KEYS = {"label", "genes", "expected_present_genes", "expected_missing_genes", "minimum_present_occurrences"}
NAMES = ["result.parquet", "output.h5ad", "audit.json", "marker.log", "genes.tsv", "request_ledger.tsv", "groups.parquet"]
PREFIX = "cachexia_marker_"
VERSIONS = {"scanpy": "1.11.3", "anndata": "0.11.4", "numpy": "2.1.3", "scipy": "1.14.1", "pandas": "2.2.3"}
GROUP_COLUMNS = ["group_id", "group_position", "signature_id", "signature_position", "n_cells", "mean_score", "best_signature", "assignment_score", "annotated_label", "unknown", "margin", "margin_kind", "tied"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(filename):
    checksum = hashlib.sha256()
    with Path(filename).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("Nonfinite JSON constant: " + value)


def load_request(filename):
    return json.loads(Path(filename).read_text(), object_pairs_hook=unique_object, parse_constant=reject_constant)


def recover_id(filename):
    try:
        pairs = json.loads(Path(filename).read_text(), object_pairs_hook=lambda entries: entries, parse_constant=reject_constant)
        matches = [value for key, value in pairs if key == "test_id"]
        if len(matches) == 1 and isinstance(matches[0], str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", matches[0]): return matches[0]
    except (ValueError, TypeError, UnicodeError):
        pass
    return None


def lexical(value):
    return isinstance(value, str) and bool(value) and not any(char in value for char in "\t\r\n")


def axis(value, allow_empty=False, unique=True):
    return type(value) is list and (bool(value) or allow_empty) and all(lexical(item) for item in value) and (not unique or len(value) == len(set(value)))


def validate(request):
    require(type(request) is dict and set(request) == KEYS, "Exact frozen request keys required")
    require(type(request["schema_version"]) is int and request["schema_version"] == 1, "Unsupported schema")
    require(request["scope"] == "TECHNICAL_MARKER_HEURISTIC_NOT_G0", "Explicit technical heuristic scope required")
    require(isinstance(request["test_id"], str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", request["test_id"]), "Invalid frozen test ID")
    require(isinstance(request["input_sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", request["input_sha256"]), "Frozen input SHA256 required")
    require(request["row_unit"] == "CELL_OR_NUCLEUS_NOT_DONOR_INFERENCE", "Explicit cell/nucleus annotation unit required")
    require(request["species"] in {"Homo_sapiens", "Mus_musculus"}, "Explicit supported species required")
    require(request["matrix_gene_id_type"] in {"gene_symbol", "entrez", "ensembl", "probe_id"} and request["marker_gene_id_type"] == request["matrix_gene_id_type"], "Same frozen marker and matrix namespace required; no mapping")
    require(lexical(request["matrix_layer"]), "Explicit matrix layer required")
    require(request["normalize"] in {"none", "log_cp10k"} and type(request["normalization_target"]) is int and request["normalization_target"] == 10000, "Explicit original normalization rule required")
    require(request["expression_scale"] in {"raw_integer_counts", "log1p_cp10000_all_genes", "finite_expression"}, "Explicit expression scale required")
    require(request["normalize"] != "log_cp10k" or request["expression_scale"] == "raw_integer_counts", "Normalization requires qualified raw counts; no double-log transformation")
    for key in ("expected_cell_ids", "expected_gene_ids"):
        require(axis(request[key]), "Unique complete frozen axes required: " + key)
    require(request["tie_policy"] == "FIRST_IN_FROZEN_MARKER_ORDER" and request["duplicate_member_policy"] == "PRESERVE_OCCURRENCES" and request["missing_member_policy"] == "FROZEN_AVAILABLE_OCCURRENCES_NO_IMPUTATION", "Explicit original heuristic tie/member policies required")
    require(request["annotation_basis"] == "FROZEN_REFERENCE_NOT_CANDIDATE_RESULT", "Candidate-driven annotation forbidden")
    require(type(request["min_score"]) in (int, float) and math.isfinite(request["min_score"]), "Finite nonboolean score threshold required")
    require(lexical(request["unknown_label"]), "Explicit unknown label required")
    markers = request["marker_sets"]
    require(type(markers) is list and markers, "Complete frozen marker list required")
    labels = []
    for marker in markers:
        require(type(marker) is dict and set(marker) == MARKER_KEYS, "Exact frozen marker contract required")
        require(lexical(marker["label"]) and axis(marker["genes"], unique=False) and axis(marker["expected_present_genes"], unique=False) and axis(marker["expected_missing_genes"], allow_empty=True, unique=False), "Complete lexical marker occurrence axes required")
        require(type(marker["minimum_present_occurrences"]) is int and 1 <= marker["minimum_present_occurrences"] <= len(marker["genes"]), "Explicit positive marker coverage gate required")
        labels.append(marker["label"])
    require(len(labels) == len(set(labels)) and request["unknown_label"] not in labels, "Unique marker labels and distinct Unknown required")
    if request["groupby"] is None:
        require(request["expected_group_ids"] == [] and request["expected_group_counts"] == {}, "Inactive group contract must be neutral")
    else:
        require(lexical(request["groupby"]) and axis(request["expected_group_ids"]) and type(request["expected_group_counts"]) is dict and set(request["expected_group_counts"]) == set(request["expected_group_ids"]) and all(type(value) is int and value > 0 for value in request["expected_group_counts"].values()), "Complete frozen group axes/counts required")


def choose(scores, names, threshold, unknown):
    winner = max(range(len(scores)), key=lambda position: scores[position])
    top = float(scores[winner])
    others = [float(score) for position, score in enumerate(scores) if position != winner]
    margin = top - max(others) if others else top
    fallback = not top > threshold
    return {"winner_position": winner, "best_signature": names[winner], "assignment_score": top, "annotated_label": unknown if fallback else names[winner], "unknown": fallback, "margin": margin, "margin_kind": "TOP_MINUS_RUNNER_UP" if others else "SINGLE_SIGNATURE_SCORE", "tied": sum(float(score) == top for score in scores) > 1}


def write_json(filename, value):
    Path(filename).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def ledger(filename, test_id, status, error=""):
    with Path(filename).open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["test_id", "status", "error", "scientific_release"])
        writer.writerow([test_id or "UNKNOWN_UNRECOVERABLE_ID", status, error, "NOT_GRANTED"])


def calculate(filename, request, directory):
    import anndata as ad
    import numpy as np
    import pandas as pd
    import pyarrow as pa
    import scanpy as sc
    from scipy import sparse

    versions = {name: importlib.metadata.version(name) for name in VERSIONS}
    require(versions == VERSIONS, "Actual frozen versions differ")
    require(digest(filename) == request["input_sha256"], "Frozen H5AD content differs")
    data = ad.read_h5ad(filename)
    require(list(data.obs_names) == request["expected_cell_ids"] and list(data.var_names) == request["expected_gene_ids"], "Complete frozen H5AD axes differ")
    require(not any(str(key).startswith(PREFIX) for mapping in (data.obs, data.uns, data.obsm) for key in mapping), "Reserved output namespace exists")
    layer = request["matrix_layer"]
    require(layer == "X" or layer in data.layers, "Explicit expression layer missing")
    matrix = data.X if layer == "X" else data.layers[layer]
    require(matrix is not None, "Explicit matrix missing")
    matrix = matrix.astype(np.float64).copy()
    if sparse.issparse(matrix):
        matrix = matrix.tocsr()
        matrix.sum_duplicates()
        values = matrix.data
    else: values = np.asarray(matrix)
    require(np.isfinite(values).all(), "Every-cell expression must be finite")
    scale = request["expression_scale"]
    if scale == "raw_integer_counts":
        require((values >= 0).all() and np.equal(values, np.floor(values)).all(), "Qualified raw integer counts required")
    elif scale == "log1p_cp10000_all_genes":
        require((values >= 0).all() and (values <= np.log1p(10000) + 1e-10).all(), "Qualified log1p CP10k values required")
        if sparse.issparse(matrix):
            recovered = matrix.copy()
            recovered.data = np.expm1(recovered.data)
            totals = np.asarray(recovered.sum(axis=1)).ravel()
        else: totals = np.expm1(matrix).sum(axis=1)
        require(np.all(np.abs(totals - request["normalization_target"]) <= 1), "Every-cell full-library log normalization differs")
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        if request["normalize"] == "log_cp10k":
            totals = np.asarray(matrix.sum(axis=1)).ravel()
            require(np.isfinite(totals).all() and (totals > 0).all(), "Positive full-library count totals required")
            working = ad.AnnData(X=matrix)
            sc.pp.normalize_total(working, target_sum=request["normalization_target"], exclude_highly_expressed=False, inplace=True)
            sc.pp.log1p(working, base=None)
            matrix = working.X
    names = [marker["label"] for marker in request["marker_sets"]]
    positions = {gene: position for position, gene in enumerate(data.var_names)}
    coverage = []
    scores = []
    gene_rows = []
    for signature_position, marker in enumerate(request["marker_sets"]):
        present = [gene for gene in marker["genes"] if gene in positions]
        missing = [gene for gene in marker["genes"] if gene not in positions]
        require(present == marker["expected_present_genes"] and missing == marker["expected_missing_genes"], "Frozen marker occurrence coverage differs: " + marker["label"])
        require(len(present) >= marker["minimum_present_occurrences"], "Frozen minimum marker coverage not met: " + marker["label"])
        selected = matrix[:, [positions[gene] for gene in present]]
        score = np.asarray(selected.mean(axis=1)).ravel()
        scores.append(score)
        coverage.append({"label": marker["label"], "requested_occurrences": len(marker["genes"]), "present_occurrences": len(present), "missing_occurrences": len(missing)})
        gene_rows += [(signature_position, marker["label"], member_position, gene, gene in positions, positions.get(gene)) for member_position, gene in enumerate(marker["genes"])]
    score_matrix = np.column_stack(scores)
    require(np.isfinite(score_matrix).all(), "Nonfinite marker arithmetic result")
    groupby = request["groupby"]
    group_rows = []
    group_decisions = {}
    cell_groups = [None] * data.n_obs
    if groupby is not None:
        require(groupby in data.obs, "Frozen group column missing")
        grouping = data.obs[groupby]
        require(not grouping.isna().any() and all(lexical(value) for value in grouping), "Complete lexical nonmissing groups required")
        cell_groups = list(grouping)
        require(set(cell_groups) == set(request["expected_group_ids"]) and {name: cell_groups.count(name) for name in request["expected_group_ids"]} == request["expected_group_counts"], "Complete frozen group universe/counts differ")
        for group_position, group in enumerate(request["expected_group_ids"]):
            selected = [position for position, value in enumerate(cell_groups) if value == group]
            means = score_matrix[selected].mean(axis=0)
            decision = choose(means, names, request["min_score"], request["unknown_label"])
            group_decisions[group] = decision
            for signature_position, name in enumerate(names):
                group_rows.append({"group_id": group, "group_position": group_position, "signature_id": name, "signature_position": signature_position, "n_cells": len(selected), "mean_score": float(means[signature_position]), **{key: value for key, value in decision.items() if key != "winner_position"}})
    table_rows = []
    cell_decisions = []
    for cell_position, cell_id in enumerate(data.obs_names):
        own = choose(score_matrix[cell_position], names, request["min_score"], request["unknown_label"])
        assigned = own if groupby is None else group_decisions[cell_groups[cell_position]]
        selected_score = own["assignment_score"] if assigned["unknown"] else float(score_matrix[cell_position, assigned["winner_position"]])
        cell_decisions.append({**assigned, "selected_score": selected_score})
        for signature_position, name in enumerate(names):
            table_rows.append({"cell_id": str(cell_id), "cell_position": cell_position, "signature_id": name, "signature_position": signature_position, "group_id": cell_groups[cell_position], "mean_marker_score": float(score_matrix[cell_position, signature_position]), "own_best_signature": own["best_signature"], "own_best_score": own["assignment_score"], "selected_score": selected_score, "test_id": request["test_id"], **{key: value for key, value in assigned.items() if key != "winner_position"}})
    table = pd.DataFrame(table_rows)
    table.to_parquet(directory / NAMES[0], index=False, schema=pa.Schema.from_pandas(table).set(table.columns.get_loc("group_id"), pa.field("group_id", pa.string())))
    group_table = pd.DataFrame(group_rows, columns=GROUP_COLUMNS)
    group_table = group_table.astype({"group_id": "object", "group_position": "int64", "signature_id": "object", "signature_position": "int64", "n_cells": "int64", "mean_score": "float64", "best_signature": "object", "assignment_score": "float64", "annotated_label": "object", "unknown": "bool", "margin": "float64", "margin_kind": "object", "tied": "bool"})
    group_types = {"group_position": pa.int64(), "signature_position": pa.int64(), "n_cells": pa.int64(), "mean_score": pa.float64(), "assignment_score": pa.float64(), "unknown": pa.bool_(), "margin": pa.float64(), "tied": pa.bool_()}
    group_table.to_parquet(directory / NAMES[6], index=False, schema=pa.schema([(name, group_types.get(name, pa.string())) for name in GROUP_COLUMNS]))
    output = data.copy()
    for field in ["annotated_label", "selected_score", "margin", "assignment_score", "unknown", "tied", "margin_kind"]:
        output.obs[PREFIX + field] = [row[field] for row in cell_decisions]
    output.obsm[PREFIX + "scores"] = pd.DataFrame(score_matrix, index=data.obs_names, columns=names)
    output.uns[PREFIX + "contract"] = json.dumps(request, sort_keys=True)
    if groupby is not None: output.uns[PREFIX + "groups"] = group_table
    output.write_h5ad(directory / NAMES[1])
    with (directory / NAMES[4]).open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["signature_position", "signature_id", "member_position", "gene_id", "present", "matrix_gene_position"])
        writer.writerows(gene_rows)
    ledger(directory / NAMES[5], request["test_id"], "TECHNICAL_PASS_NOT_SCIENTIFIC")
    print("USER_DEFINED_MEAN_MARKER_HEURISTIC_NOT_OFFICIAL_CELL_TYPE_METHOD")
    return {"versions": versions, "statistical_official_layer": "NOT_APPLICABLE", "cells": data.n_obs, "genes": data.n_vars, "marker_coverage": coverage, "unknown_cells": sum(row["unknown"] for row in cell_decisions), "tied_cells": sum(row["tied"] for row in cell_decisions), "warnings": [{"category": item.category.__name__, "message": str(item.message)} for item in captured]}


def main():
    inputs = [Path(os.environ["AUTONOMICS_INPUT" + str(position)]) for position in range(2)]
    outputs = [Path(os.environ.get("AUTONOMICS_OUTPUT" + str(position), "/work/" + name)) for position, name in enumerate(NAMES)]
    test_id = recover_id(inputs[1])
    audit = {"status": "BLOCKED", "test_id": test_id, "G0_granted": False, "scientific_release_granted": False, "resident_deployment_granted": False, "statistical_official_layer": "NOT_APPLICABLE"}
    temporary = None
    published = []
    safe = False
    parent = outputs[0].parent
    try:
        require(len(set(outputs)) == len(outputs) and parent.is_dir() and not parent.is_symlink() and all(path.is_absolute() and path.parent == parent and path.name == name and not path.exists() and not path.is_symlink() for path, name in zip(outputs, NAMES)), "Unsafe or preexisting output paths")
        safe = True
        request = load_request(inputs[1])
        validate(request)
        temporary = Path(tempfile.mkdtemp(prefix="marker-publication-", dir=parent))
        with (temporary / NAMES[3]).open("w") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            details = calculate(inputs[0], request, temporary)
        audit.update(details, status="TECHNICAL_PASS_NOT_SCIENTIFIC", request=request, request_sha256=digest(inputs[1]), input_sha256=[digest(filename) for filename in inputs], output_sha256={str(position): digest(temporary / NAMES[position]) for position in [0, 1, 3, 4, 5, 6]})
        write_json(temporary / NAMES[2], audit)
        for position, name in enumerate(NAMES):
            (temporary / name).replace(outputs[position])
            published.append(outputs[position])
    except Exception as error:
        audit["error"] = str(error)
        if safe:
            for filename in published: filename.unlink()
            write_json(outputs[2], audit)
            ledger(outputs[5], test_id, "BLOCKED", str(error))
            outputs[3].write_text(str(error) + "\n")
        else: print(json.dumps(audit), file=sys.stderr)
        print(str(error), file=sys.stderr)
        return 1
    finally:
        if temporary is not None: shutil.rmtree(temporary)
    return 0


if __name__ == "__main__": sys.exit(main())
