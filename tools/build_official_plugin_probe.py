"""Build a reusable file-backed-plugin DAG probe, not a scientific certificate."""

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import build_current_ldsc as builder


def main():
    if any(argument in {'--help','-h'} for argument in sys.argv[1:]):
        print(__doc__)
        builder.main()
        return
    permanent=os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Managed build-profile validation required")
    source=Path(permanent)/"generic-probe-builder-entry.py"
    with source.open("xb") as stream:
        stream.write(Path(__file__).read_bytes())
    builder.EXAMPLE="official_plugin_dag"
    builder.EXAMPLE_PATH="crates/container-plugin/examples/official_plugin_dag.rs"
    builder.main()
    with (Path(permanent)/"generic-builder-module-binding.json").open("x") as stream:
        json.dump(dict(entry_sha256=builder.digest(source),shared_builder_sha256=builder.digest(Path(builder.__file__)),
                       example=builder.EXAMPLE,scientific_authorized=False,g0_granted=False),stream,indent=2)


if __name__ == "__main__":
    main()
