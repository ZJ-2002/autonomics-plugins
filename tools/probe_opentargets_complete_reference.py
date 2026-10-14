"""One-pass official Open Targets pagination control; not a native-node certificate."""

from collections import defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen

ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"
CONTROL = "MONDO_0004975"
PAGE_SIZE = 3000
MAX_COUNT = 30000
MAX_RESPONSE_BYTES = 16 * 1024**2
QUERY = ("query($id: String!, $page: Pagination!) { disease(efoId: $id) { id "
         "associatedTargets(page: $page, enableIndirect: false) { count rows { "
         "score novelty target { id approvedSymbol approvedName biotype } "
         "datasourceScores { id score } datatypeScores { id score } } } } }")
META = "query { meta { name apiVersion { x y z suffix } dataVersion { year month iteration } } }"


def write(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False, allow_nan=False)
        handle.write("\n")


def request(directory, label, query, variables):
    payload = dict(query=query, variables=variables)
    write(directory / (label + ".request.json"), payload)
    outgoing = Request(ENDPOINT, json.dumps(payload).encode(),
                       {"Content-Type": "application/json", "User-Agent": "autonomics-single-pass-source-control/1.0"})
    try:
        with urlopen(outgoing, timeout=90) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            metadata = dict(status=response.status, received_url=response.url,
                            content_type=response.headers.get("Content-Type"),
                            bytes=len(body), sha256=hashlib.sha256(body).hexdigest(), retry_count=0)
            if len(body) > MAX_RESPONSE_BYTES or response.url != ENDPOINT or response.status != 200:
                raise RuntimeError("Official source response identity or byte bound failed")
        (directory / (label + ".response.json")).write_bytes(body)
        write(directory / (label + ".http.json"), metadata)
        value = json.loads(body)
        if value.get("errors") or not isinstance(value.get("data"), dict):
            raise RuntimeError("Official GraphQL source returned errors or no data")
        return value["data"]
    except Exception as error:
        write(directory / (label + ".failure.json"), dict(error_type=type(error).__name__,
              message=str(error), retries=0, native_DAG_verified=False, g0_granted=False))
        raise


def check_page(value, page_index, count):
    parent = value.get("disease")
    if not isinstance(parent, dict) or parent.get("id") != CONTROL:
        raise RuntimeError("Official parent disease identity mismatch")
    page = parent.get("associatedTargets")
    if not isinstance(page, dict):
        raise RuntimeError("Official association page missing")
    total = page.get("count")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0 or total > MAX_COUNT:
        raise RuntimeError("Official count outside the declared control budget")
    if count is not None and total != count:
        raise RuntimeError("Official total count drifted during pagination")
    rows = page.get("rows")
    expected = min(PAGE_SIZE, max(0, total - page_index * PAGE_SIZE))
    if not isinstance(rows, list) or len(rows) != expected:
        raise RuntimeError("Official page is truncated or has an unexpected row count")
    for row in rows:
        target = row.get("target")
        if not isinstance(target, dict) or not isinstance(target.get("id"), str) or not target["id"]:
            raise RuntimeError("Official target identity missing")
        score = row.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score) or not 0 <= score <= 1:
            raise RuntimeError("Official association score invalid")
    return total, rows


def main():
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Use research_validation_session.py run")
    directory = Path(permanent) / "opentargets-complete-reference-control"
    directory.mkdir(mode=0o700)
    (directory / "driver.py").write_bytes(Path(__file__).read_bytes())
    write(directory / "predeclared.json", dict(endpoint=ENDPOINT, disease=CONTROL,
          page_size=PAGE_SIZE, maximum_count=MAX_COUNT, max_response_bytes=MAX_RESPONSE_BYTES,
          retries=0, duplicate_rows_removed=False, count_shrunk=False,
          previously_seen_control=True, scope="OFFICIAL_SOURCE_RECHECK_NOT_NEW_SCIENTIFIC_VALIDATION",
          native_DAG_verified=False, g0_granted=False))
    report = dict(control=CONTROL, status="NOT_VERIFIED", native_DAG_verified=False,
                  production_deployed=False, formal_authorized=False, g0_granted=False)
    try:
        before = request(directory, "metadata-before", META, {})
        pages = []
        positions = defaultdict(list)
        count = None
        page_index = 0
        returned_rows = 0
        while count is None or page_index < math.ceil(count / PAGE_SIZE):
            time.sleep(2)
            value = request(directory, "page-" + str(page_index), QUERY,
                            dict(id=CONTROL, page=dict(index=page_index, size=PAGE_SIZE)))
            count, rows = check_page(value, page_index, count)
            for offset, row in enumerate(rows):
                positions[row["target"]["id"]].append(dict(page=page_index, offset=offset, score=row["score"]))
            pages.append(dict(index=page_index, row_count=len(rows), declared_count=count))
            returned_rows += len(rows)
            page_index += 1
        time.sleep(2)
        after = request(directory, "metadata-after", META, {})
        if before != after:
            raise RuntimeError("Official API/data metadata changed during the one-pass control")
        duplicates = {identity: values for identity, values in positions.items() if len(values) > 1}
        write(directory / "duplicate-positions.json", duplicates)
        complete = returned_rows == count and len(positions) == count and not duplicates
        report.update(status="ONE_PASS_SOURCE_COMPLETE_NOT_NODE_QUALIFIED" if complete else "OFFICIAL_REFERENCE_INCOMPLETE_NO_DEDUPLICATION",
                      metadata=after, declared_count=count, returned_rows=returned_rows,
                      distinct_target_ids=len(positions), duplicate_target_ids=len(duplicates),
                      pages=pages, source_complete_on_this_pass=complete,
                      repeated_transport_stability_verified=False, duplicate_rows_removed=False, count_shrunk=False)
    except Exception as error:
        report.update(status="OFFICIAL_SOURCE_RECHECK_FAILED", error_type=type(error).__name__, error=str(error))
        raise
    finally:
        write(directory / "verification.json", report)
    print(json.dumps(report, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
