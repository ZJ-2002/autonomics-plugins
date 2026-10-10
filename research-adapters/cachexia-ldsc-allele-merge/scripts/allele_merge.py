import contextlib
import csv
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import traceback
import warnings

import cloudpickle
import numpy as np
import pandas as pd


SOURCE = Path("/opt/cachexia-official-ldsc")
KEYS = {"schema_version", "method", "input_sha256", "input_rows", "official_runtime_files", "scale",
        "ancestry", "build", "input_origin", "reference_policy", "effect_alignment", "family_id", "test_id", "seed"}


def need(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            value.update(chunk)
    return value.hexdigest()


def unique(pairs):
    result = {}
    for name, value in pairs:
        need(name not in result, "Duplicate frozen key")
        result[name] = value
    return result


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_identity(expected):
    observed = {str(path.relative_to(SOURCE)): sha(path) for path in sorted(SOURCE.rglob("*.py"))
                if path.parent == SOURCE or str(path.relative_to(SOURCE)).startswith("ldscore/")}
    need(observed == expected, "Complete pristine runtime differs")
    for name, module in sys.modules.items():
        if name == "ldscore" or name.startswith("ldscore."):
            need(Path(module.__file__).resolve().is_relative_to(SOURCE), "Patched namespace loaded")
    return observed


def run(outputs, audit):
    need(os.environ.get("AUTONOMICS_INPUT_COUNT") == "3", "Three declared File inputs required")
    inputs = [Path(os.environ["AUTONOMICS_INPUT" + str(position)]) for position in range(3)]
    request = json.loads(inputs[2].read_text(), object_pairs_hook=unique,
                         parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))
    need(set(request) == KEYS and type(request["schema_version"]) is int and request["schema_version"] == 1 and
         request["method"] == "official_allele_merge_transport", "Wrong or incomplete frozen contract")
    for name in ("family_id", "test_id"):
        need(isinstance(request[name], str) and request[name] and not any(character in request[name] for character in "\t\r\n"),
             "Invalid family/test ID")
    audit["request"] = request
    need(request["scale"] == "STANDARD_LDSC_Z_IN_ORIGINAL_A1" and request["ancestry"] == "EUR" and request["build"] == "GRCh37",
         "Unsupported input scale/ancestry/build")
    need(request["reference_policy"] == "FIRST_TRAIT_FULL_SNP_ALLELE_AXIS" and
         request["effect_alignment"] == "NO_PREALIGNMENT_OFFICIAL_RG_ALIGNS_ONCE", "Unfrozen reference or effect-alignment rule")
    need(request["input_origin"] in ("SYNTHETIC_TECHNICAL_ONLY", "LEGACY_SEEN_NOT_NEW_EVIDENCE"), "Scientific filtering permission not granted")
    need(type(request["seed"]) is int and 0 <= request["seed"] <= 4294967295, "Invalid seed")
    need(request["input_sha256"] == [sha(path) for path in inputs[:2]] and isinstance(request["input_rows"], list) and
         len(request["input_rows"]) == 2 and all(type(value) is int and value > 0 for value in request["input_rows"]), "Frozen input identity/row contract differs")
    original = []
    numeric = []
    for position, path in enumerate(inputs[:2]):
        with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as stream:
            header = next(csv.reader(stream, delimiter="\t"))
            need(len(header) == len(set(header)) and set(header) == {"SNP", "A1", "A2", "N", "Z"}, "Exact standard columns required")
            stream.seek(0)
            frame = pd.read_csv(stream, sep="\t", dtype=str, keep_default_na=False)
        need(len(frame) == request["input_rows"][position] and frame.SNP.ne("").all() and not frame.SNP.duplicated().any(),
             "Original SNP universe differs or duplicate IDs need prior official munging")
        need(frame.SNP.str.fullmatch(r"rs[0-9]+").all(), "This frozen transport profile is rsID-only; no guessed SNP identity")
        original.append(frame)
        value = frame.copy(deep=True)
        for name in ("N", "Z"):
            value[name] = pd.to_numeric(value[name], errors="raise")
        need(np.isfinite(value[["N", "Z"]].to_numpy()).all() and (value.N > 0).all(), "Official-munged finite N/Z required")
        numeric.append(value)
    sys.path.insert(0, str(SOURCE))
    cli = load("cachexia_allele_merge_pristine_cli", SOURCE / "ldsc.py")
    munge = load("cachexia_allele_merge_pristine_munge", SOURCE / "munge_sumstats.py")
    source_identity(request["official_runtime_files"])
    need((numeric[0].A1 + numeric[0].A2).isin(cli.sumstats.VALID_SNPS).all(), "Invalid canonical reference alleles")
    alleles = pd.DataFrame({"SNP": numeric[0].SNP.copy(), "MA": numeric[0].A1 + numeric[0].A2})
    random.seed(request["seed"])
    np.random.seed(request["seed"])
    before = (random.getstate(), np.random.get_state())
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        logger = cli.Logger(str(Path(os.environ["AUTONOMICS_WORKDIR"]) / "official-allele-merge.log"))
        try:
            result = munge.allele_merge(numeric[1].copy(deep=True), alleles.copy(deep=True), logger)
        finally:
            logger.log_fh.close()
    warning_messages = [(type(item.message).__name__, str(item.message)) for item in captured]
    state = {"request": request, "original_tables": original, "numeric_tables": numeric, "allele_reference": alleles,
             "result": result, "rng_before": before, "rng_after": (random.getstate(), np.random.get_state()), "warnings": warning_messages}
    need(cloudpickle.__version__ == "3.1.2", "Serialization version differs")
    with outputs[1].open("wb") as stream:
        cloudpickle.dump(state, stream, protocol=4)
    transport = result.copy(deep=True)
    transport.insert(0, "official_row_position", range(len(transport)))
    transport.to_csv(outputs[0], sep="\t", index=False, float_format="%.17g", na_rep="")
    retained = set(result.loc[result.N.notna() & result.Z.notna(), "SNP"])
    reference_ids = set(numeric[0].SNP)
    target_ids = set(numeric[1].SNP)
    with outputs[4].open("w") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["input_position", "source_position", "SNP_json", "status"])
        for input_position, frame in enumerate(original):
            for source_position, identifier in enumerate(frame.SNP):
                status = ("OFFICIAL_ELIGIBLE_ID_NO_Z_PREALIGNMENT" if identifier in retained else
                          "ABSENT_FROM_TARGET_OFFICIAL_MISSING" if identifier in reference_ids and identifier not in target_ids else
                          "ALLELE_MISMATCH_OFFICIAL_MISSING" if identifier in reference_ids else
                          "OUTSIDE_FROZEN_REFERENCE_AXIS_RETAINED_IN_ORIGINAL_LEDGER")
                writer.writerow([input_position, source_position, json.dumps(identifier), status])
    pd.DataFrame([{"family_id": request["family_id"], "test_id": request["test_id"], "status": "TECHNICAL_QC_TRANSPORT_NOT_SCIENTIFIC_FILTERING_PERMISSION"}]).to_csv(outputs[5], sep="\t", index=False)
    audit.update(status="TECHNICAL_PASS_NOT_SCIENTIFIC", input_sha256=[sha(path) for path in inputs],
                 original_rows=[len(frame) for frame in original], returned_rows=len(result), eligible_rows=len(retained),
                 official_runtime_sha256=source_identity(request["official_runtime_files"]), loaded_namespace=str(munge.__file__),
                 original_input_runtime_paths=[str(path) for path in inputs[:2]],
                 outputs={str(position): sha(outputs[position]) for position in (0, 1, 4, 5)}, warnings=warning_messages,
                 numeric_Z_prealigned=False, missing_transport="EMPTY_TSV_FIELDS_TRUE_NULL_NOT_NUMERIC_NA_TOKEN",
                 scientific_filtering_permission_granted=False)
    print("PASS official allele_merge; missing rows retained, no Z prealignment, no scientific release")


def main():
    outputs = [Path(os.environ["AUTONOMICS_OUTPUT" + str(position)]) for position in range(6)]
    need(len(set(outputs)) == 6 and not any(path.exists() for path in outputs), "Six non-overwritten declared ports required")
    audit = {"status": "RUNNING", "G0_granted": False, "scientific_release_granted": False, "resident_deployment_granted": False}
    with outputs[3].open("w") as stream, contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
        try:
            run(outputs, audit)
        except BaseException as error:
            for position in (0, 1, 4):
                outputs[position].unlink(missing_ok=True)
            audit.update(status="BLOCKED", error=type(error).__name__ + ": " + str(error))
            if "request" in audit:
                request = audit["request"]
                pd.DataFrame([{"family_id": request["family_id"], "test_id": request["test_id"], "status": "BLOCKED_NOT_ESTIMATED"}]).to_csv(outputs[5], sep="\t", index=False)
            traceback.print_exc()
    outputs[2].write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
    return 0 if audit["status"] == "TECHNICAL_PASS_NOT_SCIENTIFIC" else 1


if __name__ == "__main__":
    sys.exit(main())
