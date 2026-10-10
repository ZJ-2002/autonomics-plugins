import csv
import hashlib
import json
import os
from pathlib import Path
import re

import anndata as ad
import h5py
import numpy as np
import pandas as pd
import scipy.sparse as sparse


def checksum(filename):
    with Path(filename).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identity(value):
    if not isinstance(value, str) or not value or value != value.strip() or any(character in value for character in "\t\r\n"):
        raise ValueError("Exact nonempty lexical identity required")
    return value


def unique(values):
    result = [identity(value) for value in values]
    if len(set(result)) != len(result):
        raise ValueError("Duplicate axis or column identity")
    return result


def read_table(filename):
    with Path(filename).open(newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream, delimiter="\t"))
    if len(rows) < 2 or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("Empty or ragged TSV")
    return unique(rows[0]), rows[1:]


def write_json(filename, value):
    Path(filename).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def signatures(filename, gene_ids):
    columns, rows = read_table(filename)
    if columns != ["signature", "gene"]:
        raise ValueError("Signature columns must be signature/gene")
    programs = {}
    for name, member in rows:
        identity(member)
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", name):
            raise ValueError("Scoped signature name must be ASCII and unambiguous")
        gene = member[:-1] if member[-1] in "+-" else member
        identity(gene)
        members = programs.setdefault(name, [])
        if gene in [existing[:-1] if existing[-1] in "+-" else existing for existing in members]:
            raise ValueError("Duplicate base gene or both signed arms")
        members.append(member)
    coverage = {}
    for name, members in programs.items():
        base = [member[:-1] if member[-1] in "+-" else member for member in members]
        present = [gene for gene in base if gene in gene_ids]
        if not present:
            raise ValueError("No present genes for signature; no automatic score-zero qualification")
        coverage[name] = {"present": present, "missing": [gene for gene in base if gene not in gene_ids], "qualification_granted": False}
    return rows, programs, coverage


def prepare():
    source = os.environ["AUTONOMICS_INPUT0"]
    signature_file = os.environ["AUTONOMICS_INPUT1"]
    request = json.loads(Path(os.environ["AUTONOMICS_INPUT2"]).read_text())
    if request.get("input_sha256") != checksum(source) or request.get("signature_sha256") != checksum(signature_file):
        raise ValueError("Frozen input/signature SHA256 mismatch")
    layer = identity(os.environ["UB_LAYER"])
    chunk, cap = int(os.environ["UB_CHUNK"]), int(os.environ["UB_MAX_ENTRIES"])
    params = {"max_rank": int(os.environ["UCELL_MAX_RANK"]), "negative_weight": float(os.environ["UCELL_NEGATIVE_WEIGHT"]), "missing_genes": os.environ["UCELL_MISSING_GENES"]}
    if "/" in layer or request.get("input_layer") != layer or type(request.get("chunk")) is not int or request["chunk"] != chunk or chunk < 1 or type(request.get("max_entries")) is not int or request["max_entries"] != cap or not 1 <= cap <= 2000000:
        raise ValueError("Frozen layer/chunk/allocation cap mismatch")
    configured = request.get("ucell_params", {})
    if configured != params or type(configured.get("max_rank")) is not int or params["max_rank"] < 2 or type(configured.get("negative_weight")) not in (float, int) or not np.isfinite(params["negative_weight"]) or params["negative_weight"] < 0 or params["missing_genes"] not in ("impute", "skip"):
        raise ValueError("Frozen official UCell parameters differ")
    if request.get("expression_scale") not in ("raw_integer_counts", "finite_nonnegative_expression") or not request.get("provenance_attestation") or request.get("cell_alignment") != "REINDEX_EXACT_CELL_SET" or request.get("output_content") != "PRESERVE_ALL_ADD_OBS_SCORES":
        raise ValueError("Explicit scale/provenance/alignment/preservation contract required")
    with h5py.File(source, "r") as handle:
        obs, var = ad.io.read_elem(handle["obs"]), ad.io.read_elem(handle["var"])
        cells, genes = unique(obs.index.tolist()), unique(var.index.tolist())
        if not cells or len(genes) < 2 or any(gene[-1] in "+-" for gene in genes) or len(cells) * len(genes) > cap:
            raise ValueError("Empty/ambiguous axes or dense allocation cap exceeded")
        rows, programs, coverage = signatures(signature_file, set(genes))
        mapping = request.get("obs_score_columns")
        if not isinstance(mapping, dict) or set(mapping) != set(programs):
            raise ValueError("Frozen signature-to-obs mapping differs")
        output_columns = unique(list(mapping.values()))
        if set(output_columns) & set(obs.columns) or "cell_id" in output_columns or "cachexia_ucell_chain" in handle.get("uns", {}):
            raise ValueError("Existing obs/provenance column collision")
        node = handle["X"] if layer == "X" else handle["layers"][layer]
        matrix = ad.io.sparse_dataset(node) if isinstance(node, h5py.Group) else node
        if matrix.shape != (len(cells), len(genes)):
            raise ValueError("Matrix/axis shape mismatch")
        dense = np.empty(matrix.shape, dtype=np.float64)
        for start in range(0, len(cells), chunk):
            stop = min(start + chunk, len(cells))
            block = matrix[start:stop]
            if sparse.issparse(block):
                block = block.copy()
                block.sort_indices()
                if not block.has_canonical_format:
                    raise ValueError("Duplicate sparse coordinates")
                values = block.data
            else:
                values = np.asarray(block)
            if values.dtype.kind not in "biuf" or values.dtype.itemsize > 8 or not np.isfinite(values).all() or np.any(values < 0):
                raise ValueError("Finite nonnegative float64-compatible expression required")
            if values.dtype.kind in "iu" and np.any(values > 2**53):
                raise ValueError("Lossy integer-to-float64 conversion")
            if request["expression_scale"] == "raw_integer_counts" and (np.any(values != np.floor(values)) or np.any(values > 2147483647)):
                raise ValueError("Raw counts must be int32-compatible integers")
            dense[start:stop] = block.toarray() if sparse.issparse(block) else block
    with Path(os.environ["AUTONOMICS_OUTPUT0"]).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["gene", *cells])
        for gene, values in zip(genes, dense.T, strict=True):
            writer.writerow([gene, *values.tolist()])
    with Path(os.environ["AUTONOMICS_OUTPUT1"]).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["signature", "gene"])
        writer.writerows(rows)
    handoff = {"schema_version": 1, "execution_status": "COMPLETED", "request": request, "cell_ids": cells, "gene_ids": genes,
        "matrix_sha256": checksum(os.environ["AUTONOMICS_OUTPUT0"]), "signature_sha256": checksum(os.environ["AUTONOMICS_OUTPUT1"]),
        "official_score_columns": [name + "_UCell" for name in programs], "coverage": coverage, "scientific_release": False, "g0_granted": False}
    write_json(os.environ["AUTONOMICS_OUTPUT2"], handoff)
    return {"cells": len(cells), "genes": len(genes), "dense_entries": dense.size, "coverage": coverage, "full_H5AD_loaded": False}


def writeback():
    source, scores_file = os.environ["AUTONOMICS_INPUT0"], os.environ["AUTONOMICS_INPUT1"]
    handoff = json.loads(Path(os.environ["AUTONOMICS_INPUT2"]).read_text())
    official = json.loads(Path(os.environ["AUTONOMICS_INPUT3"]).read_text())
    request = handoff["request"]
    if handoff.get("schema_version") != 1 or handoff.get("execution_status") != "COMPLETED" or checksum(source) != request["input_sha256"]:
        raise ValueError("H5AD/handoff identity or execution mismatch")
    if official.get("execution_status") != "COMPLETED" or official.get("method") != "UCell" or official.get("version") != "2.16.0" or official.get("ties_method") != "average":
        raise ValueError("Official UCell execution identity differs")
    for name, expected in (("params", request["ucell_params"]), ("matrix_sha256", handoff["matrix_sha256"]), ("signature_sha256", handoff["signature_sha256"]), ("cell_ids", handoff["cell_ids"]), ("gene_ids", handoff["gene_ids"]), ("scores_sha256", checksum(scores_file))):
        if official.get(name) != expected:
            raise ValueError("Official score handoff linkage differs: " + name)
    if request.get("cell_alignment") != "REINDEX_EXACT_CELL_SET" or request.get("output_content") != "PRESERVE_ALL_ADD_OBS_SCORES":
        raise ValueError("Frozen alignment/preservation convention differs")
    columns, rows = read_table(scores_file)
    if columns[0] != "cell" or set(columns[1:]) != set(handoff["official_score_columns"]) or official.get("score_columns") != columns[1:]:
        raise ValueError("Official score columns differ")
    ids = unique([row[0] for row in rows])
    if set(ids) != set(handoff["cell_ids"]):
        raise ValueError("Scores must contain the exact unique cell set")
    scores = np.asarray([row[1:] for row in rows], dtype=np.float64)
    if not np.isfinite(scores).all():
        raise ValueError("Undefined/nonfinite UCell scores cannot be silently written")
    data = ad.read_h5ad(source)
    if unique(data.obs_names.tolist()) != handoff["cell_ids"] or unique(data.var_names.tolist()) != handoff["gene_ids"]:
        raise ValueError("H5AD axes differ from frozen handoff")
    mapping = request["obs_score_columns"]
    target_columns = unique(list(mapping.values()))
    if set(target_columns) & set(data.obs.columns) or "cell_id" in target_columns or "cachexia_ucell_chain" in data.uns:
        raise ValueError("Existing score/provenance collision")
    lookup = {cell: index for index, cell in enumerate(ids)}
    for name, target in mapping.items():
        column = columns.index(name + "_UCell") - 1
        data.obs[target] = [scores[lookup[cell], column] for cell in data.obs_names]
    data.uns["cachexia_ucell_chain"] = json.dumps({"method": "UCell", "version": "2.16.0", "params": request["ucell_params"], "input_sha256": request["input_sha256"], "scores_sha256": checksum(scores_file), "handoff_sha256": checksum(os.environ["AUTONOMICS_INPUT2"]), "g0_granted": False}, sort_keys=True)
    ad.settings.allow_write_nullable_strings = True
    data.write_h5ad(os.environ["AUTONOMICS_OUTPUT0"], compression="gzip")
    data.obs[target_columns].to_csv(os.environ["AUTONOMICS_OUTPUT1"], sep="\t", index_label="cell_id")
    return {"cells": data.n_obs, "genes": data.n_vars, "obs_score_columns": target_columns, "output_sha256": checksum(os.environ["AUTONOMICS_OUTPUT0"]), "whole_H5AD_loaded": True, "provenance_linkage_is_not_authentication": True}


if __name__ == "__main__":
    mode = os.environ.get("UCELL_BRIDGE_MODE")
    port = 3 if mode == "prepare" else 2
    try:
        if mode not in ("prepare", "writeback"):
            raise ValueError("Unsupported UCell bridge mode")
        result = {"prepare": prepare, "writeback": writeback}[mode]()
        write_json(os.environ[f"AUTONOMICS_OUTPUT{port}"], {"execution_status": "COMPLETED", "mode": mode, **result, "scientific_release": False, "g0_granted": False})
    except Exception as error:
        for index in range(port):
            if os.environ.get(f"AUTONOMICS_OUTPUT{index}"):
                Path(os.environ[f"AUTONOMICS_OUTPUT{index}"]).unlink(missing_ok=True)
        if os.environ.get(f"AUTONOMICS_OUTPUT{port}"):
            write_json(os.environ[f"AUTONOMICS_OUTPUT{port}"], {"execution_status": "FAILED", "status": "BLOCKED", "error": str(error), "scientific_release": False, "g0_granted": False})
        raise SystemExit(2)
