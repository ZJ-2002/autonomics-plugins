import copy
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import pickle
import shutil
import sys
import tempfile
import warnings

import numpy as np
import pyarrow as arrow
import pyarrow.parquet as parquet
import scipy
from scipy import stats


FIELDS = ["test_id", "row_id", "field", "value", "value_kind", "source_position"]
REQUEST_KEYS = {"scope", "scientific_qualification", "analysis_role", "test_id", "family_test_ids", "family_size", "input0_sha256",
    "expected_sample_names", "expected_row_ids", "statistic", "permutation_type", "exchangeability_model", "unmodeled_dependencies",
    "sampling_mode", "n_resamples", "batch", "alternative", "seed", "max_attainable_raw_p", "missing_policy"}
STATISTICS = {"independent": {"mean_difference", "median_difference", "welch_t", "mannwhitney_u"},
    "samples": {"mean_difference", "median_difference", "paired_t", "wilcoxon_statistic"},
    "pairings": {"pearson_r", "spearman_r", "kendall_tau"}}
MODELS = {"independent": "DONOR_INDEPENDENT_UNSTRATIFIED", "samples": "DONOR_PAIRED_SAMPLE_SWAP", "pairings": "DONOR_PAIRED_PAIRINGS_UNSTRATIFIED"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def checksum(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def unique_object(items):
    require(len({key for key, value in items}) == len(items), "Duplicate JSON keys forbidden")
    return dict(items)


def read_json(path):
    def invalid_constant(value):
        raise ValueError("Nonstandard JSON numeric constant forbidden: "+value)
    return json.loads(path.read_text(), object_pairs_hook=unique_object, parse_constant=invalid_constant)


def identity(value):
    return isinstance(value, str) and bool(value) and value.strip() == value and not any(char in value for char in "\t\r\n\x00")


def integer(value, minimum, maximum):
    return type(value) is int and minimum <= value <= maximum


def statistic_function(name):
    if name == "mean_difference":
        return lambda first, second: np.mean(first)-np.mean(second)
    if name == "median_difference":
        return lambda first, second: np.median(first)-np.median(second)
    if name == "welch_t":
        return lambda first, second: stats.ttest_ind(first, second, equal_var=False, nan_policy="raise").statistic
    if name == "mannwhitney_u":
        return lambda first, second: stats.mannwhitneyu(first, second, method="asymptotic", alternative="two-sided", nan_policy="raise").statistic
    if name == "paired_t":
        return lambda first, second: stats.ttest_rel(first, second, nan_policy="raise").statistic
    if name == "wilcoxon_statistic":
        return lambda first, second: stats.wilcoxon(first, second, zero_method="wilcox", correction=False, alternative="two-sided", method="asymptotic", nan_policy="raise").statistic
    if name == "pearson_r":
        return lambda first, second: stats.pearsonr(first, second).statistic
    if name == "spearman_r":
        return lambda first, second: stats.spearmanr(first, second, nan_policy="raise").statistic
    if name == "kendall_tau":
        return lambda first, second: stats.kendalltau(first, second, variant="b", method="asymptotic", nan_policy="raise").statistic
    raise ValueError("Unsupported frozen statistic")


def distinct_count(kind, sizes, limit=100000):
    if kind == "independent":
        return min(math.comb(sum(sizes), sizes[0]), limit+1)
    count = 1
    for position in range(1, sizes[0]+1):
        count *= 2 if kind == "samples" else position**2
        if count > limit:
            return limit+1
    return count


def write_products(outputs):
    require(len({path.resolve() for path in outputs}) == 5 and not any(path.exists() for path in outputs), "Five distinct non-overwritten output ports required")
    audit = {"status": "RUNNING", "G0_granted": False, "resident_deployment_granted": False, "scientific_qualification_granted": False}
    state = None

    def save():
        outputs[2].write_text(json.dumps(audit, indent=2, allow_nan=False)+"\n")

    save()
    outputs[3].write_text("RUNNING frozen official permutation contract\n")
    try:
        require(os.environ["AUTONOMICS_INPUT_COUNT"] == "2", "Exactly two file inputs required")
        require((scipy.__version__, np.__version__, arrow.__version__) == ("1.18.1", "2.5.3", "25.0.1"), "Pinned official runtime required")
        inputs = [Path(os.environ["AUTONOMICS_INPUT"+str(index)]) for index in range(2)]
        require(all(path.stat().st_size <= 4*1024**2 for path in inputs), "Frozen input budget exceeded")
        request = read_json(inputs[1])
        require(set(request) == REQUEST_KEYS, "Exact frozen request schema required")
        require(request["scope"] == "TECHNICAL_ONLY_NOT_G0" and request["scientific_qualification"] == "NOT_GRANTED" and request["analysis_role"] == "AUXILIARY_PERMUTATION_TECHNICAL_ONLY", "No scientific or primary-role escalation")
        require(identity(request["test_id"]) and isinstance(request["family_test_ids"], list) and all(identity(value) for value in request["family_test_ids"]), "Canonical lexical test identities required")
        require(integer(request["family_size"], 1, 100000) and len(request["family_test_ids"]) == request["family_size"] and len(set(request["family_test_ids"])) == request["family_size"] and request["test_id"] in request["family_test_ids"], "Complete frozen test family required")
        require(checksum(inputs[0]) == request["input0_sha256"], "Frozen sample input hash mismatch")
        kind = request["permutation_type"]
        require(kind in STATISTICS and request["statistic"] in STATISTICS[kind], "Statistic/permutation type not in frozen official registry")
        require(request["exchangeability_model"] == MODELS[kind] and request["unmodeled_dependencies"] == [], "Unmodeled donor/batch/stratum/spatial/network dependencies cannot become a global permutation")
        require(request["alternative"] in {"greater", "less", "two-sided"} and request["sampling_mode"] in {"EXACT", "MONTE_CARLO", "AUTO_OFFICIAL"}, "Explicit alternative and sampling mode required")
        require(integer(request["seed"], 0, 2**64-1) and integer(request["batch"], 1, 512), "Explicit integer seed and bounded batch required")
        require(type(request["max_attainable_raw_p"]) in {int, float} and math.isfinite(request["max_attainable_raw_p"]) and 0 < request["max_attainable_raw_p"] <= 1, "Frozen raw-P resolution required")
        require(request["missing_policy"] in {"PROPAGATE", "BLOCK"}, "Explicit missing policy required")
        data = read_json(inputs[0])
        require(set(data) == {"samples"} and isinstance(data["samples"], list) and len(data["samples"]) == 2, "Exactly two complete scalar sample records required")
        samples = data["samples"]
        require([sample.get("name") for sample in samples] == request["expected_sample_names"] and len(set(request["expected_sample_names"])) == 2 and all(identity(name) for name in request["expected_sample_names"]), "Frozen sample names/order differ")
        require([sample.get("row_ids") for sample in samples] == request["expected_row_ids"], "Frozen row identities/order differ")
        for sample in samples:
            require(set(sample) == {"name", "row_ids", "values"} and isinstance(sample["row_ids"], list) and isinstance(sample["values"], list), "Exact complete sample schema required")
            require(2 <= len(sample["row_ids"]) <= 5000 and len(sample["row_ids"]) == len(sample["values"]), "At least two bounded complete observations per sample required")
            require(all(identity(value) for value in sample["row_ids"]) and len(set(sample["row_ids"])) == len(sample["row_ids"]), "Unique canonical within-sample donor identities required")
            for value in sample["values"]:
                require(value is None or (type(value) in {int, float} and math.isfinite(value) and (type(value) is not int or abs(value) <= 2**53)), "Finite exactly representable numeric values or explicit missing required")
        if kind == "independent":
            require(not set(samples[0]["row_ids"]) & set(samples[1]["row_ids"]), "Independent samples share donor identities")
        else:
            require(samples[0]["row_ids"] == samples[1]["row_ids"], "Paired donors must have identical frozen row order")
        count = distinct_count(kind, [len(sample["row_ids"]) for sample in samples])
        if request["sampling_mode"] == "EXACT":
            require(request["n_resamples"] == "EXACT" and count <= 100000, "Exact enumeration exceeds frozen budget or mode differs")
            draws, exact = count, True
            resamples = np.inf
        else:
            require(integer(request["n_resamples"], 1, 100000), "Bounded integer n_resamples required")
            exact = request["n_resamples"] >= count
            require(request["sampling_mode"] != "MONTE_CARLO" or not exact, "Official auto-exact switch forbidden under frozen Monte-Carlo mode")
            draws = count if exact else request["n_resamples"]
            resamples = request["n_resamples"]
        minimum = min(1., (2 if request["alternative"] == "two-sided" else 1)/(draws if exact else draws+1))
        require(minimum <= request["max_attainable_raw_p"], "Frozen permutation budget cannot reach requested family precision")
        audit.update(request_json=json.dumps(request, separators=(",", ":"), allow_nan=False), input0_sha256=checksum(inputs[0]), input1_sha256=checksum(inputs[1]),
            official_versions={"scipy": scipy.__version__, "numpy": np.__version__, "pyarrow": arrow.__version__}, effective_sampling_mode="EXACT" if exact else "MONTE_CARLO",
            complete_family_size=request["family_size"], expected_null_draws=draws, attainable_raw_p_minimum=minimum)
        ledger = []
        for sample in samples:
            for position, (row_id, value) in enumerate(zip(sample["row_ids"], sample["values"], strict=True)):
                ledger.append({"test_id": request["test_id"], "sample": sample["name"], "row_id": row_id, "source_position": position,
                    "value": json.dumps(value, allow_nan=False), "value_kind": "MISSING" if value is None else "FINITE"})
        missing = any(value is None for sample in samples for value in sample["values"])
        require(not missing or request["missing_policy"] == "PROPAGATE", "Missing input cannot be silently omitted")
        generator = np.random.default_rng(request["seed"])
        before = copy.deepcopy(generator.bit_generator.state)
        result = None
        messages = []
        if not missing:
            arrays = tuple(np.asarray(sample["values"], dtype=np.float64) for sample in samples)
            with warnings.catch_warnings(record=True) as emitted:
                warnings.simplefilter("always")
                result = stats.permutation_test(arrays, statistic_function(request["statistic"]), permutation_type=kind, vectorized=False,
                    n_resamples=resamples, batch=request["batch"], alternative=request["alternative"], axis=0, rng=generator)
            messages = [{"category": type(item.message).__module__+"."+type(item.message).__qualname__, "message": str(item.message)} for item in emitted]
            audit["warning_origins"] = [{"filename": item.filename, "lineno": item.lineno} for item in emitted]
        state = {"result": result, "input": data, "request": request, "rng_before": before, "rng_after": copy.deepcopy(generator.bit_generator.state),
            "warnings": messages, "result_status": "NOT_ESTIMABLE_INPUT_MISSING" if missing else "ESTIMATED", "effective_sampling_mode": "EXACT" if exact else "MONTE_CARLO"}
        if not missing:
            require(np.asarray(result.statistic).shape == () and np.asarray(result.pvalue).shape == () and result.null_distribution.shape == (draws,), "Complete official scalar/null cardinality differs")
            require(np.isfinite(result.statistic) and np.isfinite(result.pvalue) and np.all(np.isfinite(result.null_distribution)), "Nonfinite official statistic or null retained only diagnostically")
        rows = [("statistic", None if missing else float(result.statistic)), ("pvalue", None if missing else float(result.pvalue))]
        if not missing:
            rows += [("null_"+str(position), float(value)) for position, value in enumerate(result.null_distribution)]
        fields = {field: [] for field in FIELDS}
        for position, (row_id, value) in enumerate(rows):
            values = [request["test_id"], row_id, "null_statistic" if position >= 2 else row_id, value, "MISSING" if value is None else "FINITE", position]
            for field, entry in zip(FIELDS, values, strict=True):
                fields[field].append(entry)
        schema = arrow.schema([arrow.field(field, arrow.float64() if field == "value" else arrow.uint32() if field == "source_position" else arrow.string(), nullable=field == "value") for field in FIELDS])
        table = arrow.Table.from_pydict(fields, schema=schema)
        parquet.write_table(table, outputs[0], compression="zstd")
        require(parquet.read_table(outputs[0]).equals(table, check_metadata=True), "Typed output readback differs")
        with outputs[1].open("wb") as stream:
            pickle.dump(state, stream, protocol=5)
        with outputs[4].open("w") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(ledger[0]), delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(ledger)
        audit.update(status="TECHNICAL_PASS_NOT_SCIENTIFIC", result_status=state["result_status"], result_rows=len(rows), null_draws=0 if missing else draws,
            missing_input_propagated=missing, official_function_invoked=not missing, output0_sha256=checksum(outputs[0]), output1_sha256=checksum(outputs[1]), input_ledger_sha256=checksum(outputs[4]),
            warnings=messages, source_ledger_rows=len(ledger), mc_raw_tail_resolution=None if exact else 1/(draws+1), mc_raw_one_sided_tail_standard_error_upper_bound=None if exact else .5/math.sqrt(draws))
        save()
        with outputs[3].open("a") as stream:
            stream.write("PASS "+state["result_status"]+"\n")
        return 0
    except Exception as error:
        if state is not None:
            state["result_status"] = "BLOCKED_OFFICIAL_OUTPUT_NOT_USABLE"
            audit["result_status"] = state["result_status"]
            diagnostic = outputs[2].parent/"failed-official-state.pkl"
            with diagnostic.open("wb") as stream:
                pickle.dump(state, stream, protocol=5)
            audit["diagnostic_state_sha256"] = checksum(diagnostic)
        for position in (0, 1, 4):
            outputs[position].unlink(missing_ok=True)
        audit.update(status="BLOCKED", error=str(error))
        save()
        with outputs[3].open("a") as stream:
            stream.write("BLOCKED "+str(error)+"\n")
        print(str(error), file=sys.stderr)
        return 2


def publish_outputs(writer):
    names = ["values.parquet", "state.pkl", "audit.json", "permutation.log", "input_ledger.tsv"]
    auxiliary = "failed-official-state.pkl"
    outputs = [Path(os.environ["AUTONOMICS_OUTPUT" + str(index)]) for index in range(5)]
    stage = None
    published = []
    complete = False
    try:
        require(all(path.is_absolute() for path in outputs), "Absolute declared output paths required")
        outputs = [path.parent.resolve(strict=True) / path.name for path in outputs]
        parent = outputs[0].parent
        require([path.name for path in outputs] == names and all(path.parent == parent for path in outputs), "Exact declared output names and common parent required")
        destinations = outputs + [parent / auxiliary]
        require(not any(os.path.lexists(path) for path in destinations), "Refusing to overwrite existing output or diagnostic")
        inputs = [Path(os.environ["AUTONOMICS_INPUT" + str(index)]).resolve(strict=True) for index in range(2)]
        require(not set(inputs) & set(destinations), "Input and output paths must be distinct")
        stage = Path(tempfile.mkdtemp(prefix=".permutation-owned-", dir=parent))
        private = [stage / name for name in names]
        status = writer(private)
        require(type(status) is int and status in (0, 2), "Invalid writer status")
        positions = range(5) if status == 0 else (2, 3)
        products = [(private[position], outputs[position]) for position in positions]
        if status == 2 and os.path.lexists(stage / auxiliary):
            products.append((stage / auxiliary, parent / auxiliary))
        for source, destination in products:
            require(source.is_file() and not source.is_symlink(), "Regular owned staged file required")
            identity = source.stat()
            os.link(source, destination, follow_symlinks=False)
            published.append((destination, identity.st_dev, identity.st_ino))
        complete = True
        return status
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 2
    finally:
        if not complete:
            for filename, device, inode in reversed(published):
                try:
                    current = filename.lstat()
                    if (current.st_dev, current.st_ino) == (device, inode):
                        filename.unlink()
                except FileNotFoundError:
                    pass
        if stage is not None:
            shutil.rmtree(stage)


def main():
    return publish_outputs(write_products)


if __name__ == "__main__":
    raise SystemExit(main())
