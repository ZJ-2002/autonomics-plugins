"""Python2-compatible MTAG artifact guard; no replacement statistical estimator."""

import csv
import hashlib
import importlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile


FLAGS = ("force", "no_overlap", "perfect_gencov", "equal_h2", "std_betas", "numerical_omega")
SOURCE_HASHES = {
    "mtag.py": "42ed6fd6bb207681d7d6634c7f3d5a98d63e259a87733650959c8f28df5fe1dc",
    "mtag_munge.py": "41585994de59dd681098ac0ec716985051a90afd73c94c437038237932e61be8",
    "ldsc_mod/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "ldsc_mod/ldscore/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "ldsc_mod/ldscore/allele_info.py": "88d98773115c2e17de86586364327f6a39c03b4f998afc5e37ba2e4cc1e7026b",
    "ldsc_mod/ldscore/irwls.py": "5462bfa82faa561a0132ca07899a02a19fe73ab74fda347a1a326d93f251ccb3",
    "ldsc_mod/ldscore/jackknife.py": "ced2ad44cdd065f9f93c233ce3df8ea93ac28735ca19ebda93ca29a9f8af4ddf",
    "ldsc_mod/ldscore/ldscore.py": "e8608a33c81fa236a2c878ec7d624090ccdaa036bdeefa16884898f4e43b830e",
    "ldsc_mod/ldscore/parse.py": "06d51e3b17664e6889602afa5b479d48c66fb6a31a32641edc30ec30ac577cf9",
    "ldsc_mod/ldscore/regressions.py": "2cebed84e0c89a28f7b5df936ac89ac2763ab61ec50614345babc29dfa8bd583",
    "ldsc_mod/ldscore/sumstats.py": "cc39e884ae820e8e9829b067b7d7ddf1e78646ec4412ee49d2665d50a2d679eb"
}


def digest(filename):
    hasher = hashlib.sha256()
    with open(filename, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def finite(number):
    return not (math.isnan(number) or math.isinf(number))


def parameters(environment):
    values = {}
    for name in FLAGS:
        text = environment["MTAG_" + name.upper()]
        if text not in ("", "false", "true"):
            raise ValueError("Invalid explicit flag: " + name)
        values[name] = text == "true"
    if values["equal_h2"] and not values["perfect_gencov"]:
        raise ValueError("equal_h2 requires perfect_gencov")
    for name, variable in (("time_limit_hours", "MTAG_TIME_LIMIT_HOURS"), ("tol", "MTAG_TOL")):
        text = environment[variable]
        value = float(text)
        if not finite(value) or value <= 0:
            raise ValueError("Nonpositive/nonfinite optimizer parameter: " + name)
        values[name] = text
    return values


def command(inputs, prefix, panel, values):
    if len(inputs) != 2 or len(set(inputs)) != 2 or any("," in path for path in inputs):
        raise ValueError("Two distinct comma-free GWAS paths required by official comma-separated CLI")
    tokens = ["mtag", "--sumstats", ",".join(inputs), "--snp_name", "snpid", "--z_name", "z",
        "--n_name", "n", "--eaf_name", "freq", "--chr_name", "chr", "--bpos_name", "bpos",
        "--a1_name", "a1", "--a2_name", "a2", "--ld_ref_panel", panel, "--out", prefix,
        "--make_full_path", "--time_limit", values["time_limit_hours"], "--tol", values["tol"]]
    tokens.extend("--" + name for name in FLAGS if values[name])
    return tokens


def table_rows(filename, mode):
    binary = sys.version_info[0] == 2
    with open(filename, "rb" if binary else "r") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        header = reader.fieldnames
        common = {"SNP", "CHR", "BP", "A1", "A2", "mtag_beta", "mtag_se", "mtag_z", "mtag_pval"}
        required = common | ({"meta_freq"} if mode == "META_ANALYSIS" else {"Z", "N", "FRQ"})
        if not header or len(header) != len(set(header)) or not required <= set(header):
            raise ValueError("Incomplete or duplicate official result header")
        count, seen = 0, set()
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Malformed official result row")
            identity = row["SNP"]
            if not identity or identity in seen:
                raise ValueError("Empty or duplicate official result SNP")
            seen.add(identity)
            for name in required - {"SNP", "A1", "A2"}:
                if not finite(float(row[name])):
                    raise ValueError("Nonfinite official result field: " + name)
            if float(row["mtag_se"]) <= 0 or not 0 <= float(row["mtag_pval"]) <= 1:
                raise ValueError("Invalid official SE/P value")
            count += 1
        if not count:
            raise ValueError("Empty official result table")
    return count


def matrix(filename):
    with open(filename) as handle:
        rows = [line.split() for line in handle if line.strip()]
    if len(rows) != 2 or any(len(row) != 2 for row in rows) or any(not finite(float(value)) for row in rows for value in row):
        raise ValueError("Official covariance matrix must be finite 2 by 2")


def collect(prefix, values, returncode):
    if returncode != 0:
        raise ValueError("MTAG process failed with exit " + str(returncode))
    log_path = prefix + ".log"
    with open(log_path, "rb") as handle:
        log = handle.read()
    if b"Analysis terminated from error" in log or b"Traceback (most recent call last):" in log:
        raise ValueError("Official caught-error log despite exit zero")
    if not re.search(br"(?m)^\d{4}/\d{2}/\d{2}/\d{2}:\d{2}:\d{2} (?:AM|PM) MTAG complete\. Time elapsed:", log):
        raise ValueError("Official MTAG completion marker missing")
    if not re.search(br"(?m)^\d{4}/\d{2}/\d{2}/\d{2}:\d{2}:\d{2} (?:AM|PM) MTAG results saved to file\.$", log):
        raise ValueError("Official MTAG result-save marker missing")
    if values["numerical_omega"] and not values["equal_h2"]:
        convergence = re.findall(br"(?m)^Successful termination\? (Yes|No)\s*$", log)
        if convergence != [b"Yes"]:
            raise ValueError("Official numerical Omega convergence not uniquely confirmed")
    mode = "META_ANALYSIS" if values["equal_h2"] else "MULTITRAIT"
    tables = [prefix + "_mtag_meta.txt"] if mode == "META_ANALYSIS" else [prefix + "_trait_1.txt", prefix + "_trait_2.txt"]
    forbidden = [prefix + "_trait_1.txt", prefix + "_trait_2.txt", prefix + "_omega_hat.txt"] if mode == "META_ANALYSIS" else [prefix + "_mtag_meta.txt"]
    if any(os.path.lexists(path) for path in forbidden):
        raise ValueError("Mode-incompatible official artifact present")
    counts = [table_rows(path, mode) for path in tables]
    matrices = [prefix + "_sigma_hat.txt"] + ([] if mode == "META_ANALYSIS" else [prefix + "_omega_hat.txt"])
    for filename in matrices:
        matrix(filename)
    parent, basename = os.path.split(prefix)
    files = sorted(os.path.join(parent, name) for name in os.listdir(parent) if name.startswith(basename))
    if any(os.path.islink(filename) or not os.path.isfile(filename) for filename in files):
        raise ValueError("Official artifact is a symlink or not a regular file")
    index = [{"file_name": os.path.basename(filename), "sha256": digest(filename), "size_bytes": os.path.getsize(filename)} for filename in files]
    return {"mode": mode, "result_files": [os.path.basename(path) for path in tables], "result_rows": counts,
        "omega_artifact_status": "NOT_PRODUCED_BY_OFFICIAL_EQUAL_H2_MODE" if mode == "META_ANALYSIS" else "OFFICIAL_FILE_PRESENT",
        "index": index, "files": files, "log_path": log_path}


def write_package_products(record, outputs, audit):
    if len(outputs) != 4 or len(set(outputs)) != 4 or any(os.path.lexists(path) for path in outputs):
        raise ValueError("Four distinct fresh output paths required; no old artifact overwritten")
    with tarfile.open(outputs[0], "w") as archive:
        for filename in record["files"]:
            info = archive.gettarinfo(filename, arcname=os.path.basename(filename))
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ""
            with open(filename, "rb") as handle:
                archive.addfile(info, handle)
    shutil.copyfile(record["log_path"], outputs[1])
    with open(outputs[2], "w") as handle:
        handle.write("file_name\tsha256\tsize_bytes\n")
        for item in record["index"]:
            handle.write("{file_name}\t{sha256}\t{size_bytes}\n".format(**item))
    with open(outputs[3], "w") as handle:
        json.dump(dict(audit, mode=record["mode"], official_result_files=record["result_files"],
            official_result_rows=record["result_rows"], omega_artifact_status=record["omega_artifact_status"],
            raw_artifact_index=record["index"], g0_granted=False, scientific_signoff_granted=False,
            full_official_numerical_certification_granted=False, raw_file_bytes_preserved=True), handle, indent=2, allow_nan=False)
        handle.write("\n")


def validated_output_destinations(outputs):
    if len(outputs) != 4 or any(not path for path in outputs):
        raise ValueError("Four declared output paths required")
    destinations = [os.path.join(os.path.realpath(os.path.dirname(os.path.abspath(path))), os.path.basename(path)) for path in outputs]
    if len(set(destinations)) != 4 or any(os.path.lexists(path) for path in destinations):
        raise ValueError("Four distinct fresh normalized outputs required")
    if any(not os.path.isdir(os.path.dirname(path)) for path in destinations):
        raise ValueError("Every output parent must already exist")
    return destinations


def package_products(record, outputs, audit):
    destinations = validated_output_destinations(outputs)
    stage = tempfile.mkdtemp(prefix=".mtag-publish-", dir=os.path.dirname(destinations[0]))
    created = []
    completed = False
    try:
        private_outputs = [os.path.join(stage, "port-" + str(index)) for index in range(4)]
        write_package_products(record, private_outputs, audit)
        for private, destination in zip(private_outputs, destinations):
            identity = os.lstat(private)
            if not stat.S_ISREG(identity.st_mode) or identity.st_nlink != 1:
                raise ValueError("Staged output must be a private regular file")
            os.link(private, destination)
            created.append((destination, identity.st_dev, identity.st_ino))
        completed = True
    finally:
        if not completed:
            for destination, device, inode in reversed(created):
                try:
                    current = os.lstat(destination)
                    if (current.st_dev, current.st_ino) == (device, inode):
                        os.unlink(destination)
                except OSError:
                    pass
        shutil.rmtree(stage)


def runtime_identity(root):
    if sys.version_info[:2] != (2, 7):
        raise ValueError("Frozen MTAG Python2.7 runtime required")
    versions = {}
    for name, expected in (("numpy", "1.16.6"), ("pandas", "0.24.2"), ("scipy", "1.2.3"), ("joblib", "0.14.1")):
        actual = importlib.import_module(name).__version__
        if actual != expected:
            raise ValueError("Frozen MTAG runtime package mismatch: " + name)
        versions[name] = actual
    for relative, expected in SOURCE_HASHES.items():
        if digest(os.path.join(root, relative)) != expected:
            raise ValueError("Frozen declared MTAG source differs: " + relative)
    return versions


def main():
    outputs = [os.environ["AUTONOMICS_OUTPUT" + str(index)] for index in range(4)]
    validated_output_destinations(outputs)
    values = parameters(os.environ)
    identity = runtime_identity("/opt/mtag")
    inputs = [os.environ["AUTONOMICS_INPUT0"], os.environ["AUTONOMICS_INPUT1"]]
    hashes = [digest(filename) for filename in inputs]
    panel = "/panels/ld_ref/"
    panel_hashes = {}
    for chromosome in range(1, 23):
        for suffix in (".l2.ldscore.gz", ".l2.M_5_50"):
            name = str(chromosome) + suffix
            panel_hashes[name] = digest(os.path.join(panel, name))
    scratch = tempfile.mkdtemp(prefix="mtag-run-", dir=os.environ["AUTONOMICS_WORKDIR"])
    prefix = os.path.join(scratch, "mtag")
    tokens = command(inputs, prefix, panel, values)
    code = subprocess.call(tokens)
    record = collect(prefix, values, code)
    package_products(record, outputs, {"official_command": tokens, "parameters": values, "input_sha256": hashes,
        "observed_panel_sha256": panel_hashes, "observed_hashes_are_not_plan_freeze_approval": True,
        "runtime_package_versions": identity, "declared_source_sha256": SOURCE_HASHES,
        "source_attribution": "Fixed upstream9e17f3c; expected source hashes checked. Independent 11-file byte identity is documented in the bounded host proof, not re-fetched inside this run.",
        "legacy_three_output_ports_compatible": False, "installed_production_plugin_certified": False})


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        sys.stderr.write("MTAG_ACCEPTANCE_BLOCK: " + str(error) + "\n")
        sys.exit(2)
