"""Independent official aggregation plus mathematical and contract checks."""

from collections import Counter
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import anndata as ad
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import scanpy as sc
from scipy import sparse


SOURCE = Path(__file__).resolve().parents[1]
GENES = ["gene with space", 'gene"quote', "gene\\backslash", "基因α", "gene:5!?()"]


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def fixture(form="dense", counts=True):
    values = np.array([[0, 2, 1, 0, 7], [1, 0, 3, 1, 5], [2, 1, 0, 3, 4],
                       [0, 4, 2, 3, 1], [3, 1, 4, 2, 0], [1, 3, 0, 4, 2]], dtype=np.float64)
    base = values.copy()
    if form in ["csr", "csc"]:
        values = getattr(sparse, form + "_matrix")(values)
    elif form == "stored-zero":
        values = sparse.csr_matrix((values.ravel(), np.tile(np.arange(5), 6), np.arange(0, 31, 5)), shape=(6, 5))
    obs = pd.DataFrame({"group": pd.Categorical(["b", "b", "a", "a", "c", "c"], categories=["c", "unused", "b", "a"])},
                       index=[f"c{index}" for index in range(6)])
    data = ad.AnnData(values, obs=obs, var=pd.DataFrame(index=GENES))
    if counts:
        data.layers["counts"] = sparse.csr_matrix((base * 3 + 1).astype(np.int32))
    data.raw = ad.AnnData(np.arange(42).reshape(6, 7), obs=obs.copy(), var=pd.DataFrame(index=[f"raw{index}" for index in range(7)]))
    return data


def prepare(root, name, data, overrides=None):
    directory = root / name
    directory.mkdir()
    data.write_h5ad(directory / "input.h5ad")
    settings = {"groupby": "group", "genes": [], "normalize": "cp10k", "include_percent_expressed": True}
    settings.update(overrides or {})
    (directory / "request.json").write_text(json.dumps(settings, ensure_ascii=False) + "\n")
    return directory, settings


def execute(directory, extra=None):
    settings = json.loads((directory / "request.json").read_text())
    encoded = "c(" + ",".join(json.dumps(value, ensure_ascii=False) for value in settings["genes"]) + ")"
    variables = dict(os.environ, AUTONOMICS_INPUT0=str(directory / "input.h5ad"),
                     AUTONOMICS_OUTPUT0=str(directory / "cluster_mean_expression.parquet"),
                     SC_P_STR_GROUPBY=settings["groupby"], SC_P_STR_NORMALIZE=settings["normalize"],
                     SC_P_R_ARRAY_GENES=encoded, SC_P_BOOL_INCLUDE_PERCENT_EXPRESSED=str(settings["include_percent_expressed"]).lower())
    variables.update(extra or {})
    result = subprocess.run([sys.executable, str(SOURCE / "scripts/cluster_mean_expression.py")], env=variables,
                            capture_output=True, timeout=180)
    (directory / "stdout.txt").write_bytes(result.stdout)
    (directory / "stderr.txt").write_bytes(result.stderr)
    (directory / "execution.json").write_text(json.dumps({"exit": result.returncode, "G0": False}) + "\n")
    return result


def author_reference(directory):
    settings = json.loads((directory / "request.json").read_text())
    source = ad.read_h5ad(directory / "input.h5ad")
    matrix = source.layers["counts"] if settings["normalize"] == "cp10k" and "counts" in source.layers else source.X
    if sparse.issparse(matrix):
        matrix = matrix.tocsr()
        if matrix.dtype.kind == "b":
            matrix.sum_duplicates()
    matrix = matrix.astype(np.float64)
    if sparse.issparse(matrix):
        matrix.sum_duplicates()
        matrix.eliminate_zeros()
    labels = [str(value) for value in source.obs[settings["groupby"]]]
    reference = ad.AnnData(matrix.copy(), obs=pd.DataFrame({"cluster": pd.Categorical(labels, categories=sorted(set(labels)))},
                                                         index=source.obs_names), var=source.var.copy())
    if settings["normalize"] == "cp10k":
        sc.pp.normalize_total(reference, target_sum=10000, exclude_highly_expressed=False, key_added=None, inplace=True)
    selected = settings["genes"] or list(source.var_names)
    reduced = reference[:, selected].copy()
    combined = sc.get.aggregate(reduced, by="cluster", func=["mean", "count_nonzero"], axis="obs", dof=1)
    count = Counter(labels)
    rows = []
    for index, label in enumerate(combined.obs["cluster"].astype(str)):
        for position, gene in enumerate(selected):
            row = {"cluster": label, "gene": gene, "mean_expression": float(combined.layers["mean"][index, position])}
            if settings["include_percent_expressed"]:
                row["pct_expressed"] = float(combined.layers["count_nonzero"][index, position] / count[label] * 100)
            rows.append(row)
    pd.DataFrame.from_records(rows).to_parquet(directory / "author-reference.parquet", index=False)


def compare(directory):
    actual = pd.read_parquet(directory / "cluster_mean_expression.parquet")
    expected = pd.read_parquet(directory / "author-reference.parquet")
    pd.testing.assert_frame_equal(actual, expected, check_exact=False, atol=1e-10, rtol=1e-12)
    assert actual["cluster"].tolist() == expected["cluster"].tolist()
    assert actual["gene"].tolist() == expected["gene"].tolist()
    settings = json.loads((directory / "request.json").read_text())
    source = ad.read_h5ad(directory / "input.h5ad")
    chosen = source.layers["counts"] if settings["normalize"] == "cp10k" and "counts" in source.layers else source.X
    values = chosen.toarray() if sparse.issparse(chosen) else np.asarray(chosen)
    values = values.astype(float)
    if settings["normalize"] == "cp10k":
        values = np.asarray([[float(value) / math.fsum(row) * 10000 for value in row] for row in values])
    labels = [str(value) for value in source.obs[settings["groupby"]]]
    for record in actual.to_dict("records"):
        position = source.var_names.get_loc(record["gene"])
        rows = [index for index, label in enumerate(labels) if label == record["cluster"]]
        mean = math.fsum(float(values[index, position]) for index in rows) / len(rows)
        np.testing.assert_allclose(record["mean_expression"], mean, atol=1e-10, rtol=1e-12)
        if settings["include_percent_expressed"]:
            pct = sum(values[index, position] != 0 for index in rows) / len(rows) * 100
            assert record["pct_expressed"] == pct
    report = json.loads(pq.read_schema(directory / "cluster_mean_expression.parquet").metadata[b"autonomics_cluster_mean_report"])
    assert report["parameters"] == settings and report["input_sha256"] == digest(directory / "input.h5ad")
    assert report["group_cell_counts"] == dict(Counter(labels)) and report["output_rows"] == len(actual)
    assert report["input_cells"] == source.n_obs and report["background_genes"] == source.n_vars
    assert report["selected_genes"] == (settings["genes"] or list(source.var_names))
    assert [item["cell_id"] for item in report["cell_ledger"]] == list(source.obs_names)
    assert [item["cluster"] for item in report["cell_ledger"]] == labels
    assert report["matrix_source"] == ("layers/counts" if settings["normalize"] == "cp10k" and "counts" in source.layers else "X")
    assert report["scientific_release"] == "NOT_GRANTED" and report["G0"] is False and report["raw_used"] is False
    assert report["schema_version"] == "2.0" and report["operation"] == "cluster_mean_expression"
    assert report["normalization_background"] == "all_input_var_names_before_gene_selection"
    assert report["ordered_cluster_labels"] == sorted(set(labels))
    assert report["fraction_definition"] == "100 * count_nonzero_after_coordinate_coalescing / cells_in_cluster"
    assert report["mean_definition"] == "cell-level arithmetic mean on chosen scale, not donor pseudobulk sum"
    assert report["study_input_scale_verified"] is False
    assert report["packages"] == {name: importlib.metadata.version(name) for name in ["scanpy", "anndata", "numpy", "scipy", "pandas", "pyarrow"]}
    assert isinstance(report["warnings"], list) and all(isinstance(value, str) for value in report["warnings"])
    return {"rows": len(actual), "author_and_independent_math": True, "G0": False}


def positives(root):
    cases = [("dense-counts-cp10k", fixture(), {}), ("csr-X-cp10k", fixture("csr", False), {}),
             ("csc-X-cp10k", fixture("csc", False), {}),
             ("full-background-before-selection", fixture(), {"genes": [GENES[0], GENES[3]]}),
             ("special-gene-identity", fixture(), {"genes": GENES[::-1]}),
             ("none-X-not-counts", fixture(), {"normalize": "none"}),
             ("stored-zero-none", fixture("stored-zero", False), {"normalize": "none"}),
             ("without-percent", fixture(), {"include_percent_expressed": False})]
    for name, dtype in [("float32", np.float32), ("integer32", np.int32), ("boolean", bool)]:
        data = fixture(counts=False)
        data.X = data.X.astype(dtype)
        cases.append((name, data, {}))
    signed = fixture(counts=False)
    signed.X[0, 0] = -3
    cases.append(("signed-none", signed, {"normalize": "none"}))
    numeric = fixture(counts=False)
    numeric.obs["group"] = [2, 2, 10, 10, 1, 1]
    cases.append(("numeric-groups", numeric, {}))
    no_x = fixture()
    no_x.X = None
    cases.append(("absent-X-uses-counts", no_x, {}))
    duplicated = fixture(counts=False)
    dense = duplicated.X.copy()
    values = np.concatenate([dense[0], [3., -3.], dense[1:].ravel()])
    indices = np.concatenate([np.arange(5), [0, 0], np.tile(np.arange(5), 5)])
    indptr = np.array([0, 7, 12, 17, 22, 27, 32])
    duplicated.X = sparse.csr_matrix((values, indices, indptr), shape=dense.shape)
    assert not duplicated.X.has_canonical_format
    cases.append(("duplicate-coordinate-cancellation", duplicated, {"normalize": "none"}))
    boolean_dupes = duplicated.copy()
    boolean_dupes.X = sparse.csr_matrix((duplicated.X.data.astype(bool), duplicated.X.indices.copy(), duplicated.X.indptr.copy()),
                                       shape=duplicated.shape)
    assert not boolean_dupes.X.has_canonical_format
    cases.append(("boolean-duplicate-coordinates", boolean_dupes, {"normalize": "none"}))
    records = []
    for name, data, settings in cases:
        directory, settings = prepare(root, name, data, settings)
        author_reference(directory)
        result = execute(directory)
        assert result.returncode == 0, result.stderr.decode()
        records.append({"case": name, **compare(directory)})
        print(name, "PASS", flush=True)
    return records


def boundaries(root):
    cases = []
    for name, value in [("nan-X", np.nan), ("inf-X", np.inf), ("negative-cp10k", -1.)]:
        data = fixture(counts=False)
        data.X[0, 0] = value
        cases.append((name, data, {}, "finite real" if not np.isfinite(value) else "nonnegative"))
    missing_group = fixture()
    missing_group.obs.loc["c0", "group"] = np.nan
    cases.append(("missing-group", missing_group, {}, "must not be missing"))
    zeros = fixture(counts=False)
    zeros.X[0] = 0
    cases.append(("zero-cell-total", zeros, {}, "positive full-background"))
    counts_nan = fixture()
    counts_nan.layers["counts"] = counts_nan.layers["counts"].astype(float)
    counts_nan.layers["counts"][0, 0] = np.nan
    cases.append(("invalid-preferred-counts", counts_nan, {}, "finite real"))
    duplicated = fixture()
    duplicated.var_names = ["g"] * 5
    cases.append(("duplicate-vars", duplicated, {}, "var_names must be unique"))
    dup_cells = fixture()
    dup_cells.obs_names = ["c"] * 6
    cases.append(("duplicate-cells", dup_cells, {}, "obs_names must be unique"))
    huge = fixture(counts=False)
    huge.X = huge.X.astype(np.uint64)
    huge.X[0, 0] = 2 ** 53 + 1
    cases.append(("inexact-integer", huge, {}, "exact float64 range"))
    duplicated_huge = fixture(counts=False)
    duplicated_huge.X = sparse.csr_matrix((np.array([2 ** 53, 1] + [1] * 5, dtype=np.uint64),
                                          np.array([0, 0, 0, 0, 0, 0, 0]), np.array([0, 2, 3, 4, 5, 6, 7])), shape=(6, 5))
    assert not duplicated_huge.X.has_canonical_format
    cases.append(("inexact-integer-coordinate-sum", duplicated_huge, {"normalize": "none"}, "integer coordinate sums"))
    cases += [("missing-gene", fixture(), {"genes": ["absent"]}, "requested genes are absent"),
              ("duplicate-request-gene", fixture(), {"genes": [GENES[0], GENES[0]]}, "genes must be unique"),
              ("missing-groupby", fixture(), {"groupby": "missing"}, "unique named groupby"),
              ("zero-cells", fixture()[:0].copy(), {}, "nonempty"),
              ("zero-vars", fixture()[:, :0].copy(), {}, "nonempty"),
              ("invalid-normalize", fixture(), {"normalize": "log"}, "cp10k or none")]
    absent_x = fixture(counts=False)
    absent_x.X = None
    cases.append(("absent-chosen-X", absent_x, {"normalize": "none"}, "matrix source is absent"))
    empty_group = fixture(counts=False)
    empty_group.obs["group"] = ["", "a", "a", "b", "b", "b"]
    cases.append(("empty-group", empty_group, {}, "nonempty lexical"))
    too_large = fixture(counts=False)
    too_large.X[:, 0] = 1e308
    cases.append(("mean-overflow", too_large, {"normalize": "none"}, "nonfinite results"))
    records = []
    for name, data, settings, fragment in cases:
        directory, settings = prepare(root, name, data, settings)
        result = execute(directory)
        assert result.returncode == 2 and fragment in result.stderr.decode(), result.stderr.decode()
        assert not (directory / "cluster_mean_expression.parquet").exists()
        records.append({"case": name, "specific_refusal": fragment})
        print(name, "REFUSED", flush=True)
    for name, extra, fragment in [("invalid-array", {"SC_P_R_ARRAY_GENES": 'c("unterminated)'}, "invalid lossless"),
                                  ("numeric-array", {"SC_P_R_ARRAY_GENES": "c(4)"}, "nonempty lexical"),
                                  ("invalid-bool", {"SC_P_BOOL_INCLUDE_PERCENT_EXPRESSED": "1"}, "true or false"),
                                  ("existing-output", {}, "refusing to overwrite"),
                                  ("input-overwrite", {}, "paths must be distinct")]:
        directory, settings = prepare(root, name, fixture())
        if name == "existing-output":
            (directory / "cluster_mean_expression.parquet").write_bytes(b"retain sentinel")
        if name == "input-overwrite":
            extra = {"AUTONOMICS_OUTPUT0": str(directory / "input.h5ad")}
        before = digest(directory / "input.h5ad")
        result = execute(directory, extra)
        assert result.returncode == 2 and fragment in result.stderr.decode(), result.stderr.decode()
        assert digest(directory / "input.h5ad") == before
        if name == "existing-output":
            assert (directory / "cluster_mean_expression.parquet").read_bytes() == b"retain sentinel"
        else:
            assert not (directory / "cluster_mean_expression.parquet").exists()
        records.append({"case": name, "specific_refusal": fragment})
    return records


def main():
    root = Path(sys.argv[1])
    root.mkdir()
    mode = sys.argv[2]
    records = {"positive": positives, "boundary": boundaries}[mode](root)
    (root / "SUMMARY.json").write_text(json.dumps({"mode": mode, "cases": len(records), "records": records, "G0": False}, indent=2) + "\n")


if __name__ == "__main__":
    main()
