import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import anndata as ad
import h5py
import numpy as np
import pandas as pd
from scipy import sparse

from qc_compare import compare_value


FAMILY = Path(__file__).resolve().parents[1]
SCRIPT = FAMILY / "scripts/marker_annotate.py"


def fixture():
    data = ad.AnnData(np.array([[9., 0., 4., 8.], [1., 6., 0., 3.], [0., 0., 0., 0.], [2., 3., 0., 1.]]),
        obs=pd.DataFrame({"cluster": ['A', 'A', 'B', 'B'], "donor": ['d1', 'd1', 'd2', 'd2']}, index=['c1', 'c2', 'c3', 'c4']),
        var=pd.DataFrame({"tag": ['one', 'two', 'three', 'background']}, index=['g1', 'g2', 'g3', 'background']))
    data.layers['counts'] = np.full(data.shape, 77., dtype=np.float32)
    data.obsm['old_embedding'] = np.arange(8, dtype=np.float32).reshape(4, 2)
    data.varm['old_loading'] = np.arange(8, dtype=np.float64).reshape(4, 2)
    data.obsp['old_graph'] = sparse.eye(4, format='csr')
    data.varp['old_graph'] = sparse.eye(4, format='csr')
    data.uns['old_data'] = {'meaning': 'unchanged', 'values': np.array([1, 2, 3])}
    data.var['integer_metadata'] = np.array([2 ** 53 + 1, 2, 3, 4], dtype=np.int64)
    raw = ad.AnnData(np.ones((4, 2)), obs=data.obs.copy(), var=pd.DataFrame(index=['different1', 'different2']))
    data.raw = raw
    return data


def compare(directory):
    actual, expected = ad.read_h5ad(directory / 'output.h5ad'), ad.read_h5ad(directory / 'reference.h5ad')
    assert actual.shape == expected.shape
    finite = compare_value(actual.X, expected.X) + compare_value(actual.obs, expected.obs) + compare_value(actual.var, expected.var)
    for key in ['layers', 'obsm', 'varm', 'obsp', 'varp', 'uns']:
        finite += compare_value(dict(getattr(actual, key)), dict(getattr(expected, key)))
    finite += compare_value(actual.raw.X, expected.raw.X) + compare_value(actual.raw.var, expected.raw.var)
    with h5py.File(directory / 'output.h5ad') as observed, h5py.File(directory / 'reference.h5ad') as author:
        observed_paths, author_paths = [], []
        observed.visit(observed_paths.append)
        author.visit(author_paths.append)
        assert observed_paths == author_paths
        for name in ['/'] + author_paths:
            left, right = observed[name], author[name]
            assert type(left) == type(right)
            finite += compare_value(dict(left.attrs), dict(right.attrs))
            if isinstance(left, h5py.Dataset):
                assert left.dtype == right.dtype and left.shape == right.shape
                finite += compare_value(left[()], right[()])
    reference = json.loads((directory / 'reference.json').read_text())
    report = json.loads((directory / 'report.json').read_text())
    request = json.loads((directory / 'request.json').read_text())
    assert report['cell_ids'] == expected.obs_names.tolist() and report['gene_ids'] == expected.var_names.tolist()
    assert report['label_counts'] == reference['label_counts'] and report['fallback_count'] == reference['fallback_count']
    assert report['marker_label_order'] == list(request['marker_sets'])
    assert report['statistical_official_equivalence'] == 'NOT_APPLICABLE_CUSTOM_ARITHMETIC_RULE'
    assert not report['calibrated_probability_or_biological_specificity'] and not report['G0']
    assert report['input_sha256'] == hashlib.sha256((directory / 'input.h5ad').read_bytes()).hexdigest()
    assert report['matrix_source'] == 'X only; raw and layers ignored'
    assert report['groupby'] == request['groupby'] and report['normalize'] == request['normalize']
    assert report['min_score'] == float(request['min_score']) and report['unknown_label'] == request['unknown_label']
    assert report['mode'] == ('cluster' if request['groupby'] is not None else 'per_cell')
    assert report['cells'] == expected.n_obs and report['scientific_input_qualification'] is False
    for name, genes in request['marker_sets'].items():
        actual_panel = report['marker_sets'][name]
        present = [gene for gene in genes if gene in expected.var_names]
        assert actual_panel['requested_members'] == genes
        assert actual_panel['present_members'] == [gene for gene in genes if gene in expected.var_names]
        assert actual_panel['missing_genes'] == sorted(set(genes) - set(expected.var_names))
        assert actual_panel['genes_requested'] == len(genes) and actual_panel['genes_present'] == len(present)
        assert actual_panel['duplicate_members'] == {gene: genes.count(gene) for gene in dict.fromkeys(genes) if genes.count(gene) > 1}
        assert actual_panel['effective_weights'] == {gene: present.count(gene) / len(present) for gene in dict.fromkeys(present)}
        assert abs(sum(actual_panel['effective_weights'].values()) - 1) < 1e-12
    if request.get('groupby'):
        assert report['cluster_labels'] == {name: values['label'] for name, values in reference['cluster_scores'].items()}
        for name, values in reference['cluster_scores'].items():
            assert report['cluster_scores'][name]['n_cells'] == values['n_cells']
            np.testing.assert_allclose(report['cluster_scores'][name]['scores'], values['scores'], atol=1e-12, rtol=0)
    return {'whole_AnnData_preserved_and_Decimal_means_labels_scores_margins': True, 'finite_checked': int(finite), 'G0': False}


def run(root, name, data, *, markers=None, normalize='log_cp10k', groupby=None, minimum=0., unknown='Unknown',
        raw_json=None, error=None, mode=None, inject=False):
    directory = root / name
    directory.mkdir()
    data.write_h5ad(directory / 'input.h5ad')
    markers = {'type1': ['g1'], 'type2': ['g2', 'g3']} if markers is None else markers
    request = {'marker_sets': markers, 'normalize': normalize, 'groupby': groupby, 'min_score': minimum, 'unknown_label': unknown}
    (directory / 'request.json').write_text(json.dumps(request) + '\n')
    output, report = directory / 'output.h5ad', directory / 'report.json'
    if mode == 'sentinel':
        output.write_text('IMMUTABLE SENTINEL')
    elif mode == 'symlink':
        output.symlink_to('absent.h5ad')
    elif mode == 'alias':
        report = output
    elif mode == 'input':
        output = directory / 'input.h5ad'
    source_sha = hashlib.sha256((directory / 'input.h5ad').read_bytes()).hexdigest()
    environment = dict(os.environ, AUTONOMICS_INPUT0=str(directory / 'input.h5ad'), AUTONOMICS_OUTPUT0=str(output),
        AUTONOMICS_OUTPUT1=str(report), SC_P_JSON_MARKER_SETS=raw_json if raw_json is not None else json.dumps(markers),
        SC_P_STR_NORMALIZE=normalize, SC_P_STR_GROUPBY=groupby or '', SC_P_NUM_MIN_SCORE=str(minimum), SC_P_STR_UNKNOWN_LABEL=unknown)
    command = [sys.executable, str(SCRIPT)]
    if inject:
        code = "import importlib.util,os,sys\nspecification=importlib.util.spec_from_file_location('subject',sys.argv[1])\nsubject=importlib.util.module_from_spec(specification);specification.loader.exec_module(subject)\n"
        if inject == 'input-mutation':
            code += "original=subject.ad.AnnData.write_h5ad\ndef write(*args,**kwargs):\n result=original(*args,**kwargs)\n with open(os.environ['AUTONOMICS_INPUT0'],'ab') as stream:stream.write(b'MUTATED')\n return result\nsubject.ad.AnnData.write_h5ad=write\n"
        elif inject == 'H5-write':
            code += "def write(*args,**kwargs):raise OSError('INJECTED_H5_WRITE_FAILURE')\nsubject.ad.AnnData.write_h5ad=write\n"
        else:
            code += "original=os.link\ncalls=0\nfirst=None\ndef link(source,destination):\n global calls,first\n calls+=1\n if calls==1:first=(source,destination)\n if calls==2:\n"
            if inject == 'replacement-symlink':
                code += "  os.unlink(first[1]);os.symlink(first[0],first[1])\n"
            code += "  raise OSError('INJECTED_SECOND_LINK_FAILURE')\n return original(source,destination)\nos.link=link\n"
        command = [sys.executable, '-c', code + 'sys.exit(subject.main())', str(SCRIPT)]
    result = subprocess.run(command, env=environment, capture_output=True)
    (directory / 'stdout.txt').write_bytes(result.stdout)
    (directory / 'stderr.txt').write_bytes(result.stderr)
    changed = hashlib.sha256((directory / 'input.h5ad').read_bytes()).hexdigest() != source_sha
    assert changed == (inject == 'input-mutation')
    if error:
        assert result.returncode != 0 and error in result.stderr.decode(), (name, result.stderr.decode())
        if mode == 'sentinel':
            assert output.read_text() == 'IMMUTABLE SENTINEL'
        elif mode == 'symlink':
            assert output.is_symlink()
        elif inject == 'replacement-symlink':
            assert output.is_symlink()
        elif mode != 'input':
            assert not output.exists()
        if report != output:
            assert not report.exists()
        assert not list(directory.glob('.marker-annotate-*'))
        return {'case': name, 'specific_refusal': error, 'exit': result.returncode}
    assert result.returncode == 0, (name, result.stderr.decode())
    reference = subprocess.run([sys.executable, str(FAMILY / 'tests/marker_reference.py'), str(directory)],
        env=dict(os.environ, PYTHONPATH=os.environ['MARKER_REFERENCE_LIBRARY']), capture_output=True)
    (directory / 'reference.stdout.txt').write_bytes(reference.stdout)
    (directory / 'reference.stderr.txt').write_bytes(reference.stderr)
    assert reference.returncode == 0, reference.stderr.decode()
    return {'case': name, 'independent_custom_math_reference': compare(directory), 'exit': 0}


def main(root):
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for normalize in ['log_cp10k', 'none']:
        for kind in ['dense', 'csr', 'csc', 'float32', 'integer', 'boolean']:
            data = fixture()
            if kind == 'csr': data.X = sparse.csr_matrix(data.X)
            if kind == 'csc': data.X = sparse.csc_matrix(data.X)
            if kind == 'float32': data.X = data.X.astype(np.float32)
            if kind == 'integer': data.X = data.X.astype(np.int64)
            if kind == 'boolean': data.X = data.X.astype(bool)
            records.append(run(root, normalize + '-' + kind, data, normalize=normalize))
    records.append(run(root, 'cluster-unknown-fixed', fixture(), groupby='cluster', minimum=100))
    records.append(run(root, 'cluster-assigned-own-score', fixture(), groupby='cluster', normalize='none'))
    records.append(run(root, 'reserved-marker-label', fixture(), groupby='cluster', markers={'__group__': ['g1'], 'type2': ['g2']}))
    records.append(run(root, 'single-list-margin', fixture(), markers={'only': ['g1']}, normalize='none'))
    records.append(run(root, 'repeat-members-retained', fixture(), markers={'weighted': ['g1', 'g1', 'g2'], 'other': ['g3']}, normalize='none'))
    records.append(run(root, 'missing-members-disclosed', fixture(), markers={'partial': ['g1', 'absent'], 'other': ['g2']}))
    records.append(run(root, 'tie-first-JSON', fixture(), markers={'first': ['g1'], 'second': ['g1']}))
    records.append(run(root, 'strict-threshold', fixture(), markers={'only': ['g1']}, normalize='none', minimum=9))
    records.append(run(root, 'unknown-name-also-marker', fixture(), markers={'Unknown': ['g1'], 'other': ['g2']}, groupby='cluster', normalize='none'))
    data = fixture(); data.X = data.X - 3
    records.append(run(root, 'signed-none-expression', data, normalize='none', minimum=-2))
    for name, value in [('tiny-positive', 1e-320), ('large-positive', 1e308)]:
        data = fixture(); data.X = np.full(data.shape, value)
        records.append(run(root, name, data, error='normalization'))
    data = fixture(); data.X = sparse.csr_matrix((np.array([2 ** 53, 1, -(2 ** 53)] + [1] * 3, dtype=np.int64),
        np.array([0, 0, 0, 0, 0, 0]), np.array([0, 3, 4, 5, 6])), shape=(4, 4))
    records.append(run(root, 'integer-duplicate-cancellation-exact', data, normalize='none', markers={'only': ['g1']}))
    for name, value in [('nan', np.nan), ('infinite', np.inf)]:
        data = fixture(); data.X[0, 0] = value
        records.append(run(root, name, data, error='finite real'))
    data = fixture(); data.X[0, 0] = -1
    records.append(run(root, 'negative-cp10k', data, error='nonnegative X'))
    data = fixture(); data.X = data.X.astype(np.int64); data.X[0, 0] = 2 ** 53 + 1
    records.append(run(root, 'integer-outside-range', data, error='exact float64'))
    records.append(run(root, 'missing-group-column', fixture(), groupby='absent', error='absent from obs'))
    data = fixture(); data.obs.loc['c1', 'cluster'] = np.nan
    records.append(run(root, 'missing-group-label', data, groupby='cluster', error='missing or blank'))
    data = fixture(); data.obs['cluster'] = [np.inf, 1., 2., 2.]
    records.append(run(root, 'infinite-numeric-group', data, groupby='cluster', error='nonfinite numeric cluster'))
    for label in ['NA', '0001', '__group__', '未分类', 'None']:
        records.append(run(root, 'literal-unknown-' + label, fixture(), groupby='cluster', minimum=100, unknown=label))
    for field in ['marker_label', 'marker_score', 'marker_margin']:
        data = fixture(); data.obs[field] = 1
        records.append(run(root, 'old-' + field, data, error='cannot be overwritten'))
    data = fixture(); data.uns['marker_annotate_params'] = {'old': 'value'}
    records.append(run(root, 'old-params', data, error='cannot be overwritten'))
    records.append(run(root, 'duplicate-JSON-key', fixture(), raw_json='{"same":["g1"],"same":["g2"]}', error='duplicate JSON key'))
    records.append(run(root, 'invalid-JSON', fixture(), raw_json='broken', error='strict JSON'))
    records.append(run(root, 'JSON-NaN', fixture(), raw_json='{"bad":[NaN]}', error='strict JSON'))
    records.append(run(root, 'no-present-members', fixture(), markers={'absent': ['missing']}, error='no genes present'))
    records.append(run(root, 'empty-marker-list', fixture(), markers={'empty': []}, error='nonempty gene'))
    records.append(run(root, 'invalid-normalization', fixture(), normalize='automatic', error='normalize must'))
    records.append(run(root, 'nonfinite-threshold', fixture(), minimum=np.inf, error='finite number'))
    for mode, error in [('sentinel', 'refusing overwrite'), ('symlink', 'refusing overwrite'), ('alias', 'must be distinct'), ('input', 'refusing overwrite')]:
        records.append(run(root, 'output-' + mode, fixture(), mode=mode, error=error))
    records.append(run(root, 'ordinary-rollback', fixture(), inject=True, error='INJECTED_SECOND_LINK_FAILURE'))
    records.append(run(root, 'replacement-symlink-rollback', fixture(), inject='replacement-symlink', error='INJECTED_SECOND_LINK_FAILURE'))
    records.append(run(root, 'H5-write-failure', fixture(), inject='H5-write', error='INJECTED_H5_WRITE_FAILURE'))
    records.append(run(root, 'input-mutation-during-staging', fixture(), inject='input-mutation', error='input changed during marker output staging'))
    (root / 'SUMMARY.json').write_text(json.dumps({'cases': len(records), 'records': records,
        'script_sha256': hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
        'statistical_official_equivalence': 'NOT_APPLICABLE_CUSTOM_ARITHMETIC_RULE', 'G0': False}, indent=2) + '\n')
    print('CASES', len(records))


if __name__ == '__main__':
    main(Path(sys.argv[1]))

