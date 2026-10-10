import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys


directory = Path(__file__).resolve().parent
request = json.loads((directory / "request.json").read_text())
definition = importlib.util.spec_from_file_location("frozen_tenx_guard", directory / "guard.py")
guard = importlib.util.module_from_spec(definition)
sys.modules[definition.name] = guard
definition.loader.exec_module(guard)
upstream = guard.load_upstream(request["upstream_script"])
settings = request["parameters"]
for port, name in enumerate(["input0.mtx.gz" if settings["matrix_gzip"] else "input0.mtx",
                             "input1.tsv", "input2.tsv", "input3.tsv"]):
    os.environ["AUTONOMICS_INPUT" + str(port)] = str(directory / name)
os.environ.update({"AUTONOMICS_OUTPUT0": str(directory / "preprocess_report.json"),
                   "AUTONOMICS_OUTPUT1": str(directory / "preprocessed.h5ad"),
                   "AUTONOMICS_SINGLE_CELL_OPERATION": settings["operation"],
                   "AUTONOMICS_SINGLE_CELL_MIN_GENES": str(settings["min_genes"]),
                   "AUTONOMICS_SINGLE_CELL_MIN_CELLS": str(settings["min_cells"]),
                   "AUTONOMICS_SINGLE_CELL_NORMALIZE_TOTAL": str(settings["normalize_total"]).lower(),
                   "AUTONOMICS_SINGLE_CELL_METADATA_SEP": settings["metadata_separator"]})
guard.run(upstream)
bindings = {}
for module in list(sys.modules.values()):
    filename = getattr(module, "__file__", None)
    if filename and Path(filename).is_file():
        filename = Path(filename).resolve()
        bindings[str(filename)] = hashlib.sha256(filename.read_bytes()).hexdigest()
record = {"loaded_module_bindings": [{"path": filename, "sha256": checksum}
                                     for filename, checksum in sorted(bindings.items())],
          "python": sys.version, "host_not_container": True,
          "full_singlecell_pipeline_certified": False, "g0_granted": False}
(directory / "worker-runtime.json").write_text(json.dumps(record, indent=2) + "\n")
