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


FIELDS = ["test_id", "row_id", "field", "value", "value_kind"]


def require(value, message):
    if not value:
        raise ValueError(message)


def sha256(filename):
    return hashlib.sha256(filename.read_bytes()).hexdigest()


def unique_object(items):
    require(len({key for key, value in items}) == len(items), "Duplicate JSON keys forbidden")
    return dict(items)


def main():
    outputs = [Path(os.environ["AUTONOMICS_OUTPUT" + str(index)]) for index in range(4)]
    require(len(set(filename.resolve() for filename in outputs)) == 4 and not any(filename.exists() for filename in outputs), "Distinct fresh declared typed ports required")
    audit = {"status": "RUNNING", "G0_granted": False, "resident_deployment_granted": False}

    def save():
        outputs[1].write_text(json.dumps(audit, indent=2) + "\n")

    save()
    outputs[2].write_text("RUNNING explicit typed sensitivity boundary\n")
    try:
        require(os.environ["AUTONOMICS_INPUT_COUNT"] == "2" and arrow.__version__ == "25.0.1", "Pinned Arrow/two inputs required")
        source, evidence = (Path(os.environ["AUTONOMICS_INPUT" + str(index)]) for index in range(2))
        require(source.stat().st_size <= 64*1024**2 and evidence.stat().st_size <= 2*1024**2, "Input byte budget exceeded")
        upstream = json.loads(evidence.read_text(), object_pairs_hook=unique_object)
        request = json.loads(upstream["request_json"], object_pairs_hook=unique_object)
        require(upstream["status"] == "TECHNICAL_PASS_NOT_SCIENTIFIC" and upstream["G0_granted"] is False and upstream["resident_deployment_granted"] is False, "Successful non-scientific upstream audit required")
        require(request["scope"] == "TECHNICAL_ONLY_NOT_G0" and request["scientific_qualification"] == "NOT_GRANTED" and request["operation"] in {"evalue", "combine"} and request["analysis_role"] == {"evalue": "AUXILIARY_SENSITIVITY_NOT_CAUSAL_PROOF", "combine": "AUXILIARY_INDEPENDENT_OMNIBUS_NOT_PRIMARY_IUT"}.get(request["operation"]), "Technical upstream scope required")
        require(sha256(source) == upstream["output0_sha256"], "Upstream source hash mismatch")
        reader = csv.DictReader(io.StringIO(source.read_text()), delimiter="\t")
        require(reader.fieldnames == FIELDS, "Exact sensitivity summary columns required")
        rows = list(reader)
        require(0 < len(rows) <= 1000000 and len(rows) == upstream["rows"], "Full summary cardinality mismatch")
        identities = set()
        parsed = {field: [] for field in FIELDS}
        for row in rows:
            require(None not in row and all(value is not None for value in row.values()), "Ragged summary")
            require(row["test_id"] == request["test_id"] and row["row_id"] == "0001" and row["field"], "Foreign lexical field axis")
            identity = tuple(row[field] for field in ("test_id", "row_id", "field"))
            require(identity not in identities, "Duplicate numeric field coordinate")
            identities.add(identity)
            kind = row["value_kind"]
            if kind in {"MISSING", "NAN"}:
                require(row["value"] == "NA", "Missing/NaN must not become zero")
                value = None
            else:
                value = float(row["value"])
                require((kind == "FINITE" and math.isfinite(value)) or (kind == "POS_INF" and value == math.inf) or (kind == "NEG_INF" and value == -math.inf), "Numeric value/status mismatch")
            for field in FIELDS:
                parsed[field].append(value if field == "value" else row[field])
        schema = arrow.schema([arrow.field(field, arrow.float64() if field == "value" else arrow.string(), nullable=field == "value") for field in FIELDS] + [arrow.field("source_position", arrow.uint32(), nullable=False)])
        parsed["source_position"] = list(range(len(rows)))
        table = arrow.Table.from_pydict(parsed, schema=schema)
        parquet.write_table(table, outputs[0], compression="zstd")
        require(parquet.read_table(outputs[0]).equals(table, check_metadata=True), "Parquet readback differs")
        outputs[3].write_text(json.dumps({"schema": str(schema), "rows": len(rows), "nullable_numeric_value": True, "string_columns": [field for field in FIELDS if field != "value"], "source_position_uint32": True, "source_position_must_remain_in_materialized_tables": True, "physical_file_row_order_not_guaranteed": True}, indent=2) + "\n")
        audit.update(status="TECHNICAL_TYPED_VALUES_PASS_NOT_SCIENTIFIC", input0_sha256=sha256(source), input1_sha256=sha256(evidence), output0_sha256=sha256(outputs[0]), rows=len(rows))
        save()
        outputs[2].write_text("PASS explicit types and readback; not G0\n")
        return 0
    except Exception as error:
        for index in (0, 3):
            outputs[index].unlink(missing_ok=True)
        audit.update(status="BLOCKED", error=str(error))
        save()
        outputs[2].write_text("BLOCKED " + str(error) + "\n")
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

