"""Mandatory real-image cases and fresh full-author-stack comparisons."""

import argparse
import itertools
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import anndata as ad
import numpy as np
import pandas as pd
from scipy import sparse

from embedding_compare import compare


FAMILY = Path(__file__).resolve().parents[1]
DEFAULTS = {'n_pcs': 30, 'n_neighbors': 15, 'n_top_genes': 2000, 'random_state': 0,
            'resolution': .5, 'min_dist': .5, 'normalize': True, 'log1p': True, 'subset_hvg': False, 'scale': False}


def fixture(directory, variant, settings):
    if variant == 'large-approximate-9000':
        data = ad.AnnData(obs=pd.DataFrame({'donor': ['0001', 'NA'] * 4500},
            index=[f'cell-{index}' for index in range(9000)]), var=pd.DataFrame(index=[]))
        data.obsm['X_pca'] = np.random.default_rng(1467).normal(size=(9000, 8))
        data.uns['frozen_history'] = {'scope': 'SYNTHETIC_NOT_QUALIFIED_COHORT'}
        data.write_h5ad(directory / 'input.h5ad')
        return
    cells = 4200 if variant == 'large-exact-4200' else 80
    genes = 8 if variant == 'small-existing' else 0 if variant == 'metadata-existing' else 128
    generator = np.random.default_rng(1467)
    values = generator.poisson(4, size=(cells, genes)).astype(float)
    data = ad.AnnData(values, obs=pd.DataFrame({'donor': ['0001', 'NA'] * (cells//2)},
        index=[f'cell-{index}' for index in range(cells)]), var=pd.DataFrame(index=[f'gene-{index}' for index in range(genes)]))
    data.layers['retained_derived'] = values - 8
    data.obsm['coordinates'] = generator.normal(size=(cells, 2))
    data.varm['prior_loadings'] = generator.normal(size=(genes, 2))
    data.obsp['retained_graph'] = sparse.eye(cells, format='csr')
    data.varp['retained_gene_graph'] = sparse.eye(genes, format='csr')
    data.uns['frozen_history'] = {'scope': 'SYNTHETIC_NOT_QUALIFIED_COHORT'}
    if variant in ['csr', 'csc']:
        data.X = getattr(sparse, variant + '_matrix')(values)
    elif variant == 'float32':
        data.X = values.astype(np.float32)
    elif variant == 'integer':
        data.X = values.astype(np.int64)
    elif variant == 'raw-wider':
        data.raw = data.copy()
        data = data[:, :96].copy()
    elif variant == 'raw-narrower':
        data.raw = data[:, :64].copy()
    elif variant == 'existing-counts':
        data.layers['counts'] = values + 1
    if variant.endswith('existing') or variant in ['large-exact-4200', 'reuse-longer', 'reuse-sparse']:
        data.obsm['X_pca'] = generator.normal(size=(cells, 40))
        if variant == 'reuse-sparse':
            data.obsm['X_pca'] = sparse.csr_matrix(data.obsm['X_pca'])
        if variant == 'metadata-existing':
            data.X = None
    elif not settings['normalize'] and not settings['log1p']:
        data.X = np.log1p(data.X)
    data.write_h5ad(directory / 'input.h5ad')


def environment(directory, settings):
    result = dict(os.environ, AUTONOMICS_INPUT0=str(directory / 'input.h5ad'),
                  AUTONOMICS_OUTPUT0=str(directory / 'output.h5ad'), AUTONOMICS_OUTPUT1=str(directory / 'report.json'))
    for name, value in settings.items():
        kind = 'BOOL' if name in ['normalize', 'log1p', 'subset_hvg', 'scale'] else \
               'INT' if name in ['n_pcs', 'n_neighbors', 'n_top_genes', 'random_state'] else 'NUM'
        result['SC_P_' + kind + '_' + name.upper()] = str(value).lower()
    return result


def execute(command, directory, label, variables):
    started = time.monotonic()
    result = subprocess.run(command, env=variables, capture_output=True, timeout=900)
    (directory / (label + '.stdout.txt')).write_bytes(result.stdout)
    (directory / (label + '.stderr.txt')).write_bytes(result.stderr)
    (directory / (label + '.execution.json')).write_text(json.dumps({'command': command, 'exit': result.returncode,
        'seconds': time.monotonic()-started, 'G0': False}, indent=2)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--reference-library', type=Path, required=True)
    parser.add_argument('--pbmc3k-file', type=Path)
    arguments = parser.parse_args()
    arguments.evidence.mkdir()
    cases = [('defaults', 'dense', {})]
    cases += [(f'flags-n{int(normalize)}-l{int(logarithm)}-h{int(subset)}-s{int(scale)}', 'dense',
        {'normalize': normalize, 'log1p': logarithm, 'subset_hvg': subset, 'scale': scale, 'n_pcs': 4, 'n_neighbors': 5})
        for normalize, logarithm, subset, scale in itertools.product([False, True], repeat=4)
        if not (normalize and not logarithm)]
    cases += [(variant, variant, {'n_pcs': 4, 'n_neighbors': 5}) for variant in ['csr', 'csc', 'float32', 'integer',
        'raw-wider', 'raw-narrower', 'existing-counts', 'small-existing', 'metadata-existing', 'reuse-longer', 'reuse-sparse']]
    cases += [('min-dist-zero', 'dense', {'n_pcs': 4, 'n_neighbors': 5, 'min_dist': 0.}),
              ('hvg-selected', 'dense', {'n_pcs': 4, 'n_neighbors': 5, 'n_top_genes': 24}),
              ('seed-one', 'dense', {'n_pcs': 4, 'n_neighbors': 5, 'random_state': 1}),
              ('seed-zero-repeat', 'dense', {'n_pcs': 4, 'n_neighbors': 5}),
              ('large-exact-4200', 'large-exact-4200', {'n_pcs': 4, 'n_neighbors': 5}),
              ('large-approximate-9000', 'large-approximate-9000', {'n_pcs': 4, 'n_neighbors': 5})]
    if arguments.pbmc3k_file:
        cases.append(('official-pbmc3k', 'pbmc3k', {}))
    records = []
    for name, variant, changes in cases:
        directory = arguments.evidence / name
        directory.mkdir()
        settings = {**DEFAULTS, **changes}
        if variant == 'pbmc3k':
            shutil.copyfile(arguments.pbmc3k_file, directory / 'input.h5ad')
        else:
            fixture(directory, variant, settings)
        (directory / 'request.json').write_text(json.dumps(settings, indent=2)+'\n')
        author_command = [sys.executable, str(FAMILY / 'tests/embedding_reference.py'), str(directory)]
        node_command = [sys.executable, str(FAMILY / 'scripts/embedding.py')]
        author_environment = dict(os.environ, PYTHONPATH=str(arguments.reference_library))
        node_environment = environment(directory, settings)
        if variant == 'large-approximate-9000':
            observer = str(FAMILY / 'tests/profile_embedding_backend.py')
            author_command.insert(1, observer)
            node_command.insert(1, observer)
            author_environment['BACKEND_TRACE_PATH'] = str(directory / 'author-backend.json')
            node_environment['BACKEND_TRACE_PATH'] = str(directory / 'node-backend.json')
        author = execute(author_command, directory, 'fresh-author', author_environment)
        node = execute(node_command, directory, 'declared-node-script', node_environment)
        if author.returncode or node.returncode:
            raise AssertionError(author.stderr.decode() + node.stderr.decode())
        checked = compare(directory)
        if variant == 'large-approximate-9000':
            for filename in ['author-backend.json', 'node-backend.json']:
                trace = json.loads((directory / filename).read_text())
                assert any(entry['class'] == 'PyNNDescentTransformer' and entry['method'] == 'fit_transform'
                           for entry in trace['observations'])
        (directory / 'CHECKS.json').write_text(json.dumps(checked, indent=2)+'\n')
        records.append({'case': name, **checked})
        print(name, 'PASS', flush=True)
    first = ad.read_h5ad(arguments.evidence / 'flags-n1-l1-h0-s0/output.h5ad')
    repeated = ad.read_h5ad(arguments.evidence / 'seed-zero-repeat/output.h5ad')
    changed = ad.read_h5ad(arguments.evidence / 'seed-one/output.h5ad')
    np.testing.assert_array_equal(first.obsm['X_umap'], repeated.obsm['X_umap'])
    assert not np.array_equal(first.obsm['X_umap'], changed.obsm['X_umap'])
    (arguments.evidence / 'SUMMARY.json').write_text(json.dumps({'cases': len(records), 'records': records,
        'same_seed_repeat_exact': True, 'different_seed_stochastic_path_exercised': True,
        'complete_author_stack_independent_imports': True, 'G0': False}, indent=2)+'\n')


if __name__ == '__main__':
    main()
