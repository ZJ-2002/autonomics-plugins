import csv
from decimal import Decimal
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import warnings

import anndata as ad
import h5py
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import scanpy as sc
import scipy.sparse as sparse
from sklearn.exceptions import ConvergenceWarning


KEYS = {"schema_version", "scope", "mode", "input_role", "scientific_qualification", "analysis_role", "input0_sha256", "input2_sha256",
        "input_layer", "expression_scale", "expected_cell_ids", "expected_gene_ids", "max_input_bytes", "max_cells", "max_genes", "max_entries", "params"}
PARAMS = {"ingest": {"orientation", "metadata_columns"}, "subset": {"order"},
          "rank": {"groupby", "group_counts", "groups", "reference", "method", "n_genes", "tie_correct", "corr_method", "rankby_abs", "logreg"},
          "means": {"groupby", "group_counts", "genes", "normalize", "target_sum"},
          "embedding": {"normalize", "log1p", "target_sum", "hvg_flavor", "n_top_genes", "n_bins", "scale", "zero_center", "max_value", "n_pcs", "svd_solver", "n_neighbors", "metric", "min_dist", "spread", "umap_epochs", "resolution", "leiden_iterations", "seed"}}
VERSIONS = {"scanpy": "1.11.3", "anndata": "0.11.4", "numpy": "2.1.3", "scipy": "1.14.1"}
ROLE = "CELL_LEVEL_DESCRIPTIVE_EXPLORATORY_NOT_DONOR_INFERENCE"


def require(value, message):
    if not value: raise ValueError(message)


def sha256(filename):
    with Path(filename).open("rb") as handle: return hashlib.file_digest(handle, "sha256").hexdigest()


def identity(value):
    require(isinstance(value, str) and value and value == value.strip() and not any(ord(character) < 32 or ord(character) == 127 for character in value), "Exact nonempty lexical identity required")
    return value


def identities(values):
    require(isinstance(values, (list, pd.Index)), "Explicit identity sequence required")
    result = [identity(value) for value in values]
    require(result and len(set(result)) == len(result), "Empty or duplicated cell/gene/selection identities")
    return result


def integer(value, minimum, maximum):
    require(type(value) is int and minimum <= value <= maximum, "Frozen integer outside bounded domain")
    return value


def number(value, minimum, maximum, inclusive=True):
    require(type(value) in {int, float} and np.isfinite(value) and (minimum <= value if inclusive else minimum < value) and value <= maximum, "Frozen finite numerical parameter outside domain")
    return float(value)


def boolean(value):
    require(type(value) is bool, "Frozen boolean required")
    return value


def write_table(filename, columns, rows):
    with filename.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def numeric(value):
    if np.isnan(value): return "NA"
    if np.isposinf(value): return "Inf"
    if np.isneginf(value): return "-Inf"
    return format(float(value), ".17g")


def write_result(filename, records):
    floating = {"score", "logfoldchange", "pvalue", "pvalue_adj", "PC1", "UMAP1", "UMAP2", "mean_expression", "pct_expressed"}
    integral = {"input_index", "rank", "n_expressing", "n_cells"}
    schema = pa.schema([(name, pa.float64() if name in floating else pa.int64() if name in integral else pa.string()) for name in records[0]])
    typed = [{name: (None if value == "NA" else float(value)) if name in floating else int(value) if name in integral else str(value) for name, value in row.items()} for row in records]
    pq.write_table(pa.Table.from_pylist(typed, schema=schema), filename)


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicated JSON contract key; no last-value-wins configuration")
        result[key] = value
    return result


def expression_token(value, raw):
    decimal = Decimal(value)
    require(decimal.is_finite() and 0 <= decimal <= (2147483647 if raw else 2**53), "Finite nonnegative decimal expression within exact input scale required")
    if raw: require(decimal == decimal.to_integral_value(), "Raw-count decimal token must be an integer before float conversion")
    converted = float(decimal)
    require(decimal == 0 or converted != 0, "Nonzero expression token underflows float64; no silent zero")
    return converted


def metadata_columns(values):
    columns = identities(values)
    require("cell_id" not in columns, "Metadata columns cannot duplicate reserved cell_id header")
    return columns


def canonical_matrix(matrix, raw=False):
    if sparse.issparse(matrix):
        matrix = matrix.copy()
        matrix.sort_indices()
        require(matrix.has_canonical_format, "Duplicate sparse coordinates cannot be silently summed")
        values = matrix.data
    else:
        matrix = np.asarray(matrix)
        values = matrix
    require(values.dtype.kind in "biuf" and np.isfinite(values).all() and np.all(values >= 0), "Finite nonnegative real expression required")
    require(np.all(values <= (2147483647 if raw else 2**53)), "Expression outside exact bounded input scale")
    if raw: require(np.all(values == np.floor(values)), "Raw counts must be integers, not normalized/log expression")
    matrix = matrix.astype(np.float64, copy=True)
    if sparse.issparse(matrix):
        matrix = matrix.tocsr()
        matrix.eliminate_zeros()
    return matrix


def read_request(mode):
    require(os.environ.get("AUTONOMICS_INPUT_COUNT") == ("3" if mode in {"ingest", "subset"} else "2"), "Declared input count differs")
    filename = Path(os.environ["AUTONOMICS_INPUT1"])
    request = json.loads(filename.read_text(), object_pairs_hook=unique_json)
    require(isinstance(request, dict) and set(request) == KEYS and type(request["schema_version"]) is int and request["schema_version"] == 1, "Exact frozen contract schema required")
    require(request["mode"] == mode and mode in PARAMS, "Node and request mode differ")
    require(request["scope"] == "TECHNICAL_ONLY_NOT_G0" and request["scientific_qualification"] == "NOT_GRANTED" and request["analysis_role"] == ROLE, "Descriptive technical scope required; no donor-level inference/G0")
    require(request["input_role"] in {"SYNTHETIC_TECHNICAL_INPUT", "LEGACY_SEEN_NOT_QUALIFIED_COHORT"}, "Independent research evidence not authorized")
    require(isinstance(request["params"], dict) and set(request["params"]) == PARAMS[mode], "Exact method parameters required; no defaults or unknown keys")
    integer(request["max_input_bytes"], 1, 64 * 1024**2)
    integer(request["max_cells"], 2, 5000)
    integer(request["max_genes"], 2, 1000)
    integer(request["max_entries"], 1, 5_000_000)
    cells, genes = identities(request["expected_cell_ids"]), identities(request["expected_gene_ids"])
    require(len(cells) <= request["max_cells"] and len(genes) <= request["max_genes"] and len(cells) * len(genes) <= request["max_entries"], "Frozen axes exceed matrix budget")
    require(request["expression_scale"] in {"raw_integer_counts", "log1p_cp10k", "finite_nonnegative_expression"}, "Explicit expression scale required")
    for port in (0, 2) if mode in {"ingest", "subset"} else (0,):
        checksum = request[f"input{port}_sha256"]
        source = Path(os.environ[f"AUTONOMICS_INPUT{port}"])
        require(isinstance(checksum, str) and re.fullmatch(r"[a-f0-9]{64}", checksum) and source.stat().st_size <= request["max_input_bytes"] and sha256(source) == checksum, "Frozen input SHA256/byte budget differs")
    if mode not in {"ingest", "subset"}: require(request["input2_sha256"] == "NOT_APPLICABLE", "Undeclared sidecar hash")
    return request


def load_h5ad(request):
    filename = Path(os.environ["AUTONOMICS_INPUT0"])
    with h5py.File(filename, "r") as handle:
        obs, var = ad.io.read_elem(handle["obs"]), ad.io.read_elem(handle["var"])
        require(identities(obs.index.tolist()) == request["expected_cell_ids"] and identities(var.index.tolist()) == request["expected_gene_ids"], "Frozen complete H5AD axes/order differ")
        require(request["input_layer"] == "X" or request["input_layer"] in handle["layers"], "Explicit expression layer absent; no X fallback")
        encoded_bytes = []
        handle.visititems(lambda name, value: encoded_bytes.append(value.size * value.dtype.itemsize) if isinstance(value, h5py.Dataset) else None)
        require(sum(encoded_bytes) <= 256 * 1024**2, "Complete H5AD encoded arrays exceed backed preflight budget")
    data = ad.read_h5ad(filename)
    matrix = data.X if request["input_layer"] == "X" else data.layers[request["input_layer"]]
    matrix = canonical_matrix(matrix, request["expression_scale"] == "raw_integer_counts")
    return data, matrix


def group_labels(data, params):
    name = identity(params["groupby"])
    require(name in data.obs and not data.obs[name].isna().any(), "Group labels absent/missing; cannot convert missingness to a group")
    labels = [identity(value) for value in data.obs[name].tolist()]
    observed = {value: labels.count(value) for value in sorted(set(labels))}
    expected = params["group_counts"]
    require(isinstance(expected, dict) and all(type(value) is int and value > 0 for value in expected.values()) and expected == observed, "Complete frozen group/cell counts differ")
    return observed


def ingest(request):
    params = request["params"]
    columns = metadata_columns(params["metadata_columns"])
    require(request["input_layer"] == "NOT_APPLICABLE" and params["orientation"] in {"gene_by_cell", "cell_by_gene"}, "Explicit dense ingest orientation required")
    with Path(os.environ["AUTONOMICS_INPUT0"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle, delimiter="\t", strict=True))
    require(rows and len(rows) > 1, "Empty matrix")
    by_gene = params["orientation"] == "gene_by_cell"
    row_ids, column_ids = [row[0] for row in rows[1:]], rows[0][1:]
    require(rows[0][0] == ("gene_id" if by_gene else "cell_id"), "Explicit axis header required")
    require(identities(row_ids) == (request["expected_gene_ids"] if by_gene else request["expected_cell_ids"]) and identities(column_ids) == (request["expected_cell_ids"] if by_gene else request["expected_gene_ids"]), "All frozen TSV axes/order must match")
    require(all(len(row) == len(rows[0]) for row in rows[1:]), "Matrix row width differs")
    matrix = canonical_matrix(np.array([[expression_token(value, request["expression_scale"] == "raw_integer_counts") for value in row[1:]] for row in rows[1:]]), request["expression_scale"] == "raw_integer_counts")
    if by_gene: matrix = matrix.T
    with Path(os.environ["AUTONOMICS_INPUT2"]).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t", strict=True)
        require(reader.fieldnames == ["cell_id", *columns], "Exact cell metadata header/order required")
        metadata = list(reader)
    require(all(set(row) == set(reader.fieldnames) and all(isinstance(value, str) and value for value in row.values()) for row in metadata), "Cell metadata cannot be missing/padded")
    require([row["cell_id"] for row in metadata] == request["expected_cell_ids"], "Complete cell metadata order differs")
    obs = pd.DataFrame(metadata).set_index("cell_id")
    data = ad.AnnData(X=matrix, obs=obs, var=pd.DataFrame(index=request["expected_gene_ids"]))
    if request["expression_scale"] == "raw_integer_counts": data.layers["counts"] = matrix.astype(np.int64)
    elif request["expression_scale"] == "log1p_cp10k": data.layers["lognorm"] = matrix.copy()
    return data, [{"cell_id": value, "input_index": index, "status": "INGESTED_WITHOUT_NORMALIZATION"} for index, value in enumerate(data.obs_names)], {"orientation": params["orientation"], "normalization_performed": False}


def subset(data, request):
    table = pq.read_table(os.environ["AUTONOMICS_INPUT2"])
    require(table.column_names == ["cell_id"] and (pa.types.is_string(table["cell_id"].type) or pa.types.is_large_string(table["cell_id"].type)), "Selection must contain exact string cell_id, not numeric/coerced IDs")
    requested = identities(table["cell_id"].to_pylist())
    require(set(requested) <= set(data.obs_names), "Unknown requested cell; no partial cohort deletion")
    policy = request["params"]["order"]
    require(policy in {"INPUT_CELL_ORDER", "SELECTION_ORDER"}, "Explicit subset ordering required")
    selected = [value for value in data.obs_names if value in set(requested)] if policy == "INPUT_CELL_ORDER" else requested
    indices = [data.obs_names.get_loc(value) for value in selected]
    output = data[indices, :].copy()
    return output, [{"cell_id": value, "input_index": data.obs_names.get_loc(value), "status": "SELECTED" if value in set(selected) else "NOT_REQUESTED"} for value in data.obs_names], {"selected_cells": len(selected), "old_graph_submatrices_are_not_new_graphs": True}


def embedding(data, matrix, request):
    params = request["params"]
    for name in ("normalize", "log1p", "scale", "zero_center"): boolean(params[name])
    raw = request["expression_scale"] == "raw_integer_counts"
    require((raw and params["normalize"] and params["log1p"]) or (request["expression_scale"] == "log1p_cp10k" and not params["normalize"] and not params["log1p"]), "HVG requires explicit log1p scale; no double normalization/log or raw-as-log")
    require(not any(key in data.obsm for key in ("X_pca", "X_umap")) and not any(key in data.uns for key in ("pca", "neighbors", "umap")) and "PCs" not in data.varm and "leiden" not in data.obs, "Existing PCA/graph/result provenance unqualified; no reuse/clobber")
    require("distances" not in data.obsp and "connectivities" not in data.obsp, "Existing neighbor graph must be explicitly separated")
    integer(params["seed"], 0, 2147483647)
    integer(params["n_top_genes"], 2, data.n_vars)
    integer(params["n_bins"], 2, 100)
    integer(params["n_neighbors"], 2, data.n_obs-1)
    integer(params["n_pcs"], 1, min(data.n_obs-1, data.n_vars-1))
    integer(params["umap_epochs"], 10, 1000)
    integer(params["leiden_iterations"], 2, 100)
    for name in ("target_sum", "max_value", "spread", "resolution"): number(params[name], 0, 1e6, False)
    number(params["min_dist"], 0, params["spread"])
    require(params["hvg_flavor"] in {"seurat", "cell_ranger"} and params["svd_solver"] == "arpack" and params["metric"] in {"euclidean", "cosine"}, "Unsupported explicit official embedding method")
    data.X = matrix.copy()
    if params["normalize"]:
        require(np.all(np.asarray(matrix.sum(axis=1)).ravel() > 0), "Zero-total cells must pass QC before normalization")
        sc.pp.normalize_total(data, target_sum=params["target_sum"])
    if params["log1p"]:
        require("log1p" not in data.uns, "Existing log metadata cannot qualify raw count layer")
        sc.pp.log1p(data)
    require("cachexia_model_log1p" not in data.layers, "Existing model layer cannot be overwritten")
    data.layers["cachexia_model_log1p"] = data.X.copy()
    sc.pp.highly_variable_genes(data, n_top_genes=params["n_top_genes"], n_bins=params["n_bins"], flavor=params["hvg_flavor"], subset=False)
    hvg = int(data.var["highly_variable"].sum())
    require(params["n_pcs"] < min(hvg, data.n_obs), "Requested PCA dimensions exceed observed HVGs; no silent reduction")
    if params["scale"]: sc.pp.scale(data, zero_center=params["zero_center"], max_value=params["max_value"])
    sc.pp.pca(data, n_comps=params["n_pcs"], zero_center=params["zero_center"], svd_solver=params["svd_solver"], random_state=params["seed"], mask_var="highly_variable", dtype="float32")
    sc.pp.neighbors(data, n_neighbors=params["n_neighbors"], n_pcs=params["n_pcs"], use_rep="X_pca", metric=params["metric"], method="umap", random_state=params["seed"])
    sc.tl.umap(data, min_dist=params["min_dist"], spread=params["spread"], maxiter=params["umap_epochs"], random_state=params["seed"])
    sc.tl.leiden(data, resolution=params["resolution"], random_state=params["seed"], flavor="igraph", n_iterations=params["leiden_iterations"], directed=False, key_added="leiden")
    records = [{"cell_id": value, "leiden": str(data.obs["leiden"].iloc[index]), "PC1": numeric(data.obsm["X_pca"][index,0]), "UMAP1": numeric(data.obsm["X_umap"][index,0]), "UMAP2": numeric(data.obsm["X_umap"][index,1]), "analysis_role": ROLE} for index, value in enumerate(data.obs_names)]
    return data, records, {"n_HVG": hvg, "n_pcs_actual": int(data.obsm["X_pca"].shape[1]), "gene_selection": "HVG_MASK_PRESERVE_ALL_GENES", "existing_PCA_reused": False}


def rank(data, request):
    params = request["params"]
    require(request["expression_scale"] == "log1p_cp10k", "Markers require frozen log1p expression; raw/integrated/scaled input not accepted")
    counts = group_labels(data, params)
    require("rest" not in counts, "Actual group named rest conflicts with official marker reference semantics")
    groups = identities(params["groups"])
    require(set(groups) <= set(counts) and all(counts[value] >= 2 for value in groups), "Unknown/underpowered marker group")
    reference = params["reference"]
    require(reference == "rest" or reference in counts and reference not in groups and counts[reference] >= 2, "Reference missing/in target groups")
    require(params["method"] in {"wilcoxon", "t-test", "t-test_overestim_var", "logreg"} and params["corr_method"] in {"benjamini-hochberg", "bonferroni"}, "Explicit official marker method/correction required")
    require(len(counts) >= 2 and all(data.n_obs-counts[value] >= 2 for value in groups), "No adequate reference cells")
    integer(params["n_genes"], 1, data.n_vars)
    boolean(params["tie_correct"])
    boolean(params["rankby_abs"])
    options = params["logreg"]
    if params["method"] == "logreg":
        require(isinstance(options, dict) and set(options) == {"solver", "max_iter", "C", "tol", "random_state"} and options["solver"] == "lbfgs", "Explicit complete logreg method required")
        integer(options["max_iter"], 100, 10000)
        integer(options["random_state"], 0, 2147483647)
        number(options["C"], 0, 100, False)
        number(options["tol"], 0, 1, False)
    else: require(options == {}, "Logreg parameters cannot alter another method")
    require("cachexia_rank_genes_groups" not in data.uns, "Existing marker result must not be overwritten")
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always")
        sc.tl.rank_genes_groups(data, groupby=params["groupby"], groups=groups, reference=reference, n_genes=params["n_genes"], method=params["method"],
                               corr_method=params["corr_method"], tie_correct=params["tie_correct"], rankby_abs=params["rankby_abs"], use_raw=False,
                               layer=None if request["input_layer"] == "X" else request["input_layer"], key_added="cachexia_rank_genes_groups", **options)
    require(not any(issubclass(value.category, ConvergenceWarning) for value in notices), "Official logistic marker model did not converge; no silent result")
    results = data.uns["cachexia_rank_genes_groups"]
    records = []
    for group in results["names"].dtype.names:
        for index in range(len(results["names"])):
            row = {"group_id": str(group), "gene_id": str(results["names"][index][group]), "rank": index+1, "analysis_role": ROLE}
            for output, key in (("score", "scores"), ("logfoldchange", "logfoldchanges"), ("pvalue", "pvals"), ("pvalue_adj", "pvals_adj")):
                row[output] = numeric(results[key][index][group]) if key in results else "NA"
            row["pvalue_status"] = "OFFICIAL_VALUE_OR_NAN" if "pvals" in results else "NOT_PROVIDED_BY_OFFICIAL_LOGREG"
            records.append(row)
    require(records, "Official marker result empty")
    return data, records, {"official_result_fields": list(results), "official_warning_messages": [str(value.message) for value in notices], "cell_markers_are_not_donor_inference": True}


def means(data, matrix, request):
    params = request["params"]
    counts = group_labels(data, params)
    selected = identities(params["genes"])
    require(set(selected) <= set(data.var_names), "Requested summary gene absent; no silent intersection")
    require(params["normalize"] in {"none", "cp10k"}, "Explicit cluster mean scale required")
    number(params["target_sum"], 0, 1e6, False)
    if params["normalize"] == "cp10k":
        require(request["expression_scale"] == "raw_integer_counts", "CP10K must start from qualified raw counts")
        totals = np.asarray(matrix.sum(axis=1)).ravel()
        require(np.all(totals > 0), "Zero-total cell must be qualified before cluster mean normalization")
        matrix = sparse.diags(params["target_sum"]/totals) @ matrix if sparse.issparse(matrix) else matrix * (params["target_sum"]/totals)[:, None]
    work = ad.AnnData(X=matrix[:, [data.var_names.get_loc(value) for value in selected]], obs=data.obs.copy(), var=data.var.loc[selected].copy())
    work.obs[params["groupby"]] = pd.Categorical(work.obs[params["groupby"]].tolist(), categories=list(counts))
    result = sc.get.aggregate(work, by=params["groupby"], func=["mean", "count_nonzero"], axis="obs", dof=0)
    records = []
    for row_index, group in enumerate(result.obs[params["groupby"]]):
        for gene_index, gene in enumerate(result.var_names):
            detected = int(result.layers["count_nonzero"][row_index, gene_index])
            records.append({"group_id": str(group), "gene_id": str(gene), "mean_expression": numeric(result.layers["mean"][row_index, gene_index]),
                            "n_expressing": detected, "n_cells": counts[str(group)], "pct_expressed": numeric(100 * detected/counts[str(group)]), "analysis_role": ROLE})
    return result, records, {"normalization_gene_universe": "FULL_INPUT_BEFORE_GENE_SELECTION", "zero_detection": "POSITIVE_NONNEGATIVE_VALUES_NOT_STORED_SPARSE_ZEROS", "n_groups": result.n_obs}


def main():
    outputs = [Path(os.environ[f"AUTONOMICS_OUTPUT{index}"]) for index in range(5)]
    require(len({value.resolve() for value in outputs}) == 5 and not any(os.path.lexists(value) for value in outputs), "Refusing output overwrite or aliased ports")
    audit = {"status": "RUNNING", "g0_granted": False, "donor_inference_granted": False, "resident_deployment_granted": False}
    def save(): outputs[2].write_text(json.dumps(audit, indent=2) + "\n")
    def log(value):
        with outputs[3].open("a", encoding="utf-8") as handle: handle.write(value+"\n")
    try:
        save()
        log("RUNNING " + ROLE)
        require(all(importlib.metadata.version(name) == version for name, version in VERSIONS.items()), "Official package versions differ from locked runtime")
        mode = os.environ["CACHEXIA_SCANPY_MODE"]
        request = read_request(mode)
        audit.update(request=request, contract_sha256=sha256(os.environ["AUTONOMICS_INPUT1"]), versions=VERSIONS)
        save()
        if mode == "ingest": data, records, details = ingest(request)
        else:
            data, matrix = load_h5ad(request)
            if mode == "subset": data, records, details = subset(data, request)
            elif mode == "embedding": data, records, details = embedding(data, matrix, request)
            elif mode == "rank":
                if request["input_layer"] == "X": data.X = matrix
                else: data.layers[request["input_layer"]] = matrix
                data, records, details = rank(data, request)
            else: data, records, details = means(data, matrix, request)
        data.write_h5ad(outputs[1], compression="gzip")
        write_result(outputs[0], records)
        ledger = [{"gene_id": value, "input_index": index, "status": "RETAINED" if value in data.var_names else "NOT_REQUESTED"} for index, value in enumerate(request["expected_gene_ids"])]
        write_table(outputs[4], ["gene_id", "input_index", "status"], ledger)
        audit.update(details=details, numerical_missing_policy="OFFICIAL_NAN_OR_ABSENT_TO_TYPED_NULL_RAW_UNS_PRESERVED", status="TECHNICAL_PASS_NOT_SCIENTIFIC_OR_DONOR_INFERENCE", output0_sha256=sha256(outputs[0]), output1_sha256=sha256(outputs[1]), result_rows=len(records), output_cells=data.n_obs, output_genes=data.n_vars)
        save()
        log("PASS " + mode + " output_rows=" + str(len(records)))
        return 0
    except Exception as error:
        for index in (0, 1, 4): outputs[index].unlink(missing_ok=True)
        audit.update(status="BLOCKED", error_type=type(error).__name__, error=str(error))
        save()
        log("BLOCKED " + str(error))
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__": sys.exit(main())
