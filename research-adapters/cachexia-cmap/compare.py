"""Full frozen perturbation-response comparison without implicit identities or filtering."""

import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import warnings
import zipfile

KEYS = {"schema_version","scope","test_id","metric","input_sha256","reference_format","gene_col","value_col","expected_query_genes","expected_reference_genes","expected_signatures","expected_common_genes","expected_metadata","family_test_ids","query_scale","reference_scale","identity_policy","missing_policy","aggregation_policy","up_genes","down_genes","reference_tie_policy","signature_chunk","min_common_genes","max_input_bytes","max_expanded_bytes","max_matrix_elements","max_signatures","diagnostic_p_policy"}
NAMES = ["scores.parquet","query.parquet","reference.parquet","metadata.parquet","audit.json","request_ledger.tsv","cmap.log","gene_ledger.parquet","source_inputs.zip"]
METADATA = {"signature_id","cell_type","dose","dose_unit","time_hours","perturbagen_id","perturbagen_type"}


def require(condition, message):
    if not condition: raise ValueError(message)


def digest(filename):
    checksum = hashlib.sha256()
    with Path(filename).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""): checksum.update(block)
    return checksum.hexdigest()


def lexical(value):
    return isinstance(value,str) and bool(value.strip()) and not any(char in value for char in "\t\r\n\x00")


def distinct(values, name, empty=False):
    require(isinstance(values,list) and (empty or bool(values)) and all(lexical(value) for value in values) and len(set(values)) == len(values), "Distinct lexical " + name + " required")


def load_request(filename):
    def pairs(items):
        answer = {}
        for key,value in items:
            require(key not in answer, "Duplicate JSON key: " + key); answer[key] = value
        return answer
    return json.loads(Path(filename).read_text(),object_pairs_hook=pairs,parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON constant")))


def recover_test_id(raw):
    decoder,identifiers = json.JSONDecoder(),[]
    cursor = len(raw) - len(raw.lstrip())
    if not raw[cursor:].startswith("{"): return None
    cursor += 1
    try:
        while True:
            while raw[cursor].isspace(): cursor += 1
            if raw[cursor] == "}": break
            key,cursor = decoder.raw_decode(raw,cursor)
            if not isinstance(key,str): break
            while raw[cursor].isspace(): cursor += 1
            if raw[cursor] != ":": break
            cursor += 1
            while raw[cursor].isspace(): cursor += 1
            value,cursor = decoder.raw_decode(raw,cursor)
            if key == "test_id": identifiers.append(value)
            while raw[cursor].isspace(): cursor += 1
            if raw[cursor] != ",": break
            cursor += 1
    except (ValueError,IndexError): pass
    return identifiers[0] if len(identifiers) == 1 and (identifiers[0] is None or isinstance(identifiers[0],str)) else None


def validate(request, family):
    require(isinstance(request,dict) and set(request) == KEYS,"Exact frozen request keys required")
    require(type(request["schema_version"]) is int and request["schema_version"] == 1 and request["scope"] == "TECHNICAL_CMAP_NOT_G0" and lexical(request["test_id"]),"Frozen identity/schema required")
    require(request["metric"] in (["pearson","spearman"] if family == "correlation" else ["exploratory_rank_reversal"]),"Metric incompatible with declared node family")
    require(isinstance(request["input_sha256"],list) and len(request["input_sha256"]) == 3 and all(isinstance(value,str) and re.fullmatch(r"[0-9a-f]{64}",value) for value in request["input_sha256"]),"Three source content hashes required")
    require(request["reference_format"] in ["gct1.2","gct1.2.gz","gctx","gctx.gz"],"Supported frozen reference format required")
    require(lexical(request["gene_col"]) and lexical(request["value_col"]) and request["gene_col"] != request["value_col"],"Distinct query columns required")
    for field in ["expected_query_genes","expected_reference_genes","expected_signatures","expected_common_genes","family_test_ids"]: distinct(request[field],field)
    require(len(request["family_test_ids"]) == len(request["expected_signatures"]),"Full frozen family differs")
    require(set(request["expected_common_genes"]) == set(request["expected_query_genes"]) & set(request["expected_reference_genes"]),"Complete common gene universe differs")
    for field in ["up_genes","down_genes"]: distinct(request[field],field,empty=True)
    require(set(request["up_genes"] + request["down_genes"]) <= set(request["expected_common_genes"]),"Frozen rank membership outside common universe")
    require(request["reference_tie_policy"] in ["NOT_APPLICABLE","LEGACY_DOUBLE_ARGSORT_FROZEN_AXIS","AVERAGE_RANKS"],"Explicit reference tie policy required")
    require((family == "correlation" and request["reference_tie_policy"] == "NOT_APPLICABLE" and not request["up_genes"] and not request["down_genes"]) or (family == "rank" and request["reference_tie_policy"] != "NOT_APPLICABLE" and bool(request["up_genes"]) and bool(request["down_genes"])),"Frozen method-specific membership/tie contract differs")
    metadata = request["expected_metadata"]
    require(isinstance(metadata,list) and len(metadata) == len(request["expected_signatures"]) and all(isinstance(row,dict) and METADATA <= set(row) and all(lexical(key) and isinstance(value,str) for key,value in row.items()) for row in metadata),"Complete frozen condition metadata required")
    require([row["signature_id"] for row in metadata] == request["expected_signatures"] and all(all(lexical(row[field]) for field in METADATA) for row in metadata),"Frozen signature condition identity differs")
    require(request["query_scale"] in ["SIGNED_LOGFC","SIGNED_QUERY_RESPONSE"] and request["reference_scale"] in ["L1000_LEVEL5_MODZ","SIGNED_REFERENCE_RESPONSE"],"Explicit signed input scale required")
    policies = {"identity_policy":"LITERAL_FROZEN_IDS_NO_GENE_MAPPING","missing_policy":"FULL_FAMILY_NULL_NOT_DROP_OR_ZERO","aggregation_policy":"NONE_ALL_FROZEN_SIGNATURES_NO_BEST_CONDITION_SELECTION","diagnostic_p_policy":"GENE_LEVEL_DIAGNOSTIC_NOT_DONOR_OR_DRUG_INFERENCE"}
    require(all(request[key] == value for key,value in policies.items()),"Unsupported scientific/interface policy")
    for field in ["signature_chunk","min_common_genes","max_input_bytes","max_expanded_bytes","max_matrix_elements","max_signatures"]:
        require(type(request[field]) is int and request[field] > 0,"Positive frozen resource bound required: " + field)
    require(request["min_common_genes"] >= 2 and len(request["expected_common_genes"]) >= request["min_common_genes"] and len(request["expected_signatures"]) <= request["max_signatures"],"Frozen gene/signature budget violated")


def read_tsv(filename):
    with filename.open(newline="",encoding="utf-8") as handle:
        reader = csv.reader(handle,delimiter="\t"); columns = next(reader); values = list(reader)
    require(columns and len(set(columns)) == len(columns) and all(lexical(value) for value in columns),"Distinct TSV columns required")
    require(all(len(row) == len(columns) for row in values),"Ragged TSV input")
    return columns,[dict(zip(columns,row)) for row in values]


def numeric(value):
    if value in ["","NA","NaN","nan"]: return None
    number = float(value)
    require(math.isfinite(number),"Nonfinite query signal")
    return number


def read_reference(filename,request,folder):
    import h5py
    import numpy as np
    original_format = request["reference_format"]
    if original_format.endswith(".gz"):
        expanded = folder / "expanded-reference"
        with gzip.open(filename,"rb") as source,expanded.open("wb") as target:
            size = 0
            for block in iter(lambda: source.read(1024 * 1024),b""):
                size += len(block); require(size <= request["max_expanded_bytes"],"Frozen gzip expanded byte budget exceeded"); target.write(block)
        filename = expanded
    require(filename.stat().st_size <= request["max_expanded_bytes"],"Frozen expanded byte budget exceeded")
    if original_format.startswith("gctx"):
        with h5py.File(filename,"r") as handle:
            require("/0/DATA/0/matrix" in handle and isinstance(handle["/0/DATA/0/matrix"],h5py.Dataset),"Official GCTX matrix dataset required")
            axes = []
            for name in ["ROW","COL"]:
                dataset = handle["/0/META/" + name + "/id"]
                require(dataset.ndim == 1 and h5py.check_string_dtype(dataset.dtype) is not None,"GCTX IDs must have lexical string types")
                axes.append(dataset.asstr(encoding="utf-8",errors="strict")[...].tolist())
            genes,signatures = axes
            data = handle["/0/DATA/0/matrix"]
            require(data.ndim == 2 and data.shape == (len(signatures),len(genes)) and data.dtype.kind in "iuf","GCTX shape/orientation/numeric type differs")
            require(data.size <= request["max_matrix_elements"],"Frozen matrix element budget exceeded")
            matrix = data[...].T
    else:
        with filename.open(newline="",encoding="utf-8") as handle:
            require(handle.readline().strip() == "#1.2","GCT1.2 version required")
            dims = handle.readline().split(); require(len(dims) == 2,"GCT dimensions required")
            n_rows,n_cols = [int(value) for value in dims]
            require(n_rows > 0 and n_cols > 0 and n_rows * n_cols <= request["max_matrix_elements"],"Frozen matrix element budget exceeded")
            reader = csv.reader(handle,delimiter="\t"); header = next(reader)
            require(len(header) == n_cols + 2 and header[:2] == ["NAME","Description"],"Exact GCT1.2 header width/metadata required")
            rows = list(reader); require(len(rows) == n_rows and all(len(row) == n_cols + 2 for row in rows),"Declared GCT row/column counts differ")
        genes,signatures = [row[0] for row in rows],header[2:]
        matrix = np.array([[float(value) if value not in ["","NA","NaN","nan"] else float("nan") for value in row[2:]] for row in rows],dtype=np.float64)
    distinct(genes,"reference gene axis"); distinct(signatures,"signature axis")
    require(genes == request["expected_reference_genes"] and signatures == request["expected_signatures"],"Frozen reference axes differ")
    require(not np.isinf(matrix).any(),"Infinite reference signal")
    return genes,signatures,matrix


def compute(query,reference,request):
    import numpy as np
    import scipy.stats as stats
    if any(value is None for value in query): return None,None,None,None,"NOT_ESTIMABLE_QUERY_MISSING",[]
    if not np.isfinite(reference).all(): return None,None,None,None,"NOT_ESTIMABLE_REFERENCE_MISSING",[]
    if max(query) == min(query) or np.max(reference) == np.min(reference): return None,None,None,None,"NOT_ESTIMABLE_CONSTANT",[]
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if request["metric"] == "pearson":
            result = stats.pearsonr(np.array(query),reference,alternative="two-sided",method=None)
            score,pvalue = float(result.statistic),float(result.pvalue); up,down = None,None
        elif request["metric"] == "spearman":
            result = stats.spearmanr(np.array(query),reference,axis=0,nan_policy="propagate",alternative="two-sided")
            score,pvalue = float(result.statistic),float(result.pvalue); up,down = None,None
        else:
            size = len(reference)
            ranks = size - 1 - np.argsort(np.argsort(-reference.astype(np.float64))) if request["reference_tie_policy"] == "LEGACY_DOUBLE_ARGSORT_FROZEN_AXIS" else stats.rankdata(reference,method="average") - 1
            ranks = ranks / max(size - 1,1)
            axis = request["expected_common_genes"]
            up = float(np.mean([ranks[axis.index(gene)] for gene in request["up_genes"]])); down = float(np.mean([ranks[axis.index(gene)] for gene in request["down_genes"]])); score,pvalue = down - up,None
    warning_messages = [type(row.message).__name__ + ": " + str(row.message) for row in caught]
    if not math.isfinite(score) or (pvalue is not None and not math.isfinite(pvalue)): return None,None,None,None,"NOT_ESTIMABLE_OFFICIAL_NONFINITE",warning_messages
    return score,pvalue,up,down,"ESTIMABLE",warning_messages


def calculate(inputs,request,folder):
    import importlib.metadata
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    require(importlib.metadata.version("scipy") == "1.17.1","Frozen SciPy version differs")
    require(all(filename.stat().st_size <= request["max_input_bytes"] for filename in inputs),"Frozen input byte budget exceeded")
    require([digest(filename) for filename in inputs] == request["input_sha256"],"Frozen source content differs")
    columns,query_rows = read_tsv(inputs[0]); require(request["gene_col"] in columns and request["value_col"] in columns,"Query contract columns missing")
    require(not {"_proof_gene_position","_proof_numeric_value"} & set(columns),"Reserved query output fields collide")
    query_genes = [row[request["gene_col"]] for row in query_rows]; distinct(query_genes,"query gene axis")
    require(query_genes == request["expected_query_genes"],"Frozen query axis differs")
    query_values = [numeric(row[request["value_col"]]) for row in query_rows]
    genes,signatures,matrix = read_reference(inputs[1],request,folder)
    meta_columns,metadata = read_tsv(inputs[2]); require(METADATA <= set(meta_columns) and metadata == request["expected_metadata"],"Complete frozen condition metadata differs")
    query_map = dict(zip(query_genes,query_values)); row_positions = {gene:position for position,gene in enumerate(genes)}
    common = request["expected_common_genes"]; query = [query_map[gene] for gene in common]; common_positions = [row_positions[gene] for gene in common]
    scores = []
    for start in range(0,len(signatures),request["signature_chunk"]):
        for position in range(start,min(start + request["signature_chunk"],len(signatures))):
            score,pvalue,up,down,status,caught = compute(query,matrix[common_positions,position],request)
            direction = "not_estimable" if score is None else "flat" if score == 0 else ("reversed" if score < 0 else "same_direction") if request["metric"] in ["pearson","spearman"] else ("reversed" if score > 0 else "concordant")
            scores.append({"signature_id":signatures[position],"source_position":position,"test_id":request["family_test_ids"][position],"metric":request["metric"],"score":score,"diagnostic_p_not_donor_inference":pvalue,"a_up":up,"a_down":down,"status":status,"direction":direction,"n_common":len(common),"fixed_family_size":len(signatures),"warnings":json.dumps(caught,ensure_ascii=False),"reference_tie_policy":request["reference_tie_policy"]})
    ordered = sorted(scores,key=lambda row:(row["score"] is None,(row["score"] or 0) * (-1 if request["metric"] == "exploratory_rank_reversal" else 1),row["signature_id"]))
    for position,row in enumerate(ordered): row["display_rank"] = position + 1
    schema = pa.schema([(key,pa.float64() if key in ["score","diagnostic_p_not_donor_inference","a_up","a_down"] else pa.int64() if key in ["source_position","n_common","fixed_family_size","display_rank"] else pa.string()) for key in ordered[0]])
    pq.write_table(pa.Table.from_pylist(ordered,schema=schema),folder / NAMES[0])
    table = pa.Table.from_arrays([pa.array([row[column] for row in query_rows],pa.string()) for column in columns] + [pa.array(list(range(len(query_rows))),pa.int64()),pa.array(query_values,pa.float64())],names=columns + ["_proof_gene_position","_proof_numeric_value"])
    pq.write_table(table,folder / NAMES[1])
    pq.write_table(pa.Table.from_arrays([pa.array(genes,pa.string())] + [pa.array(matrix[:,position]) for position in range(len(signatures))],names=["gene_id"] + ["s" + str(position) for position in range(len(signatures))]),folder / NAMES[2])
    pq.write_table(pa.Table.from_arrays([pa.array([row[column] for row in metadata],pa.string()) for column in meta_columns],names=meta_columns),folder / NAMES[3])
    union = query_genes + [gene for gene in genes if gene not in query_map]
    ledger = [{"gene_id":gene,"query_position":query_genes.index(gene) if gene in query_map else None,"reference_position":row_positions.get(gene),"common_position":common.index(gene) if gene in common else None,"up_member":gene in request["up_genes"],"down_member":gene in request["down_genes"]} for gene in union]
    ledger_schema = pa.schema([("gene_id",pa.string()),("query_position",pa.int64()),("reference_position",pa.int64()),("common_position",pa.int64()),("up_member",pa.bool_()),("down_member",pa.bool_())]); pq.write_table(pa.Table.from_pylist(ledger,schema=ledger_schema),folder / NAMES[7])
    with zipfile.ZipFile(folder / NAMES[8],"w",compression=zipfile.ZIP_STORED) as archive:
        for filename,name in zip(inputs,["query.tsv","reference.bin","metadata.tsv"]): archive.writestr(name,filename.read_bytes())
    require([digest(filename) for filename in inputs] == request["input_sha256"],"Sources changed during execution")
    (folder / NAMES[6]).write_text("Complete frozen family retained; no best-condition filtering; diagnostic P is not donor or efficacy inference; metric=" + request["metric"] + "\n")
    return {"signatures":len(signatures),"genes":len(genes),"common_genes":len(common),"estimable":sum(row["status"] == "ESTIMABLE" for row in scores),"not_Broad_WTCS_NCS_tau":True,"query_scale":request["query_scale"],"reference_scale":request["reference_scale"],"source_numeric_dtype":str(matrix.dtype),"legacy_rank_uses_original_float64_view":request["reference_tie_policy"] == "LEGACY_DOUBLE_ARGSORT_FROZEN_AXIS","frozen_query_rank_membership_overlap":len(set(request["up_genes"]) & set(request["down_genes"]))}


def save_json(filename,value): filename.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False) + "\n")


def save_ledger(filename,identifier,status):
    with filename.open("w",newline="",encoding="utf-8") as handle:
        writer = csv.writer(handle,delimiter="\t")
        writer.writerow(["test_id","status","scientific_release"])
        writer.writerow([identifier or "UNKNOWN_UNRECOVERABLE_ID",status,"NOT_GRANTED"])


def main():
    outputs = [Path(os.environ.get("AUTONOMICS_OUTPUT" + str(position),"/work/" + name)) for position,name in enumerate(NAMES)]
    audit = {"status":"BLOCKED","test_id":None,"G0_granted":False,"resident_daemon_certified":False,"full_Broad_CMap_algorithm_certified":False}
    temporary,published,safe = None,[],False
    try:
        parent = outputs[0].parent
        require(parent.is_dir() and not parent.is_symlink() and len(set(outputs)) == len(outputs) and all(filename.is_absolute() and filename.parent == parent and filename.name == name and not filename.exists() and not filename.is_symlink() for filename,name in zip(outputs,NAMES)),"Unsafe or preexisting output paths")
        safe = True
        inputs = [Path(os.environ["AUTONOMICS_INPUT" + str(position)]) for position in range(4)]
        raw = inputs[3].read_text(); audit["test_id"] = recover_test_id(raw)
        save_json(outputs[4],dict(audit,status="STARTED_NOT_VERIFIED"))
        request = load_request(inputs[3]); validate(request,os.environ["CMAP_CLASS"])
        temporary = Path(tempfile.mkdtemp(prefix="cmap-publication-",dir=parent)); details = calculate(inputs[:3],request,temporary)
        save_ledger(temporary / NAMES[5],request["test_id"],"TECHNICAL_PASS_NOT_SCIENTIFIC")
        with zipfile.ZipFile(temporary / NAMES[8],"a") as archive: archive.writestr("request.json",inputs[3].read_bytes())
        audit.update(details,status="TECHNICAL_PASS_NOT_SCIENTIFIC",request=request,input_sha256=[digest(filename) for filename in inputs],output_sha256={str(position):digest(temporary / name) for position,name in enumerate(NAMES) if position != 4},statistical_official_scope="SciPy1.17.1 requested correlation only" if os.environ["CMAP_CLASS"] == "correlation" else "NOT_APPLICABLE_CUSTOM_RANK_REVERSAL")
        save_json(temporary / NAMES[4],audit)
        for position,name in enumerate(NAMES): (temporary / name).replace(outputs[position]); published.append(outputs[position])
    except Exception as error:
        audit.update(status="BLOCKED",error=str(error)); audit.pop("output_sha256",None)
        if safe:
            for filename in published: filename.unlink()
            save_json(outputs[4],audit); save_ledger(outputs[5],audit["test_id"],"BLOCKED"); outputs[6].write_text(str(error) + "\n")
        print(str(error),file=sys.stderr); return 1
    finally:
        if temporary is not None: shutil.rmtree(temporary)
    return 0


if __name__ == "__main__": sys.exit(main())
