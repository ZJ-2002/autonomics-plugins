"""Official R package calls, independent rank mathematics and complete H5AD IO."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import anndata as ad
import h5py
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.stats import rankdata


FAMILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FAMILY.parent / 'single-cell/tests'))
from qc_compare import compare_value


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def call(command, directory, name, variables):
    started = time.monotonic()
    result = subprocess.run(command, env=variables, capture_output=True, timeout=900)
    (directory / (name + '.stdout.txt')).write_bytes(result.stdout)
    (directory / (name + '.stderr.txt')).write_bytes(result.stderr)
    (directory / (name + '.execution.json')).write_text(json.dumps({'command': command,
        'exit': result.returncode, 'seconds': time.monotonic()-started, 'G0': False}, indent=2) + '\n')
    return result


def create(directory, variant):
    cells = 129 if variant == 'multiple-batches' else 1 if variant == 'one-cell' else 7
    width = 4000 if variant in ['rank-cutoff', 'flat-large-background'] else 1500 if variant == 'rank-boundary' else 10
    genes = ['A', 'B', 'C', 'D', 'NA', '0001', 'Gene-', 'Gene+', *[f'gene-{index:04d}' for index in range(8, width)]]
    generator = np.random.default_rng(21)
    values = generator.integers(0, 7, size=(cells, width)).astype(np.float64)
    if variant == 'negative-values': values -= 4
    if variant == 'close-floating-values': values[:, :3] = [1., np.nextafter(1., 0.), np.nextafter(1., 2.)]
    if variant == 'signed-int-edge': values[:, :3] = [2**53, 2**53-1, -(2**53)]
    if variant in ['flat-small-background', 'flat-large-background']: values[:] = 0
    if variant in ['rank-cutoff', 'rank-boundary']: values[:] = np.arange(width, 0, -1)
    if variant == 'tied-ranks': values[:, :5] = 30
    identifiers = ['0001', 'NA', '炎症', 'gene', *[f'cell-{index}' for index in range(4, cells)]][:cells]
    data = ad.AnnData(values, obs=pd.DataFrame({'donor': ['technical-not-qualified']*cells}, index=identifiers),
                     var=pd.DataFrame({'id': genes}, index=pd.Index(genes, name='var_name')))
    data.layers['original_integer_layer'] = sparse.csr_matrix(generator.integers(0, 6, size=data.shape))
    data.obsm['coordinates'] = generator.normal(size=(cells, 2))
    data.varm['loadings'] = generator.normal(size=(width, 2))
    data.obsp['graph'] = sparse.eye(cells, format='csr')
    data.uns['history'] = {'scope': 'SYNTHETIC_NOT_QUALIFIED_DONORS'}
    if variant in ['csr', 'csc']: data.X = getattr(sparse, variant + '_matrix')(data.X)
    if variant == 'float32': data.X = data.X.astype(np.float32)
    if variant == 'integer32': data.X = data.X.astype(np.int32)
    if variant == 'signed-int-edge': data.X = data.X.astype(np.int64)
    if variant == 'boolean': data.X = data.X > 3
    if variant == 'reordered': data = data[::-1, ::-1].copy()
    if variant == 'unrelated-raw':
        raw = data.copy()
        raw.X[:] = 200
        data.raw = raw[:, :6].copy()
    if variant == 'old-parameters': data.uns['ucell_params'] = {'method': 'incorrect-old-rank-score'}
    programs = {'positive': ['A', 'B'], 'mixed': ['A+', 'C-'],
                'negative-only': ['B-', 'D-'], 'partial': ['A', 'NOT_PRESENT'],
                'NA': ['NA', '0001'], 'punctuation': ['Gene-+', 'Gene+-']}
    if variant == 'rank-cutoff': programs.update(cutoff=['gene-1499', 'gene-1500', 'gene-1501'])
    if variant == 'rank-boundary': programs.update(boundary=['gene-1498', 'gene-1499'])
    if variant == 'one-program': programs = {'one': ['A']}
    data.write_h5ad(directory / 'input.h5ad')
    (directory / 'request.json').write_text(json.dumps(programs, ensure_ascii=False, indent=2) + '\n')
    return programs


def mathematics(data, programs):
    expression = data.X.toarray() if sparse.issparse(data.X) else np.asarray(data.X)
    maximum = min(1500, data.n_vars)
    ranks = np.minimum(rankdata(-expression.astype(float), axis=1, method='average'), maximum)
    axis = {name: index for index, name in enumerate(data.var_names)}
    result = {}
    for name, genes in programs.items():
        arms = []
        for negative in [False, True]:
            identifiers = [gene[:-1] if gene.endswith(('+', '-')) else gene for gene in genes if gene.endswith('-') == negative]
            count = len(identifiers)
            if not count:
                arms.append(np.zeros(data.n_obs)); continue
            rank_sum = sum((ranks[:, axis[gene]] if gene in axis else np.full(data.n_obs, maximum)) for gene in identifiers)
            minimum = count * (count + 1) / 2
            arms.append(1 - (rank_sum - minimum) / (count * maximum - minimum))
        result[name] = np.maximum(0, arms[0] - arms[1])
    return result


def compare(directory, programs):
    source = ad.read_h5ad(directory / 'input.h5ad')
    actual = ad.read_h5ad(directory / 'output.h5ad')
    with (directory / 'author-scores.tsv').open(encoding='utf-8', newline='') as handle:
        rows = list(csv.reader(handle, delimiter='\t', quoting=csv.QUOTE_NONE))
    assert rows[0] == ['cell', *programs]
    assert [row[0] for row in rows[1:]] == list(source.obs_names)
    official = np.array([[float(value) for value in row[1:]] for row in rows[1:]])
    independent = mathematics(source, programs)
    expected = source.copy()
    for index, name in enumerate(programs):
        np.testing.assert_allclose(official[:, index], independent[name], atol=1e-12, rtol=0)
        expected.obs[name] = official[:, index]
    expected.uns['ucell_params'] = {'method': 'UCell', 'version': '2.16.0', 'maxRank': 1500,
        'effective_maxRank': min(1500, source.n_vars), 'w_neg': 1., 'missing_genes': 'impute',
        'ties_method': 'average', 'matrix': 'X', 'gene_sets': {name: len(genes) for name, genes in programs.items()}}
    expected.write_h5ad(directory / 'fresh-author.h5ad', compression='lzf')
    expected = ad.read_h5ad(directory / 'fresh-author.h5ad')
    finite = compare_value(actual.X, expected.X) + compare_value(actual.obs, expected.obs) + compare_value(actual.var, expected.var)
    for name in ['layers', 'obsm', 'varm', 'obsp', 'varp', 'uns']:
        finite += compare_value(dict(getattr(actual, name)), dict(getattr(expected, name)))
    assert (actual.raw is None) == (expected.raw is None)
    if expected.raw is not None:
        finite += compare_value(actual.raw.X, expected.raw.X) + compare_value(actual.raw.var, expected.raw.var)
        finite += compare_value(dict(actual.raw.varm), dict(expected.raw.varm))
    with h5py.File(directory / 'output.h5ad') as actual_file, h5py.File(directory / 'fresh-author.h5ad') as author_file:
        actual_names, expected_names = [], []
        actual_file.visit(actual_names.append); author_file.visit(expected_names.append)
        assert actual_names == expected_names
        for name in ['/', *expected_names]:
            assert set(actual_file[name].attrs) == set(author_file[name].attrs)
            for key in author_file[name].attrs:
                np.testing.assert_array_equal(actual_file[name].attrs[key], author_file[name].attrs[key])
            if isinstance(author_file[name], h5py.Dataset):
                assert actual_file[name].dtype == author_file[name].dtype
                if author_file[name].dtype.kind in 'fc':
                    np.testing.assert_allclose(actual_file[name][()], author_file[name][()], atol=1e-12, rtol=0, equal_nan=True)
                else: np.testing.assert_array_equal(actual_file[name][()], author_file[name][()])
    report = json.loads((directory / 'report.json').read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    assert report['input_sha256'] == digest(directory / 'input.h5ad')
    assert report['cell_ids'] == list(source.obs_names) and report['gene_ids'] == list(source.var_names)
    assert report['score_columns'] == list(programs) and report['source_matrix'] == 'X'
    for index, name in enumerate(programs):
        np.testing.assert_allclose(report['gene_sets'][name]['mean'], official[:, index].mean(), atol=1e-12, rtol=0)
    assert report['scientific_release'] == 'NOT_GRANTED' and report['G0'] is False
    assert report['outputs'] == [{'port': 0, 'name': 'output.h5ad', 'bytes': (directory/'output.h5ad').stat().st_size,
                                   'sha256': digest(directory/'output.h5ad')}]
    return {'pass': True, 'whole_HDF5_AnnData_and_raw_checked': True,
        'official_R_and_independent_rank_math_agree': True, 'finite_values_checked': int(finite),
        'float_atol': 1e-12, 'float_rtol': 0, 'integers_exact': True, 'G0': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--reference-library', type=Path, required=True)
    arguments = parser.parse_args(); arguments.evidence.mkdir()
    variants = ['dense', 'csr', 'csc', 'float32', 'integer32', 'boolean', 'reordered',
                'negative-values', 'close-floating-values', 'signed-int-edge', 'tied-ranks',
                'flat-small-background', 'flat-large-background', 'rank-cutoff', 'rank-boundary',
                'unrelated-raw', 'old-parameters', 'one-cell', 'one-program', 'multiple-batches']
    records = []
    for variant in variants:
        directory = arguments.evidence / variant; directory.mkdir()
        programs = create(directory, variant)
        data = ad.read_h5ad(directory / 'input.h5ad')
        values = data.X.toarray() if sparse.issparse(data.X) else data.X
        with (directory/'author-expression.tsv').open('w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle, delimiter='\t', quoting=csv.QUOTE_NONE)
            writer.writerow(['gene', *data.obs_names])
            for index, gene in enumerate(data.var_names): writer.writerow([gene, *[repr(float(value)) for value in values[:, index]]])
        author = call(['Rscript', '--vanilla', str(FAMILY/'tests/reference.R'), str(arguments.reference_library),
            str(directory/'author-expression.tsv'), str(directory/'request.json'), str(directory/'author-scores.tsv'),
            str(directory/'author-result.RDS')], directory, 'fresh-author', dict(os.environ))
        variables = dict(os.environ, AUTONOMICS_INPUT0=str(directory/'input.h5ad'),
            AUTONOMICS_OUTPUT0=str(directory/'output.h5ad'), AUTONOMICS_OUTPUT1=str(directory/'report.json'),
            SC_P_JSON_GENE_SETS=json.dumps(programs, ensure_ascii=False))
        node = call([sys.executable, str(FAMILY/'scripts/score.py')], directory, 'declared-node-script', variables)
        assert author.returncode == node.returncode == 0, author.stderr.decode() + node.stderr.decode()
        checks = compare(directory, programs)
        (directory/'CHECKS.json').write_text(json.dumps(checks, indent=2) + '\n')
        records.append({'case': variant, **checks}); print(variant, 'PASS', flush=True)
    (arguments.evidence/'SUMMARY.json').write_text(json.dumps({'cases': len(records), 'records': records,
        'full_signed_and_negative_only_default_semantics_tested': True,
        'chunk_partition_against_single_full_author_call_tested': True, 'G0': False}, indent=2) + '\n')


if __name__ == '__main__':
    main()
