"""Custom legacy spatial label exchange; not the locked v4.1 main spatial null."""

import csv
import json
import math
import os
from pathlib import Path
import sys


def integer(text, name, minimum):
    try:
        value = int(text)
    except (ValueError, TypeError) as error:
        raise ValueError(name + " must be an integer") from error
    if str(value) != text or value < minimum:
        raise ValueError(name + " outside the integer domain")
    return value


def read_rows(filename, required):
    with filename.open(newline="") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        header = next(reader, None)
        if not header or len(set(header)) != len(header) or any(not name for name in header):
            raise ValueError("Empty or duplicate TSV header")
        if not set(required) <= set(header):
            raise ValueError("Required column missing")
        rows = []
        for row in reader:
            if len(row) != len(header):
                raise ValueError("TSV row width differs")
            rows.append(dict(zip(header, row)))
    if not rows:
        raise ValueError("Empty cell table")
    return rows


def build_graph(coordinates, blocks, neighbors):
    import numpy as np
    from sklearn.neighbors import NearestNeighbors

    source_parts, target_parts, groups, reductions = [], [], [], []
    for block in sorted(set(blocks)):
        indices = np.flatnonzero(blocks == block)
        groups.append(indices)
        effective = min(neighbors, len(indices) - 1)
        if effective < neighbors:
            reductions.append({"block": str(block), "cells": len(indices), "effective_k": effective})
        if effective < 1:
            continue
        distances, selected = NearestNeighbors(n_neighbors=effective, n_jobs=1).fit(coordinates[indices]).kneighbors()
        if not np.isfinite(distances).all():
            raise ValueError("Neighbor distance not finite")
        rows = np.repeat(np.arange(len(indices)), effective)
        columns = selected.ravel()
        if np.any(rows == columns):
            raise ValueError("Official self-excluding query retained a self edge")
        endpoints = np.sort(np.column_stack((indices[rows], indices[columns])), axis=1)
        endpoints = np.unique(endpoints, axis=0)
        source_parts.append(endpoints[:, 0])
        target_parts.append(endpoints[:, 1])
    sources = np.concatenate(source_parts) if source_parts else np.array([], dtype=np.int64)
    targets = np.concatenate(target_parts) if target_parts else np.array([], dtype=np.int64)
    return sources, targets, groups, reductions


def counts(code, sources, targets, levels):
    import numpy as np

    lower = np.minimum(code[sources], code[targets])
    upper = np.maximum(code[sources], code[targets])
    return np.bincount(lower * levels + upper, minlength=levels * levels).reshape(levels, levels)


def main():
    import numpy as np
    import sklearn

    role = os.environ["NH_ANALYSIS_ROLE"]
    if role == "B_SPATIAL_MAIN":
        raise ValueError("PLAN_MAIN_BLOCKED: spatial structure-preserving null is TO_LOCK; label exchange is not a substitute")
    if role != "legacy_label_exchange":
        raise ValueError("Unsupported analysis_role")
    if sklearn.__version__ != "1.9.1" or np.__version__ != "2.4.6":
        raise ValueError("Frozen numeric package version differs")
    x_col, y_col, label_col = (os.environ[name] for name in ("NH_X_COL", "NH_Y_COL", "NH_LABEL_COL"))
    if len({x_col, y_col, label_col}) != 3 or any(not name.strip() for name in (x_col, y_col, label_col)):
        raise ValueError("Coordinate and label columns must be distinct and nonempty")
    block_col = os.environ.get("NH_BLOCK_COL", "")
    if block_col and not block_col.strip():
        raise ValueError("Empty block column name")
    neighbors = integer(os.environ["NH_K"], "n_neighbors", 1)
    iterations = integer(os.environ["NH_PERM"], "n_perm", 100)
    seed = integer(os.environ["NH_SEED"], "seed", 0)
    cap = integer(os.environ["NH_MAX_PAIR_ENTRIES"], "max_pair_entries", 1)
    rows = read_rows(Path(os.environ["AUTONOMICS_INPUT0"]), [x_col, y_col, label_col, *([block_col] if block_col else [])])
    labels = [row[label_col] for row in rows]
    blocks = np.asarray([row[block_col] for row in rows] if block_col else ["ALL"] * len(rows))
    if any(not label.strip() for label in labels) or any(not block.strip() for block in blocks):
        raise ValueError("Empty label or block identity")
    if "cell_id" in rows[0]:
        identities = [row["cell_id"] for row in rows]
        if any(not identity.strip() for identity in identities) or len(set(identities)) != len(identities):
            raise ValueError("Empty or duplicate cell identity")
    coordinates = np.asarray([[float(row[x_col]), float(row[y_col])] for row in rows], dtype=np.float64)
    if not np.isfinite(coordinates).all():
        raise ValueError("Coordinates must be finite")
    levels = sorted(set(labels))
    if len(levels) < 2:
        raise ValueError("At least two distinct lexical labels required")
    if len(levels) ** 2 > cap:
        raise ValueError("Pair budget exceeded; no label or planned pair dropped")
    label_codes = dict(zip(levels, range(len(levels))))
    codes = np.array([label_codes[label] for label in labels], dtype=np.int64)
    sources, targets, groups, reductions = build_graph(coordinates, blocks, neighbors)
    if iterations * len(sources) ** 2 > np.iinfo(np.int64).max:
        raise ValueError("Exact null-accumulator capacity exceeded; no iterations reduced")
    observed = counts(codes, sources, targets, len(levels))
    sums = np.zeros_like(observed)
    squares = np.zeros_like(observed)
    upper_tail = np.zeros_like(observed)
    lower_tail = np.zeros_like(observed)
    generator = np.random.default_rng(seed)
    for iteration in range(iterations):
        shuffled = codes.copy()
        for indices in groups:
            shuffled[indices] = codes[indices][generator.permutation(len(indices))]
        current = counts(shuffled, sources, targets, len(levels))
        sums += current
        squares += current * current
        upper_tail += current >= observed
        lower_tail += current <= observed
    columns = ["label_a", "label_b", "count", "expected_mean", "expected_sd", "z", "p_upper", "p_lower", "null_status"]
    with Path(os.environ["AUTONOMICS_OUTPUT0"]).open("w", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=columns)
        writer.writeheader()
        for left, label_a in enumerate(levels):
            for right in range(left, len(levels)):
                total = int(sums[left, right])
                mean = total / iterations
                variance_numerator = iterations * int(squares[left, right]) - total ** 2
                deviation = math.sqrt(variance_numerator / (iterations * (iterations - 1)))
                writer.writerow({"label_a": label_a, "label_b": levels[right], "count": int(observed[left, right]),
                    "expected_mean": mean, "expected_sd": deviation,
                    "z": "" if deviation == 0 else (int(observed[left, right]) - mean) / deviation,
                    "p_upper": (1 + int(upper_tail[left, right])) / (iterations + 1),
                    "p_lower": (1 + int(lower_tail[left, right])) / (iterations + 1),
                    "null_status": "DEGENERATE_NULL" if deviation == 0 else "FINITE_LABEL_EXCHANGE_NULL"})
    log = {"method": "CUSTOM_LABEL_EXCHANGE_NOT_SQUIDPY", "cells": len(rows), "labels": len(levels),
           "k": neighbors, "edges": len(sources), "n_perm": iterations, "seed": seed,
           "perm_scope": "within-block" if block_col else "global", "block_column": block_col,
           "effective_k_reductions": reductions, "pair_rows": len(levels) * (len(levels) + 1) // 2,
           "accumulator": "EXACT_INTEGER_SUMS_SQUARES_NO_B_BY_L_BY_L_ARRAY",
           "spatial_autocorrelation_preserved": False, "plan_main_ready": False,
           "scientific_signoff_granted": False,
           "warning": "Label exchange preserves block composition, NOT spatial autocorrelation, anatomy-aware sampling or qualified donor inference"}
    Path(os.environ["AUTONOMICS_OUTPUT1"]).write_text(json.dumps(log, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("spatial_nhood: " + str(error), file=sys.stderr)
        sys.exit(2)
