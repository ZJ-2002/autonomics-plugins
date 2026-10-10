import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
from urllib.parse import urljoin, urlsplit

import requests


KEYS = {"schema_version", "scope", "test_id", "input_role", "mode", "release", "collection", "gene_id_type",
        "expected_sha256", "expected_bytes", "expected_set_ids", "expected_n_sets", "expected_n_memberships",
        "connect_timeout", "read_timeout", "max_attempts", "max_redirects", "max_bytes", "max_line_bytes", "encoding"}
OUTPUT_NAMES = ["memberships.tsv", "sets.tsv", "source.gmt", "audit.json", "msigdb.log", "http_attempts.tsv", "request_ledger.tsv"]
ATTEMPT_COLUMNS = ["attempt", "requested_url", "final_url", "http_status", "bytes", "sha256", "outcome"]
CHUNK = 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(filename):
    checksum = hashlib.sha256()
    with Path(filename).open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            checksum.update(block)
    return checksum.hexdigest()


def integer(value, minimum, maximum):
    require(type(value) is int and minimum <= value <= maximum, "Invalid frozen integer or transport budget")
    return value


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("Nonfinite JSON constant: " + value)


def recover_request_id(filename):
    try:
        pairs = json.loads(Path(filename).read_text(encoding="utf-8"), object_pairs_hook=lambda entries: entries, parse_constant=reject_constant)
        if isinstance(pairs, list) and all(isinstance(entry, tuple) and len(entry) == 2 for entry in pairs):
            identifiers = [value for key, value in pairs if key == "test_id"]
            if len(identifiers) == 1 and isinstance(identifiers[0], str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", identifiers[0]):
                return identifiers[0]
    except (ValueError, UnicodeError):
        pass
    return None


def request_url(request):
    release, collection, flavor = request["release"], request["collection"], request["gene_id_type"]
    require(isinstance(release, str) and re.fullmatch(r"[0-9]{4}\.[1-9][0-9]*\.(Hs|Mm)", release), "Explicit MSigDB release/species required")
    require(isinstance(collection, str) and re.fullmatch(r"[a-z][a-z0-9]*(?:[._][a-z0-9]+)*", collection), "Safe explicit collection required")
    require(flavor in {"symbols", "entrez"}, "Explicit identifier flavor required")
    return f"https://data.broadinstitute.org/gsea-msigdb/msigdb/release/{release}/{collection}.v{release}.{flavor}.gmt"


def read_contract(filename, mode):
    request = json.loads(Path(filename).read_text(encoding="utf-8"), object_pairs_hook=unique_object, parse_constant=reject_constant)
    require(isinstance(request, dict) and set(request) == KEYS, "Missing or unknown frozen request key")
    require(type(request["schema_version"]) is int and request["schema_version"] == 1 and
            request["scope"] == "TECHNICAL_RESOURCE_ONLY_NOT_G0", "Invalid schema or scientific scope")
    require(isinstance(request["test_id"], str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", request["test_id"]), "Valid frozen request ID required")
    require(request["mode"] == mode and mode in {"fetch", "parse"}, "Node kind and frozen mode differ")
    require(request["input_role"] in {"OFFICIAL_RESOURCE_TECHNICAL_ONLY", "LEGACY_SEEN", "SYNTHETIC_TECHNICAL_INPUT"}, "Scientific input eligibility not granted")
    request_url(request)
    require(request["encoding"] == "ascii", "Official ASCII GMT profile required")
    require(isinstance(request["expected_sha256"], str) and re.fullmatch(r"[a-f0-9]{64}", request["expected_sha256"]), "Frozen content SHA256 required")
    integer(request["max_bytes"], 1, 2**31)
    integer(request["expected_bytes"], 1, request["max_bytes"])
    integer(request["max_line_bytes"], 1, min(request["max_bytes"], 32 * 1024**2))
    integer(request["expected_n_sets"], 1, 1000000)
    integer(request["expected_n_memberships"], 1, 100000000)
    integer(request["connect_timeout"], 1, 120)
    integer(request["read_timeout"], 1, 600)
    integer(request["max_attempts"], 1, 3)
    integer(request["max_redirects"], 0, 5)
    names = request["expected_set_ids"]
    require(isinstance(names, list) and len(names) == request["expected_n_sets"] and
            all(isinstance(name, str) and name and all(32 <= ord(character) < 127 for character in name) for name in names)
            and len(set(names)) == len(names), "Complete ordered unique frozen set axis required")
    return request


def write_tsv(filename, columns, rows):
    with Path(filename).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def verify_raw(filename, request):
    require(Path(filename).stat().st_size == request["expected_bytes"], "Frozen source byte count differs")
    require(digest(filename) == request["expected_sha256"], "Frozen source SHA256 differs")


def fetch(request, destination, attempts, session_factory=requests.Session, sleeper=time.sleep):
    original_url = request_url(request)
    destination = Path(destination)
    for attempt in range(1, request["max_attempts"] + 1):
        record = {"attempt": attempt, "requested_url": original_url, "final_url": original_url,
                  "http_status": "NOT_RECEIVED", "bytes": 0, "sha256": "NOT_COMPLETE", "outcome": "STARTED"}
        attempts.append(record)
        checksum = hashlib.sha256()
        try:
            with session_factory() as session:
                url = original_url
                for hop in range(request["max_redirects"] + 1):
                    with session.get(url, stream=True, allow_redirects=False,
                                     timeout=(request["connect_timeout"], request["read_timeout"]),
                                     headers={"User-Agent": "autonomics-content-frozen-msigdb/1", "Accept-Encoding": "identity"}) as response:
                        record.update(final_url=url, http_status=response.status_code)
                        if response.status_code in {301, 302, 303, 307, 308}:
                            require(hop < request["max_redirects"], "Redirect budget exhausted")
                            target = urljoin(url, response.headers.get("Location", ""))
                            parsed = urlsplit(target)
                            require(parsed.scheme == "https" and parsed.hostname == "data.broadinstitute.org" and
                                    parsed.port in {None, 443} and parsed.username is None and parsed.password is None and
                                    not parsed.query and not parsed.fragment and parsed.path == urlsplit(original_url).path,
                                    "Redirect leaves exact official release resource")
                            url = target
                            continue
                        require(response.status_code == 200, "HTTP status is not complete 200")
                        require(response.headers.get("Content-Encoding", "identity").lower() in {"", "identity"}, "Unexpected HTTP content encoding")
                        require("html" not in response.headers.get("Content-Type", "").lower(), "HTML response is not GMT")
                        length = response.headers.get("Content-Length")
                        if length is not None:
                            require(re.fullmatch(r"[0-9]+", length) and int(length) == request["expected_bytes"], "HTTP length differs from freeze")
                        with destination.open("wb") as handle:
                            for block in response.iter_content(chunk_size=CHUNK):
                                if not block:
                                    continue
                                record["bytes"] += len(block)
                                require(record["bytes"] <= request["expected_bytes"], "HTTP payload exceeds frozen bytes")
                                handle.write(block)
                                checksum.update(block)
                        record["sha256"] = checksum.hexdigest()
                        verify_raw(destination, request)
                        record["outcome"] = "COMPLETE_BYTES_VERIFIED"
                        return
        except requests.RequestException as error:
            record["outcome"] = "TRANSPORT_ERROR:" + type(error).__name__
            destination.unlink(missing_ok=True)
            if attempt == request["max_attempts"]:
                raise ValueError("Transport retries exhausted") from error
            sleeper(2 ** (attempt - 1))
        except Exception as error:
            record["outcome"] = "BLOCKED:" + type(error).__name__
            destination.unlink(missing_ok=True)
            raise
    raise ValueError("No completed official response")


def parse_gmt(raw, request, members_file, sets_file):
    verify_raw(raw, request)
    names = []
    total = 0
    duplicates = 0
    member_columns = ["source_set_position", "member_position", "set_id", "gene_id"]
    set_columns = ["source_set_position", "set_id", "description", "n_memberships", "n_unique_members",
                   "release", "collection", "gene_id_type", "database_species"]
    with Path(raw).open("rb") as source, Path(members_file).open("w", encoding="utf-8", newline="") as members, \
            Path(sets_file).open("w", encoding="utf-8", newline="") as sets:
        member_writer = csv.writer(members, delimiter="\t", lineterminator="\n")
        set_writer = csv.writer(sets, delimiter="\t", lineterminator="\n")
        member_writer.writerow(member_columns)
        set_writer.writerow(set_columns)
        while True:
            line = source.readline(request["max_line_bytes"] + 1)
            if not line:
                break
            require(len(line) <= request["max_line_bytes"], "GMT line exceeds frozen budget")
            if line.endswith(b"\n"):
                line = line[:-1].removesuffix(b"\r")
            fields = line.decode("ascii").split("\t")
            require(len(fields) >= 3 and fields[0] and all(fields[2:]), "Malformed GMT record or empty member")
            require(all(all(32 <= ord(character) < 127 for character in field) for field in fields), "GMT field contains control character")
            name, description, genes = fields[0], fields[1], fields[2:]
            position = len(names) + 1
            require(position <= len(request["expected_set_ids"]) and name == request["expected_set_ids"][position - 1], "Frozen complete set axis differs")
            if request["gene_id_type"] == "entrez":
                require(all(re.fullmatch(r"[0-9]+", gene) for gene in genes), "Entrez profile contains nonnumeric identifier")
            names.append(name)
            unique = len(set(genes))
            duplicates += len(genes) - unique
            total += len(genes)
            require(total <= request["expected_n_memberships"], "Frozen membership count exceeded")
            member_writer.writerows((position, member_position, name, gene) for member_position, gene in enumerate(genes, 1))
            set_writer.writerow([position, name, description, len(genes), unique, request["release"], request["collection"],
                                 request["gene_id_type"], request["release"].split(".")[-1]])
    require(names == request["expected_set_ids"] and len(names) == request["expected_n_sets"] and total == request["expected_n_memberships"], "Incomplete frozen collection")
    return {"sets": len(names), "membership_occurrences": total, "duplicate_member_occurrences_preserved": duplicates,
            "identifier_mapping_performed": False, "gene_case_or_identifier_normalization_performed": False}


def main():
    work = Path(os.environ.get("AUTONOMICS_WORKDIR", "/work")).resolve()
    outputs = []
    published = []
    attempts = []
    request = None
    safe_outputs = False
    audit = {"status": "BLOCKED", "test_id": None, "G0_granted": False, "scientific_release_granted": False,
             "resident_deployment_granted": False, "statistical_official_layer": "NOT_APPLICABLE"}
    try:
        mode = os.environ["CACHEXIA_GMT_MODE"]
        inputs = [Path(os.environ["AUTONOMICS_INPUT0"]).resolve()]
        if mode == "parse":
            inputs.append(Path(os.environ["AUTONOMICS_INPUT1"]).resolve())
        require(mode in {"fetch", "parse"}, "Unknown GMT mode")
        contract = inputs[-1]
        audit["contract_sha256"] = digest(contract)
        audit["test_id"] = recover_request_id(contract)
        outputs = [Path(os.environ["AUTONOMICS_OUTPUT" + str(port)]).resolve() for port in range(7)]
        require(len(set(outputs)) == 7 and not set(inputs) & set(outputs) and
                all(path.is_relative_to(work) and path != work and not path.exists() for path in outputs), "Unsafe or pre-existing publication path")
        safe_outputs = True
        request = read_contract(contract, mode)
        audit.update(test_id=request["test_id"], request=request, mode=mode, source_url=request_url(request),
                     input_sha256=[digest(path) for path in inputs], input_role=request["input_role"],
                     original_source_bytes_preserved=True, selection_or_ortholog_mapping_performed=False)
        with tempfile.TemporaryDirectory(prefix="msigdb-publication-", dir=work) as directory:
            stage = Path(directory)
            staged = [stage / name for name in OUTPUT_NAMES]
            if mode == "fetch":
                fetch(request, staged[2], attempts)
            else:
                require(inputs[0].stat().st_size <= request["max_bytes"], "Raw GMT exceeds frozen budget")
                shutil.copyfile(inputs[0], staged[2])
            result = parse_gmt(staged[2], request, staged[0], staged[1])
            write_tsv(staged[5], ATTEMPT_COLUMNS, [[record[key] for key in ATTEMPT_COLUMNS] for record in attempts])
            write_tsv(staged[6], ["request_id", "status", "role", "resource_sha256", "resource_bytes"],
                      [[request["test_id"], "TECHNICAL_RESOURCE_PASS_NOT_G0", request["input_role"], digest(staged[2]), staged[2].stat().st_size]])
            staged[4].write_text("PASS mode=" + mode + " sets=" + str(result["sets"]) + " memberships=" + str(result["membership_occurrences"]) + "\n")
            audit.update(status="TECHNICAL_RESOURCE_PASS_NOT_G0", **result, raw_source_sha256=digest(staged[2]), bytes=staged[2].stat().st_size,
                         HTTP_retrieval_performed=mode == "fetch", ordered_complete_collection_verified=True,
                         output_sha256={str(port): digest(path) for port, path in enumerate(staged) if port != 3})
            staged[3].write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
            for source, target in zip(staged, outputs, strict=True):
                target.parent.mkdir(parents=True, exist_ok=True)
                source.replace(target)
                published.append(target)
        return 0
    except Exception as error:
        for path in published:
            path.unlink(missing_ok=True)
        audit.update(status="BLOCKED", error=type(error).__name__ + ": " + str(error))
        diagnostic_paths = [outputs[3], outputs[4], outputs[5]] if safe_outputs else [work / "blocked-audit.json", work / "blocked.log", work / "blocked-http-attempts.tsv"]
        for path in diagnostic_paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            require(not path.exists(), "Refuse to overwrite existing diagnostic")
        diagnostic_paths[0].write_text(json.dumps(audit, indent=2, allow_nan=False) + "\n")
        diagnostic_paths[1].write_text("BLOCKED " + audit["error"] + "\n")
        write_tsv(diagnostic_paths[2], ATTEMPT_COLUMNS, [[record[key] for key in ATTEMPT_COLUMNS] for record in attempts])
        if audit["test_id"] is not None:
            ledger = work / "blocked-request.tsv"
            require(not ledger.exists(), "Refuse to overwrite existing request ledger")
            write_tsv(ledger, ["request_id", "status"], [[audit["test_id"], "BLOCKED"]])
        print(audit["error"], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
