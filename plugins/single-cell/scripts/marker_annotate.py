"""Custom marker-list means and margins; not a calibrated official classifier."""

from collections import Counter
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
import tempfile

import anndata as ad
import numpy as np
from scipy import sparse


class ContractError(RuntimeError):
    pass


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"marker_sets contains duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ContractError(f"marker_sets must be strict JSON; invalid constant {value}")


def parameters():
    try:
        markers = json.loads(os.environ.get("SC_P_JSON_MARKER_SETS", ""), object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (ValueError, TypeError) as error:
        raise ContractError("marker_sets must be strict JSON") from error
    if not isinstance(markers, dict) or not markers:
        raise ContractError("marker_sets must be a nonempty JSON object")
    for name, genes in markers.items():
        if not isinstance(name, str) or not name.strip():
            raise ContractError("marker labels must be nonempty strings")
        if not isinstance(genes, list) or not genes or any(not isinstance(gene, str) or not gene.strip() for gene in genes):
            raise ContractError(f"marker list {name} must contain nonempty gene strings")
    normalize = os.environ.get("SC_P_STR_NORMALIZE", "log_cp10k") or "log_cp10k"
    if normalize not in {"log_cp10k", "none"}:
        raise ContractError("normalize must be log_cp10k or none")
    try:
        minimum = float(os.environ.get("SC_P_NUM_MIN_SCORE", "0") or "0")
    except ValueError as error:
        raise ContractError("min_score must be a finite number") from error
    if not math.isfinite(minimum):
        raise ContractError("min_score must be a finite number")
    unknown = os.environ.get("SC_P_STR_UNKNOWN_LABEL", "Unknown") or "Unknown"
    if not unknown.strip():
        raise ContractError("unknown_label must be nonblank")
    groupby = os.environ.get("SC_P_STR_GROUPBY", "")
    if groupby and not groupby.strip():
        raise ContractError("groupby must be nonblank when supplied")
    return markers, normalize, minimum, unknown, groupby or None


def paths():
    values = [os.environ.get(name) for name in ["AUTONOMICS_INPUT0", "AUTONOMICS_OUTPUT0", "AUTONOMICS_OUTPUT1"]]
    if not all(values):
        raise ContractError("input and both declared output ports are required")
    source, output, report = [Path(value).absolute() for value in values]
    if not source.is_file():
        raise ContractError("input must name a readable H5AD file")
    if output.resolve() == report.resolve():
        raise ContractError("output paths must be distinct")
    for path in [output, report]:
        if os.path.lexists(path):
            raise ContractError(f"output already exists; refusing overwrite: {path}")
        if not path.parent.is_dir():
            raise ContractError("output parent must already exist")
    return source, output, report


def scoring_matrix(data, normalize):
    if not data.n_obs or not data.n_vars or data.X is None:
        raise ContractError("input must contain nonempty X with cells and genes")
    for label, names in [("cell", data.obs_names), ("gene", data.var_names)]:
        if not names.is_unique or any(not str(value).strip() for value in names):
            raise ContractError(f"{label} identifiers must be unique and nonempty")
    if data.obs.columns.has_duplicates or data.var.columns.has_duplicates:
        raise ContractError("obs and var metadata column names must be unique")
    if any(name in data.obs for name in ["marker_label", "marker_score", "marker_margin"]) or "marker_annotate_params" in data.uns:
        raise ContractError("existing marker annotation fields cannot be overwritten")
    matrix = data.X
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix)
    if values.dtype.kind not in "biuf" or not np.isfinite(values).all():
        raise ContractError("X must contain finite real numeric values")
    if values.dtype.kind in "iu" and values.size and max(abs(int(values.min())), abs(int(values.max()))) > 2 ** 53:
        raise ContractError("integer X exceeds exact float64 scoring-input range")
    if sparse.issparse(matrix):
        try:
            matrix.check_format(full_check=True)
        except ValueError as error:
            raise ContractError(f"invalid sparse X: {error}") from error
        if values.dtype.kind in "iu" and not matrix.has_canonical_format:
            coordinates = matrix.tocoo(copy=False)
            exact = {}
            for row, column, value in zip(coordinates.row, coordinates.col, coordinates.data):
                key = (int(row), int(column))
                exact[key] = exact.get(key, 0) + int(value)
            if any(abs(value) > 2 ** 53 for value in exact.values()):
                raise ContractError("logical sparse integer X exceeds exact float64 scoring-input range")
            matrix = sparse.csr_matrix(([float(value) for value in exact.values()],
                ([key[0] for key in exact], [key[1] for key in exact])), shape=matrix.shape)
        else:
            matrix = matrix.copy()
            matrix.data = matrix.data.astype(np.float64)
            matrix = matrix.tocsr()
            matrix.sum_duplicates()
    else:
        matrix = np.array(matrix, dtype=np.float64, copy=True)
    values = matrix.data if sparse.issparse(matrix) else matrix
    if not np.isfinite(values).all():
        raise ContractError("duplicate sparse coordinates overflow their scoring dtype")
    if normalize == "log_cp10k":
        if (values < 0).any():
            raise ContractError("log_cp10k requires nonnegative X; no scale guessing")
        totals = np.asarray(matrix.sum(axis=1)).ravel()
        if not np.isfinite(totals).all():
            raise ContractError("normalization totals must be finite; no alternate rescaling path")
        scale = np.zeros_like(totals, dtype=np.float64)
        nonzero = totals > 0
        scale[nonzero] = 1e4 / totals[nonzero]
        if not np.isfinite(scale).all():
            raise ContractError("normalization scale must be finite; no alternate rescaling path")
        matrix = (sparse.diags(scale) @ matrix).log1p() if sparse.issparse(matrix) else np.log1p(matrix * scale[:, None])
    if not np.isfinite(matrix.data if sparse.issparse(matrix) else matrix).all():
        raise ContractError("normalization produced nonfinite values")
    return matrix


def annotate(data, markers, normalize, minimum, unknown, groupby):
    matrix = scoring_matrix(data, normalize)
    positions = {str(gene): index for index, gene in enumerate(data.var_names)}
    names, columns, summaries = list(markers), [], {}
    for name, genes in markers.items():
        present = [gene for gene in genes if gene in positions]
        if not present:
            raise ContractError(f"marker list {name} has no genes present in X")
        selected = matrix[:, [positions[gene] for gene in present]]
        columns.append(np.asarray(selected.mean(axis=1)).ravel())
        summaries[name] = {"genes_requested": len(genes), "genes_present": len(present),
            "missing_genes": sorted(set(genes) - set(positions)), "requested_members": genes, "present_members": present,
            "duplicate_members": {gene: count for gene, count in Counter(genes).items() if count > 1},
            "effective_weights": {gene: count / len(present) for gene, count in Counter(present).items()}}
    scores = np.column_stack(columns)
    if not np.isfinite(scores).all():
        raise ContractError("marker arithmetic produced nonfinite means")
    rows = np.arange(data.n_obs)
    own_best = np.argmax(scores, axis=1)
    own_top = scores[rows, own_best]
    cluster_report = None
    if groupby is None:
        assigned_indices, decision_scores, decision_rows = own_best, scores, rows
    else:
        if groupby not in data.obs:
            raise ContractError("groupby column is absent from obs")
        groups = data.obs[groupby]
        if groups.isna().any() or any(not str(value).strip() for value in groups):
            raise ContractError("groupby contains missing or blank cluster identifiers")
        if any(isinstance(value, (float, np.floating)) and not math.isfinite(float(value)) for value in groups):
            raise ContractError("groupby contains nonfinite numeric cluster identifiers")
        keys = groups.astype(str).to_numpy()
        group_names = sorted(set(keys))
        averages = np.stack([scores[keys == name].mean(axis=0) for name in group_names])
        if not np.isfinite(averages).all():
            raise ContractError("cluster arithmetic produced nonfinite means")
        choices = np.argmax(averages, axis=1)
        codes = {name: index for index, name in enumerate(group_names)}
        decision_rows = np.array([codes[key] for key in keys], dtype=np.int64)
        assigned_indices, decision_scores = choices[decision_rows], averages
        cluster_report = {name: {"label": names[int(choices[index])] if averages[index, choices[index]] > minimum else unknown,
            "n_cells": int((keys == name).sum()), "scores": averages[index].tolist()} for index, name in enumerate(group_names)}
    top = decision_scores[decision_rows, assigned_indices]
    masked = decision_scores.copy()
    masked[np.arange(len(masked)), np.argmax(masked, axis=1)] = -np.inf
    second = masked.max(axis=1)[decision_rows]
    margins = np.where(np.isfinite(second), top - second, top)
    if not np.isfinite(margins).all():
        raise ContractError("marker decision margins overflow float64")
    fallback = top <= minimum
    labels = np.array([unknown if missing else names[int(index)] for index, missing in zip(assigned_indices, fallback)])
    data.obs["marker_label"] = labels
    data.obs["marker_score"] = np.where(fallback, own_top, scores[rows, assigned_indices]).astype(np.float64)
    data.obs["marker_margin"] = margins.astype(np.float64)
    data.uns["marker_annotate_params"] = {"normalize": normalize, "groupby": groupby, "min_score": minimum, "unknown_label": unknown}
    return summaries, names, cluster_report, fallback


def publish(data, report, destinations, source, input_sha):
    staged, published = [], []
    try:
        for path in destinations:
            descriptor, name = tempfile.mkstemp(prefix=".marker-annotate-", dir=path.parent)
            os.close(descriptor)
            staged.append(Path(name))
        data.write_h5ad(staged[0], compression="lzf")
        staged[1].write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        if digest(source) != input_sha:
            raise ContractError("input changed during marker output staging")
        for path in staged:
            with path.open("rb") as handle:
                os.fsync(handle.fileno())
        for temporary, destination in zip(staged, destinations):
            os.link(temporary, destination)
            published.append((destination, temporary.stat().st_dev, temporary.stat().st_ino))
    except BaseException:
        for destination, device, inode in published:
            try:
                current = destination.lstat()
                if current.st_dev == device and current.st_ino == inode:
                    destination.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for path in staged:
            path.unlink(missing_ok=True)


def run():
    markers, normalize, minimum, unknown, groupby = parameters()
    source, output, report_path = paths()
    input_sha = digest(source)
    data = ad.read_h5ad(source)
    summaries, names, clusters, fallback = annotate(data, markers, normalize, minimum, unknown, groupby)
    if digest(source) != input_sha:
        raise ContractError("input changed during marker annotation")
    report = {"schema_version": "2.0", "operation": "marker_annotate", "cells": data.n_obs,
        "mode": "cluster" if groupby is not None else "per_cell", "groupby": groupby,
        "normalize": normalize, "min_score": minimum, "unknown_label": unknown,
        "marker_sets": summaries, "marker_label_order": names,
        "label_counts": {str(key): int(value) for key, value in data.obs["marker_label"].value_counts().items()},
        "input_sha256": input_sha, "cell_ids": data.obs_names.tolist(), "gene_ids": data.var_names.tolist(),
        "fallback_count": int(fallback.sum()), "score_semantics": "Own assigned-label score; fallback uses own best candidate score",
        "margin_semantics": "Decision best-minus-runner-up; cluster margin propagated; single-list margin is its top score",
        "tie_semantics": "First marker label in original JSON order", "matrix_source": "X only; raw and layers ignored",
        "normalization_background": "All X genes; zero-total nonnegative cells remain zero",
        "array_membership_semantics": "Repeated members retain original weighting; missing members omitted and disclosed",
        "statistical_official_equivalence": "NOT_APPLICABLE_CUSTOM_ARITHMETIC_RULE",
        "calibrated_probability_or_biological_specificity": False, "scientific_input_qualification": False, "G0": False,
        "versions": {name: importlib.metadata.version(name) for name in ["anndata", "numpy", "scipy"]}}
    if clusters is not None:
        report["cluster_labels"] = {name: result["label"] for name, result in clusters.items()}
        report["cluster_scores"] = clusters
    publish(data, report, [output, report_path], source, input_sha)


def main():
    try:
        run()
    except (ContractError, ValueError, TypeError, OSError) as error:
        print(f"marker_annotate: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

