"""Shared runner shim for the single-cell H5AD workflow plugin nodes.

The digest-pinned image carries the tested workflow runner at
/opt/autonomics/workflow.py. This shim rebuilds the legacy params.json
payload from the SC_P_ environment variables declared by manifest.toml
and then hands control to the baked runner, so the Python implementation
executed in the container is the byte-identical one the image ships.

Each SC_P_ variable is named SC_P_<KIND>_<param_name>: KIND is one of
INT, NUM, BOOL, LST, JSON or STR, and the remainder is the params.json
key. An empty value means the parameter was left unset, so the key is
omitted and the workflow applies its own default.
"""

import json
import os
import runpy

PARAMS_PATH = os.environ.get(
    "AUTONOMICS_SINGLE_CELL_PARAMS", "/work/.autonomics/files/params.json"
)

# The CellTypist node has no second input port in the manifest DSL, so the
# published catalog model is injected as the legacy MODEL_INPUT path unless
# the runtime staged a model file already.
MODEL_DIR = os.environ.get("SC_MODEL_DIR", "")
if MODEL_DIR and not os.environ.get("AUTONOMICS_INPUT1"):
    model_file = os.environ.get("SC_MODEL_FILE", "")
    os.environ["AUTONOMICS_INPUT1"] = os.path.join(MODEL_DIR, model_file)


def collect_params():
    params = {}
    for name, value in sorted(os.environ.items()):
        if not name.startswith("SC_P_"):
            continue
        kind, _, key = name[5:].partition("_")
        if value == "":
            continue
        key = key.lower()
        if kind == "INT":
            params[key] = int(value)
        elif kind == "NUM":
            params[key] = float(value)
        elif kind == "BOOL":
            params[key] = value == "true"
        elif kind == "LST":
            params[key] = value.split()
        elif kind == "JSON":
            params[key] = json.loads(value)
        else:
            params[key] = value
    return params


params = collect_params()
os.makedirs(os.path.dirname(PARAMS_PATH), exist_ok=True)
with open(PARAMS_PATH, "w", encoding="utf-8") as handle:
    json.dump(params, handle)

runpy.run_path("/opt/autonomics/workflow.py", run_name="__main__")
