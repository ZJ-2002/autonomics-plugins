import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

import anndata as ad
import numpy as np
import pandas as pd
import scipy.sparse as sp


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/pseudobulk_counts.py"


def fixture(values=None, genes=None):
    values = np.array([[1, 0, 2], [3, 1, 0], [4, 0, 1], [2, 3, 0], [0, 1, 3], [2, 2, 1]], dtype=np.int64) if values is None else values
    return ad.AnnData(values, obs=pd.DataFrame({"donor": ["d1", "d1", "d1", "d2", "d2", "d2"],
        "celltype": ["A", "A", "B", "A", "A", "B"],
        "condition": ["ctrl"] * 3 + ["stim"] * 3}, index=[f"c{index}" for index in range(6)]),
        var=pd.DataFrame(index=["g1", "g2", "g3"] if genes is None else genes))


def table(path):
    with path.open(newline="") as handle:
        return list(csv.reader(handle, delimiter="\t"))


def exact_reference(data, layer="", minimum=1):
    values = data.layers[layer] if layer else data.X
    values = values.toarray() if sp.issparse(values) else values
    groups = {}
    for index, row in enumerate(data.obs.to_dict("records")):
        if any(pd.isna(row[key]) or not str(row[key]).strip() for key in ("donor", "celltype")):
            continue
        key = (str(row["donor"]), str(row["celltype"]))
        groups.setdefault(key, []).append(index)
    groups = {key: indices for key, indices in groups.items() if len(indices) >= minimum}
    integer = values.dtype.kind in "biu" or np.equal(values, np.rint(values)).all()
    return {key: [sum(int(values[index, gene]) if integer else float(values[index, gene])
        for index in indices) for gene in range(data.n_vars)] for key, indices in groups.items()}


def run(root, name, data, *, layer="", minimum=1, schema="deseq2", allow="false",
        expected_error=None, output_mode=None, inject=False):
    directory = root / name
    directory.mkdir()
    source = directory / "input.h5ad"
    data.write_h5ad(source)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    outputs = [directory / filename for filename in ["counts.tsv", "samples.tsv", "pseudobulk.log"]]
    if output_mode == "sentinel":
        outputs[0].write_text("IMMUTABLE SENTINEL\n")
    elif output_mode == "symlink":
        outputs[0].symlink_to("absent.tsv")
    elif output_mode == "alias":
        outputs[1] = outputs[0]
    elif output_mode == "input":
        outputs[0] = source
    environment = dict(os.environ, PB_SAMPLE_COL="donor", PB_CELLTYPE_COL="celltype",
        PB_CONDITION_COLUMN="condition", PB_MIN_CELLS=str(minimum), PB_SCHEMA=schema,
        PB_LAYER=layer, PB_ALLOW_NON_INTEGER=allow, AUTONOMICS_INPUT0=str(source),
        AUTONOMICS_OUTPUT0=str(outputs[0]), AUTONOMICS_OUTPUT1=str(outputs[1]), AUTONOMICS_OUTPUT2=str(outputs[2]))
    command = [sys.executable, str(SCRIPT)]
    if inject:
        command = [sys.executable, "-c", "import os,runpy,sys; original=os.link; calls=0\ndef link(source,destination):\n global calls\n calls+=1\n if calls==2: raise OSError('INJECTED_SECOND_LINK_FAILURE')\n return original(source,destination)\nos.link=link\nrunpy.run_path(sys.argv[1],run_name='__main__')", str(SCRIPT)]
    result = subprocess.run(command, env=environment, capture_output=True)
    (directory / "stdout.txt").write_bytes(result.stdout)
    (directory / "stderr.txt").write_bytes(result.stderr)
    assert source_hash == hashlib.sha256(source.read_bytes()).hexdigest(), name
    if expected_error:
        assert result.returncode != 0 and expected_error in result.stderr.decode(), (name, result.stderr.decode())
        if output_mode == "sentinel":
            assert outputs[0].read_text() == "IMMUTABLE SENTINEL\n"
        elif output_mode == "symlink":
            assert outputs[0].is_symlink() and os.readlink(outputs[0]) == "absent.tsv"
        elif output_mode != "input":
            assert not any(path.exists() for path in outputs), name
        assert not list(directory.glob(".pseudobulk-*")), name
        return {"case": name, "refused": True, "fragment": expected_error, "exit": result.returncode}
    assert result.returncode == 0, (name, result.stderr.decode())
    counts, samples = table(outputs[0]), table(outputs[1])
    assert counts[0][0] == ("gene_id" if schema == "deseq2" else "gene")
    assert samples[0] == (["sample_id", "sample", "celltype", "n_cells", "condition"] if schema == "deseq2"
        else ["pseudobulk_id", "sample", "celltype", "n_cells"])
    assert [row[0] for row in counts[1:]] == list(data.var_names)
    assert [row[0] for row in samples[1:]] == counts[0][1:]
    assert len(set(counts[0][1:])) == len(counts[0][1:])
    expected = exact_reference(data, layer, minimum)
    assert len(counts) == data.n_vars + 1
    assert all(len(row) == len(expected) + 1 for row in counts)
    assert all(len(row) == len(samples[0]) for row in samples)
    for position, row in enumerate(samples[1:]):
        actual = [float(gene[position + 1]) if allow == "true" else int(gene[position + 1]) for gene in counts[1:]]
        golden = expected[(row[1], row[2])]
        assert np.allclose(actual, golden, atol=1e-12, rtol=0) if allow == "true" else actual == golden
        members = [metadata for metadata in data.obs.to_dict("records")
            if str(metadata["donor"]) == row[1] and str(metadata["celltype"]) == row[2]]
        assert int(row[3]) == len(members)
        if schema == "deseq2":
            assert {str(metadata["condition"]) for metadata in members} == {row[4]}
    assert len(samples) - 1 == len(expected)
    assert outputs[2].stat().st_size > 0 and not list(directory.glob(".pseudobulk-*"))
    return {"case": name, "exact_independent_reference": True, "outputs_readable": True, "exit": 0,
        "sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in outputs}}


def main(root):
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for name, conversion in [("dense", np.asarray), ("csr", sp.csr_matrix), ("csc", sp.csc_matrix),
            ("uint", lambda value: value.astype(np.uint32)), ("integer-float", lambda value: value.astype(np.float64)),
            ("boolean", lambda value: value.astype(bool))]:
        data = fixture()
        data.X = conversion(data.X)
        records.append(run(root, name, data))
    data = fixture()
    data.layers["counts"] = sp.csr_matrix(data.X * 3)
    data.X = data.X.astype(float) / 3
    records.append(run(root, "named-counts-layer", data, layer="counts"))
    records.append(run(root, "minimum-filter", fixture(), minimum=2))
    records.append(run(root, "legacy", fixture(), schema="legacy"))
    data = fixture()
    data.obs.loc["c1", "donor"] = ""
    records.append(run(root, "missing-label-excluded", data))
    data = fixture()
    data.obs["donor"] = ["a__b"] * 3 + ["a"] * 3
    data.obs["celltype"] = ["c"] * 3 + ["b__c"] * 3
    records.append(run(root, "collision-safe-ids", data))
    data = fixture(np.full((6, 3), 2 ** 60, dtype=np.int64))
    records.append(run(root, "large-safe-independent-gene-sums", data))
    data = fixture()
    data.X = data.X.astype(float) / 3
    records.append(run(root, "explicit-noninteger-not-counts", data, allow="true"))
    for name, identifier in [("leading-double-quote", chr(34) + "leading"),
            ("middle-double-quote", "middle" + chr(34) + "quote"),
            ("single-quote", "O'Gene"), ("comma", "gene,comma"),
            ("literal-NA", "NA"), ("leading-zero", "0001"), ("unicode", "中文基因")]:
        data = fixture(genes=[identifier, "g2", "g3"])
        data.obs["donor"] = [identifier] * 3 + ["d2"] * 3
        records.append(run(root, name, data))
    for name, value, error in [("nan", np.nan, "non-finite"), ("inf", np.inf, "non-finite"),
            ("negative", -1, "negative"), ("noninteger", 0.5, "non-integer entries")]:
        data = fixture()
        data.X = data.X.astype(float)
        data.X[0, 0] = value
        records.append(run(root, name, data, expected_error=error))
    data = fixture(np.full((6, 3), 2 ** 62, dtype=np.int64))
    records.append(run(root, "group-overflow", data, expected_error="group sum exceeds"))
    data = fixture(np.full((6, 3), 2 ** 63, dtype=np.uint64))
    records.append(run(root, "uint-out-of-range", data, expected_error="int64-safe range"))
    for sparse_type in [sp.csr_matrix, sp.csc_matrix]:
        data = fixture()
        coordinate = sp.csr_matrix((np.array([2 ** 62] * 3 + [1] * 5, dtype=np.float64),
            np.array([0, 0, 0, 0, 0, 0, 0, 0]), np.array([0, 3, 4, 5, 6, 7, 8])), shape=(6, 3))
        data.X = coordinate if sparse_type is sp.csr_matrix else coordinate.tocsc()
        records.append(run(root, sparse_type.__name__ + "-duplicate-overflow", data, expected_error="group sum exceeds"))
    for name, genes in [("gene-tab", ["g1\tg2", "g2", "g3"]), ("gene-newline", ["g1\ng2", "g2", "g3"]),
            ("gene-empty", ["", "g2", "g3"]), ("gene-duplicate", ["g1", "g1", "g3"])]:
        records.append(run(root, name, fixture(genes=genes), expected_error="not unique" if name == "gene-duplicate" else "gene names must"))
    data = fixture()
    data.obs.loc["c0", "condition"] = "wrong"
    records.append(run(root, "within-group-condition-inconsistency", data, expected_error="not constant"))
    data = fixture()
    data.obs["condition"] = ["ctrl\nextra"] * 3 + ["stim"] * 3
    records.append(run(root, "condition-newline", data, expected_error="condition values cannot"))
    records.append(run(root, "minimum-zero", fixture(), minimum=0, expected_error="positive integer"))
    records.append(run(root, "invalid-boolean", fixture(), allow="yes", expected_error="true or false"))
    for mode, error in [("sentinel", "refusing overwrite"), ("symlink", "refusing overwrite"),
            ("alias", "must be distinct"), ("input", "refusing overwrite")]:
        records.append(run(root, "output-" + mode, fixture(), output_mode=mode, expected_error=error))
    records.append(run(root, "ordinary-second-publish-failure", fixture(), inject=True, expected_error="INJECTED_SECOND_LINK_FAILURE"))
    summary = {"cases": len(records), "records": records,
        "versions": {key: importlib.metadata.version(key) for key in ["anndata", "numpy", "scipy", "pandas"]},
        "source_sha256": hashlib.sha256(SCRIPT.read_bytes()).hexdigest(), "G0": False,
        "scope": "Small isolated integer/donor grouping and explicit noninteger branch; not full-scale or scientific qualification"}
    (root / "SUMMARY.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
