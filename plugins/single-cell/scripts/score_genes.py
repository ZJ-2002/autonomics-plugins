"""Original-kind, bounded official Scanpy score_genes wrapper."""

import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile


class PublicationError(ValueError):
    pass


def metadata(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def file_fact(path, *, timestamps=False):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise PublicationError("Publication requires ordinary non-symlink files")
    with path.open("rb") as handle:
        checksum = hashlib.file_digest(handle, "sha256").hexdigest()
    after = path.lstat()
    if metadata(before) != metadata(after):
        raise PublicationError("File changed during identity verification")
    return (metadata(before) if timestamps else metadata(before)[:6]) + (checksum,)


def directory_fact(path):
    if path.resolve(strict=True) != path:
        raise PublicationError("Publication directory aliases are forbidden")
    value = path.lstat()
    if not stat.S_ISDIR(value.st_mode):
        raise PublicationError("Ordinary publication directories required")
    return value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid


def source_fact(path):
    before = path.lstat()
    resolved = path.resolve(strict=True)
    actual = file_fact(resolved, timestamps=True)
    after = path.lstat()
    if metadata(before) != metadata(after) or path.resolve(strict=True) != resolved:
        raise PublicationError("Input binding changed during identity verification")
    return str(resolved), metadata(before), actual


def validate_outputs(paths):
    if len(paths["outputs"]) != 2 or len(set(paths["outputs"])) != 2:
        raise PublicationError("Two distinct output paths required")
    for destination in paths["outputs"]:
        if directory_fact(destination.parent) != paths["parents"][destination.parent]:
            raise PublicationError("Output parent identity changed")
        if os.path.lexists(destination):
            raise PublicationError("Existing output must not be overwritten: " + str(destination))
        if destination.resolve() == paths["input"]:
            raise PublicationError("Input/output aliases are forbidden")


def prepare_paths():
    values = [os.environ.get(name, "") for name in
              ["AUTONOMICS_INPUT0", "AUTONOMICS_OUTPUT0", "AUTONOMICS_OUTPUT1"]]
    if any(not value or any(character in value for character in "\0\r\n\t") for value in values):
        raise PublicationError("Explicit input and output paths required")
    bound = Path(values[0]).absolute()
    initial = source_fact(bound)
    outputs = [Path(value).absolute() for value in values[1:]]
    paths = {"bound_input": bound, "input": Path(initial[0]), "source_fact": initial,
             "outputs": outputs, "parents": {path.parent: directory_fact(path.parent) for path in outputs}}
    validate_outputs(paths)
    return paths


def check_input(paths):
    if source_fact(paths["bound_input"]) != paths["source_fact"]:
        raise PublicationError("Input identity or content changed during scoring")


def create_stage(destination, paths):
    if directory_fact(destination.parent) != paths["parents"][destination.parent]:
        raise PublicationError("Output parent identity changed before staging")
    directory = Path(tempfile.mkdtemp(prefix=".score-genes-", dir=destination.parent))
    path = directory / destination.name
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_RDWR, 0o600)
    stage = {"directory": directory, "directory_fact": directory_fact(directory),
             "path": path, "descriptor": descriptor,
             "descriptor_identity": metadata(os.fstat(descriptor))[:5], "fact": None}
    stage["fact"] = descriptor_fact(stage)
    return stage


def descriptor_fact(stage):
    before = os.fstat(stage["descriptor"])
    if not stat.S_ISREG(before.st_mode) or metadata(before)[:5] != stage["descriptor_identity"]:
        raise PublicationError("Owned staging descriptor identity changed")
    checksum = hashlib.sha256()
    offset = 0
    while True:
        block = os.pread(stage["descriptor"], 1024 * 1024, offset)
        if not block:
            break
        checksum.update(block)
        offset += len(block)
    after = os.fstat(stage["descriptor"])
    if metadata(before) != metadata(after) or offset != before.st_size:
        raise PublicationError("Owned staging descriptor changed while hashing")
    return metadata(before)[:6] + (checksum.hexdigest(),)


def write_descriptor_text(stage, content):
    descriptor_fact(stage)
    os.ftruncate(stage["descriptor"], 0)
    os.lseek(stage["descriptor"], 0, os.SEEK_SET)
    with os.fdopen(os.dup(stage["descriptor"]), "w", encoding="utf-8") as handle:
        handle.write(content)


def check_stage(stage):
    if directory_fact(stage["directory"]) != stage["directory_fact"]:
        raise PublicationError("Owned staging directory identity changed")


def write_stage(stage, writer):
    check_stage(stage)
    if file_fact(stage["path"]) != stage["fact"] or descriptor_fact(stage) != stage["fact"]:
        raise PublicationError("Staged path differs from its owned descriptor before writing")
    writer(Path("/proc/self/fd") / str(stage["descriptor"]))
    stage["fact"] = descriptor_fact(stage)
    check_stage(stage)
    if file_fact(stage["path"]) != stage["fact"]:
        raise PublicationError("Staged path differs from its owned descriptor after writing")


def cleanup_stage(stage):
    try:
        check_stage(stage)
        if stage["fact"] is not None and file_fact(stage["path"]) == stage["fact"]:
            check_stage(stage)
            stage["path"].unlink()
    except (OSError, PublicationError):
        pass
    finally:
        os.close(stage["descriptor"])
    try:
        check_stage(stage)
        if not any(stage["directory"].iterdir()):
            stage["directory"].rmdir()
    except (OSError, PublicationError):
        pass


def publish(data, content, paths):
    validate_outputs(paths)
    check_input(paths)
    stages = []
    published = []
    try:
        for destination in paths["outputs"]:
            stages.append(create_stage(destination, paths))
        write_stage(stages[0], lambda path: data.write_h5ad(path, compression="lzf"))
        write_stage(stages[1], lambda path: write_descriptor_text(stages[1], content))
        check_input(paths)
        for stage, destination in zip(stages, paths["outputs"], strict=True):
            check_stage(stage)
            if file_fact(stage["path"]) != stage["fact"]:
                raise PublicationError("Staged output content changed before publication")
            if directory_fact(destination.parent) != paths["parents"][destination.parent]:
                raise PublicationError("Output parent identity changed before publication")
            os.link(stage["path"], destination)
            published.append((destination, stage["fact"]))
            if file_fact(destination) != stage["fact"]:
                raise PublicationError("Published output identity or content changed")
        check_input(paths)
        for destination, expected in published:
            if directory_fact(destination.parent) != paths["parents"][destination.parent] or file_fact(destination) != expected:
                raise PublicationError("Final output identity or content changed")
    except BaseException:
        for destination, expected in reversed(published):
            try:
                if directory_fact(destination.parent) == paths["parents"][destination.parent] and file_fact(destination) == expected:
                    destination.unlink()
            except (OSError, PublicationError):
                pass
        raise
    finally:
        for stage in stages:
            cleanup_stage(stage)


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Duplicate JSON key: " + name)
        result[name] = value
    return result


def parse_sets(text):
    sets = json.loads(text, object_pairs_hook=unique_object,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonstandard JSON constant: " + value)))
    if not isinstance(sets, dict) or not sets:
        raise ValueError("gene_sets must be a nonempty JSON object")
    for name, genes in sets.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Gene-set names must be nonempty strings")
        if not isinstance(genes, list) or not genes or any(not isinstance(gene, str) or not gene.strip() for gene in genes):
            raise ValueError("Each gene set must contain nonempty gene strings")
    return sets


def integer(text, name, minimum, maximum=None):
    try:
        value = int(text)
    except (ValueError, TypeError) as error:
        raise ValueError(name + " must be an integer") from error
    if str(value) != text or value < minimum or (maximum is not None and value > maximum):
        raise ValueError(name + " outside the frozen integer domain")
    return value


def summarize(scores):
    import numpy as np

    finite = np.isfinite(scores)
    count = int(finite.sum())
    result = {"finite_cells": count, "nonfinite_cells": int(scores.size - count),
              "status": "FINITE" if count == scores.size else "NONFINITE_OFFICIAL_SCORES"}
    if count != scores.size:
        result.update(dict.fromkeys(("mean", "min", "p25", "median", "p75", "max")))
    else:
        values = np.percentile(scores, [0, 25, 50, 75, 100])
        result.update(dict(zip(("min", "p25", "median", "p75", "max"), map(float, values))))
        result["mean"] = float(np.mean(scores))
    return result


def main():
    import anndata as ad
    import numpy as np
    import pandas as pd
    import scanpy as sc

    paths = prepare_paths()
    if sc.__version__ != "1.11.3" or ad.__version__ != "0.11.4":
        raise ValueError("Frozen official package version differs")
    sets = parse_sets(os.environ["SC_P_JSON_GENE_SETS"])
    ctrl_size = integer(os.environ["SC_P_INT_CTRL_SIZE"], "ctrl_size", 1)
    seed = integer(os.environ["SC_P_INT_RANDOM_STATE"], "random_state", 0, 4294967295)
    data = ad.read_h5ad(paths["input"])
    if data.n_obs == 0 or data.n_vars == 0:
        raise ValueError("Empty AnnData axis")
    if not data.obs_names.is_unique or not data.var_names.is_unique:
        raise ValueError("Duplicate AnnData axis")
    if not data.obs.columns.is_unique:
        raise ValueError("Duplicate obs column")
    use_raw = data.raw is not None
    axis = data.raw.var_names if use_raw else data.var_names
    if not axis.is_unique:
        raise ValueError("Duplicate raw gene axis")
    requests = {}
    for name, genes in sets.items():
        if name in data.obs.columns:
            raise ValueError("Score name collides with obs: " + name)
        present = pd.Index(genes).intersection(axis)
        if len(present) < 2:
            raise ValueError("Each gene set needs at least two distinct present genes: " + name)
        requests[name] = {"genes_requested": len(genes), "genes_present": len(present),
                          "duplicate_members": len(genes) - len(set(genes)),
                          "missing_genes": sorted(set(genes) - set(axis))}
    for name, genes in sets.items():
        sc.tl.score_genes(data, genes, score_name=name, ctrl_size=ctrl_size, random_state=seed,
                          ctrl_as_ref=True, n_bins=25, gene_pool=None, copy=False, use_raw=use_raw, layer=None)
        requests[name].update(summarize(np.asarray(data.obs[name], dtype=np.float64)))
    report = {"schema_version": "1.0", "operation": "gene_set_score", "cells": data.n_obs,
              "ctrl_size": ctrl_size, "random_state": seed, "gene_sets": requests,
              "matrix_axis": "raw" if use_raw else "X", "selected_axis_genes": len(axis),
              "method": "scanpy.tl.score_genes", "official_version": "1.11.3",
              "fixed_parameters": {"ctrl_as_ref": True, "n_bins": 25, "gene_pool": None, "layer": None},
              "summary_policy": "ALL_CELLS_OR_NULL_NO_MISSING_CELL_DELETION",
              "scientific_signoff_granted": False}
    content = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ad.settings.allow_write_nullable_strings = True
    publish(data, content, paths)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("gene_set_score: " + str(error), file=sys.stderr)
        sys.exit(2)
