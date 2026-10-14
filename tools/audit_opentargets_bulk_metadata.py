"""Read official release listings/HEADs/sample footers, never full data rows."""

import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import time
import tomllib
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://ftp.ebi.ac.uk/pub/databases/opentargets/platform/26.09/output/"
DATASETS = ["association_overall_direct", "association_by_datasource_direct", "association_by_datatype_direct", "target", "disease"]
LISTING_LIMIT = 2 * 1024**2
FOOTER_LIMIT = 1024**2
READER_IMAGE = "ghcr.io/zj-2002/single-cell-preprocessor@sha256:e2f9fcd5ccf9e97b0f0129466df5abb21ae47ed32f123f6953b79fd83d915e20"


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = []

    def handle_starttag(self, tag, attributes):
        if tag == "a":
            self.values.extend(value for key, value in attributes if key == "href")


def parquet_names(body):
    parser = Links()
    parser.feed(body.decode("utf-8"))
    values = [name for name in parser.values if name.endswith(".parquet")]
    if not values or len(set(values)) != len(values) or any(not re.fullmatch(r"[A-Za-z0-9_.-]+[.]parquet", name) or ".." in name for name in values):
        raise RuntimeError("Nonempty unique literal Parquet file listing required")
    if len(values) > 200:
        raise RuntimeError("Official listing exceeds metadata request budget")
    return sorted(values)


def write(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def head(url):
    time.sleep(2)
    with urlopen(Request(url, method="HEAD"), timeout=60) as response:
        length = response.headers.get("Content-Length", "")
        if response.status != 200 or response.url != url or not length.isdigit() or int(length) < 12:
            raise RuntimeError("Official exact file length unavailable")
        return dict(url=url, status=response.status, bytes=int(length), etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"), accept_ranges=response.headers.get("Accept-Ranges"))


def ranged(url, start, end, identity):
    time.sleep(2)
    with urlopen(Request(url, headers={"Range": f"bytes={start}-{end}", "If-Match": identity["etag"] or "*"}), timeout=60) as response:
        body = response.read(end - start + 2)
        expected = f"bytes {start}-{end}/{identity['bytes']}"
        if (response.status != 206 or response.url != url or response.headers.get("Content-Range") != expected
                or len(body) != end - start + 1 or response.headers.get("ETag") != identity["etag"]):
            raise RuntimeError("Exact bounded range/ETag required; full-file fallback forbidden")
        return body


def footer_length(trailer, total):
    if len(trailer) != 8 or trailer[-4:] != b"PAR1":
        raise RuntimeError("Ordinary Parquet footer magic required")
    length = struct.unpack("<I", trailer[:4])[0]
    if not 0 < length <= FOOTER_LIMIT or length + 12 > total:
        raise RuntimeError("Parquet footer outside declared metadata budget")
    return length


READER = r'''
import json,pathlib,pyarrow,pyarrow.parquet as parquet
root=pathlib.Path("/work")
results=[]
for path in sorted(root.glob("*.footer-only.parquet")):
    metadata=parquet.read_metadata(path)
    schema=metadata.schema.to_arrow_schema()
    results.append(dict(dataset=path.name.removesuffix(".footer-only.parquet"),
        fields=[dict(name=field.name,type=str(field.type),nullable=field.nullable) for field in schema],
        sample_file_rows=metadata.num_rows,sample_file_row_groups=metadata.num_row_groups,
        schema_only_not_data_rows_read=True))
(root/"sample-schemas.json").write_text(json.dumps(dict(pyarrow_version=pyarrow.__version__,samples=results,
    all_partition_schemas_verified=False,complete_membership_verified=False,g0_granted=False),indent=2)+"\n")
'''


def archived_metadata(archive, expected_manifest, output):
    if archive.is_symlink() or not re.fullmatch(r"[0-9a-f]{32}", archive.name):
        raise RuntimeError("Literal sealed session archive required")
    artifacts = archive / "artifacts"
    manifest_path = artifacts / "MANIFEST.json"
    if manifest_path.is_symlink() or manifest_path.stat().st_size > LISTING_LIMIT:
        raise RuntimeError("Sealed metadata manifest exceeds bound or is a symlink")
    manifest_bytes = manifest_path.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != expected_manifest:
        raise RuntimeError("Sealed source manifest differs")
    manifest = json.loads(manifest_bytes)
    session = json.loads((archive / "SESSION.json").read_bytes())
    if (manifest["session"] != archive.name or session["session"] != archive.name
            or session["state"] != "CLEANED" or session["manifest_sha256"] != expected_manifest):
        raise RuntimeError("Source archive lifecycle or identity differs")
    paths = [path for path in artifacts.rglob("*") if path != manifest_path]
    if any(path.is_symlink() for path in paths):
        raise RuntimeError("Sealed metadata may not contain symlinks")
    actual = {path.relative_to(artifacts).as_posix() for path in paths if path.is_file()}
    if (actual != set(manifest["files"]) or len(actual) > 1000
            or any(not path.is_dir() and not path.is_file() for path in paths)):
        raise RuntimeError("Sealed archive membership differs")
    consumed = {}
    total_bytes = 0
    for name, identity in manifest["files"].items():
        path = artifacts / name
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or relative.parts[0] not in {"permanent", "retained"}:
            raise RuntimeError("Sealed archive path classification differs")
        if path.stat().st_size > 16 * 1024**2:
            raise RuntimeError("Metadata archive file exceeds bound")
        with path.open("rb") as handle:
            body = handle.read(16 * 1024**2 + 1)
        total_bytes += len(body)
        if len(body) > 16 * 1024**2 or total_bytes > 32 * 1024**2:
            raise RuntimeError("Metadata archive content exceeds bound")
        if len(body) != identity["bytes"] or hashlib.sha256(body).hexdigest() != identity["sha256"]:
            raise RuntimeError("Sealed archive content differs")
        consumed[name] = body
    source = "permanent/opentargets-bulk-metadata/"
    predeclared = json.loads(consumed[source + "predeclared.json"])
    if predeclared["release"] != "26.09" or predeclared["datasets"] != DATASETS:
        raise RuntimeError("Audited release or dataset scope differs")
    records = []
    for dataset in DATASETS:
        record = json.loads(consumed[source + dataset + ".resource.json"])
        if record["dataset"] != dataset:
            raise RuntimeError("Dataset resource identity differs")
        records.append(record)
        (output / (dataset + ".footer-only.parquet")).write_bytes(
            consumed[source + dataset + ".footer-only.parquet"])
        write(output / (dataset + ".resource.json"), record)
    write(output / "metadata-source.json", dict(session=archive.name, manifest_sha256=expected_manifest,
          source_worker_exit=session["worker_exit_status"], network_requests_repeated=0,
          original_failure_unchanged=True, source_complete=False, g0_granted=False))
    return records


def reader_command(output, image):
    if image != READER_IMAGE:
        raise RuntimeError("Metadata reader image identity differs")
    return ["podman", "run", "--rm", "--pull=never", "--network=none", "--read-only", "--cpus=1", "--memory=256m",
            "--userns=keep-id", f"--user={os.getuid()}:{os.getgid()}",
            "-v", f"{output}:/work:rw", "--entrypoint=python", image, "/work/read-schema.py"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-archive", type=Path)
    parser.add_argument("--manifest-sha256")
    arguments = parser.parse_args()
    if bool(arguments.metadata_archive) != bool(arguments.manifest_sha256):
        parser.error("Archive and independently fixed manifest SHA256 are required together")
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Use research_validation_session.py run")
    output = Path(permanent) / "opentargets-bulk-metadata"
    output.mkdir(mode=0o700)
    (output / "driver.py").write_bytes(Path(__file__).read_bytes())
    write(output / "predeclared.json", dict(release="26.09", datasets=DATASETS,
          full_file_fallback=False, row_data_downloaded=False, retries=0,
          footer_byte_limit=FOOTER_LIMIT, schema_samples_per_dataset=1,
          reuse_sealed_metadata=bool(arguments.metadata_archive),
          study_source_changed=False, scientific_authorized=False, g0_granted=False))
    records = []
    try:
        if arguments.metadata_archive:
            records = archived_metadata(arguments.metadata_archive, arguments.manifest_sha256, output)
        for dataset in ([] if arguments.metadata_archive else DATASETS):
            url = BASE + dataset + "/"
            time.sleep(2)
            with urlopen(Request(url), timeout=60) as response:
                body = response.read(LISTING_LIMIT + 1)
                if response.status != 200 or response.url != url or len(body) > LISTING_LIMIT:
                    raise RuntimeError("Listing bound or source identity mismatch")
            (output / (dataset + ".listing.html")).write_bytes(body)
            files = [head(url + name) for name in parquet_names(body)]
            sample = files[0]
            trailer = ranged(sample["url"], sample["bytes"] - 8, sample["bytes"] - 1, sample)
            length = footer_length(trailer, sample["bytes"])
            footer = ranged(sample["url"], sample["bytes"] - 8 - length, sample["bytes"] - 9, sample)
            magic = ranged(sample["url"], 0, 3, sample)
            if magic != b"PAR1":
                raise RuntimeError("Parquet header magic differs")
            (output / (dataset + ".footer.bin")).write_bytes(footer)
            (output / (dataset + ".footer-only.parquet")).write_bytes(magic + footer + trailer)
            records.append(dict(dataset=dataset, listing_sha256=hashlib.sha256(body).hexdigest(),
                                files=files, exact_compressed_bytes=sum(item["bytes"] for item in files),
                                sampled_footer_bytes=length, sampled_footer_sha256=hashlib.sha256(footer).hexdigest()))
            write(output / (dataset + ".resource.json"), records[-1])
        (output / "read-schema.py").write_text(READER)
        image = tomllib.loads((ROOT / "plugins/single-cell/manifest.toml").read_text())["image"]["reference"]
        command = reader_command(output, image)
        completed = subprocess.run(command, capture_output=True, timeout=60)
        (output / "reader.stdout").write_bytes(completed.stdout)
        (output / "reader.stderr").write_bytes(completed.stderr)
        write(output / "reader-execution.json", dict(image=image, exit=completed.returncode, g0_granted=False))
        if completed.returncode:
            raise RuntimeError("Official PyArrow metadata reader failed")
        write(output / "verification.json", dict(status="RESOURCE_AND_SAMPLED_SCHEMA_AUDITED_NOT_SOURCE_COMPLETE",
              datasets=records, total_compressed_bytes=sum(item["exact_compressed_bytes"] for item in records),
              full_rows_downloaded=False, all_partition_schemas_verified=False,
              complete_membership_verified=False, scientific_authorized=False, g0_granted=False))
        print(json.dumps(dict(files=sum(len(item["files"]) for item in records),
                             total_compressed_bytes=sum(item["exact_compressed_bytes"] for item in records),
                             full_rows_downloaded=False, g0_granted=False)))
    except Exception as error:
        write(output / "failure.json", dict(error_type=type(error).__name__, error=str(error),
              full_rows_downloaded=False, source_qualified=False, g0_granted=False))
        raise


if __name__ == "__main__":
    main()
