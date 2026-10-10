"""Python2 host transport for the unchanged frozen MTAG CLI and artifact guard."""

import hashlib
import imp
import json
import os
import subprocess
import sys


arguments = sys.argv[1:]
with open(arguments[0]) as handle:
    spec = json.load(handle)
guard = imp.load_source("mtag_artifact_guard", spec["guard_script"])
versions = guard.runtime_identity(spec["source_root"])
directory = os.path.dirname(arguments[0])
inputs = [os.path.join(directory, "input0.tsv"), os.path.join(directory, "input1.tsv")]
prefix = os.path.join(directory, "official", "mtag")
os.mkdir(os.path.dirname(prefix))
parameters = dict(spec["parameters"])
parameters["time_limit_hours"] = str(parameters["time_limit_hours"])
parameters["tol"] = str(parameters["tol"])
command = guard.command(inputs, prefix, spec["panel_root"].rstrip("/") + "/", parameters)
tokens = [sys.executable, os.path.join(directory, "trace.py"), os.path.join(spec["source_root"], "mtag.py")] + command[1:]
code = subprocess.call(tokens, env=dict(os.environ, MTAG_NATIVE_CALL_TRACE=os.path.join(directory, "call-trace.json")))
record = guard.collect(prefix, parameters, code)
outputs = [os.path.join(directory, name) for name in ("results.tar", "official.log", "index.tsv", "audit.json")]
guard.package_products(record, outputs, {"official_command": tokens, "parameters": parameters,
    "runtime_package_versions": versions, "input_sha256": [guard.digest(filename) for filename in inputs],
    "qualification": spec["qualification"], "host_DAG_execution": True,
    "container_or_resident_deployment": False, "synthetic_qualification_declared": True,
    "catalog_panel_certified": False, "method_functions_changed": False})
bindings = []
for name, module in sorted(sys.modules.items()):
    filename = getattr(module, "__file__", None)
    if filename and os.path.isfile(filename):
        bindings.append(dict(module=name, path=os.path.realpath(filename), sha256=guard.digest(filename)))
with open(os.path.join(directory, "worker-runtime.json"), "w") as handle:
    json.dump(dict(loaded_module_bindings=bindings, runtime_package_versions=versions,
        python=sys.version, statistical_functions_changed=False), handle, indent=2)
    handle.write("\n")
