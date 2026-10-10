import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


def prepare(output):
    lock = json.loads((Path(__file__).resolve().parents[1] / "source-lock.json").read_text())
    output.mkdir(parents=True, exist_ok=False)
    checksums = []
    for record in lock["archives"]:
        name = record["archive"]
        if Path(name).name != name or urlparse(record["url"]).scheme != "https" or urlparse(record["url"]).hostname != "bioconductor.org":
            raise ValueError("Invalid locked source location")
        target = output / name
        digest = hashlib.sha256()
        try:
            with urlopen(record["url"], timeout=120) as response, target.open("xb") as handle:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    handle.write(chunk)
            if digest.hexdigest() != record["sha256"]:
                raise ValueError("Official archive hash differs: " + name)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        checksums.append(record["sha256"] + "  " + name)
    (output / "SHA256SUMS").write_text("\n".join(checksums) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output)
