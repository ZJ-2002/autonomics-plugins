"""Compare every declared LDSC panel file with the author's versioned deposit."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
from urllib.request import Request, urlopen

SOURCES = {
    "metadata": ("0b57675010964667859028efd5ff27bd", "f311bb8cb7c0cb7bc7d699a9a4191f39bd62243ebd24e61afcaff73ea1c50b10", "ldsc-author-reference-metadata"),
    "payload": ("66c189d36d4144fe805ec617b8314244", "b1034169ef0230f4c7ca66da2abe55e2611113a6617ff11ea2d8ecd24a65b6c2", "ldsc-declared-panel-payloads"),
    "cached_archive": ("2b38d75f6c9948288d2912797eb1a935", "94370b78a1a7d582a07da5dce4a2a3c491809a27d75baee3f5a89f1973d20ead", "ldsc-author-reference-equality"),
}
BINDINGS = {"1000G_Phase3_ldscores.tgz": "ref_ld", "1000G_Phase3_weights_hm3_no_MHC.tgz": "w_ld"}


def digest(path, algorithm="sha256"):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def reference(role):
    identity, expected, packet = SOURCES[role]
    artifacts = Path.home()/".local/state/autonomics/validation-archives"/identity/"artifacts"
    if digest(artifacts/"MANIFEST.json") != expected:
        raise RuntimeError("Exact complete sealed reference required")
    manifest = json.loads((artifacts/"MANIFEST.json").read_text())
    actual = {path.relative_to(artifacts).as_posix() for path in artifacts.rglob("*") if path.is_file() and path.name != "MANIFEST.json"}
    if actual != set(manifest["files"]):
        raise RuntimeError("Exact reference membership required")
    for name, record in manifest["files"].items():
        path = artifacts/name
        if path.is_symlink() or path.stat().st_size != record["bytes"] or digest(path) != record["sha256"]:
            raise RuntimeError("Sealed reference content differs")
    return artifacts/"permanent"/packet


def compare_archive(path, expected, metadata_prefix=None, metadata_output=None):
    found = set()
    records = []
    additional = []
    seen_names = set()
    with tarfile.open(path,"r:gz") as archive:
        for member in archive:
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or member.issym() or member.islnk():
                raise RuntimeError("Unsafe author archive member")
            if member.isdir():
                continue
            name = relative.name
            if name in seen_names:
                raise RuntimeError("Duplicate author member basename")
            seen_names.add(name)
            if name not in expected and metadata_prefix is not None:
                pattern=re.escape(metadata_prefix)+r"\.([1-9]|1[0-9]|2[0-2])\.(log|l2\.M|l2\.M_5_50)"
                if not member.isfile() or re.fullmatch(pattern,name) is None or not 0 < member.size <= 32768:
                    raise RuntimeError("Unreviewed additional author archive member: "+member.name)
                source=archive.extractfile(member)
                if source is None:
                    raise RuntimeError("Author generation metadata missing")
                with source:
                    content=source.read(32769)
                if len(content)!=member.size:
                    raise RuntimeError("Author generation metadata size differs")
                content.decode('ascii')
                if metadata_output is None:
                    raise RuntimeError("Additional author metadata requires permanent preservation")
                with (metadata_output/name).open('xb') as stream:
                    stream.write(content)
                additional.append(dict(author_member=member.name,size=member.size,sha256='sha256:'+hashlib.sha256(content).hexdigest(),
                                       role='AUTHOR_GENERATION_LOG_OR_WEIGHT_UNUSED_M_COUNT_NOT_FILTERED_METHOD_DATA'))
                continue
            if not member.isfile() or name not in expected or name in found or member.size != expected[name]["size"]:
                raise RuntimeError("Unexpected, duplicate or resized author data member: "+member.name)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError("Author member could not be read")
            with source:
                actual = "sha256:"+hashlib.file_digest(source,"sha256").hexdigest()
            if actual != expected[name]["sha256"]:
                raise RuntimeError("Author distribution differs from catalog object: "+name)
            found.add(name)
            records.append(dict(author_member=member.name,catalog_path=name,size=member.size,sha256=actual))
    if found != set(expected):
        raise RuntimeError("Author distribution lacks declared data members")
    return dict(data=records,additional_preserved=additional)


def main():
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Managed validation required")
    metadata = json.loads((reference("metadata")/"verification.json").read_text())
    if (metadata["record_id"] != 7768714 or metadata["doi"] != "10.5281/zenodo.7768714"
            or not any(creator.get("name")=="Steven Gazal" and creator.get("orcid")=="0000-0003-4510-5730" for creator in metadata["creators"])
            or {item["key"] for item in metadata["files"]} != set(BINDINGS)):
        raise RuntimeError("Exact named author deposit required")
    payload = reference("payload")
    cache = reference("cached_archive")
    output = Path(permanent)/"ldsc-author-reference-equality"
    output.mkdir()
    shutil.copyfile(Path(__file__),output/"driver.py")
    results = []
    for record in metadata["files"]:
        name = record["key"]
        url = "https://zenodo.org/api/records/7768714/files/"+name+"/content"
        if record["links"]["self"] != url or type(record["size"]) is not int or not 0 < record["size"] <= 32*1024**2:
            raise RuntimeError("Bounded exact author object required")
        reused = (cache/name).is_file()
        archive = cache/name if reused else output/name
        if not reused:
            with urlopen(Request(url,headers={"User-Agent":"autonomics-reference-origin-proof/1"}),timeout=45) as response, archive.open("xb") as stream:
                remaining = record["size"]
                while remaining:
                    block = response.read(min(remaining,1024**2))
                    if not block:
                        raise RuntimeError("Author object was truncated")
                    stream.write(block)
                    remaining -= len(block)
                if response.read(1):
                    raise RuntimeError("Author object exceeds declared size")
        if archive.stat().st_size != record["size"] or "md5:"+digest(archive,"md5") != record["checksum"]:
            raise RuntimeError("Author published archive checksum differs")
        manifest = json.loads((payload/BINDINGS[name]/"manifest.json").read_text())
        metadata_output=output/(BINDINGS[name]+"-author-generation-metadata")
        metadata_output.mkdir()
        prefix="LDscore" if BINDINGS[name]=="ref_ld" else "weights.hm3_noMHC"
        files = compare_archive(archive,{item["path"]:item for item in manifest["files"]},prefix,metadata_output)
        results.append(dict(author_archive=name,doi=metadata["doi"],author_published_checksum=record["checksum"],
                            archive_sha256=digest(archive),archive_bytes=archive.stat().st_size,catalog_digest=manifest["digest"],
                            members=files['data'],additional_author_metadata_preserved=files['additional_preserved'],
                            reused_exact_sealed_download_from_failed_session=reused))
    report = dict(status="ALL_88_DECLARED_PANEL_FILES_BYTE_IDENTICAL_TO_VERSIONED_AUTHOR_DEPOSIT",author="Steven Gazal",
                  author_orcid="0000-0003-4510-5730",author_record=7768714,archives=results,
                  compressed_member_bytes_compared=True,no_tar_extraction=True,production_cache_or_frozen_binding_changed=False,
                  study_panel_eligibility_granted=False,current_DAG_or_daemon_qualified=False,g0_granted=False)
    with (output/"verification.json").open("x") as stream:
        json.dump(report,stream,indent=2)
    print(json.dumps(dict(archives=len(results),members=sum(len(item["members"]) for item in results),g0_granted=False)))


if __name__ == "__main__":
    main()
