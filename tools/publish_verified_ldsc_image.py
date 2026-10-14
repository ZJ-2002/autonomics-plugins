"""Publish an already cached author runtime; never build or upload study payloads."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "localhost/cachexia-ldsc-official@sha256:febf11d5ec554b53e2e022f26e55033233cb4692f40eb7d81cdaa7fe11d70999"
CONFIG = "sha256:a8142f85b617432173555bc0c5fde94517dd627cfb548576b3eacd061fd40e85"
REPOSITORY = "zj-2002/ldsc"
TAG = "pristine-official-6c673952"
MEDIA = "application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json"
OLD_PUBLIC_DIGEST = "sha256:93b2542386a08df10402045b8036ff4da6733bea65324d50e326d035579d247a"


def write(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def anonymous_token():
    url = "https://ghcr.io/token?service=ghcr.io&scope=repository:" + REPOSITORY + ":pull"
    with urlopen(Request(url), timeout=60) as response:
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            raise RuntimeError("Bounded anonymous registry token unavailable")
    value = json.loads(raw)
    token = value.get("token") or value.get("access_token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("Anonymous registry token missing")
    return token


def manifest(reference, token):
    url = "https://ghcr.io/v2/" + REPOSITORY + "/manifests/" + reference
    with urlopen(Request(url, headers={"Authorization": "Bearer " + token, "Accept": MEDIA}), timeout=60) as response:
        raw = response.read(2 * 1024**2 + 1)
        if response.status != 200 or response.url != url or len(raw) > 2 * 1024**2:
            raise RuntimeError("Exact bounded public manifest unavailable")
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if response.headers.get("Docker-Content-Digest") != digest:
            raise RuntimeError("Registry manifest body/header identity differs")
    return json.loads(raw), digest, raw


def check_manifest(value):
    if (value.get("schemaVersion") != 2 or value.get("config", {}).get("digest") != CONFIG
            or not isinstance(value.get("layers"), list) or not 1 <= len(value["layers"]) <= 50):
        raise RuntimeError("Exact existing author image configuration and bounded layers required")
    for item in [value["config"], *value["layers"]]:
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", item.get("digest", "")) or type(item.get("size")) is not int or item["size"] <= 0:
            raise RuntimeError("Exact registry blob digest/size required")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    arguments = parser.parse_args()
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Use the managed validation session")
    output = Path(permanent) / "ldsc-pristine-registry"
    output.mkdir(mode=0o700)
    (output / "driver.py").write_bytes(Path(__file__).read_bytes())
    report = dict(source=SOURCE, target="ghcr.io/"+REPOSITORY+":"+TAG, author_config=CONFIG,
                  no_environment_clone=True, no_image_build=True, scientific_executed=False,
                  credentials_published=False, formal_authorized=False, g0_granted=False)
    try:
        inspect = subprocess.run(["podman", "image", "inspect", SOURCE], capture_output=True, check=True)
        identity = json.loads(inspect.stdout)[0]
        if "sha256:" + identity["Id"].removeprefix("sha256:") != CONFIG or identity["Digest"] != SOURCE.split("@")[1]:
            raise RuntimeError("Cached author image identity differs")
        expected = json.loads((ROOT / "evidence/ldsc-pristine-full-precision-v1-20261012.json").read_text())["runtime_identity"]
        runtime_code = "import runpy,json; module=runpy.run_path('/work/precision.py'); print(json.dumps(module['runtime_identity'](),sort_keys=True))"
        probe = subprocess.run(["podman", "run", "--rm", "--pull=never", "--network=none", "--read-only", "--memory=256m",
                                "--tmpfs=/tmp:rw,size=32m", "-v", str(ROOT / "plugins/ldsc-precision/scripts/precision.py")+":/work/precision.py:ro",
                                "--entrypoint=python", SOURCE, "-c", runtime_code], capture_output=True, timeout=60)
        if probe.returncode or json.loads(probe.stdout) != expected:
            raise RuntimeError("Complete measured author source/package identity differs")
        write(output / "author-runtime.json", expected)
        token = anonymous_token()
        manifest(OLD_PUBLIC_DIGEST, token)
        report["existing_package_anonymously_public_before_upload"] = True
        existing = None
        try:
            existing, existing_digest, existing_raw = manifest(TAG, token)
        except HTTPError as error:
            if error.code != 404:
                raise RuntimeError("Existing tag accessibility unresolved; do not upload") from None
        if existing is not None:
            check_manifest(existing)
            published_digest = existing_digest
            report["existing_exact_tag_reused"] = True
        else:
            if not arguments.publish:
                raise RuntimeError("Author identity audited; explicit --publish required for registry write")
            login = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, check=True)
            if login.stdout.strip().lower() != b"zj-2002":
                raise RuntimeError("Publication requires the user's own GitHub namespace")
            credential = subprocess.run(["gh", "auth", "token"], capture_output=True, check=True).stdout.strip()
            auth = Path(os.environ["TMPDIR"]) / "registry-auth.json"
            descriptor = os.open(auth, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as handle:
                handle.write('{"auths":{}}')
            authenticated = subprocess.run(["podman", "login", "--authfile", str(auth), "--username", "ZJ-2002",
                                            "--password-stdin", "ghcr.io"], input=credential, capture_output=True, timeout=60)
            del credential
            if authenticated.returncode:
                raise RuntimeError("Registry authentication failed; credentials not logged")
            digest_file = Path(os.environ["TMPDIR"]) / "pushed-digest.txt"
            command = ["podman", "push", "--retry=0", "--authfile", str(auth), "--format=oci", "--digestfile", str(digest_file),
                       SOURCE, "docker://ghcr.io/"+REPOSITORY+":"+TAG]
            with (output / "push.stdout").open("wb") as stdout, (output / "push.stderr").open("wb") as stderr:
                pushed = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=1800)
            if pushed.returncode:
                raise RuntimeError("Author image upload failed; no alternate image chosen")
            published_digest = digest_file.read_text().strip()
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", published_digest):
                raise RuntimeError("Actual pushed image digest missing")
            report["existing_exact_tag_reused"] = False
        public, actual_digest, raw = manifest(published_digest, anonymous_token())
        check_manifest(public)
        if actual_digest != published_digest:
            raise RuntimeError("Published immutable digest differs")
        (output / "public-manifest.json").write_bytes(raw)
        report.update(status="AUTHOR_RUNTIME_PUBLICLY_AVAILABLE_NOT_METHOD_OR_DAG_ACCEPTANCE",
                      immutable_reference="ghcr.io/"+REPOSITORY+"@"+published_digest,
                      config_identity_unchanged=True, layers=len(public["layers"]),
                      full_runtime_identity_rechecked=True, actual_deployment_changed=False)
        write(output / "verification.json", report)
        print(json.dumps(report))
    except Exception as error:
        write(output / "failure.json", dict(error_type=type(error).__name__,
              message=str(error), credentials_published=False, scientific_executed=False, g0_granted=False))
        raise


if __name__ == "__main__":
    main()
