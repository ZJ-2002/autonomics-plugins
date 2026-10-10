import contextlib
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import random
import re
import shutil
import sys
import tempfile
import warnings


MODEL_HASHES = {
    "Immune_All_Low.pkl": "290874d35dac039d4c9218c343fde4aac1077709b72a331ce7266f6828c36502",
    "Immune_All_High.pkl": "a715fec36c2c421f7c4e31cf4cb4bea883eedab7fd7b20a4b76f091c22660448",
}
VERSIONS = {"celltypist": "1.7.1", "scanpy": "1.11.3", "anndata": "0.11.4", "numpy": "2.1.3", "scipy": "1.14.1", "scikit-learn": "1.9.1", "pandas": "2.2.3"}
KEYS = {"schema_version", "scope", "test_id", "input_sha256", "model_sha256", "model_file", "species", "gene_id_type", "expression_scale", "matrix_layer", "expected_cell_ids", "expected_gene_ids", "expected_matched_genes", "expected_model_classes", "mode", "p_thres", "majority_voting", "over_clustering_column", "min_prop", "confidence_by", "seed", "annotation_basis"}
NAMES = ["result.parquet", "output.h5ad", "audit.json", "celltypist.log", "genes.tsv", "request_ledger.tsv"]
PREFIX = "cachexia_celltypist_"


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
        pairs = json.loads(Path(filename).read_text(), object_pairs_hook=lambda items: items, parse_constant=reject_constant)
        values = [value for key, value in pairs if key == "test_id"]
        if len(values) == 1 and isinstance(values[0], str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", values[0]):
            return values[0]
    except (ValueError, TypeError, UnicodeError):
        pass
    return None


def validate_request(request):
    require(type(request) is dict and set(request) == KEYS, "Exact frozen request keys required")
    require(type(request["schema_version"]) is int and request["schema_version"] == 1, "Unsupported schema")
    require(request["scope"] == "TECHNICAL_ANNOTATION_ONLY_NOT_G0", "Explicit technical annotation scope required")
    require(isinstance(request["test_id"], str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", request["test_id"]), "Invalid frozen test ID")
    require(request["model_file"] in MODEL_HASHES and request["model_sha256"] == MODEL_HASHES[request["model_file"]], "Only authenticated frozen original official model allowed")
    require(isinstance(request["input_sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", request["input_sha256"]), "Frozen H5AD SHA256 required")
    require(request["species"] == "Homo_sapiens" and request["gene_id_type"] == "human_gene_symbol", "Explicit unconverted human model namespace required")
    require(request["expression_scale"] == "log1p_cp10000_all_genes", "Explicit full-library log1p CP10k required")
    require(isinstance(request["matrix_layer"], str) and request["matrix_layer"], "Explicit matrix layer required")
    for key in ("expected_cell_ids", "expected_gene_ids", "expected_matched_genes", "expected_model_classes"):
        value = request[key]
        require(type(value) is list and value and all(isinstance(item, str) and item and not any(char in item for char in "\t\r\n") for item in value) and len(value) == len(set(value)), "Unique complete frozen axes required: " + key)
    require(request["mode"] in {"best match", "prob match"}, "Unsupported official prediction mode")
    for key in ("p_thres", "min_prop"):
        require(type(request[key]) in (int, float) and 0 <= request[key] <= 1, "Finite probability/voting threshold required: " + key)
    require(type(request["majority_voting"]) is bool, "Explicit boolean majority_voting required")
    require(request["confidence_by"] in {"predicted_labels", "majority_voting"}, "Explicit official confidence semantics required")
    require(type(request["seed"]) is int and 0 <= request["seed"] <= 4294967295, "Frozen integer seed required")
    require(request["annotation_basis"] == "FROZEN_REFERENCE_NOT_CANDIDATE_RESULT", "Candidate-driven annotation forbidden")
    if request["majority_voting"]:
        require(isinstance(request["over_clustering_column"], str) and request["over_clustering_column"] and not request["over_clustering_column"].startswith(PREFIX), "Frozen input over-clusters required; no automatic clustering")
    else:
        require(request["over_clustering_column"] is None and request["min_prop"] == 0 and request["confidence_by"] == "predicted_labels", "Inactive voting parameters must be explicit neutral values")


def write_json(filename, value):
    Path(filename).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def ledger(filename, test_id, status, error=""):
    with Path(filename).open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["test_id", "status", "error", "scientific_release"])
        writer.writerow([test_id or "UNKNOWN_UNRECOVERABLE_ID", status, error, "NOT_GRANTED"])


def validate_official_labels(labels, probabilities, decisions, classes, mode, threshold, cell_ids):
    invalid = []
    for position, (label, values) in enumerate(zip(labels, probabilities)):
        if mode == "best match":
            expected = classes[max(range(len(values)), key=lambda column: decisions[position][column])]
        else:
            expected = "|".join(cell_type for cell_type, value in zip(classes, values) if value > threshold) or "Unassigned"
        if str(label) != expected:
            invalid.append({"cell_id": cell_ids[position], "official_raw_label": str(label), "documented_expected_label": expected})
    if invalid:
        error = ValueError("Official prediction labels contradict documented probability rule; blocked, never rewritten")
        error.official_invalid_label_rows = invalid
        raise error


def calculate(input_path, model_path, request, directory):
    import anndata as ad
    import celltypist
    import numpy as np
    import pandas as pd
    from scipy import sparse

    actual_versions = {name: importlib.metadata.version(name) for name in VERSIONS}
    require(actual_versions == VERSIONS, "Actual frozen package versions differ")
    require(digest(input_path) == request["input_sha256"], "H5AD content identity differs")
    require(digest(model_path) == request["model_sha256"], "Official model content identity differs before unpickle")
    original = ad.read_h5ad(input_path)
    require(list(original.obs_names) == request["expected_cell_ids"] and list(original.var_names) == request["expected_gene_ids"], "Complete frozen H5AD axes differ")
    require(original.obs_names.is_unique and original.var_names.is_unique, "Duplicate H5AD axes forbidden")
    require(not any(str(key).startswith(PREFIX) for mapping in (original.obs, original.uns, original.obsm) for key in mapping), "Reserved output namespace already exists")
    layer = request["matrix_layer"]
    require(layer == "X" or layer in original.layers, "Explicit expression layer missing")
    matrix = original.X if layer == "X" else original.layers[layer]
    require(matrix is not None, "Explicit expression matrix missing")
    matrix = matrix.copy()
    if sparse.issparse(matrix):
        matrix = matrix.tocsr()
        matrix.sum_duplicates()
        values = matrix.data
        transformed = matrix.copy()
        transformed.data = np.expm1(transformed.data)
        totals = np.asarray(transformed.sum(axis=1)).ravel()
    else:
        values = np.asarray(matrix)
        totals = np.expm1(values).sum(axis=1)
    require(np.isfinite(values).all() and (values >= 0).all() and (values <= np.log1p(10000) + 1e-10).all(), "Every-cell expression must be finite nonnegative log1p CP10k")
    require(np.isfinite(totals).all() and np.all(np.abs(totals - 10000) <= 1), "Every-cell full-library normalization differs; no warning-only partial-library acceptance")
    with warnings.catch_warnings(record=True) as model_warnings:
        warnings.simplefilter("always")
        model = celltypist.models.Model.load(str(Path(model_path).resolve()))
    classes = list(model.cell_types)
    require(classes == request["expected_model_classes"], "Complete official model class axis differs")
    features = set(model.features)
    matched = [gene for gene in original.var_names if gene in features]
    require(matched == request["expected_matched_genes"], "Frozen complete model gene overlap differs")
    voting = request["majority_voting"]
    cluster_column = request["over_clustering_column"]
    if voting:
        require(original.n_obs > 50, "Official majority voting skips <=50 cells; frozen voting request cannot be silently skipped")
        require(cluster_column in original.obs, "Frozen over-clustering column missing")
        groups = original.obs[cluster_column]
        require(not groups.isna().any() and all(isinstance(value, str) and value and not any(char in value for char in "\t\r\n") for value in groups), "Complete lexical nonmissing frozen cluster labels required")
    working = ad.AnnData(X=matrix, obs=original.obs.copy(), var=original.var.copy())
    random.seed(request["seed"])
    np.random.seed(request["seed"])
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        prediction = celltypist.annotate(filename=working, model=model, mode=request["mode"], p_thres=request["p_thres"], majority_voting=voting, over_clustering=cluster_column, use_GPU=False, min_prop=request["min_prop"])
        validate_official_labels(prediction.predicted_labels.predicted_labels, prediction.probability_matrix.values, prediction.decision_matrix.values, classes, request["mode"], request["p_thres"], request["expected_cell_ids"])
        official = prediction.to_adata(insert_labels=True, insert_conf=True, insert_conf_by=request["confidence_by"], insert_decision=False, insert_prob=False, prefix=PREFIX)
    require(not voting or "majority_voting" in prediction.predicted_labels, "Official voting result missing")
    require(all(list(frame.index) == request["expected_cell_ids"] for frame in (prediction.predicted_labels, prediction.decision_matrix, prediction.probability_matrix)), "Official result cell axes changed")
    require(list(prediction.decision_matrix.columns) == classes and list(prediction.probability_matrix.columns) == classes, "Official score class axes changed")
    require(np.isfinite(prediction.decision_matrix.values).all() and np.isfinite(prediction.probability_matrix.values).all(), "Nonfinite official result")
    result = original.copy()
    for column in prediction.predicted_labels.columns:
        result.obs[PREFIX + column] = official.obs[PREFIX + column]
    result.obs[PREFIX + "conf_score"] = official.obs[PREFIX + "conf_score"]
    result.obsm[PREFIX + "decision_matrix"] = prediction.decision_matrix
    result.obsm[PREFIX + "probability_matrix"] = prediction.probability_matrix
    result.uns[PREFIX + "contract"] = json.dumps(request, sort_keys=True)
    result.uns[PREFIX + "model_description"] = json.dumps(model.description, sort_keys=True, default=str)
    result.write_h5ad(directory / NAMES[1])
    label_values = prediction.predicted_labels.astype(str)
    rows = []
    for cell_position, cell_id in enumerate(original.obs_names):
        for class_position, cell_type in enumerate(classes):
            rows.append({"cell_id": str(cell_id), "cell_position": cell_position, "class_position": class_position, "cell_type": str(cell_type), "decision_score": float(prediction.decision_matrix.iloc[cell_position, class_position]), "probability": float(prediction.probability_matrix.iloc[cell_position, class_position]), "predicted_label": label_values.iloc[cell_position]["predicted_labels"], "over_cluster": label_values.iloc[cell_position].get("over_clustering", "NOT_REQUESTED"), "majority_label": label_values.iloc[cell_position].get("majority_voting", "NOT_REQUESTED"), "conf_score": float(result.obs.iloc[cell_position][PREFIX + "conf_score"]), "confidence_by": request["confidence_by"], "test_id": request["test_id"]})
    pd.DataFrame(rows).to_parquet(directory / NAMES[0], index=False)
    with (directory / NAMES[4]).open("w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["gene_position", "gene_id", "matched_official_model"])
        writer.writerows((position, gene, gene in features) for position, gene in enumerate(original.var_names))
    ledger(directory / NAMES[5], request["test_id"], "TECHNICAL_PASS_NOT_SCIENTIFIC")
    return {"versions": actual_versions, "cells": original.n_obs, "genes": original.n_vars, "matched_genes": matched, "classes": classes, "warnings": [{"category": item.category.__name__, "message": str(item.message)} for item in [*model_warnings, *captured]], "confidence_by": request["confidence_by"], "probabilities_are_softmax_or_calibrated": False, "automatic_overclustering": False}


def main():
    outputs = [Path(os.environ.get("AUTONOMICS_OUTPUT" + str(position), "/work/" + name)) for position, name in enumerate(NAMES)]
    inputs = [Path(os.environ["AUTONOMICS_INPUT" + str(position)]) for position in range(3)]
    test_id = recover_id(inputs[2])
    audit = {"status": "BLOCKED", "test_id": test_id, "G0_granted": False, "resident_deployment_granted": False, "scientific_release_granted": False}
    directory = None
    safe_parent = outputs[0].parent
    safe = False
    published = []
    try:
        require(len(set(outputs)) == len(outputs) and all(path.is_absolute() and path.name == name and path.parent == safe_parent and not path.exists() and not path.is_symlink() for path, name in zip(outputs, NAMES)), "Unsafe or preexisting output paths")
        require(safe_parent.is_dir() and not safe_parent.is_symlink() and all(path not in safe_parent.parents and path != safe_parent for path in inputs), "Unsafe output parent")
        safe = True
        request = load_request(inputs[2])
        validate_request(request)
        directory = Path(tempfile.mkdtemp(prefix="celltypist-publication-", dir=safe_parent))
        with (directory / NAMES[3]).open("w") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            details = calculate(inputs[0], inputs[1], request, directory)
            print("TECHNICAL_PASS_NOT_SCIENTIFIC")
        audit.update(details, status="TECHNICAL_PASS_NOT_SCIENTIFIC", request=request, request_sha256=digest(inputs[2]), input_sha256=[digest(filename) for filename in inputs], output_sha256={str(position): digest(directory / NAMES[position]) for position in (0, 1, 3, 4, 5)})
        write_json(directory / NAMES[2], audit)
        for staged, destination in zip([directory / name for name in NAMES], outputs):
            staged.replace(destination)
            published.append(destination)
    except Exception as error:
        audit["error"] = str(error)
        if hasattr(error, "official_invalid_label_rows"):
            audit["official_invalid_label_rows"] = error.official_invalid_label_rows
        if safe:
            for filename in published:
                filename.unlink()
            write_json(outputs[2], audit)
            ledger(outputs[5], test_id, "BLOCKED", str(error))
            outputs[3].write_text(str(error) + "\n")
        else:
            print(json.dumps(audit), file=sys.stderr)
        print(str(error), file=sys.stderr)
        return 1
    finally:
        if directory is not None:
            shutil.rmtree(directory)
    return 0


if __name__ == "__main__":
    sys.exit(main())
