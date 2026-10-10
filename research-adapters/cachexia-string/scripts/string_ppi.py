"""Complete frozen STRING downloads, exact raw links and identity-preserving display labels."""

from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile
import time

import requests

KEYS = {"schema_version", "scope", "test_id", "organism", "release", "network_type", "min_score", "source_urls", "source_sha256", "source_size_bytes", "max_download_bytes", "max_uncompressed_bytes", "max_line_bytes", "max_raw_records", "max_info_records", "max_attempts", "timeout_seconds", "mapping_policy", "duplicate_policy", "self_loop_policy", "score_policy", "source_policy"}
NAMES = ["string_edges.parquet", "string_edges_raw.parquet", "string_gene_info.parquet", "string_id_graph.tsv", "mapping_collisions.tsv", "audit.json", "request_ledger.tsv", "http_attempts.tsv", "string_ppi.log", "source_links.txt.gz", "source_info.txt.gz"]
HTTP_COLUMNS = ["source_position", "attempt", "url", "http_status", "bytes", "sha256", "outcome", "error"]
INFO_COLUMNS = ["#string_protein_id", "preferred_name", "protein_size", "annotation"]
BASE = "https://stringdb-downloads.org/download"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(filename):
    checksum = hashlib.sha256()
    with Path(filename).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def lexical(value):
    return isinstance(value, str) and bool(value.strip()) and not any(character in value for character in "\t\r\n\x00")


def recover_test_id(raw):
    decoder, identifiers = json.JSONDecoder(), []
    cursor = len(raw) - len(raw.lstrip())
    if not raw[cursor:].startswith("{"):
        return None
    cursor += 1
    try:
        while True:
            while raw[cursor].isspace():
                cursor += 1
            if raw[cursor] == "}":
                break
            key, cursor = decoder.raw_decode(raw, cursor)
            if not isinstance(key, str):
                break
            while raw[cursor].isspace():
                cursor += 1
            if raw[cursor] != ":":
                break
            cursor += 1
            while raw[cursor].isspace():
                cursor += 1
            value, cursor = decoder.raw_decode(raw, cursor)
            if key == "test_id":
                identifiers.append(value)
            while raw[cursor].isspace():
                cursor += 1
            if raw[cursor] != ",":
                break
            cursor += 1
    except (ValueError, IndexError):
        pass
    return identifiers[0] if len(identifiers) == 1 and (identifiers[0] is None or isinstance(identifiers[0], str)) else None


def urls(request):
    organism, release = request["organism"], request["release"]
    stem = "protein.physical.links" if request["network_type"] == "physical" else "protein.links"
    return [f"{BASE}/{stem}.v{release}/{organism}.{stem}.v{release}.txt.gz", f"{BASE}/protein.info.v{release}/{organism}.protein.info.v{release}.txt.gz"]


def load_request(filename):
    def unique(items):
        answer = {}
        for key, value in items:
            require(key not in answer, "Duplicate JSON key: " + key)
            answer[key] = value
        return answer
    return json.loads(Path(filename).read_text(encoding="utf-8"), object_pairs_hook=unique, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON constant")))


def validate(request):
    require(isinstance(request, dict) and set(request) == KEYS, "Exact frozen request keys required")
    require(type(request["schema_version"]) is int and request["schema_version"] == 1 and request["scope"] == "TECHNICAL_STRING_SOURCE_NOT_G0", "Frozen schema/scope required")
    require(lexical(request["test_id"]), "Frozen test_id required")
    require(isinstance(request["organism"], str) and re.fullmatch(r"[1-9][0-9]*", request["organism"]), "NCBI taxonomy organism required")
    require(request["release"] in {"12.0", "12.5"} and request["network_type"] in {"physical", "functional"}, "Explicit supported release/network type required")
    require(request["source_urls"] == urls(request), "Exact official whole-organism source URLs required")
    require(isinstance(request["source_sha256"], list) and len(request["source_sha256"]) == 2 and all(isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) for value in request["source_sha256"]), "Two frozen source SHA256 values required")
    for key, minimum, maximum in [("min_score", 0, 1000), ("max_download_bytes", 1, 2**31), ("max_uncompressed_bytes", 1, 2**34), ("max_line_bytes", 1, 2**20), ("max_raw_records", 1, 100000000), ("max_info_records", 1, 1000000), ("max_attempts", 1, 3), ("timeout_seconds", 1, 600)]:
        require(type(request[key]) is int and minimum <= request[key] <= maximum, "Frozen integer/budget invalid: " + key)
    require(isinstance(request["source_size_bytes"], list) and len(request["source_size_bytes"]) == 2 and all(type(value) is int and 1 <= value <= request["max_download_bytes"] for value in request["source_size_bytes"]), "Two frozen source byte counts required")
    policies = {"mapping_policy": "STRING_PREFERRED_DISPLAY_LABELS_NO_PROTEIN_COLLAPSE", "duplicate_policy": "EQUAL_SCORE_CANONICAL_ID_PAIR_WITH_MULTIPLICITY", "self_loop_policy": "RETAIN_RAW_EXCLUDE_GRAPH_WITH_LEDGER", "score_policy": "COMBINED_CONFIDENCE_0_1000_NOT_EFFECT", "source_policy": "FULL_ORGANISM_NETWORK_NO_QUERY_SUBSET"}
    require(all(request[key] == value for key, value in policies.items()), "Unsupported mapping/network policy")


def write_tsv(filename, columns, rows):
    with Path(filename).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def save_json(filename, value):
    Path(filename).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def fetch(request, position, destination, attempts):
    url = request["source_urls"][position]
    last = None
    for attempt in range(1, request["max_attempts"] + 1):
        record = {"source_position": position, "attempt": attempt, "url": url, "http_status": "", "bytes": 0, "sha256": "", "outcome": "BLOCKED", "error": ""}
        checksum = hashlib.sha256()
        try:
            with requests.Session() as session, session.get(url, stream=True, allow_redirects=False, timeout=request["timeout_seconds"], headers={"Accept-Encoding": "identity", "User-Agent": "autonomics-cachexia-string/1.0"}) as response:
                record["http_status"] = response.status_code
                require(response.status_code == 200, "Direct official HTTP200 required")
                require(response.headers.get("Content-Encoding", "identity") == "identity", "HTTP identity encoding required")
                declared = response.headers.get("Content-Length")
                require(declared is None or declared.isdigit() and int(declared) == request["source_size_bytes"][position], "Declared frozen source byte count differs")
                with destination.open("wb") as handle:
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if not block:
                            continue
                        require(record["bytes"] + len(block) <= request["max_download_bytes"] and record["bytes"] + len(block) <= request["source_size_bytes"][position], "Download exceeds frozen source byte budget")
                        handle.write(block)
                        checksum.update(block)
                        record["bytes"] += len(block)
            record["sha256"] = checksum.hexdigest()
            require(record["bytes"] == request["source_size_bytes"][position], "Frozen source byte count differs")
            require(record["sha256"] == request["source_sha256"][position], "Frozen source SHA256 differs")
            record["outcome"] = "VERIFIED"
            attempts.append(record)
            return
        except Exception as error:
            last = error
            record.update(error=str(error), sha256=checksum.hexdigest())
            attempts.append(record)
            destination.unlink(missing_ok=True)
            if attempt < request["max_attempts"]:
                time.sleep(2 ** (attempt - 1))
    raise ValueError("Download failed closed: " + str(last))


def bounded_lines(filename, request):
    consumed = 0
    with gzip.open(filename, "rb") as handle:
        while raw := handle.readline(request["max_line_bytes"] + 1):
            consumed += len(raw)
            require(len(raw) <= request["max_line_bytes"], "Uncompressed line byte budget exceeded")
            require(consumed <= request["max_uncompressed_bytes"], "Uncompressed source byte budget exceeded")
            yield raw.decode("utf-8")


def calculate(request, temporary):
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows, by_id, labels = [], {}, defaultdict(list)
    reader = csv.DictReader(bounded_lines(temporary / NAMES[10], request), delimiter="\t")
    require(reader.fieldnames == INFO_COLUMNS, "Exact STRING protein.info header required")
    for position, row in enumerate(reader):
        require(position < request["max_info_records"] and None not in row and all(value is not None for value in row.values()), "Ragged/over-budget STRING protein.info record")
        identity, label = row["#string_protein_id"], row["preferred_name"]
        require(lexical(identity) and identity.startswith(request["organism"] + ".") and lexical(label) and identity not in by_id, "Duplicate/missing/wrong-organism protein identity or display name")
        require(row["protein_size"].isdigit(), "Protein size must be an unsigned integer")
        require(int(row["protein_size"]) < 2**63, "Protein size exceeds int64")
        row["protein_size"] = int(row["protein_size"])
        rows.append(row)
        by_id[identity] = label
        labels[label].append(identity)
    require(rows, "Complete protein.info cannot be empty")
    info_schema = pa.schema([(name, pa.int64() if name == "protein_size" else pa.string()) for name in INFO_COLUMNS])
    pq.write_table(pa.Table.from_pylist(rows, schema=info_schema), temporary / NAMES[2])
    write_tsv(temporary / NAMES[4], ["preferred_name", "protein_ids_json", "n_proteins", "mapping_status"], ((label, json.dumps(identities, ensure_ascii=False), len(identities), "DISPLAY_NAME_COLLISION_NOT_UNIQUE_GENE_ID") for label, identities in sorted(labels.items()) if len(identities) > 1))
    raw_schema = pa.schema([("source_row", pa.int64()), ("protein_a", pa.string()), ("protein_b", pa.string()), ("combined_score", pa.int64())])
    edge_schema = pa.schema([("source_row", pa.int64()), ("gene_a", pa.string()), ("gene_b", pa.string()), ("protein_a", pa.string()), ("protein_b", pa.string()), ("combined_score", pa.int64()), ("mapping_status", pa.string())])
    database = sqlite3.connect(temporary / "canonical.sqlite")
    database.execute("PRAGMA cache_size=-65536")
    database.execute("PRAGMA temp_store=FILE")
    database.execute("CREATE TABLE edges(first TEXT, second TEXT, score INTEGER NOT NULL, multiplicity INTEGER NOT NULL, PRIMARY KEY(first, second)) WITHOUT ROWID")
    counts = Counter()
    raw_buffer, edge_buffer = [], []
    try:
        with pq.ParquetWriter(temporary / NAMES[1], raw_schema) as raw_writer, pq.ParquetWriter(temporary / NAMES[0], edge_schema) as edge_writer:
            lines = iter(bounded_lines(temporary / NAMES[9], request))
            require(next(lines, "").split() == ["protein1", "protein2", "combined_score"], "Exact STRING combined-score links header required")
            for position, line in enumerate(lines):
                fields = line.split()
                require(position < request["max_raw_records"] and len(fields) == 3 and re.fullmatch(r"[0-9]+", fields[2]) and 0 <= int(fields[2]) <= 1000, "Malformed/over-budget STRING link or combined confidence score")
                first, second, score = fields[0], fields[1], int(fields[2])
                require(first in by_id and second in by_id, "Link endpoint missing from complete protein.info")
                counts["raw_records"] += 1
                raw_buffer.append({"source_row": position, "protein_a": first, "protein_b": second, "combined_score": score})
                if first != second:
                    canonical = sorted((first, second))
                    try:
                        database.execute("INSERT INTO edges VALUES (?, ?, ?, 1) ON CONFLICT(first, second) DO UPDATE SET score=CASE WHEN edges.score=excluded.score THEN edges.score ELSE NULL END, multiplicity=edges.multiplicity+1", (*canonical, score))
                    except sqlite3.IntegrityError as error:
                        raise ValueError("Discordant duplicate/reciprocal STRING confidence scores") from error
                if score < request["min_score"]:
                    counts["below_threshold"] += 1
                elif first == second:
                    counts["self_loops_excluded_from_graph"] += 1
                else:
                    counts["mapped_records"] += 1
                    ambiguous = len(labels[by_id[first]]) > 1 or len(labels[by_id[second]]) > 1
                    counts["display_collision_records"] += int(ambiguous)
                    edge_buffer.append({"source_row": position, "gene_a": by_id[first], "gene_b": by_id[second], "protein_a": first, "protein_b": second, "combined_score": score, "mapping_status": "AMBIGUOUS_DISPLAY_LABEL_IDS_RETAINED" if ambiguous else "STRING_DISPLAY_LABEL_NOT_HGNC_VALIDATED"})
                if len(raw_buffer) >= 4096:
                    raw_writer.write_table(pa.Table.from_pylist(raw_buffer, schema=raw_schema))
                    raw_buffer.clear()
                if len(edge_buffer) >= 4096:
                    edge_writer.write_table(pa.Table.from_pylist(edge_buffer, schema=edge_schema))
                    edge_buffer.clear()
            if raw_buffer:
                raw_writer.write_table(pa.Table.from_pylist(raw_buffer, schema=raw_schema))
            if edge_buffer:
                edge_writer.write_table(pa.Table.from_pylist(edge_buffer, schema=edge_schema))
        require(counts["raw_records"], "Complete links cannot be empty")
        database.commit()
        graph_count = database.execute("SELECT COUNT(*) FROM edges WHERE score>=?", (request["min_score"],)).fetchone()[0]
        write_tsv(temporary / NAMES[3], ["node_a", "node_b", "combined_score", "raw_multiplicity"], database.execute("SELECT first, second, score, multiplicity FROM edges WHERE score>=? ORDER BY first, second", (request["min_score"],)))
    finally:
        database.close()
        (temporary / "canonical.sqlite").unlink(missing_ok=True)
    return {"counts": dict(counts), "info_records": len(rows), "canonical_graph_edges": graph_count, "display_name_collision_labels": sum(len(identities) > 1 for identities in labels.values()), "source_preferred_names_are_display_labels_not_certified_gene_ids": True, "statistical_official_layer": "NOT_APPLICABLE"}


def main():
    outputs = [Path(os.environ.get("AUTONOMICS_OUTPUT" + str(position), "/work/" + name)) for position, name in enumerate(NAMES)]
    audit = {"status": "BLOCKED", "test_id": None, "G0_granted": False, "scientific_release_granted": False, "resident_deployment_granted": False, "statistical_official_layer": "NOT_APPLICABLE"}
    safe, temporary, published, attempts = False, None, [], []
    try:
        parent = outputs[0].parent
        require(parent.is_dir() and not parent.is_symlink() and len(set(outputs)) == len(outputs) and all(filename.is_absolute() and filename.parent == parent and filename.name == name and not filename.exists() and not filename.is_symlink() for filename, name in zip(outputs, NAMES)), "Unsafe or preexisting output paths")
        safe = True
        request_file = Path(os.environ["AUTONOMICS_INPUT0"])
        audit["test_id"] = recover_test_id(request_file.read_text(encoding="utf-8"))
        save_json(outputs[5], dict(audit, status="STARTED_NOT_VERIFIED"))
        request = load_request(request_file)
        validate(request)
        temporary = Path(tempfile.mkdtemp(prefix="string-publication-", dir=parent))
        for position, name in enumerate(NAMES[9:]):
            fetch(request, position, temporary / name, attempts)
        details = calculate(request, temporary)
        write_tsv(temporary / NAMES[6], ["test_id", "status", "scientific_release"], [(request["test_id"], "TECHNICAL_PASS_NOT_SCIENTIFIC", "NOT_GRANTED")])
        write_tsv(temporary / NAMES[7], HTTP_COLUMNS, ([row[column] for column in HTTP_COLUMNS] for row in attempts))
        (temporary / NAMES[8]).write_text("Entire organism network and complete metadata verified; display names never collapse protein IDs.\n", encoding="utf-8")
        audit.update(details, status="TECHNICAL_PASS_NOT_SCIENTIFIC", request=request, request_sha256=digest(request_file), source_sha256=[digest(temporary / name) for name in NAMES[9:]], output_sha256={str(position): digest(temporary / name) for position, name in enumerate(NAMES) if position != 5})
        save_json(temporary / NAMES[5], audit)
        for position, name in enumerate(NAMES):
            (temporary / name).replace(outputs[position])
            published.append(outputs[position])
    except Exception as error:
        audit.update(status="BLOCKED", error=str(error))
        audit.pop("output_sha256", None)
        if safe:
            for filename in published:
                filename.unlink()
            save_json(outputs[5], audit)
            write_tsv(outputs[6], ["test_id", "status", "scientific_release"], [(audit["test_id"] or "UNKNOWN_UNRECOVERABLE_ID", "BLOCKED", "NOT_GRANTED")])
            write_tsv(outputs[7], HTTP_COLUMNS, ([row[column] for column in HTTP_COLUMNS] for row in attempts))
            outputs[8].write_text(str(error) + "\n", encoding="utf-8")
        print(str(error), file=sys.stderr)
        return 1
    finally:
        if temporary is not None:
            shutil.rmtree(temporary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
