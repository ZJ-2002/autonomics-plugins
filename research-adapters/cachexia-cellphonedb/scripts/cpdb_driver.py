"""Translate frozen inputs into the official CellPhoneDB API without changing its methods."""

import contextlib
import csv
import hashlib
import importlib.metadata
import inspect
import itertools
import json
import math
import os
from pathlib import Path
import pickle
import re
import sys
import warnings
import zipfile

import anndata
import h5py
import numpy as np
import pandas as pd
from scipy import sparse


DB_SHA = "b726745421b6c8f091f9b464e1d20fc676908d18a6669a969eb08877f6dff07f"
KEYS = {"schema_version", "input0_sha256", "scale", "preprocessing", "counts_data", "seed", "iterations",
        "threshold", "result_precision", "pvalue", "score_interactions", "group_column", "donor_column", "tissue_column",
        "expected_genes", "expected_cells", "expected_groups", "expected_donors", "expected_tissue", "scope", "null_unit",
        "family_id", "test_id", "input_origin", "database_sha256", "expected_x_dtype"}
FIELDS = ["test_id", "table", "row_position", "column_position", "row_label_json", "column_label_json", "value_kind",
          "numeric_value", "text_json", "missing_kind", "source_position"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def object_unique(items):
    require(len(items) == len({key for key, value in items}), "Duplicate JSON keys forbidden")
    return dict(items)


def json_read(path):
    def invalid(value):
        raise ValueError("Nonstandard JSON constant forbidden: "+value)
    return json.loads(path.read_text(), object_pairs_hook=object_unique, parse_constant=invalid)


def identity(value):
    return isinstance(value, str) and value.strip() == value and bool(value) and not any(character in value for character in "\t\r\n\x00")


def identities(value, name):
    require(type(value) is list and bool(value) and all(identity(item) for item in value) and len(value) == len(set(value)),
            "Invalid or duplicate frozen identities: "+name)
    return value


def integer(value, lower, upper, name):
    require(type(value) is int and lower <= value <= upper, "Invalid integer "+name)
    return value


def real(value, lower, upper, name):
    require(type(value) in (int, float) and math.isfinite(value) and lower <= value <= upper, "Invalid numeric "+name)
    return value


def scalar(value):
    if value is None: return "MISSING", "NA", "null", "NONE"
    if value is pd.NA: return "MISSING", "NA", "null", "PANDAS_NA"
    if isinstance(value, (np.bool_, bool)): return "BOOLEAN", "NA", json.dumps(bool(value)), ""
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        if math.isnan(number): return "MISSING", "NA", "null", "FLOAT_NAN"
        require(math.isfinite(number), "Official nonfinite result not usable")
        if isinstance(value, (int, np.integer)):
            require(int(number) == int(value), "Lossy official integer output")
        return "NUMERIC", repr(number), "null", ""
    require(isinstance(value, str), "Unsupported official scalar type: "+type(value).__name__)
    return "TEXT", "NA", json.dumps(value, ensure_ascii=True), ""


def flat_tables(result, test_id):
    rows = []
    for name, table in result.items():
        if name in {"CellSign_active_interactions", "CellSign_active_interactions_deconvoluted"} and table is pd.DataFrame:
            continue
        require(isinstance(table, pd.DataFrame) and not table.columns.has_duplicates, "Unexpected official result table")
        for row_position in range(len(table)):
            for column_position in range(len(table.columns)):
                kind, number, text, missing = scalar(table.iloc[row_position, column_position])
                row_label = table.index[row_position]
                if isinstance(row_label, np.integer): row_label = int(row_label)
                require(type(row_label) in (str, int), "Unsupported official row label")
                rows.append(dict(zip(FIELDS, [test_id, name, row_position, column_position,
                    json.dumps(row_label, ensure_ascii=True), json.dumps(str(table.columns[column_position]), ensure_ascii=True),
                    kind, number, text, missing, len(rows)], strict=True)))
    require(bool(rows), "Official result is empty")
    return rows


def write_tsv(path, fields, rows):
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def h5_structure(path):
    with h5py.File(path) as handle:
        require("X" in handle and "obs" in handle and "var" in handle, "Missing H5AD axes or X")
        sizes = []
        for axis in ("obs", "var"):
            index = handle[axis].attrs.get("_index")
            require(isinstance(index, str) and "/" not in index and index in handle[axis], "Invalid H5AD index attribute")
            sizes.append(len(handle[axis][index]))
        encoding = handle["X"].attrs.get("encoding-type")
        require(encoding in {"array", "csr_matrix", "csc_matrix"}, "Unsupported H5AD X encoding")
        if encoding == "array":
            require(handle["X"].shape == tuple(sizes), "Dense shape mismatch")
        else:
            require(tuple(handle["X"].attrs.get("shape", [])) == tuple(sizes), "Sparse shape mismatch")
            pointers, indices = handle["X/indptr"][:], handle["X/indices"][:]
            data = handle["X/data"][:]
            major, minor = sizes if encoding == "csr_matrix" else sizes[::-1]
            require(pointers.dtype.kind in "iu" and len(pointers) == major+1 and pointers[0] == 0 and
                    np.all(pointers[1:] >= pointers[:-1]) and pointers[-1] == len(data), "Invalid sparse pointers")
            require(indices.dtype.kind in "iu" and len(indices) == len(data) and np.all(indices >= 0) and
                    np.all(indices < minor), "Invalid sparse indices")
    return encoding


def candidate_family(database, debug, result, groups, family_id):
    returned = result["pvalues"]
    require(not returned["id_cp_interaction"].duplicated().any(), "Duplicate official returned interaction IDs")
    lookup = returned.set_index("id_cp_interaction")
    filtered = debug["interactions_filtered"]
    pair_index = {(int(row.multidata_1_id), int(row.multidata_2_id)): index for index, row in filtered.iterrows()}
    mask = debug["real_percent_analysis"]
    records = []
    for row in database.itertuples():
        interaction = str(row.id_cp_interaction)
        index = pair_index.get((int(row.multidata_1_id), int(row.multidata_2_id)))
        for source, target in itertools.product(groups, repeat=2):
            pair = source+"|"+target
            present = interaction in lookup.index
            eligible = bool(mask.loc[index, pair]) if index is not None else None
            require(not present or index is not None, "Returned interaction has no official eligibility mask")
            records.append({"family_id":family_id, "interaction":interaction, "source":source, "target":target,
                            "status":("OFFICIAL_RETURNED_THRESHOLD_PASS" if eligible else "OFFICIAL_RETURNED_THRESHOLD_MASKED") if present else "NOT_RETURNED_OFFICIAL_PREFILTER",
                            "threshold_eligible":"NA" if eligible is None else str(eligible).lower(),
                            "official_pvalue":repr(float(lookup.loc[interaction, pair])) if present else "NA"})
    return records


def main():
    outputs = [Path(os.environ["AUTONOMICS_OUTPUT"+str(index)]) for index in range(8)]
    require(len({path.resolve() for path in outputs}) == 8 and not any(path.exists() for path in outputs),
            "Eight distinct non-overwritten declared output ports required")
    root = Path(os.environ["AUTONOMICS_WORKDIR"])
    audit = {"status":"RUNNING", "G0_granted":False, "resident_deployment_granted":False, "donor_inference_granted":False}
    payload = None
    with outputs[3].open("w") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        try:
            require(os.environ["AUTONOMICS_INPUT_COUNT"] == "2", "Exactly two declared file inputs required")
            inputs = [Path(os.environ["AUTONOMICS_INPUT"+str(index)]) for index in range(2)]
            request = json_read(inputs[1])
            require(type(request) is dict and set(request) == KEYS, "Missing or unknown frozen contract key")
            require(type(request["schema_version"]) is int and request["schema_version"] == 1, "Unsupported schema")
            for key in ("family_id", "test_id", "expected_tissue", "group_column", "donor_column", "tissue_column"):
                require(identity(request[key]), "Invalid contract identity: "+key)
            require(re.fullmatch(r"[a-f0-9]{64}", request["input0_sha256"]) is not None and
                    checksum(inputs[0]) == request["input0_sha256"], "Input byte identity mismatch")
            require(request["database_sha256"] == DB_SHA, "Frozen database identity mismatch")
            require(request["scope"] == "within_tissue_candidate_only" and
                    request["null_unit"] == "official_cell_labels_not_donor_inference", "Unsupported scope or null unit")
            require(request["input_origin"] in {"SYNTHETIC_TECHNICAL_ONLY", "LEGACY_SEEN_NOT_NEW_EVIDENCE"}, "Research qualification not granted")
            require(request["scale"] in {"raw_counts", "log1p_cp10k"}, "Explicit supported input scale required")
            require(request["preprocessing"] in {"none", "cp10k_log1p"}, "Unsupported preprocessing")
            require(type(request["score_interactions"]) is bool, "Scoring flag must be JSON boolean")
            require(request["scale"] != "log1p_cp10k" or request["preprocessing"] == "none", "Double normalization forbidden")
            require(not request["score_interactions"] or request["scale"] == "log1p_cp10k" or
                    request["preprocessing"] == "cp10k_log1p", "Official interaction scoring requires log-normalized data")
            require(request["counts_data"] in {"hgnc_symbol", "gene_name", "ensembl"}, "Unsupported human gene identifier type")
            integer(request["seed"], 0, 2**32-1, "seed")
            integer(request["iterations"], 100, 10000, "iterations")
            integer(request["result_precision"], 3, 12, "result_precision")
            real(request["threshold"], 0, 1, "threshold")
            real(request["pvalue"], 0, 1, "pvalue")
            require(0 < request["pvalue"] < 1, "P cutoff must be strictly between zero and one")
            cells = identities(request["expected_cells"], "expected_cells")
            genes = identities(request["expected_genes"], "expected_genes")
            groups = identities(request["expected_groups"], "expected_groups")
            donors = identities(request["expected_donors"], "expected_donors")
            require(groups == sorted(groups) and not any("|" in group or re.fullmatch(r"[+-]?\d+(\.\d+)?", group) for group in groups),
                    "Group ordering or unsupported numeric/separator group labels")
            require(importlib.metadata.version("cellphonedb") == "5.0.1", "Official package version mismatch")
            database = Path("/opt/cellphonedb/cellphonedb.zip")
            require(checksum(database) == DB_SHA, "Actual database identity mismatch")
            encoding = h5_structure(inputs[0])
            try:
                original = anndata.read_h5ad(inputs[0])
            except Exception as error:
                raise ValueError("Invalid H5AD: "+str(error)) from error
            require(original.obs_names.tolist() == cells and original.var_names.tolist() == genes and
                    len(cells) == len(set(cells)) and len(genes) == len(set(genes)), "Frozen cell or gene axes mismatch")
            require(str(original.X.dtype) == request["expected_x_dtype"] and original.X.dtype.kind in "iuf", "Frozen expression dtype mismatch")
            require(original.n_obs*original.n_vars <= 2000000, "Official dense-reader small-proof budget exceeded; full-scale resources unqualified")
            labels = {}
            for key in ("group_column", "donor_column", "tissue_column"):
                name = request[key]
                require(name in original.obs, "Missing metadata column: "+name)
                values = original.obs[name].tolist()
                require(all(identity(value) for value in values), "Missing or invalid metadata labels: "+name)
                labels[key] = values
            require(sorted(set(labels["group_column"])) == groups and set(labels["donor_column"]) == set(donors), "Frozen group or donor universe mismatch")
            require(set(labels["tissue_column"]) == {request["expected_tissue"]}, "Pooled or unexpected tissues blocked")
            prepared = original.copy()
            if sparse.issparse(prepared.X):
                prepared.X = prepared.X.tocsr(copy=True)
                prepared.X.sum_duplicates()
                values = prepared.X.data
            else:
                values = prepared.X
            require(np.all(np.isfinite(values)) and np.all(values >= 0), "Invalid expression values")
            require(np.all(np.asarray(prepared.X.sum(axis=1)).ravel() > 0), "Zero-library cell")
            if request["scale"] == "raw_counts": require(np.all(values == np.floor(values)), "Raw counts must be integral")
            if request["preprocessing"] == "cp10k_log1p":
                prepared.X = prepared.X.astype(np.float64)
                totals = np.asarray(prepared.X.sum(axis=1)).ravel()
                if sparse.issparse(prepared.X):
                    prepared.X.data = np.log1p(prepared.X.data / np.repeat(totals, np.diff(prepared.X.indptr)) * 10000)
                else:
                    prepared.X = np.log1p(prepared.X / totals[:, None] * 10000)
            actual_values = prepared.X.data if sparse.issparse(prepared.X) else prepared.X
            require(np.all(np.isfinite(actual_values.astype(np.float32))), "Official Float32 input cast would overflow")
            temporary = root/"cpdb-input-and-official-work"
            temporary.mkdir()
            prepared.write_h5ad(temporary/"prepared.h5ad")
            pd.DataFrame({"Cell":cells, "cell_type":labels["group_column"]}).to_pickle(temporary/"meta.pickle")
            from cellphonedb.src.core.methods import cpdb_statistical_analysis_method
            from cellphonedb.utils import db_utils
            kwargs = {"cpdb_file_path":str(database), "counts_file_path":str(temporary/"prepared.h5ad"),
                      "meta_file_path":str(temporary/"meta.pickle"), "output_path":str(temporary),
                      "counts_data":request["counts_data"], "debug_seed":request["seed"], "iterations":request["iterations"],
                      "threshold":request["threshold"], "result_precision":request["result_precision"], "pvalue":request["pvalue"],
                      "score_interactions":request["score_interactions"], "threads":1, "subsampling":False,
                      "subsampling_log":False, "subsampling_num_pc":100, "subsampling_num_cells":None,
                      "separator":"|", "debug":True, "output_suffix":"frozen_acceptance", "microenvs_file_path":None, "active_tfs_file_path":None}
            require(set(kwargs) == set(inspect.signature(cpdb_statistical_analysis_method.call).parameters), "Official signature mismatch; no dropped kwargs")
            np.random.seed(request["seed"])
            before = np.random.get_state()
            with warnings.catch_warnings(record=True) as records:
                warnings.simplefilter("always")
                try:
                    result = cpdb_statistical_analysis_method.call(**kwargs)
                except Exception as error:
                    raise ValueError("Official CellPhoneDB call failed: "+type(error).__name__+": "+str(error)) from error
            debug_file = temporary/"debug_intermediate.pkl"
            require(debug_file.is_file(), "Official debug object not retained")
            debug = pickle.loads(debug_file.read_bytes())
            payload = {"result":result, "debug":debug, "rng_before":before, "rng_after":np.random.get_state(),
                       "warnings":[{"category":record.category.__name__, "message":str(record.message)} for record in records],
                       "request":request, "method_parameters":{key:kwargs[key] for key in sorted(kwargs) if not key.endswith("_path")},
                       "official_float32_input_cast":True}
            tables = {"deconvoluted", "deconvoluted_percents", "means", "pvalues", "significant_means",
                      "CellSign_active_interactions", "CellSign_active_interactions_deconvoluted"}
            if request["score_interactions"]: tables.add("interaction_scores")
            require(set(result) == tables and not result["pvalues"].empty, "Official result empty or key contract mismatch")
            pairs = [source+"|"+target for source,target in itertools.product(groups, repeat=2)]
            require([column for column in result["pvalues"] if "|" in str(column)] == pairs, "Official frozen group pair order mismatch")
            for name in ("pvalues", "means", *( ("interaction_scores",) if request["score_interactions"] else ())):
                matrix = result[name][pairs].to_numpy(dtype=float)
                require(np.all(np.isfinite(matrix)) and np.all(matrix >= 0), "Official numeric matrix not usable")
                if name == "pvalues": require(np.all(matrix <= 1), "Official P matrix out of range")
            flat = flat_tables(result, request["test_id"])
            interactions, gene_data, *_ = db_utils.get_interactions_genes_complex(str(database))
            require(not interactions["id_cp_interaction"].duplicated().any(), "Duplicate curated interaction IDs")
            family = candidate_family(interactions, debug, result, groups, request["family_id"])
            cell_rows = [{"cell":cell, "group":group, "donor":donor, "tissue":tissue, "source_position":index}
                         for index,(cell,group,donor,tissue) in enumerate(zip(cells,labels["group_column"],labels["donor_column"],labels["tissue_column"],strict=True))]
            gene_rows = [{"gene":gene, "source_position":index, "database_multidata_ids_json":json.dumps(sorted(set(
                            int(value) for value in gene_data.loc[gene_data[request["counts_data"]] == gene, "id_multidata"]))),
                          "mapping_status":"MAPPED_IN_FROZEN_DB" if gene in set(gene_data[request["counts_data"]]) else "NOT_MAPPED_IN_FROZEN_DB"}
                         for index,gene in enumerate(genes)]
            write_tsv(outputs[0], FIELDS, flat)
            outputs[1].write_bytes(pickle.dumps(payload, protocol=5))
            write_tsv(outputs[4], list(cell_rows[0]), cell_rows)
            write_tsv(outputs[5], list(gene_rows[0]), gene_rows)
            write_tsv(outputs[6], list(family[0]), family)
            with zipfile.ZipFile(outputs[7], "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for file in sorted(temporary.iterdir()):
                    if file.name in {"prepared.h5ad", "meta.pickle"}: continue
                    require(file.is_file(), "Unexpected official output directory")
                    information = zipfile.ZipInfo(file.name, date_time=(1980,1,1,0,0,0))
                    information.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(information, file.read_bytes())
            audit.update(status="TECHNICAL_PASS_NOT_SCIENTIFIC", request=request, input0_sha256=checksum(inputs[0]), input1_sha256=checksum(inputs[1]),
                         database_sha256=DB_SHA, original_X_encoding=encoding, original_X_dtype=str(original.X.dtype),
                         official_input_scale="log1p_cp10k" if request["preprocessing"] == "cp10k_log1p" else request["scale"],
                         official_result_keys=list(result), full_DB_pair_rows=len(family), value_rows=len(flat), threads=1,
                         official_disabled_CellSign_class_sentinels=[name for name,value in result.items() if value is pd.DataFrame],
                         declared_outputs={str(index):checksum(path) for index,path in enumerate(outputs) if index not in (2,3)})
            print("PASS official CellPhoneDB candidate analysis; NOT donor inference, cross-organ transport or G0")
        except Exception as error:
            if payload is not None:
                diagnostic = root/"failed-official-state.pkl"
                diagnostic.write_bytes(pickle.dumps(payload, protocol=5))
                audit["failed_official_state_sha256"] = checksum(diagnostic)
            for index in (0,1,4,5,6,7):
                if outputs[index].exists(): outputs[index].unlink()
            audit.update(status="BLOCKED", error=str(error), error_class=type(error).__name__)
            print("BLOCKED", str(error))
        outputs[2].write_text(json.dumps(audit, indent=2, ensure_ascii=False, allow_nan=False)+"\n")
    return 0 if audit["status"] == "TECHNICAL_PASS_NOT_SCIENTIFIC" else 1


if __name__ == "__main__":
    sys.exit(main())
