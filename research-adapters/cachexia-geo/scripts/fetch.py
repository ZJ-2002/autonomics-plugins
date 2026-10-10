import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import quote, urljoin, urlsplit

import requests
from urllib3.exceptions import HTTPError


KEYS = {"schema_version", "scope", "test_id", "input_role", "mode", "accession", "filename", "sra_accession", "sra_resolution",
        "expected_sha256", "expected_bytes", "max_uncompressed_bytes", "expected_series_accession", "expected_runs",
        "expected_runinfo_columns", "connect_timeout", "read_timeout", "max_attempts", "max_redirects"}
CHUNK = 1024 * 1024
MAX_BYTES = 64 * 1024**3
GSE = r"GSE[1-9][0-9]{0,11}"
SRA = r"(?:SRP|SRX|SRR)[0-9]{1,12}"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(filename):
    checksum = hashlib.sha256()
    with Path(filename).open("rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            checksum.update(block)
    return checksum.hexdigest()


def integer(raw, minimum, maximum):
    require(isinstance(raw, str) and re.fullmatch(r"0|[1-9][0-9]*", raw) is not None and len(raw) <= len(str(maximum)), "Canonical integer required")
    value = int(raw)
    require(minimum <= value <= maximum, "Integer outside frozen transport budget")
    return value


def read_contract(filename, mode):
    with Path(filename).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t", strict=True)
        require(reader.fieldnames == ["key", "value"], "Frozen request header differs")
        rows = list(reader)
    require(all(set(row) == {"key", "value"} and isinstance(row["value"], str) for row in rows), "Malformed frozen request")
    require(len(rows) == len(KEYS) and {row["key"] for row in rows} == KEYS, "Missing/duplicate/unknown frozen request key")
    request = {row["key"]: row["value"] for row in rows}
    require(request["schema_version"] == "1" and request["scope"] == "TECHNICAL_ONLY_NOT_G0", "Invalid schema/scientific scope")
    require(re.fullmatch(r"[A-Za-z0-9_.-]+", request["test_id"]) is not None, "Invalid frozen request identity")
    require(request["input_role"] in {"SYNTHETIC_TECHNICAL_INPUT", "OFFICIAL_METADATA_TECHNICAL_ONLY", "LEGACY_SEEN"}, "Independent scientific evidence not authorized")
    require(request["mode"] == mode and mode in {"matrix", "soft", "suppl", "runinfo"}, "Node kind and request mode differ")
    require(re.fullmatch(r"[a-f0-9]{64}", request["expected_sha256"]) is not None, "Frozen SHA256 required before retrieval")
    integer(request["expected_bytes"], 1, MAX_BYTES)
    integer(request["max_uncompressed_bytes"], 1, MAX_BYTES)
    integer(request["connect_timeout"], 1, 120)
    integer(request["read_timeout"], 1, 600)
    integer(request["max_attempts"], 1, 3)
    integer(request["max_redirects"], 0, 5)
    if mode == "runinfo":
        runinfo_expectations(request)
    return request


def runinfo_expectations(request):
    columns = json.loads(request["expected_runinfo_columns"])
    runs = json.loads(request["expected_runs"])
    require(isinstance(columns, list) and columns and all(isinstance(value, str) and value and "\x00" not in value for value in columns)
            and len(set(columns)) == len(columns), "Explicit unique runinfo header required")
    require(isinstance(runs, list) and 1 <= len(runs) <= 100000
            and all(isinstance(value, str) and re.fullmatch(r"SRR[0-9]{1,12}", value) and int(value[3:]) > 0 for value in runs)
            and len(set(runs)) == len(runs), "Complete unique frozen run-ID set required")
    require({"Run", "Experiment", "SRAStudy", "Sample", "LibraryName"} <= set(columns), "Required official run/sample/experiment/library identities missing")
    return columns, runs


def request_url(request):
    accession, mode, filename = request["accession"], request["mode"], request["filename"]
    if mode == "runinfo":
        require(filename == "NOT_APPLICABLE" and request["expected_series_accession"] == "NOT_APPLICABLE", "Runinfo must not infer a GEO filename/series")
        resolved = request["sra_accession"]
        require(re.fullmatch(SRA, resolved) is not None and int(resolved[3:]) > 0, "Resolved SRA accession required")
        if re.fullmatch(GSE, accession):
            require(request["sra_resolution"] == "EXTERNALLY_AUDITED_GSE_LINK", "GSE-to-SRA association must be independently qualified")
        else:
            require(accession == resolved and request["sra_resolution"] == "NOT_REQUIRED_SRA_ACCESSION", "Unexpected SRA resolution contract")
        return "https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo?acc=" + resolved
    require(re.fullmatch(GSE, accession) is not None, "Canonical positive GEO accession required")
    require(request["sra_accession"] == "NOT_APPLICABLE" and request["sra_resolution"] == "NOT_APPLICABLE", "GEO request cannot infer SRA associations")
    require(request["expected_runs"] == "[]" and request["expected_runinfo_columns"] == "[]", "GEO request cannot contain runinfo expectations")
    require(filename not in {"", ".", ".."} and len(filename.encode("utf-8")) <= 255 and re.fullmatch(r"[A-Za-z0-9_.+() -]+", filename) is not None, "Exact safe bare filename required")
    prefix = "GSE" + accession[3:][:-3] + "nnn"
    if mode == "matrix":
        require(re.fullmatch(re.escape(accession) + r"(?:[-_]GPL[1-9][0-9]*)?_series_matrix\.txt\.gz", filename) is not None, "Exact accession/platform matrix filename required")
    elif mode == "soft":
        require(filename == accession + "_family.soft.gz", "Official SOFT filename is family.soft.gz, not .tgz")
    if mode in {"matrix", "soft"}:
        require(request["expected_series_accession"] == accession, "Frozen series identity differs")
    else:
        require(request["expected_series_accession"] == "NOT_APPLICABLE", "Opaque supplements are not interpreted as a series")
    return f"https://ftp.ncbi.nlm.nih.gov/geo/series/{prefix}/{accession}/{mode}/{quote(filename)}"


def validate_redirect(target, initial):
    parsed, origin = urlsplit(target), urlsplit(initial)
    require(parsed.scheme == "https" and parsed.hostname == origin.hostname and parsed.port in {None, 443}
            and not parsed.username and not parsed.password and not parsed.fragment and parsed.path == origin.path and parsed.query == origin.query,
            "Redirect changed official host/path/query identity")


def transfer(url, request, partial, attempts, save):
    expected = int(request["expected_bytes"])
    maximum_redirects = int(request["max_redirects"])
    last_error = None
    for attempt in range(1, int(request["max_attempts"]) + 1):
        current = url
        partial.unlink(missing_ok=True)
        try:
            for redirect in range(maximum_redirects + 1):
                item = {"attempt": attempt, "redirect": redirect, "url": current, "http_status": "NOT_RECEIVED", "bytes": 0, "outcome": "STARTED"}
                attempts.append(item)
                save()
                with requests.get(current, stream=True, allow_redirects=False, timeout=(int(request["connect_timeout"]), int(request["read_timeout"])),
                                  headers={"User-Agent": "autonomics-cachexia-geo-proof/1", "Accept-Encoding": "identity"}) as response:
                    item["http_status"] = response.status_code
                    save()
                    if response.status_code in {301, 302, 303, 307, 308}:
                        require(redirect < maximum_redirects and response.headers.get("Location"), "Redirect limit/location invalid")
                        target = urljoin(current, response.headers["Location"])
                        validate_redirect(target, url)
                        item["outcome"] = "ALLOWED_SAME_RESOURCE_REDIRECT"
                        current = target
                        save()
                        continue
                    require(response.status_code == 200, "HTTP response must be complete status 200")
                    require(response.headers.get("Content-Encoding", "identity").lower() in {"", "identity"}, "Unexpected HTTP content encoding; raw byte identity is not implicit")
                    require("text/html" not in response.headers.get("Content-Type", "").lower(), "HTML response cannot masquerade as metadata/data")
                    length = response.headers.get("Content-Length")
                    if length is not None:
                        require(re.fullmatch(r"[0-9]+", length) is not None and int(length) == expected, "HTTP Content-Length differs from frozen bytes")
                    checksum = hashlib.sha256()
                    size = 0
                    with partial.open("xb") as handle:
                        for block in response.raw.stream(CHUNK, decode_content=False):
                            size += len(block)
                            item["bytes"] = size
                            require(size <= expected, "Response exceeds frozen byte budget")
                            checksum.update(block)
                            handle.write(block)
                        handle.flush()
                        os.fsync(handle.fileno())
                    require(size == expected and checksum.hexdigest() == request["expected_sha256"], "Source bytes/SHA256 differ; no updated content accepted silently")
                    item["outcome"] = "COMPLETE_BYTES_VERIFIED"
                    save()
                    return {"bytes": size, "sha256": checksum.hexdigest(), "final_url": current}
            raise ValueError("Redirect chain did not resolve a complete payload")
        except (requests.RequestException, OSError, HTTPError) as error:
            last_error = error
            if attempts and attempts[-1]["outcome"] == "STARTED":
                attempts[-1]["outcome"] = "TRANSPORT_ERROR:" + type(error).__name__
            save()
            partial.unlink(missing_ok=True)
            if attempt < int(request["max_attempts"]):
                time.sleep(2 ** (attempt - 1))
        except ValueError:
            if attempts and attempts[-1]["outcome"] == "STARTED":
                attempts[-1]["outcome"] = "BLOCKED_CONTENT_OR_HTTP_CONTRACT"
            save()
            raise
    raise ValueError("Transport attempts exhausted: " + str(last_error))


def validate_payload(filename, request):
    mode = request["mode"]
    with filename.open("rb") as handle:
        prefix = handle.read(4096).lstrip(b"\xef\xbb\xbf \t\r\n")
    require(not re.match(rb"(?i)(?:<!DOCTYPE\s+html|<html\b)", prefix), "HTML body cannot masquerade as a data file")
    compressed = mode in {"matrix", "soft"} or request["filename"].endswith(".gz")
    details = {"gzip_CRC_checked": compressed, "uncompressed_bytes": None, "series_identity_checked": mode in {"matrix", "soft"}}
    if compressed:
        total, series, begin, end, begin_offset, end_offset = 0, [], 0, 0, None, None
        with gzip.open(filename, "rb") as handle:
            while True:
                line = handle.readline(64 * CHUNK + 1)
                if not line:
                    break
                total += len(line)
                require(len(line) <= 64 * CHUNK and total <= int(request["max_uncompressed_bytes"]), "Expanded gzip exceeds frozen byte/line budget")
                if total == len(line):
                    require(not re.match(rb"(?i)(?:<!DOCTYPE\s+html|<html\b)", line.lstrip(b"\xef\xbb\xbf \t\r\n")), "Expanded HTML cannot masquerade as data")
                if mode == "matrix" and line.startswith(b"!Series_geo_accession\t"):
                    series.append(next(csv.reader([line.decode("ascii")], delimiter="\t"))[1])
                if mode == "soft" and line.startswith(b"^SERIES = "):
                    series.append(line.decode("ascii").strip().split(" = ", 1)[1])
                if mode == "matrix":
                    begin += line.rstrip() == b"!series_matrix_table_begin"
                    end += line.rstrip() == b"!series_matrix_table_end"
                    if line.rstrip() == b"!series_matrix_table_begin": begin_offset = total
                    if line.rstrip() == b"!series_matrix_table_end": end_offset = total
        require(total > 0, "Empty expanded gzip payload")
        details["uncompressed_bytes"] = total
        if mode in {"matrix", "soft"}:
            require(series == [request["expected_series_accession"]], "GEO payload series identity differs or is ambiguous")
        if mode == "matrix":
            require(begin == end == 1 and begin_offset < end_offset, "Exactly one ordered platform table begin/end required")
    return details


def convert_runinfo(source, target, request):
    expected_columns, expected_runs = runinfo_expectations(request)
    csv.field_size_limit(64 * CHUNK)
    with source.open(encoding="utf-8-sig", newline="") as handle, target.open("x", encoding="utf-8", newline="") as output:
        reader = csv.reader(handle, strict=True)
        columns = next(reader)
        require(columns == expected_columns, "Official runinfo header/order differs")
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        run_column = columns.index("Run")
        ids = []
        for row in reader:
            require(len(row) == len(columns), "Runinfo row width differs; no truncation/padding")
            require(all("\x00" not in value for value in row), "NUL bytes cannot be represented faithfully in metadata tables")
            ids.append(row[run_column])
            require(len(ids) <= len(expected_runs), "Runinfo exceeds complete frozen run set")
            writer.writerow(row)
        require(len(ids) == len(expected_runs) and len(set(ids)) == len(ids) and set(ids) == set(expected_runs), "Missing/empty/duplicate/unexpected RunInfo runs")
    return {"runinfo_rows": len(ids), "runinfo_columns": len(columns), "runinfo_source_format": "OFFICIAL_RUNINFO_CSV_NOT_RUN_SELECTOR_EXTRA_FIELDS",
            "clinical_donors_inferred": False, "all_source_field_strings_preserved": True}


def main():
    outputs = [Path(os.environ[f"AUTONOMICS_OUTPUT{port}"]) for port in range(5)]
    partial = outputs[0].with_name(outputs[0].name + ".partial")
    require(len(set(filename.resolve() for filename in outputs)) == 5 and not any(os.path.lexists(filename) for filename in [*outputs, partial]), "Refusing to overwrite any prior output/partial path")
    attempts = []
    audit = {"status": "RUNNING", "scientific_G0_granted": False, "source_metadata_does_not_define_clinical_donors": True}
    def save():
        outputs[2].write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
        with outputs[3].open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["attempt", "redirect", "url", "http_status", "bytes", "outcome"], delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(attempts)
    def log(message):
        with outputs[1].open("a", encoding="utf-8") as handle:
            handle.write(message + "\n")
    try:
        save()
        log("RUNNING TECHNICAL_ONLY_NOT_G0")
        require(os.environ.get("AUTONOMICS_INPUT_COUNT") == "1", "Exactly one frozen request input required")
        request_file = Path(os.environ["AUTONOMICS_INPUT0"])
        request = read_contract(request_file, os.environ["CACHEXIA_GEO_MODE"])
        url = request_url(request)
        audit.update(request=request, contract_sha256=digest(request_file), canonical_url=url, platform_or_gse_mapping_not_independently_qualified=True)
        save()
        log("FROZEN_REQUEST " + json.dumps(request, sort_keys=True))
        audit.update(transfer(url, request, partial, attempts, save))
        audit.update(validate_payload(partial, request))
        if request["mode"] == "runinfo":
            audit.update(convert_runinfo(partial, outputs[0], request))
            partial.rename(outputs[4])
        else:
            partial.rename(outputs[4])
            os.link(outputs[4], outputs[0])
        audit.update(status="TECHNICAL_RESOURCE_PASS_NOT_ANALYSIS_OR_G0", output0_sha256=digest(outputs[0]), raw_source_sha256=digest(outputs[4]))
        save()
        log("PASS bytes=" + str(audit["bytes"]) + " raw_sha256=" + audit["sha256"])
        return 0
    except Exception as error:
        for filename in (partial, outputs[0], outputs[4]):
            filename.unlink(missing_ok=True)
        audit.update(status="BLOCKED", error_type=type(error).__name__, error=str(error))
        save()
        log("BLOCKED " + str(error))
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
