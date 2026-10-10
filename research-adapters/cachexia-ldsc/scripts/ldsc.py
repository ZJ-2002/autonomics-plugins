import argparse
import contextlib
import csv
import gzip
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import shutil
import sys
import traceback
import warnings
import zipfile

import cloudpickle
import numpy as np
import pandas as pd


SOURCE = Path("/opt/cachexia-official-ldsc")
PANEL = Path("/panels/ldsc_assets")
KEYS = {"schema_version", "method", "input_sha256", "input_rows", "snp_columns", "options", "panel_manifest_sha256",
        "official_runtime_files", "scale", "ancestry", "build", "null_unit", "input_origin", "family_id", "test_id", "seed"}
OPTIONS = {
    "munge": {"snp", "N_col", "N_cas_col", "N_con_col", "a1", "a2", "p", "frq", "info", "info_list", "info_min",
              "maf_min", "n_min", "nstudy_min", "nstudy", "N", "N_cas", "N_con", "daner", "daner_n", "no_alleles",
              "a1_inc", "signed_sumstats", "keep_maf", "ignore", "chunksize"},
    "h2": {"n_blocks", "intercept_h2", "chisq_max", "two_step", "no_intercept", "samp_prev", "pop_prev", "not_M_5_50"},
    "rg": {"n_blocks", "intercept_h2", "intercept_gencov", "chisq_max", "two_step", "no_intercept", "samp_prev",
           "pop_prev", "not_M_5_50", "return_silly_things"},
}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            result.update(chunk)
    return result.hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "Duplicate frozen key: " + key)
        result[key] = value
    return result


def read_request(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON scalar")))


def load_module(name, path):
    specification = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def option_arguments(options, method, parser):
    need(isinstance(options, dict) and set(options) <= OPTIONS[method], "Unsupported official option or invented a1_is_a2 flag")
    actions = {action.dest: action for action in parser._actions}
    arguments = []
    for name, value in options.items():
        need(name in actions, "Official parser does not define option: " + name)
        action = actions[name]
        flag = next((flag for flag in action.option_strings if flag.startswith("--")), None)
        need(flag is not None, "Missing official long option")
        if isinstance(action, argparse._StoreTrueAction):
            need(type(value) is bool, "Presence option must be Boolean: " + name)
            if value:
                arguments.append(flag)
        else:
            need(type(value) in (str, int, float) and (not isinstance(value, float) or math.isfinite(value)) and
                 (not isinstance(value, str) or value.strip() == value and value and not any(character in value for character in "\r\n\t")), "Invalid official option value: " + name)
            arguments.extend((flag, str(value)))
    if method != "munge":
        need("n_blocks" in options and type(options["n_blocks"]) is int and options["n_blocks"] >= 2, "Freeze integer n_blocks >= 2")
    return arguments


def runtime_identity(expected):
    need(isinstance(expected, dict) and expected and all(isinstance(name, str) and not name.startswith("/") and
         ".." not in Path(name).parts and Path(name).suffix == ".py" for name in expected), "Invalid official source identities")
    actual = {str(path.relative_to(SOURCE)): digest(path) for path in sorted(SOURCE.rglob("*.py"))
              if path.parent == SOURCE or str(path.relative_to(SOURCE)).startswith("ldscore/")}
    need(actual == expected, "Complete official runtime source identity mismatch")
    for name, module in sys.modules.items():
        if name == "ldscore" or name.startswith("ldscore."):
            filename = Path(module.__file__).resolve()
            need(filename.is_relative_to(SOURCE), "Official namespace resolved to patched baked code")
    return actual


def flatten(value, path=()):
    if isinstance(value, np.ndarray):
        for position in np.ndindex(value.shape):
            yield from flatten(value[position], path + ("array", tuple(position)))
    elif isinstance(value, pd.DataFrame):
        for row in range(len(value)):
            for column in value.columns:
                yield from flatten(value.iloc[row][column], path + ("frame", row, str(column)))
    elif isinstance(value, dict):
        for key in sorted(value):
            yield from flatten(value[key], path + (str(key),))
    elif isinstance(value, tuple) and hasattr(value, "_fields"):
        for name, item in zip(value._fields, value):
            yield from flatten(item, path + ("namedtuple", type(value).__name__, name))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from flatten(item, path + (index,))
    elif hasattr(value, "__dict__"):
        yield from flatten(vars(value), path + (type(value).__module__ + "." + type(value).__name__,))
    elif value is None:
        yield path, "MISSING", "", "null", "NONE"
    elif isinstance(value, (bool, np.bool_)):
        yield path, "BOOLEAN", "", json.dumps(bool(value)), ""
    elif isinstance(value, (float, np.floating, int, np.integer)):
        number = float(value)
        if not math.isfinite(number):
            yield path, "MISSING", "", "null", "NAN" if math.isnan(number) else "POSINF" if number > 0 else "NEGINF"
        else:
            yield path, "NUMERIC", format(number, ".17g"), "null", ""
    elif isinstance(value, str):
        yield path, "TEXT", "", json.dumps(value), ""
    else:
        raise ValueError("Unsupported official scalar type: " + str(type(value)))


def analysis(outputs, audit):
    method = os.environ["CACHEXIA_LDSC_METHOD"]
    count = 3 if method == "rg" else 2
    need(os.environ.get("AUTONOMICS_INPUT_COUNT") == str(count), "Wrong declared input count")
    inputs = [Path(os.environ["AUTONOMICS_INPUT" + str(index)]) for index in range(count)]
    request = read_request(inputs[-1])
    need(set(request) == KEYS and len(request) == len(KEYS) and type(request["schema_version"]) is int and
         request["schema_version"] == 1 and request["method"] == method, "Missing, unknown or wrong frozen contract")
    for key in ("test_id", "family_id"):
        need(isinstance(request[key], str) and request[key] and not any(character in request[key] for character in "\t\r\n"), "Invalid family/test identity")
    audit["request"] = request
    need(request["scale"] == ("RAW_P_AND_EXPLICIT_SIGNED_STAT" if method == "munge" else "LDSC_Z_AND_N") and
         request["ancestry"] == "EUR" and request["build"] == "GRCh37" and request["null_unit"] == "GWAS_SNP_BLOCK_JACKKNIFE_NOT_DONOR_CONTRAST", "Unsupported input scale/ancestry/build/null unit")
    need(request["input_origin"] in ("SYNTHETIC_TECHNICAL_ONLY", "LEGACY_SEEN_NOT_NEW_EVIDENCE"), "Scientific qualification not granted")
    need(type(request["seed"]) is int and 0 <= request["seed"] <= 4294967295, "Invalid frozen seed")
    need(isinstance(request["input_sha256"], list) and len(request["input_sha256"]) == count - 1 and
         request["input_sha256"] == [digest(path) for path in inputs[:-1]], "Frozen input byte identity mismatch")
    need(isinstance(request["input_rows"], list) and isinstance(request["snp_columns"], list) and
         len(request["input_rows"]) == len(request["snp_columns"]) == count - 1, "Missing source row/ID contract")
    sources = []
    for index, path in enumerate(inputs[:-1]):
        opener = gzip.open if path.suffix == ".gz" else open
        with opener(path, "rt") as stream:
            header = next(csv.reader(stream, delimiter="\t"), [])
            need(header and len(header) == len(set(header)) and all(name and name.strip() == name for name in header),
                 "Duplicate, empty or padded original column header")
            stream.seek(0)
            frame = pd.read_csv(stream, sep="\t", dtype=str, keep_default_na=False)
        need(type(request["input_rows"][index]) is int and len(frame) == request["input_rows"][index] and len(frame) > 0 and
             request["snp_columns"][index] in frame and frame[request["snp_columns"][index]].ne("").all(), "Frozen original row or SNP column mismatch")
        sources.append(frame)
    sys.path.insert(0, str(SOURCE))
    cli = load_module("cachexia_pristine_ldsc_cli", SOURCE / "ldsc.py")
    munge = load_module("cachexia_pristine_munge", SOURCE / "munge_sumstats.py")
    runtime_identity(request["official_runtime_files"])
    parser = munge.parser if method == "munge" else cli.parser
    arguments = option_arguments(request["options"], method, parser)
    if method == "munge":
        options = request["options"]
        need(request["snp_columns"] == [options.get("snp", "SNP")], "Source ledger SNP column must be the frozen official SNP option")
        need(bool(options.get("signed_sumstats")) != bool(options.get("a1_inc", False)),
             "Freeze exactly one explicit signed-statistic or A1-increasing convention")
        need(not options.get("daner", False) or not options.get("daner_n", False), "daner and daner_n are incompatible")
        need(not (options.get("N") and (options.get("N_cas") or options.get("N_con"))), "Competing constant N conventions")
        need(bool(options.get("N_cas")) == bool(options.get("N_con")), "Constant case/control N must be paired")
        if options.get("N") or options.get("N_cas"):
            translated_names = {munge.clean_header(name) for name in sources[0].columns}
            column_names = {munge.clean_header(options[name]) for name in ("N_col", "N_cas_col", "N_con_col") if options.get(name)}
            need(not column_names and not translated_names.intersection(
                {name for name, translated in munge.default_cnames.items() if translated in {"N", "N_CAS", "N_CON"}}),
                 "Ambiguous constant and per-SNP N: frozen upstream prioritizes columns despite CLI help")
    else:
        need(request["snp_columns"] == ["SNP"] * len(sources), "LDSC uses the SNP column, not an unrelated ledger ID")
        options = request["options"]
        need(("samp_prev" in options) == ("pop_prev" in options), "Freeze paired sample and population prevalence; never silently ignore a singleton")
        need(not options.get("no_intercept", False) or not any(name in options for name in ("intercept_h2", "intercept_gencov")),
             "Do not silently override an explicit intercept with no_intercept")
    prefix = Path(os.environ["AUTONOMICS_WORKDIR"]) / "official-result"
    arguments += ["--out", str(prefix)]
    if method == "munge":
        need(request["panel_manifest_sha256"] is None, "Munge must not claim LD-panel inference")
        official_input = inputs[0]
        if inputs[0].suffix == ".gz":
            official_input = prefix.parent / ".autonomics/ldsc-uncompressed-input-0.tsv"
            need(not official_input.exists(), "Do not overwrite gzip transport materialization")
            official_input.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(inputs[0], "rb") as source, official_input.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            audit["gzip_transport"] = {"original_compressed_sha256": digest(inputs[0]), "decompressed_sha256": digest(official_input),
                                       "official_reader_receives_plain_bytes": True, "pristine_upstream_gzip_reader_not_claimed": True}
        arguments += ["--sumstats", str(official_input)]
    else:
        manifest = PANEL / "manifest.json"
        need(digest(manifest) == request["panel_manifest_sha256"], "Frozen LD panel manifest differs")
        panel = read_request(manifest)
        need(len(panel["files"]) >= 45, "Incomplete chromosome/weight panel")
        for item in panel["files"]:
            path = (PANEL / item["path"]).resolve()
            need(path.is_relative_to(PANEL) and path.stat().st_size == item["size"] and digest(path) == item["sha256"].removeprefix("sha256:"), "Complete LD panel file identity differs")
        need(all((PANEL / "eur_w_ld_chr" / (str(chromosome) + suffix)).exists()
                 for chromosome in range(1, 23) for suffix in (".l2.ldscore.gz", ".l2.M_5_50")), "Missing required chromosome files")
        need(not request["options"].get("not_M_5_50", False), "This frozen panel lacks unrestricted M; do not substitute M_5_50")
        arguments += ["--" + method, str(inputs[0]) if method == "h2" else ",".join(map(str, inputs[:-1])),
                      "--ref-ld-chr", str(PANEL / "eur_w_ld_chr") + "/", "--w-ld-chr", str(PANEL / "eur_w_ld_chr") + "/"]
    parsed = parser.parse_args(arguments)
    random.seed(request["seed"])
    np.random.seed(request["seed"])
    before = (random.getstate(), np.random.get_state())
    with warnings.catch_warnings(record=True) as collected:
        warnings.simplefilter("always")
        if method == "munge":
            result = munge.munge_sumstats(parsed, p=True)
            merged = [result.copy(deep=True)]
        else:
            logger = cli.Logger(str(prefix) + ".log")
            try:
                first = cli.sumstats._read_ld_sumstats(parsed, logger, str(inputs[0]), alleles=method == "rg", dropna=True)
                merged = [first[3].copy(deep=True)]
                if method == "rg":
                    merged.append(cli.sumstats._read_other_sumstats(parsed, logger, str(inputs[1]), first[3].copy(deep=True), first[2]))
                result = cli.sumstats.estimate_h2(parsed, logger) if method == "h2" else cli.sumstats.estimate_rg(parsed, logger)
                need(result is not None and (method != "rg" or len(result) == 1 and result[0] is not None), "Official RG swallowed a component failure; no fallback result")
            finally:
                logger.log_fh.close()
    after = (random.getstate(), np.random.get_state())
    runtime_identity(request["official_runtime_files"])
    warning_messages = [(type(item.message).__name__, str(item.message)) for item in collected]
    state = {"method": method, "result": result, "original_tables": sources, "official_merged_tables": merged,
             "rng_before": before, "rng_after": after, "warnings": warning_messages, "request": request}
    with outputs[1].open("wb") as stream:
        need(cloudpickle.__version__ == "3.1.2", "Pinned dynamic-object serialization differs")
        cloudpickle.dump(state, stream, protocol=4)
    if method == "munge":
        table = result.copy(deep=True)
        table.insert(0, "official_row_position", range(len(table)))
        table["SNP"] = table["SNP"].map(lambda value: json.dumps(str(value)))
        table.rename(columns={"SNP": "SNP_json"}, inplace=True)
        table.to_csv(outputs[0], sep="\t", index=False, float_format="%.17g")
    else:
        with outputs[0].open("w") as stream:
            writer = csv.writer(stream, delimiter="\t")
            writer.writerow(["test_id", "source_position", "path_json", "value_kind", "numeric_value", "text_json", "missing_kind"])
            for position, (path, kind, number, text, missing) in enumerate(flatten(result)):
                writer.writerow([request["test_id"], position, json.dumps(path), kind, number, text, missing])
    selected = set(merged[-1].SNP.astype(str))
    ledger = []
    for index, frame in enumerate(sources):
        for position, identifier in enumerate(frame[request["snp_columns"][index]]):
            ledger.append({"input_position": index, "source_position": position, "SNP_json": json.dumps(identifier),
                           "status": "OFFICIAL_RESULT_ID_PRESENT_NOT_SOURCE_ROW_ATTESTATION" if identifier in selected else "NOT_IN_OFFICIAL_RESULT"})
    pd.DataFrame(ledger).to_csv(outputs[4], sep="\t", index=False)
    products = sorted(prefix.parent.glob(prefix.name + ".*"))
    with zipfile.ZipFile(outputs[5], "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in products:
            archive.write(path, path.name)
    result_status = "OFFICIAL_RESULT_RETAINED_NOT_G0"
    if method == "rg" and not all(isinstance(value, (float, int, np.floating, np.integer)) and math.isfinite(value)
                                  for value in (result[0].rg_ratio, result[0].p)):
        result_status = "NON_ESTIMABLE_OFFICIAL_RESULT_RETAINED_NOT_G0"
    pd.DataFrame([{"family_id": request["family_id"], "test_id": request["test_id"], "method": method,
                   "status": result_status}]).to_csv(outputs[6], sep="\t", index=False)
    audit.update(status="TECHNICAL_PASS_NOT_SCIENTIFIC", request=request, resolved_official_arguments=vars(parsed), loaded_namespace=str(cli.sumstats.__file__),
                 official_runtime_sha256=runtime_identity(request["official_runtime_files"]), input_sha256=[digest(path) for path in inputs],
                 original_input_runtime_paths=[str(path) for path in inputs[:-1]],
                 outputs={str(index): digest(outputs[index]) for index in (0, 1, 4, 5, 6)}, original_rows=[len(frame) for frame in sources],
                 official_selected_rows=[len(frame) for frame in merged], warnings=warning_messages)
    print("PASS pristine official LDSC; not MRlap equivalence, scientific release or G0")
    return audit


def main():
    outputs = [Path(os.environ["AUTONOMICS_OUTPUT" + str(index)]) for index in range(7)]
    need(len(set(outputs)) == 7 and not any(path.exists() for path in outputs), "Seven distinct non-overwritten declared ports required")
    audit = {"status": "RUNNING", "G0_granted": False, "resident_deployment_granted": False, "scientific_release_granted": False}
    with outputs[3].open("w") as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        try:
            audit = analysis(outputs, audit)
        except BaseException as error:
            for index in (0, 1, 4, 5):
                outputs[index].unlink(missing_ok=True)
            audit.update(status="BLOCKED", error=type(error).__name__ + ": " + str(error))
            if "request" in audit:
                request = audit["request"]
                pd.DataFrame([{"family_id": request["family_id"], "test_id": request["test_id"],
                               "method": request["method"], "status": "BLOCKED_NOT_ESTIMATED"}]).to_csv(outputs[6], sep="\t", index=False)
            print("BLOCKED", audit["error"])
            traceback.print_exc()
    outputs[2].write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    return 0 if audit["status"] == "TECHNICAL_PASS_NOT_SCIENTIFIC" else 1


if __name__ == "__main__":
    sys.exit(main())
