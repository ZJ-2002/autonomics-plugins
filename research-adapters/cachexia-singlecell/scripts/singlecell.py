import csv
import hashlib
import json
import os
from pathlib import Path

import anndata as ad
import h5py
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import scipy
import scipy.sparse as sparse


MAX_COUNT = 2147483647


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identity(value):
    if not isinstance(value, str) or not value or value != value.strip() or any(character in value for character in "\t\n\r"):
        raise ValueError("identity must be a nonempty exact lexical string without ambiguous whitespace")
    return value


def identities(values):
    result = [identity(value) for value in values]
    if len(set(result)) != len(result):
        raise ValueError("duplicate cell/gene axis identity")
    return result


def write_table(path, columns, records):
    with Path(path).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


class H5Input:
    def __init__(self, path, layer):
        self.file = h5py.File(path, "r")
        try:
            self.obs = ad.io.read_elem(self.file["obs"])
            self.var = ad.io.read_elem(self.file["var"])
            self.cell_ids = identities(self.obs.index.tolist())
            self.gene_ids = identities(self.var.index.tolist())
            if not self.cell_ids or not self.gene_ids:
                raise ValueError("empty cell/gene axis")
            node = self.file["X"] if layer == "X" else self.file["layers"][layer]
            self.matrix = ad.io.sparse_dataset(node) if isinstance(node, h5py.Group) else node
            if self.matrix.shape != (len(self.cell_ids), len(self.gene_ids)):
                raise ValueError("H5AD matrix/axis shape mismatch")
        except Exception:
            self.file.close()
            raise

    def close(self):
        self.file.close()

    def blocks(self, chunk, raw):
        for start in range(0, len(self.cell_ids), chunk):
            stop = min(start + chunk, len(self.cell_ids))
            block = self.matrix[start:stop]
            if sparse.issparse(block):
                block = sparse.csr_matrix(block, copy=True)
                block.sort_indices()
                if not block.has_canonical_format:
                    raise ValueError("duplicate sparse matrix coordinate; no silent coordinate summation")
                values = block.data
            else:
                values = np.asarray(block)
            if values.dtype.kind not in "biuf" or not np.isfinite(values).all():
                raise ValueError("expression values must be real and finite")
            if raw:
                if np.any(values < 0) or np.any(values > MAX_COUNT) or np.any(values != np.floor(values)):
                    raise ValueError("raw counts must be nonnegative int32-compatible integers")
            elif values.dtype.kind in "iu" and (np.any(values > 2**53) or np.any(values < -(2**53))):
                raise ValueError("integer expression outside exact float64 range")
            block = sparse.csr_matrix(block, dtype=np.int64 if raw else np.float64)
            block.eliminate_zeros()
            yield start, stop, block


def common_request():
    request = json.loads(Path(os.environ["AUTONOMICS_INPUT1"]).read_text())
    if not isinstance(request, dict) or request.get("input_sha256") != digest(os.environ["AUTONOMICS_INPUT0"]):
        raise ValueError("frozen H5AD SHA256 differs")
    layer = identity(os.environ["CS_LAYER"])
    chunk = int(os.environ["CS_CHUNK"])
    if "/" in layer or type(request.get("chunk")) is not int or chunk < 1 or chunk != request["chunk"] or request.get("input_layer") != layer:
        raise ValueError("frozen input layer/chunk differs; no fallback")
    if request.get("expression_scale") not in ("raw_integer_counts", "finite_numeric_expression") or not request.get("provenance_attestation"):
        raise ValueError("explicit expression scale and provenance attestation required")
    return request, layer, chunk


def aggregate(data, request, chunk):
    if request["expression_scale"] != "raw_integer_counts" or request.get("analysis_unit") != "SINGLE_CROSS_SECTIONAL_DONOR" or request.get("missing_label_policy") != "ERROR":
        raise ValueError("raw counts, cross-sectional donor units and strict missing-label policy required")
    target, minimum = identity(os.environ["CS_CELLTYPE"]), int(os.environ["CS_MIN_CELLS"])
    if request.get("celltype") != target or type(request.get("min_cells")) is not int or minimum < 1 or request["min_cells"] != minimum:
        raise ValueError("frozen cell type/eligibility threshold differs")
    columns = request.get("columns")
    if not isinstance(columns, dict) or set(columns) != {"donor", "celltype", "condition", "library"} or len(set(columns.values())) != 4:
        raise ValueError("distinct donor/celltype/condition/library columns are required")
    for name in columns.values():
        identity(name)
        if name not in data.obs or data.obs[name].isna().any():
            raise ValueError("missing cell identity/design label")
    labels = {name: [identity(value) for value in data.obs[column].tolist()] for name, column in columns.items()}
    donors = sorted(set(labels["donor"]))
    if request.get("planned_donor_ids") != donors:
        raise ValueError("predeclared donor universe differs")
    covariates = request.get("covariate_columns")
    if not isinstance(covariates, list) or len(set(covariates)) != len(covariates) or any(name not in data.obs or name in {"sample_id", "donor_id", "condition", "celltype", "n_cells"} for name in covariates):
        raise ValueError("covariate columns missing, duplicate or reserved")
    values = {}
    for donor in donors:
        rows = np.flatnonzero(np.array(labels["donor"]) == donor)
        conditions = {labels["condition"][index] for index in rows}
        if len(conditions) != 1:
            raise ValueError("condition differs within one donor, including across cell types/libraries")
        values[donor] = {"condition": next(iter(conditions))}
        for column in covariates:
            entries = data.obs.iloc[rows][column]
            if entries.isna().any() or any(isinstance(value, (float, np.floating)) and not np.isfinite(value) for value in entries):
                raise ValueError("missing/nonfinite donor covariate")
            distinct = {identity(str(value)) for value in entries}
            if len(distinct) != 1:
                raise ValueError("donor covariate differs across libraries/cell types")
            values[donor][column] = next(iter(distinct))
    if request.get("donor_conditions") != {donor: values[donor]["condition"] for donor in donors}:
        raise ValueError("frozen donor/condition map differs")
    sizes = {donor: sum(first == donor and second == target for first, second in zip(labels["donor"], labels["celltype"], strict=True)) for donor in donors}
    kept = [donor for donor in donors if sizes[donor] >= minimum]
    if not kept:
        raise ValueError("no donor reaches frozen target-cell eligibility")
    if len(kept) * len(data.gene_ids) > 20000000:
        raise ValueError("dense aggregated output exceeds scoped 20-million-entry allocation budget")
    if max(sizes.values()) * MAX_COUNT > np.iinfo(np.int64).max:
        raise ValueError("conservative int64 accumulation safety bound exceeded")
    counts = np.zeros((len(data.gene_ids), len(kept)), dtype=np.int64)
    group = {donor: index for index, donor in enumerate(kept)}
    participating = [labels["celltype"][index] == target and labels["donor"][index] in group for index in range(len(data.cell_ids))]
    for start, stop, block in data.blocks(chunk, raw=True):
        local = [index for index in range(stop - start) if participating[start + index]]
        if local:
            codes = [group[labels["donor"][start + index]] for index in local]
            onehot = sparse.csr_matrix((np.ones(len(local), dtype=np.int64), (codes, np.arange(len(local)))), shape=(len(kept), len(local)))
            counts += (onehot @ block[local]).T.toarray()
            if np.any(counts > MAX_COUNT):
                raise ValueError("aggregated count exceeds downstream int32 range; no integer wrap/truncation")
    with Path(os.environ["AUTONOMICS_OUTPUT0"]).open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["gene_id", *kept])
        for gene, row in zip(data.gene_ids, counts, strict=True):
            writer.writerow([gene, *row.tolist()])
    metadata = [{"sample_id": donor, "donor_id": donor, "condition": values[donor]["condition"], "celltype": target, "n_cells": sizes[donor], **{column: values[donor][column] for column in covariates}} for donor in kept]
    write_table(os.environ["AUTONOMICS_OUTPUT1"], list(metadata[0]), metadata)
    ledger = [{"donor_id": donor, "condition": values[donor]["condition"], "target_n_cells": sizes[donor],
        "libraries": json.dumps(sorted({labels["library"][index] for index in range(len(data.cell_ids)) if labels["donor"][index] == donor})),
        "status": "ELIGIBLE" if donor in group else "NO_TARGET_CELLS" if sizes[donor] == 0 else "LOW_CELL_COUNT"} for donor in donors]
    write_table(os.environ["AUTONOMICS_OUTPUT2"], list(ledger[0]), ledger)
    cells = [{"cell_id": cell, "donor_id": labels["donor"][index], "celltype": labels["celltype"][index],
        "library_id": labels["library"][index], "status": "AGGREGATED" if participating[index] else "NOT_TARGET" if labels["celltype"][index] != target else "LOW_CELL_COUNT"} for index, cell in enumerate(data.cell_ids)]
    write_table(os.environ["AUTONOMICS_OUTPUT3"], list(cells[0]), cells)
    return {"planned_donor_ids": donors, "eligible_donor_ids": kept, "gene_ids": data.gene_ids,
        "independent_units_are_donors_not_cells_or_libraries": True, "sample_id_equals_donor_id_single_celltype": True,
        "input_cells": len(data.cell_ids), "aggregated_cells": sum(participating), "dense_output_entries": counts.size,
        "library_and_donor_authenticity_remains_attestation": True, "gene_family_filtering_performed": False}


def export(data, request, chunk):
    if request.get("coordinate_policy") != "NONZERO_WITH_COMPLETE_AXES_IMPLICIT_ZERO" or request.get("output_precision") != "FLOAT64_EXACT_INPUT":
        raise ValueError("explicit coordinate/precision policy required")
    if "cell_id" in data.obs.columns or "gene_id" in data.var.columns:
        raise ValueError("metadata identity column collides with exported axis header")
    entries = 0
    schema = pa.schema([("cell_id", pa.string()), ("gene_id", pa.string()), ("value", pa.float64())])
    with pq.ParquetWriter(os.environ["AUTONOMICS_OUTPUT0"], schema, compression="zstd") as writer:
        for start, stop, block in data.blocks(chunk, request["expression_scale"] == "raw_integer_counts"):
            coordinates = block.tocoo()
            table = pa.table({"cell_id": [data.cell_ids[start + index] for index in coordinates.row],
                "gene_id": [data.gene_ids[index] for index in coordinates.col], "value": coordinates.data.astype(np.float64)}, schema=schema)
            writer.write_table(table)
            entries += len(coordinates.data)
    data.obs.to_csv(os.environ["AUTONOMICS_OUTPUT1"], sep="\t", index_label="cell_id")
    data.var.to_csv(os.environ["AUTONOMICS_OUTPUT2"], sep="\t", index_label="gene_id")
    return {"shape": [len(data.cell_ids), len(data.gene_ids)], "cell_ids": data.cell_ids, "gene_ids": data.gene_ids,
        "nonzero_coordinates": entries, "coordinate_policy": request["coordinate_policy"], "implicit_zero_is_not_biological_missingness": True,
        "matrix_full_load_fallback": False, "metadata_loaded_in_memory": True}


def qc(data, request, chunk):
    import scanpy as sc

    if request["expression_scale"] != "raw_integer_counts" or request.get("filter_order") != "CELL_THEN_GENE" or request.get("zero_total_policy") != "DROP_WITH_UNDEFINED_PERCENTAGE" or request.get("output_content") != "COUNTS_ONLY_OBS_VAR":
        raise ValueError("raw counts and exact QC filtering/zero/output conventions required")
    annotations = request.get("qc_gene_ids")
    if not isinstance(annotations, dict) or set(annotations) != {"mt", "rb"}:
        raise ValueError("exact frozen mt/rb gene IDs required; no guessed symbol regex")
    for name, genes in annotations.items():
        if not isinstance(genes, list) or identities(genes) != genes or not set(genes) <= set(data.gene_ids):
            raise ValueError("QC annotation IDs absent/duplicate/invalid")
    thresholds = request.get("thresholds")
    expected = {"min_genes", "max_genes", "min_counts", "max_counts", "min_cells", "max_cells", "max_pct_mt", "max_pct_rb"}
    if not isinstance(thresholds, dict) or set(thresholds) != expected:
        raise ValueError("all prelocked QC thresholds required")
    for name, value in thresholds.items():
        if name.startswith("max_pct"):
            if type(value) not in (float, int) or not np.isfinite(value) or not 0 <= value <= 100:
                raise ValueError("invalid percentage threshold")
        elif type(value) is not int or value < 0:
            raise ValueError("nonnegative integer count thresholds required")
    for suffix in ("genes", "counts", "cells"):
        if thresholds["max_" + suffix] and thresholds["max_" + suffix] < thresholds["min_" + suffix]:
            raise ValueError("maximum QC threshold below minimum")
    for name in ("mt", "rb"):
        if not annotations[name] and thresholds["max_pct_" + name] < 100:
            raise ValueError("active percentage filter has no qualified annotation genes")
    matrix = sparse.vstack([block for _, _, block in data.blocks(chunk, raw=True)], format="csr")
    filtered = ad.AnnData(X=matrix, obs=data.obs.copy(), var=data.var.copy())
    reserved_obs = {"n_genes_by_counts", "total_counts", "total_counts_qc_mt", "pct_counts_qc_mt", "total_counts_qc_rb", "pct_counts_qc_rb"}
    reserved_var = {"qc_mt", "qc_rb", "n_cells_by_counts", "mean_counts", "pct_dropout_by_counts", "total_counts"}
    if set(filtered.obs.columns) & reserved_obs or set(filtered.var.columns) & reserved_var:
        raise ValueError("preexisting QC metric/annotation columns would be overwritten")
    for name in ("mt", "rb"):
        filtered.var["qc_" + name] = filtered.var_names.isin(annotations[name])
    sc.pp.calculate_qc_metrics(filtered, qc_vars=["qc_mt", "qc_rb"], percent_top=None, log1p=False, inplace=True, parallel=False)
    values = filtered.obs
    retained = values["total_counts"].to_numpy() > 0
    for feature, minimum, maximum in (("n_genes_by_counts", "min_genes", "max_genes"), ("total_counts", "min_counts", "max_counts")):
        retained &= values[feature].to_numpy() >= thresholds[minimum]
        if thresholds[maximum]:
            retained &= values[feature].to_numpy() <= thresholds[maximum]
    for name in ("mt", "rb"):
        retained &= values["pct_counts_qc_" + name].to_numpy() <= thresholds["max_pct_" + name]
    if not retained.any():
        raise ValueError("QC filters removed all cells")
    detections = np.asarray((filtered.X[retained] > 0).sum(axis=0)).ravel()
    retained_genes = detections >= thresholds["min_cells"]
    if thresholds["max_cells"]:
        retained_genes &= detections <= thresholds["max_cells"]
    if not retained_genes.any():
        raise ValueError("QC filters removed all genes")
    cell_rows = [{"cell_id": cell, **{column: "NA" if pd.isna(values.iloc[index][column]) else values.iloc[index][column] for column in sorted(reserved_obs)},
        "status": "KEPT" if retained[index] else "ZERO_TOTAL" if values.iloc[index]["total_counts"] == 0 else "QC_EXCLUDED"} for index, cell in enumerate(data.cell_ids)]
    gene_rows = [{"gene_id": gene, "n_cells_detected_after_cell_filter": int(detections[index]), "status": "KEPT" if retained_genes[index] else "QC_EXCLUDED"} for index, gene in enumerate(data.gene_ids)]
    write_table(os.environ["AUTONOMICS_OUTPUT1"], list(cell_rows[0]), cell_rows)
    write_table(os.environ["AUTONOMICS_OUTPUT2"], list(gene_rows[0]), gene_rows)
    filtered = filtered[retained, retained_genes].copy()
    filtered.layers["counts"] = filtered.X.copy()
    filtered.uns["cachexia_qc_contract_sha256"] = digest(os.environ["AUTONOMICS_INPUT1"])
    ad.settings.allow_write_nullable_strings = True
    filtered.write_h5ad(os.environ["AUTONOMICS_OUTPUT0"], compression="gzip")
    return {"scanpy": sc.__version__, "input_cells": len(data.cell_ids), "output_cells": filtered.n_obs,
        "input_genes": len(data.gene_ids), "output_genes": filtered.n_vars, "retained_cell_ids": filtered.obs_names.tolist(),
        "retained_gene_ids": filtered.var_names.tolist(), "filter_order": request["filter_order"],
        "zero_total_percentage": "NA", "zero_total_cell_policy": "DROP", "output_content": "COUNTS_ONLY_OBS_VAR",
        "other_layers_embeddings_uns_not_preserved": True, "doublet_or_ambient_RNA_correction_performed": False,
        "matrix_loaded_for_official_QC": True, "all_QC_metrics_on_pre_filter_raw_layer": True}


def run():
    mode = os.environ["CS_MODE"]
    if mode not in ("pseudobulk", "export", "qc"):
        raise ValueError("unsupported single-cell execution mode")
    request, layer, chunk = common_request()
    data = H5Input(os.environ["AUTONOMICS_INPUT0"], layer)
    try:
        audit = {"execution_status": "COMPLETED", "mode": mode, "input_sha256": request["input_sha256"],
            "contract_sha256": digest(os.environ["AUTONOMICS_INPUT1"]), "layer": layer, "chunk": chunk,
            "runtime": {"anndata": ad.__version__, "numpy": np.__version__, "scipy": scipy.__version__},
            "scientific_release": False, "g0_granted": False, "provenance_is_attestation_not_authentication": True}
        audit.update({"pseudobulk": aggregate, "export": export, "qc": qc}[mode](data, request, chunk))
        port = 4 if mode == "pseudobulk" else 3
        Path(os.environ[f"AUTONOMICS_OUTPUT{port}"]).write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    finally:
        data.close()


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        port = 4 if os.environ.get("CS_MODE") == "pseudobulk" else 3
        for index in range(port):
            if os.environ.get(f"AUTONOMICS_OUTPUT{index}"):
                Path(os.environ[f"AUTONOMICS_OUTPUT{index}"]).unlink(missing_ok=True)
        report = os.environ.get(f"AUTONOMICS_OUTPUT{port}")
        if report:
            Path(report).write_text(json.dumps({"execution_status": "FAILED", "status": "BLOCKED", "error": str(error), "scientific_release": False, "g0_granted": False}, indent=2) + "\n")
        raise SystemExit(2)
