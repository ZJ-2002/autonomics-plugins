import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys

import pyarrow as arrow
import pyarrow.parquet as parquet


FIELDS = ["test_id", "row_id", "imputation", "variable", "value", "value_kind", "label"]


def require(value, message):
    if not value:
        raise ValueError(message)


def sha256(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def unique_object(items):
    require(len({key for key, value in items}) == len(items), "Duplicate JSON keys forbidden")
    return dict(items)


def main():
    outputs = [Path(os.environ["AUTONOMICS_OUTPUT"+str(index)]) for index in range(4)]
    require(len(set(filename.resolve() for filename in outputs)) == 4 and not any(filename.exists() for filename in outputs), "Missing/aliased/overwritten typed ports")
    audit = {"status": "RUNNING", "G0_granted": False, "resident_deployment_granted": False, "statistical_method": "NOT_APPLICABLE_ENGINEERING_TYPED_BOUNDARY"}

    def save():
        outputs[1].write_text(json.dumps(audit, indent=2)+"\n")

    save()
    outputs[2].write_text("RUNNING explicit typed MICE values boundary\n")
    try:
        require(os.environ["AUTONOMICS_INPUT_COUNT"] == "2" and arrow.__version__ == "25.0.1", "Pinned Arrow/two input ports required")
        source = Path(os.environ["AUTONOMICS_INPUT0"])
        evidence = Path(os.environ["AUTONOMICS_INPUT1"])
        require(source.stat().st_size <= 64*1024**2 and evidence.stat().st_size <= 2*1024**2, "Typed input budget exceeded")
        upstream = json.loads(evidence.read_text(), object_pairs_hook=unique_object)
        request = json.loads(upstream["request_json"], object_pairs_hook=unique_object)
        require(upstream["status"] == "TECHNICAL_PASS_NOT_SCIENTIFIC" and upstream["G0_granted"] is False and upstream["resident_deployment_granted"] is False,
                "Successful non-scientific upstream receipt required")
        require(request["scope"] == "TECHNICAL_ONLY_NOT_G0" and request["scientific_qualification"] == "NOT_GRANTED" and request["analysis_role"] == "SYNTHETIC_MISSINGNESS_TECHNICAL_NOT_LONGITUDINAL_QUALIFICATION", "Frozen technical upstream scope required")
        require(sha256(source) == upstream["output0_sha256"], "Upstream numeric payload identity differs")
        reader = csv.DictReader(io.StringIO(source.read_text()), delimiter="\t")
        require(reader.fieldnames == FIELDS, "Exact seven-column MICE values schema required")
        rows = list(reader)
        require(0 < len(rows) <= 1000000 and len(rows) == upstream["result_rows"], "Upstream values cardinality differs")
        identities = set()
        frozen_rows = set(request["expected_row_ids"])
        frozen_columns = set(request["expected_columns"])
        parsed = {field: [] for field in FIELDS}
        for row in rows:
            require(None not in row and all(value is not None for value in row.values()), "Ragged values row")
            require(row["test_id"] == request["test_id"] and row["row_id"] in frozen_rows and row["variable"] in frozen_columns, "Foreign lexical source identity")
            require(row["imputation"].isdigit() and str(int(row["imputation"])) == row["imputation"], "Exact official imputation index required")
            identity = tuple(row[field] for field in ("test_id", "row_id", "imputation", "variable"))
            require(identity not in identities, "Duplicate imputation coordinates")
            identities.add(identity)
            if row["value_kind"] == "MISSING":
                require(row["value"] == "NA", "Missing value must remain missing")
                numeric = None
            else:
                require(row["value_kind"] == "FINITE", "Unsupported/nonfinite value status")
                numeric = float(row["value"])
                require(math.isfinite(numeric), "Malformed/nonfinite numeric value")
            for field in FIELDS:
                parsed[field].append(numeric if field == "value" else row[field])
        schema = arrow.schema([arrow.field(field, arrow.float64() if field == "value" else arrow.string(), nullable=field == "value") for field in FIELDS])
        table = arrow.Table.from_pydict(parsed, schema=schema)
        parquet.write_table(table, outputs[0], compression="zstd")
        require(parquet.read_table(outputs[0]).equals(table, check_metadata=True), "Typed Parquet readback differs")
        outputs[3].write_text(json.dumps({"schema": str(schema), "rows": len(rows), "string_columns": [field for field in FIELDS if field != "value"], "nullable_numeric_value": True}, indent=2)+"\n")
        audit.update(status="TECHNICAL_TYPED_VALUES_PASS_NOT_SCIENTIFIC", input0_sha256=sha256(source), input1_sha256=sha256(evidence), output0_sha256=sha256(outputs[0]), rows=len(rows))
        save()
        with outputs[2].open("a") as stream:
            stream.write("PASS\n")
        return 0
    except Exception as error:
        for index in (0, 3):
            outputs[index].unlink(missing_ok=True)
        audit.update(status="BLOCKED", error=str(error))
        save()
        with outputs[2].open("a") as stream:
            stream.write("BLOCKED "+str(error)+"\n")
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
