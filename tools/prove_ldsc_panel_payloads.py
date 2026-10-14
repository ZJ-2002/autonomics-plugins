"""Verify exact declared catalog payloads without altering production panel bindings."""

import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = "9e1ee551780e4c93856aab15b1aaac49"
SEAL = "657ffef0cf489307e01d92f7cfe07551176f8b840391cea7536fe33dea86b741"
REPOSITORIES = {
    "wjixiang/catalog-ldsc-ref-ld-1000g-eur-basic": ("ref_ld", "ldsc_ref_ld_chr"),
    "wjixiang/catalog-ldsc-w-ld-1000g-eur-hm3-no-mhc": ("w_ld", "ldsc_w_ld_chr"),
}


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_manifest(value, repository, expected_digest):
    binding, kind = REPOSITORIES[repository]
    if (set(value) != {"schema_version", "repo", "version", "kind", "metadata", "files", "payload", "digest"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 2
            or value["repo"] != repository or value["kind"] != kind or value["version"] != "v1"
            or value["payload"] != {} or value["digest"] != expected_digest
            or value["metadata"] != {"genome_build": "GRCh37", "population": "EUR"}):
        raise RuntimeError("Exact declared catalog schema and identity required")
    expected = ({f"LDscore.{chromosome}.l2.{suffix}" for chromosome in range(1, 23) for suffix in ["M", "M_5_50", "ldscore.gz"]}
                if binding == "ref_ld" else {f"weights.hm3_noMHC.{chromosome}.l2.ldscore.gz" for chromosome in range(1, 23)})
    files = value["files"]
    if not isinstance(files, list) or len(files) != len(expected) or {item["path"] for item in files} != expected:
        raise RuntimeError("Exact 22-chromosome file inventory required")
    for item in files:
        if (set(item) != {"path", "size", "sha256"} or type(item["size"]) is not int
                or not 0 < item["size"] <= 4*1024**2 or not re.fullmatch(r"sha256:[0-9a-f]{64}", item["sha256"])):
            raise RuntimeError("Bounded safe file identity required")
    if sum(item["size"] for item in files) > 32*1024**2:
        raise RuntimeError("Declared package exceeds admitted payload budget")
    unsigned = {key: value[key] for key in ["schema_version", "repo", "version", "kind", "metadata", "files", "payload"]}
    unsigned["metadata"] = dict(sorted(value["metadata"].items()))
    unsigned["files"] = [{key: item[key] for key in ["path", "size", "sha256"]} for item in files]
    actual = "sha256:"+hashlib.sha256(json.dumps(unsigned, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if actual != expected_digest:
        raise RuntimeError("Canonical unsigned catalog digest differs")
    return files


def main():
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Managed validation required")
    artifacts = Path.home()/".local/state/autonomics/validation-archives"/ARCHIVE/"artifacts"
    if digest(artifacts/"MANIFEST.json") != SEAL:
        raise RuntimeError("Exact sealed immutable metadata required")
    manifest = json.loads((artifacts/"MANIFEST.json").read_text())
    for name, identity in manifest["files"].items():
        path = artifacts/name
        if path.is_symlink() or path.stat().st_size != identity["bytes"] or digest(path) != identity["sha256"]:
            raise RuntimeError("Metadata source identity changed")
    source = artifacts/"permanent/ldsc-declared-panel-manifests"
    metadata = json.loads((source/"verification.json").read_text())["panels"]
    if len(metadata) != 2 or {item["repository"] for item in metadata} != set(REPOSITORIES):
        raise RuntimeError("Exact two declared repositories required")
    output = Path(permanent)/"ldsc-declared-panel-payloads"
    output.mkdir(mode=0o700)
    shutil.copyfile(Path(__file__), output/"driver.py")
    results = []
    for record in metadata:
        repository = record["repository"]
        revision = record["revision"]
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise RuntimeError("Exact immutable repository revision required")
        name = repository.split("/")[1]+".manifest.json"
        package = json.loads((source/name).read_text())
        files = validate_manifest(package, repository, record["catalog_digest"])
        expected_key = "v1/sha256-"+record["catalog_digest"].removeprefix("sha256:")+"/manifest.json"
        if record["manifest_key"] != expected_key or digest(source/name) != record["manifest_sha256"]:
            raise RuntimeError("Manifest object path or bytes differ")
        destination = output/REPOSITORIES[repository][0]
        destination.mkdir()
        shutil.copyfile(source/name, destination/"manifest.json")
        def download(item):
            path = destination/item["path"]
            url = "https://huggingface.co/datasets/"+repository+"/resolve/"+revision+"/"+expected_key.removesuffix("manifest.json")+item["path"]
            request = Request(url, headers={"User-Agent": "autonomics-scoped-resource-audit/1"})
            with urlopen(request, timeout=30) as response, path.open("xb") as stream:
                remaining = item["size"]
                while remaining:
                    block = response.read(min(remaining, 1024**2))
                    if not block:
                        raise RuntimeError("Declared object was truncated")
                    stream.write(block)
                    remaining -= len(block)
                if response.read(1):
                    raise RuntimeError("Declared object exceeds admitted size")
            if digest(path) != item["sha256"].removeprefix("sha256:"):
                raise RuntimeError("Downloaded catalog payload hash differs")
            return dict(path=item["path"], size=path.stat().st_size, sha256="sha256:"+digest(path))
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            verified = list(executor.map(download, files))
        if verified != files:
            raise RuntimeError("Complete ordered payload inventory differs")
        results.append(dict(repository=repository, revision=revision, catalog_digest=record["catalog_digest"],
                            manifest_sha256=digest(destination/"manifest.json"), files=len(files), bytes=sum(item["size"] for item in files),
                            every_payload_hash_verified=True, author_distribution_origin_independently_proven=False))
    with (output/"verification.json").open("x") as stream:
        json.dump(dict(status="DECLARED_CATALOG_PAYLOADS_CONTENT_VERIFIED_NOT_SCIENTIFICALLY_QUALIFIED", panels=results,
                       production_cache_or_frozen_binding_changed=False, real_data_DAG_verified=False, g0_granted=False), stream, indent=2)
    print(json.dumps(results))


if __name__ == "__main__":
    main()
