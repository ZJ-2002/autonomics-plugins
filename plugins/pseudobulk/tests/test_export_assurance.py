import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import anndata as ad
import h5py
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import scipy.sparse as sp


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/h5ad_export_matrix.py'


def fixture(kind='dense', size=7):
    dense = np.arange(size * 4).reshape(size, 4) % 5 - 2
    dense[dense == -1] = 0
    value = dense.astype(np.int64)
    if kind == 'csr':
        value = sp.csr_matrix(value)
    elif kind == 'csc':
        value = sp.csc_matrix(value)
    elif kind == 'float32':
        value = dense.astype(np.float32) / 4
    elif kind == 'bool':
        value = dense > 0
    elif kind == 'wide-exact':
        value[0, 0] = 2**54
        value[1, 0] = -(2**63)
    elif kind == 'nonfinite':
        value = dense.astype(np.float64)
        value[0, :3] = [np.nan, np.inf, -np.inf]
    names = ['0001', 'NA', '炎症', 'tab\tkey', 'line\nbreak', 'quoted"', ''][:size]
    names = [(name or 'last') for name in names] if size <= 7 else [f'c{index:04}' for index in range(size)]
    obs = pd.DataFrame({'text': ['NA', '', 'null', 'a\tb', 'a\nb', '"q"', '0'][:size] if size <= 7 else ['NA'] * size, 'number': np.arange(size, dtype=np.int64), 'missing': [np.nan] + list(np.arange(1, size, dtype=float)), 'type': pd.Categorical(['a' if index % 2 else 'b' for index in range(size)], categories=['b', 'a', 'unused'], ordered=True)}, index=pd.Index(names, name='original_cells'))
    var = pd.DataFrame({'symbol': ['NA', '', 'G3', 'G4'], 'integer': [2**53 + 1, 2, 3, 4]}, index=pd.Index(['0001', 'NA', '基因', 'gene\t4'], name='original_genes'))
    data = ad.AnnData(X=value, obs=obs, var=var)
    data.layers['alternate'] = value.copy() * 2
    data.raw = data.copy()
    return data


def run_node(directory, data, layer='X', chunk='100', mode=None, corrupt=None):
    directory.mkdir(parents=True)
    source = directory / 'input.h5ad'
    compression = 'lzf' if directory.name == 'lzf' else 'gzip' if directory.name == 'gzip' else None
    data.write_h5ad(source, compression=compression)
    if corrupt:
        corrupt(source)
    outputs = [directory / filename for filename in ['matrix.parquet', 'obs.tsv', 'var.tsv', 'export.log']]
    before = {}
    if mode == 'stale':
        outputs[2].write_bytes(b'ORIGINAL_RESULT')
        before[str(outputs[2])] = outputs[2].read_bytes()
    elif mode == 'dangling':
        outputs[2].symlink_to('not-created')
    elif mode == 'alias':
        outputs[2] = outputs[1]
    elif mode == 'input-alias':
        outputs[0] = source
        before[str(source)] = source.read_bytes()
    env = dict(os.environ, EXPORT_LAYER=layer, EXPORT_CHUNK=chunk)
    env['AUTONOMICS_INPUT0'] = str(source)
    env.update({f'AUTONOMICS_OUTPUT{number}': str(path) for number, path in enumerate(outputs)})
    if mode == 'second-link-failure':
        driver = directory / 'inject-link-failure.py'
        driver.write_text("import importlib.util,os\ns=importlib.util.spec_from_file_location('subject'," + repr(str(SCRIPT)) + ")\nm=importlib.util.module_from_spec(s);s.loader.exec_module(m)\noriginal=os.link\ncalls=0\ndef fault(*args,**kwargs):\n global calls\n calls+=1\n if calls==2: raise OSError('injected second-link failure')\n return original(*args,**kwargs)\nm.os.link=fault\nm.run()\n")
        command = [sys.executable, str(driver)]
    else:
        command = [sys.executable, str(SCRIPT)]
    process = subprocess.run(command, env=env, capture_output=True, text=True)
    (directory / 'stdout.txt').write_text(process.stdout)
    (directory / 'stderr.txt').write_text(process.stderr)
    (directory / 'exit.txt').write_text(str(process.returncode) + '\n')
    for path, content in before.items():
        assert Path(path).read_bytes() == content
    return source, outputs, process


def damage(path, kind):
    with h5py.File(path, 'r+') as handle:
        if kind == 'shape':
            del handle['X']
            handle.create_dataset('X', data=np.zeros((1, 1)))
        elif kind == 'encoding':
            handle['X'].attrs['encoding-type'] = 'unknown_sparse'
        elif kind == 'index':
            handle['X/indices'][0] = 999
        elif kind == 'pointer':
            handle['X/indptr'][-1] = 999
        elif kind == 'late-unsafe-integer':
            handle['X'][-1, -1] = 2**53 + 1


def compare(directory, source, outputs, layer):
    reference = ad.read_h5ad(source)
    selection = reference.X if layer in {'', 'X'} else reference.layers[layer.removeprefix('layers/')]
    dense = selection.toarray() if sp.issparse(selection) else np.asarray(selection)
    expected = []
    for row in range(dense.shape[0]):
        for column in range(dense.shape[1]):
            value = dense[row, column]
            if value != 0:
                expected.append((str(reference.obs_names[row]), str(reference.var_names[column]), float(value)))
    actual = pq.read_table(outputs[0])
    assert actual.schema == pa.schema([('cell_id', pa.string()), ('gene', pa.string()), ('value', pa.float64())])
    result = list(zip(*[actual.column(name).to_pylist() for name in ['cell_id', 'gene', 'value']]))
    assert len(result) == len(expected)
    assert [(row[0], row[1]) for row in result] == [(row[0], row[1]) for row in expected]
    np.testing.assert_array_equal(np.array([row[2] for row in result]), np.array([row[2] for row in expected]))
    assert len(set((row[0], row[1]) for row in result)) == len(result)
    expected_obs = reference.obs.to_csv(sep='\t', index_label='cell_id')
    expected_var = reference.var.to_csv(sep='\t', index_label='gene_id')
    assert outputs[1].read_text() == expected_obs and outputs[2].read_text() == expected_var
    log = dict(line.split('\t', 1) for line in outputs[3].read_text().splitlines())
    assert log['selection_path'] == ('X' if layer in {'', 'X'} else 'layers/' + layer.removeprefix('layers/'))
    assert log['input_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    typed = json.loads(log['metadata_schema_json'])
    for axis, frame in [('obs', reference.obs), ('var', reference.var)]:
        assert typed[axis]['index_name'] == frame.index.name and typed[axis]['rows'] == len(frame)
        assert [field['name'] for field in typed[axis]['fields']] == list(frame.columns)
        for field in typed[axis]['fields']:
            series = frame[field['name']]
            assert field['dtype'] == str(series.dtype)
            assert field['missing_rows'] == np.flatnonzero(series.isna().to_numpy()).tolist()
            if isinstance(series.dtype, pd.CategoricalDtype):
                assert field['categories'] == series.cat.categories.tolist() and field['ordered'] == series.cat.ordered
    assert 'NOT_VERIFIED' in log['scientific_eligibility']
    (directory / 'reference.tsv.json').write_text(json.dumps({'matrix_values': len(expected), 'whole_obs_csv_bytes_match': True, 'whole_var_csv_bytes_match': True, 'schema_and_missing_masks_match': True, 'value_comparison': 'EXACT_WITH_NAN_MASKS;NO_FLOAT_TOLERANCE'}, indent=2))
    return {'case': directory.name, 'matrix_values': len(expected), 'status': 'PASS'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', type=Path)
    arguments = parser.parse_args()
    records = []
    cases = [(kind, fixture(kind), 'X', '100') for kind in ['dense', 'csr', 'csc', 'float32', 'bool', 'wide-exact', 'nonfinite']]
    cases += [('plain-layer', fixture('csr'), 'alternate', '100'), ('prefixed-layer', fixture('csc'), 'layers/alternate', '100'), ('empty-default', fixture(), '', '100'), ('multiple-row-groups', fixture('csr', 201), 'X', '100'), ('zero-cells', ad.AnnData(np.empty((0, 2)), obs=pd.DataFrame(index=[]), var=pd.DataFrame(index=['g1', 'g2'])), 'X', '100'), ('zero-genes', ad.AnnData(np.empty((2, 0)), obs=pd.DataFrame(index=['c1', 'c2']), var=pd.DataFrame(index=[])), 'X', '100')]
    duplicated = fixture()
    duplicated.X = sp.csr_matrix((np.array([1, -1, 2, 3, 4]), np.array([0, 0, 2, 2, 1]), np.array([0, 4, 5, 5, 5, 5, 5, 5])), shape=(7, 4))
    cases.append(('sparse-duplicate-cancellation', duplicated, 'X', '100'))
    selected_without_x = fixture()
    selected_without_x.X = None
    cases.append(('selected-layer-without-X', selected_without_x, 'layers/alternate', '100'))
    alternate_named_x = fixture()
    alternate_named_x.layers['X'] = alternate_named_x.X * 3
    cases.append(('selected-layer-named-X', alternate_named_x, 'layers/X', '100'))
    for name, data, layer, chunk in cases:
        directory = arguments.evidence / name
        source, outputs, process = run_node(directory, data, layer, chunk)
        assert process.returncode == 0, (name, process.stderr)
        records.append(compare(directory, source, outputs, layer))
        print(name, 'PASS', flush=True)
    negatives = []
    for name, change, layer, chunk, mode, corrupt in [
        ('unsafe-integer', lambda data: setattr(data, 'X', np.full(data.shape, 2**53 + 1, dtype=np.uint64)), 'X', '100', None, None),
        ('duplicate-cells', lambda data: setattr(data, 'obs_names', ['same'] * data.n_obs), 'X', '100', None, None),
        ('duplicate-genes', lambda data: setattr(data, 'var_names', ['same'] * data.n_vars), 'X', '100', None, None),
        ('empty-cell-id', lambda data: setattr(data, 'obs_names', [''] + data.obs_names.tolist()[1:]), 'X', '100', None, None),
        ('reserved-obs-key', lambda data: data.obs.__setitem__('cell_id', 'conflicting'), 'X', '100', None, None),
        ('reserved-var-key', lambda data: data.var.__setitem__('gene_id', 'conflicting'), 'X', '100', None, None),
        ('missing-layer', None, 'not-a-layer', '100', None, None),
        ('layer-traversal', None, 'layers/../X', '100', None, None),
        ('zero-chunk', None, 'X', '0', None, None),
        ('negative-chunk', None, 'X', '-1', None, None),
        ('noninteger-chunk', None, 'X', '100.1', None, None),
        ('stale-output', None, 'X', '100', 'stale', None),
        ('dangling-output', None, 'X', '100', 'dangling', None),
        ('output-alias', None, 'X', '100', 'alias', None),
        ('input-alias', None, 'X', '100', 'input-alias', None),
        ('second-link-rollback', None, 'X', '100', 'second-link-failure', None),
    ]:
        data = fixture()
        if change:
            change(data)
        directory = arguments.evidence / name
        source, outputs, process = run_node(directory, data, layer, chunk, mode, corrupt)
        assert process.returncode != 0, name
        for number, path in enumerate(outputs):
            if mode in {'stale', 'dangling'} and number == 2:
                assert os.path.lexists(path), name
                if mode == 'dangling':
                    assert path.is_symlink() and os.readlink(path) == 'not-created', name
            elif mode == 'input-alias' and number == 0:
                assert path == source, name
            else:
                assert not os.path.lexists(path), name
        assert not list(directory.glob('.h5ad-export-*')), name
        negatives.append({'case': name, 'status': 'REFUSED', 'exit': process.returncode, 'stderr_file': str(directory / 'stderr.txt')})
        print(name, 'REFUSED', flush=True)
    for name, data, corrupt in [
        ('matrix-shape-mismatch', fixture(), lambda path: damage(path, 'shape')),
        ('unknown-sparse-encoding', fixture('csr'), lambda path: damage(path, 'encoding')),
        ('sparse-index-out-of-bounds', fixture('csc'), lambda path: damage(path, 'index')),
        ('sparse-pointer-out-of-bounds', fixture('csr'), lambda path: damage(path, 'pointer')),
        ('late-unsafe-integer', ad.AnnData(np.ones((201, 4), dtype=np.uint64), obs=pd.DataFrame(index=[f'c{index}' for index in range(201)]), var=pd.DataFrame(index=['g1', 'g2', 'g3', 'g4'])), lambda path: damage(path, 'late-unsafe-integer')),
        ('complex-matrix', ad.AnnData(np.array([[1+2j]]), obs=pd.DataFrame(index=['c']), var=pd.DataFrame(index=['g'])), None),
        ('sparse-integer-sum-overflow', ad.AnnData(sp.csr_matrix((np.array([2**63 - 1, 2**63 - 1], dtype=np.int64), np.array([0, 0]), np.array([0, 2])), shape=(1, 1)), obs=pd.DataFrame(index=['c']), var=pd.DataFrame(index=['g'])), None),
    ]:
        directory = arguments.evidence / name
        source, outputs, process = run_node(directory, data, corrupt=corrupt)
        assert process.returncode != 0, name
        assert all(not path.exists() for path in outputs) and not list(directory.glob('.h5ad-export-*')), name
        negatives.append({'case': name, 'status': 'REFUSED', 'exit': process.returncode, 'stderr_file': str(directory / 'stderr.txt')})
        print(name, 'REFUSED', flush=True)
    (arguments.evidence / 'SUMMARY.json').write_text(json.dumps({'status': 'PASS_COMPLETE_EXACT_EXPORT_AND_NEGATIVE_BOUNDARIES', 'positive_cases': records, 'negative_cases': negatives, 'original_ports': 4, 'actual_method_reference': 'Direct official AnnData read_h5ad plus independent whole-matrix coordinate enumeration and exact Pandas to_csv; not a fresh complete dependency stack installation or statistical algorithm certificate'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
