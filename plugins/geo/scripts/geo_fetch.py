"""Official GEO/SRA transport with complete gzip/format/identity admission.

GEO payloads retain raw bytes; official RunInfo CSV fields are losslessly rendered
as the originally declared TSV. Logs distinguish source and output hashes.
SOFT's legacy .tgz output name contains gzip SOFT text, never a tar archive.
Explicit matrix filenames and official GSE relations do not grant frozen study,
clinical donor, cohort, biological replication or scientific eligibility.
The existing approximate supplementary listing contract remains separate.
"""
import gzip
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, urljoin, urlsplit

# `requests` is imported lazily inside download()/fetch_listing(): the
# offline selftest (test_geo_list_parse.py) loads this module via importlib
# and must stay runnable with stdlib only (python3 -S, CI runners without
# pip packages). The listing parser below deliberately never needs it.
MODE = os.environ.get("GEO_MODE", "matrix")
ACCESSION = os.environ.get("GEO_ACCESSION", os.environ.get("SRA_ACCESSION", ""))
SUPPL_FILE = os.environ.get("GEO_SUPPL_FILE", "")
MATRIX_FILE = os.environ.get("GEO_MATRIX_FILE", "")
SRA_CHOICE = os.environ.get("GEO_SRA_ACCESSION", "")
OUT_FILE = os.environ["AUTONOMICS_OUTPUT0"]
OUT_LOG = os.environ["AUTONOMICS_OUTPUT1"]

RETRIES = 3
TIMEOUT = (30, 300)
HEADERS = {"User-Agent": "autonomics-geo-fetch/1.1", "Accept-Encoding": "identity"}
PROVENANCE = {}
ATTEMPTS = []
OWNED_FILES = {}
OWNED_DESCRIPTORS = {}
OFFICIAL_HOSTS = {"ftp.ncbi.nlm.nih.gov", "www.ncbi.nlm.nih.gov", "trace.ncbi.nlm.nih.gov"}


class FetchError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def fail(code, message):
    raise FetchError(code, message)


def ownership_key(filename):
    return str(Path(filename).absolute())


def create_owned_file(filename, mode):
    handle = Path(filename).open(mode, **({} if "b" in mode else {"encoding": "utf-8", "newline": ""}))
    try:
        descriptor = os.dup(handle.fileno())
        identity = os.fstat(descriptor)
    except BaseException:
        handle.close()
        raise
    OWNED_FILES[ownership_key(filename)] = (identity.st_dev, identity.st_ino)
    OWNED_DESCRIPTORS[ownership_key(filename)] = descriptor
    return handle


def require_owned_file(filename):
    try:
        identity = os.lstat(filename)
    except FileNotFoundError:
        fail(3, "Owned temporary or diagnostic path disappeared")
    if (not stat.S_ISREG(identity.st_mode) or
            (identity.st_dev, identity.st_ino) != OWNED_FILES.get(ownership_key(filename))):
        fail(3, "Refusing a replaced or unowned temporary or diagnostic path")


def remove_owned_file(filename):
    try:
        identity = os.lstat(filename)
    except FileNotFoundError:
        return
    if stat.S_ISREG(identity.st_mode) and (identity.st_dev, identity.st_ino) == OWNED_FILES.get(ownership_key(filename)):
        Path(filename).unlink()
        OWNED_FILES.pop(ownership_key(filename), None)
        descriptor = OWNED_DESCRIPTORS.pop(ownership_key(filename), None)
        if descriptor is not None:
            os.close(descriptor)


def close_owned_files():
    for descriptor in OWNED_DESCRIPTORS.values():
        os.close(descriptor)
    OWNED_DESCRIPTORS.clear()
    OWNED_FILES.clear()


def open_owned_file(filename, mode):
    flags = (os.O_RDONLY if mode == "rb" else os.O_WRONLY) | os.O_NOFOLLOW
    descriptor = os.open(filename, flags)
    try:
        identity = os.fstat(descriptor)
        if (not stat.S_ISREG(identity.st_mode) or
                (identity.st_dev, identity.st_ino) != OWNED_FILES.get(ownership_key(filename))):
            fail(3, "Refusing a replaced or unowned temporary or diagnostic descriptor")
        if mode == "w":
            os.ftruncate(descriptor, 0)
        return os.fdopen(descriptor, mode, **({} if "b" in mode else {"encoding": "utf-8", "newline": ""}))
    except BaseException:
        os.close(descriptor)
        raise


def open_payload_file(filename):
    if ownership_key(filename) in OWNED_FILES:
        return open_owned_file(filename, "rb")
    return Path(filename).open("rb")


def series_prefix():
    return "GSE" + ACCESSION[3:][:-3] + "nnn"


def safe_filename(filename):
    return (filename not in {"", ".", ".."} and len(filename.encode("utf-8")) <= 255
            and not any(character in filename for character in "/\\\x00\r\n\t")
            and not any(ord(character) < 32 for character in filename))


def suppl_dir_url():
    require("GSE\\d+", "GSE series accession (e.g. GSE92742)")
    prefix = series_prefix()
    return (
        "https://ftp.ncbi.nlm.nih.gov/geo/series/"
        f"{prefix}/{ACCESSION}/suppl/"
    )


def build_url():
    if MODE == "matrix":
        require("GSE\\d+", "GSE series accession (e.g. GSE130563)")
        prefix = series_prefix()
        filename = MATRIX_FILE or ACCESSION + "_series_matrix.txt.gz"
        if not safe_filename(filename) or not re.fullmatch(re.escape(ACCESSION) + r"(?:[-_]GPL[1-9][0-9]*)?_series_matrix\.txt\.gz", filename):
            fail(2, "matrix_file must be an exact safe matrix filename belonging to the requested accession")
        PROVENANCE["matrix_file"] = filename
        PROVENANCE["platform_selection"] = "EXPLICIT_FILENAME" if MATRIX_FILE else "CANONICAL_FILENAME_ONLY_NO_PLATFORM_SELECTION"
        return (
            "https://ftp.ncbi.nlm.nih.gov/geo/series/"
            f"{prefix}/{ACCESSION}/matrix/{quote(filename, safe='')}"
        )
    if MODE == "soft":
        require("GSE\\d+", "GSE series accession (e.g. GSE130563)")
        prefix = series_prefix()
        return (
            "https://ftp.ncbi.nlm.nih.gov/geo/series/"
            f"{prefix}/{ACCESSION}/soft/{ACCESSION}_family.soft.gz"
        )
    if MODE == "runinfo":
        require("(GSE|SRP|SRX|SRR)\\d+", "GSE/SRP/SRX/SRR accession")
        resolved = resolve_sra_accession() if ACCESSION.startswith("GSE") else ACCESSION
        if SRA_CHOICE and not ACCESSION.startswith("GSE"):
            fail(2, "sra_accession is only a selection among official GSE study relations")
        PROVENANCE["resolved_sra_accession"] = resolved
        return f"https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo?acc={resolved}"
    if MODE == "suppl":
        require("GSE\\d+", "GSE series accession (e.g. GSE92742)")
        # suppl 文件名按上游发布原名传参：只允许单段文件名，杜绝路径拼接注入。
        if not safe_filename(SUPPL_FILE):
            fail(2, f"GEO_SUPPL_FILE must be a bare filename (no / or ..): {SUPPL_FILE!r}")
        return suppl_dir_url() + quote(SUPPL_FILE, safe="")
    if MODE == "list":
        return suppl_dir_url()
    fail(2, f"GEO_MODE must be matrix|soft|runinfo|suppl|list, got {MODE!r}")


def require(pattern, label):
    if not re.fullmatch(pattern, ACCESSION or ""):
        fail(2, f"{label} must match {pattern}, got {ACCESSION!r}")
    if int(re.search(r"[0-9]+$", ACCESSION).group()) == 0 or (ACCESSION.startswith("GSE") and ACCESSION[3] == "0"):
        fail(2, "Canonical positive accession required; GEO series have no leading zero padding")


def download(url, target=None, max_bytes=None):
    import requests  # lazy: keep module importable stdlib-only (see top note)

    target = Path(target or OUT_FILE)
    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            if os.path.lexists(target):
                require_owned_file(target)
                remove_owned_file(target)
            current = url
            for redirect in range(6):
                parsed = urlsplit(current)
                if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS or parsed.port not in {None, 443} or parsed.username or parsed.password:
                    fail(3, "Redirect/resource must retain an allowed official NCBI HTTPS host")
                with requests.get(current, stream=True, allow_redirects=False, timeout=TIMEOUT, headers=HEADERS) as response:
                    ATTEMPTS.append({"attempt": attempt, "redirect": redirect, "url": current, "http_status": response.status_code})
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect == 5 or not response.headers.get("Location"):
                            fail(1, "Redirect limit/location invalid")
                        current = urljoin(current, response.headers["Location"])
                        continue
                    if response.status_code in {408, 429} or response.status_code >= 500:
                        response.raise_for_status()
                    if response.status_code != 200:
                        fail(1, f"HTTP {response.status_code} for {current}; no implicit platform/resource selection")
                    if response.headers.get("Content-Encoding", "identity").lower() not in {"", "identity"}:
                        fail(3, "Unexpected HTTP content encoding would change raw byte identity")
                    if "text/html" in response.headers.get("Content-Type", "").lower():
                        fail(3, "HTML response cannot masquerade as GEO/SRA data")
                    hasher = hashlib.sha256()
                    size = 0
                    length = response.headers.get("Content-Length")
                    if max_bytes is not None and length is not None and length.isdigit() and int(length) > max_bytes:
                        fail(3, "Metadata response exceeds its supported byte bound")
                    with create_owned_file(target, "xb") as handle:
                        for block in response.raw.stream(1024 * 1024, decode_content=False):
                            handle.write(block)
                            hasher.update(block)
                            size += len(block)
                            if max_bytes is not None and size > max_bytes:
                                fail(3, "Metadata response exceeds its supported byte bound")
                        handle.flush()
                        os.fsync(handle.fileno())
                    if size == 0 or (length is not None and (not length.isdigit() or size != int(length))):
                        fail(3, "Empty/incomplete HTTP body or Content-Length mismatch")
                    PROVENANCE["final_url"] = current
                    return size, hasher.hexdigest(), response.status_code
        except FetchError:
            raise
        except Exception as error:
            last_error = error
            if attempt < RETRIES:
                time.sleep(2 ** attempt)
    fail(1, f"download failed after {RETRIES} attempts: {last_error}")


def resolve_sra_accession():
    require("GSE\\d+", "GSE series accession")
    url = f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={ACCESSION}&targ=self&form=text&view=full"
    temporary = Path(OUT_FILE).with_name(Path(OUT_FILE).name + ".relation.partial")
    try:
        size, digest, status = download(url, temporary, max_bytes=4 * 1024 * 1024)
        require_owned_file(temporary)
        if size > 4 * 1024 * 1024:
            fail(3, "GEO self-SOFT relation metadata exceeds the supported bound")
        with open_owned_file(temporary, "rb") as handle:
            content = handle.read().decode("utf-8-sig")
        series = [line.split(" = ", 1)[1] for line in content.splitlines() if line.startswith("^SERIES = ")]
        if series != [ACCESSION]:
            fail(3, "GEO self-SOFT series identity differs; no inferred SRA relation")
        raw_relations = [line for line in content.splitlines() if line.startswith("!Series_relation = SRA: ")]
        studies = set()
        for line in raw_relations:
            relation = urlsplit(line.split("SRA: ", 1)[1])
            if relation.scheme not in {"http", "https"} or relation.hostname not in OFFICIAL_HOSTS:
                fail(3, "GEO SRA relation is not an official NCBI reference")
            for value in parse_qs(relation.query).get("term", []):
                match = re.fullmatch(r"(SRP[0-9]+)(?:\[ACCN\])?", value)
                if not match:
                    fail(3, "GEO SRA relation must name an explicit SRP study")
                studies.add(match.group(1))
        PROVENANCE.update({"relation_url": url, "relation_source_sha256": digest,
                           "relation_source_bytes": size, "relation_http_status": status,
                           "relation_raw": json.dumps(raw_relations, ensure_ascii=False),
                           "relation_studies": json.dumps(sorted(studies)), "clinical_donor_qualification": "NOT_INFERRED"})
        if SRA_CHOICE:
            if SRA_CHOICE not in studies:
                fail(2, "sra_accession must belong to the official GEO SRA study relation set")
            PROVENANCE["sra_relation_selection"] = "EXPLICIT_MEMBER_SELECTION"
            return SRA_CHOICE
        if len(studies) != 1:
            fail(3, "GSE has no unique official SRA study relation; no automatic resource selection")
        PROVENANCE["sra_relation_selection"] = "UNIQUE_OFFICIAL_RELATION_TECHNICAL_ONLY"
        return next(iter(studies))
    finally:
        remove_owned_file(temporary)


def validate_payload(filename):
    with open_payload_file(filename) as handle:
        prefix = handle.read(4096).lstrip(b"\xef\xbb\xbf \t\r\n")
    if re.match(rb"(?i)(?:<!DOCTYPE\s+html|<html\b)", prefix):
        fail(3, "HTML body cannot masquerade as GEO/SRA data")
    compressed = MODE in {"matrix", "soft"} or (MODE == "suppl" and SUPPL_FILE.lower().endswith(".gz"))
    if not compressed:
        return
    series = []
    opened = False
    tables = 0
    expanded = 0
    soft_entities = set()
    soft_table = None
    matrix_width = None
    pending_samples = None
    table_samples = None
    metadata_bound_tables = 0
    with open_payload_file(filename) as raw, gzip.GzipFile(fileobj=raw, mode="rb") as handle:
        while True:
            block = handle.readline(64 * 1024 * 1024 + 1) if MODE in {"matrix", "soft"} else handle.read(1024 * 1024)
            if not block:
                break
            if expanded == 0 and re.match(rb"(?i)(?:<!DOCTYPE\s+html|<html\b)", block.lstrip(b"\xef\xbb\xbf \t\r\n")):
                fail(3, "Expanded HTML is not GEO data")
            expanded += len(block)
            if MODE in {"matrix", "soft"} and len(block) > 64 * 1024 * 1024:
                fail(3, "GEO text line exceeds the supported 64 MiB bound")
            if MODE == "matrix":
                if block.startswith(b"!Series_geo_accession\t"):
                    row = next(csv.reader([block.decode("latin1")], delimiter="\t", strict=True))
                    series.extend(row[1:])
                if block.startswith(b"!Sample_geo_accession\t"):
                    if opened or pending_samples is not None:
                        fail(3, "Sample metadata must uniquely precede its corresponding matrix table")
                    row = next(csv.reader([block.decode("latin1")], delimiter="\t", strict=True))
                    pending_samples = row[1:]
                    if (not pending_samples or len(set(pending_samples)) != len(pending_samples) or
                            not all(re.fullmatch(r"GSM[0-9]+", sample) for sample in pending_samples)):
                        fail(3, "Sample metadata requires complete unique GEO sample accessions")
                if block.rstrip() == b"!series_matrix_table_begin":
                    if opened:
                        fail(3, "Nested matrix table begin")
                    opened = True
                    matrix_width = None
                    table_samples = pending_samples
                    pending_samples = None
                elif block.rstrip() == b"!series_matrix_table_end":
                    if not opened:
                        fail(3, "Matrix table end precedes begin")
                    if matrix_width is None:
                        fail(3, "Matrix table must contain its complete unique GEO sample header")
                    opened = False
                    tables += 1
                elif opened:
                    row = next(csv.reader([block.decode("latin1")], delimiter="\t", strict=True))
                    if matrix_width is None:
                        if len(row) < 2 or row[0] != "ID_REF" or len(set(row[1:])) != len(row[1:]) or not all(re.fullmatch(r"GSM[0-9]+", sample) for sample in row[1:]):
                            fail(3, "Matrix table requires a complete unique GEO sample header")
                        if table_samples is not None:
                            if row[1:] != table_samples:
                                fail(3, "Matrix header and sample metadata identities/order differ")
                            metadata_bound_tables += 1
                        matrix_width = len(row)
                    elif len(row) != matrix_width:
                        fail(3, "Matrix row width differs from its sample header")
            elif MODE == "soft":
                line = block.decode("latin1").rstrip("\r\n")
                if line.startswith("^"):
                    entity = re.fullmatch(r"\^(DATABASE|SERIES|SAMPLE|PLATFORM|SUBSET) = (.+)", line)
                    if not entity or soft_table is not None:
                        fail(3, "Malformed SOFT entity or unclosed table")
                    soft_entities.add(entity.group(1))
                    if entity.group(1) == "SERIES":
                        series.append(entity.group(2))
                elif re.fullmatch(r"![A-Za-z]+_table_begin", line):
                    if soft_table is not None:
                        fail(3, "Nested SOFT table")
                    soft_table = line[:-len("begin")].lower()
                elif re.fullmatch(r"![A-Za-z]+_table_end", line):
                    if soft_table != line[:-len("end")].lower():
                        fail(3, "SOFT table end differs from begin")
                    soft_table = None
                elif line and not line.startswith(("!", "#")) and soft_table is None:
                    fail(3, "Unexpected non-SOFT text outside a data table")
    if expanded == 0:
        fail(3, "Empty expanded gzip payload")
    if MODE in {"matrix", "soft"} and (not series or set(series) != {ACCESSION}):
        fail(3, "GEO payload series identity does not match requested accession")
    if MODE == "matrix" and (opened or tables == 0):
        fail(3, "Matrix table markers are missing or incomplete")
    if MODE == "matrix" and pending_samples is not None:
        fail(3, "Sample metadata has no corresponding complete matrix table")
    PROVENANCE.update({"gzip_crc_checked": "true", "uncompressed_bytes": expanded})
    if MODE == "soft":
        if soft_table is not None or not {"SERIES", "SAMPLE"} <= soft_entities:
            fail(3, "SOFT family must contain series/sample records and closed tables")
        PROVENANCE["source_format"] = "GZIP_SOFT_TEXT_NOT_TAR_LEGACY_OUTPUT_BASENAME"
    if MODE == "matrix":
        PROVENANCE["validated_matrix_tables"] = tables
        PROVENANCE["sample_metadata_bound_tables"] = metadata_bound_tables
        PROVENANCE["tables_without_sample_metadata"] = tables - metadata_bound_tables


def convert_runinfo(source, target):
    csv.field_size_limit(64 * 1024 * 1024)
    requested = PROVENANCE["resolved_sra_accession"]
    ids = set()
    with io.TextIOWrapper(open_payload_file(source), encoding="utf-8-sig", newline="") as handle, create_owned_file(target, "x") as output:
        reader = csv.reader(handle, strict=True)
        columns = next(reader, [])
        if len(set(columns)) != len(columns) or not {"Run", "Experiment", "SRAStudy", "Sample", "LibraryName"} <= set(columns):
            fail(3, "Complete unique official RunInfo CSV header required")
        writer = csv.writer(output, delimiter="\t", lineterminator="\n")
        writer.writerow(columns)
        lookup = columns.index({"SRR": "Run", "SRX": "Experiment", "SRP": "SRAStudy"}[requested[:3]])
        for row in reader:
            if len(row) != len(columns) or any("\x00" in value for value in row):
                fail(3, "RunInfo row width/NUL content invalid; no truncation or padding")
            run = row[columns.index("Run")]
            if not re.fullmatch(r"(?:SRR|ERR|DRR)[0-9]+", run) or run in ids or row[lookup] != requested:
                fail(3, "RunInfo has duplicate/invalid runs or query identity mismatch")
            ids.add(run)
            writer.writerow(row)
        if not ids:
            fail(3, "RunInfo contains no runs")
    PROVENANCE.update({"source_format": "OFFICIAL_SRA_BACKEND_RUNINFO_CSV", "output_format": "LOSSLESS_TSV_STRINGS",
                       "runinfo_rows": len(ids), "runinfo_columns": len(columns), "clinical_donor_qualification": "NOT_INFERRED"})


# NCBI HTTPS 目录是 `<pre>` 行式列表：每行一个条目，
# `<a href=名字>名字</a>  日期 时间  大小`；大小是人类标注（1.2T / 99M /
# 26K / 1.4K），目录项为 `-` 且 href 以 / 结尾。
# href 值容忍双引号/单引号/无引号三种写法（_unquote 剥离）；
# 锚点对照集合则由标准库 HTML 解析器提取，杜绝引号风格的共同盲区。
LISTING_ROW = re.compile(
    r'^<a href=("([^"]+)"|\'([^\']+)\'|([^\s>]+))>'
    r'[^<]*</a>\s+'
    r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s+'
    r'(-|[0-9][0-9.,]*[KMGT]?)\s*$'
)
SIZE_MULTIPLIERS = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


class _AnchorCollector(HTMLParser):
    """收集全部 <a href=…> 的 href 值。标准库解析器天然兼容
    单引号/双引号/无引号属性与实体编码，正则的引号盲区不复存在。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value is not None:
                self.hrefs.append(value)


def parse_size(token):
    if token == "-":
        return 0
    multiplier = SIZE_MULTIPLIERS.get(token[-1].upper())
    if multiplier:
        return int(float(token[:-1]) * multiplier)
    return int(token.replace(",", ""))


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def file_anchors(html):
    """页面中所有『裸文件名』锚点（不含目录/父目录/查询串）——
    行解析结果的完整性对照集合：每一个都必须被解析成清单条目。"""
    collector = _AnchorCollector()
    collector.feed(html)
    collector.close()
    return {
        href
        for href in collector.hrefs
        if "/" not in href and not href.startswith("?") and href != ".."
    }


def parse_listing(html):
    """解析目录页 → (rows, missing)。
    rows = [(filename, approx_size_bytes, last_modified)]，已去重、未排序；
    missing = 存在锚点却未被行解析覆盖的文件名（页面格式局部漂移）。"""
    rows = []
    seen = set()
    for line in html.splitlines():
        row = LISTING_ROW.match(line.strip())
        if row is None:
            continue
        href, modified, size_token = (
            _unquote(row.group(1)),
            row.group(5),
            row.group(6),
        )
        if href.endswith("/") or href in seen:
            continue
        seen.add(href)
        rows.append((href, parse_size(size_token), modified))
    return rows, file_anchors(html) - seen


def fetch_listing(url):
    """拉目录 HTML。404 → (None, 404)：该系列无 suppl 目录，合法空态。"""
    import requests  # lazy: keep module importable stdlib-only (see top note)

    last_error = None
    for attempt in range(1, RETRIES + 1):
        try:
            with requests.get(url, timeout=TIMEOUT, headers=HEADERS) as response:
                if response.status_code == 404:
                    return None, 404
                response.raise_for_status()
                return response.text, response.status_code
        except Exception as error:  # noqa: BLE001 - 全部网络类异常统一重试
            last_error = error
            time.sleep(2 ** attempt)
    fail(1, f"listing failed after {RETRIES} attempts: {last_error}")


def run_list_mode():
    if ownership_key(OUT_LOG) not in OWNED_FILES:
        with create_owned_file(OUT_LOG, "x"):
            pass
    url = build_url()
    html, status = fetch_listing(url)
    if html is None:
        rows = []
        listing_note = f"{status} (no suppl directory)"
    else:
        rows, missing = parse_listing(html)
        # 完整性闸门：一条条目都没解析出（整页漂移），或页面锚点比解析
        # 结果多（局部漂移会静默漏文件），都拒绝输出清单。
        if not rows or missing:
            detail = f"; unparsed anchors: {sorted(missing)}" if missing else ""
            fail(
                3,
                f"suppl listing incomplete: parsed {len(rows)} entries{detail} "
                "(NCBI listing format may have changed); refusing to emit a manifest",
            )
        rows.sort()
        listing_note = str(status)

    with create_owned_file(OUT_FILE, "x") as manifest:
        manifest.write("filename\tapprox_size_bytes\tlast_modified\n")
        for href, approx_size, modified in rows:
            manifest.write(f"{href}\t{approx_size}\t{modified}\n")

    with open_owned_file(OUT_LOG, "w") as log:
        log.write(
            "\n".join(
                [
                    f"mode\t{MODE}",
                    f"accession\t{ACCESSION}",
                    f"url\t{url}",
                    f"listing_status\t{listing_note}",
                    f"files\t{len(rows)}",
                    f"manifest_sha256\t{hashlib.sha256(open(OUT_FILE, 'rb').read()).hexdigest()}",
                    f"completed\t{time.strftime('%Y-%m-%dT%H:%M:%S%z')}",
                ]
            )
            + "\n"
        )


def main():
    close_owned_files()
    payload, log = Path(OUT_FILE), Path(OUT_LOG)
    partial = payload.with_name(payload.name + ".source.partial")
    converted = payload.with_name(payload.name + ".converted.partial")
    relation = payload.with_name(payload.name + ".relation.partial")
    paths = [payload, log, partial, converted, relation]
    if len({path.resolve() for path in paths}) != len(paths) or any(os.path.lexists(path) for path in paths):
        fail(2, "Refusing to overwrite prior output/log/partial paths or aliased outputs")
    with create_owned_file(log, "x"):
        pass
    published = False
    try:
        if MODE == "list":
            run_list_mode()
            return
        url = build_url()
        size, digest, status = download(url, partial)
        require_owned_file(partial)
        PROVENANCE.update({"url": url, "http_status": status, "raw_source_bytes": size, "raw_source_sha256": digest})
        validate_payload(partial)
        result = partial
        if MODE == "runinfo":
            convert_runinfo(partial, converted)
            result = converted
        checksum = hashlib.sha256()
        with open_owned_file(result, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                checksum.update(block)
        PROVENANCE.update({"bytes": result.stat().st_size, "sha256": checksum.hexdigest(), "status": "COMPLETE"})
        require_owned_file(log)
        require_owned_file(result)
        os.link(result, payload, follow_symlinks=False)
        OWNED_FILES[ownership_key(payload)] = OWNED_FILES[ownership_key(result)]
        published = True
        OWNED_DESCRIPTORS[ownership_key(payload)] = os.dup(OWNED_DESCRIPTORS[ownership_key(result)])
        require_owned_file(payload)
    except BaseException as error:
        if published or MODE == "list":
            remove_owned_file(payload)
        PROVENANCE.update({"status": "FAILED", "error": str(error), "error_type": type(error).__name__})
        raise
    finally:
        try:
            for temporary in [partial, converted, relation]:
                remove_owned_file(temporary)
            if MODE != "list" or PROVENANCE.get("status") == "FAILED":
                with open_owned_file(log, "w") as handle:
                    writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
                    writer.writerows({"mode": MODE, "accession": ACCESSION, "suppl_file": SUPPL_FILE,
                                      **PROVENANCE, "http_attempts": json.dumps(ATTEMPTS),
                                      "completed": time.strftime('%Y-%m-%dT%H:%M:%S%z')}.items())
        except BaseException:
            if published or MODE == "list":
                remove_owned_file(payload)
            raise
        finally:
            close_owned_files()


if __name__ == "__main__":
    try:
        main()
    except FetchError as error:
        print(str(error), file=sys.stderr)
        sys.exit(error.code)
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(3)
