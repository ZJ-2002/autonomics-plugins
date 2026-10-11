"""Whole-object, stage and literal-axis comparisons against author outputs."""

import hashlib
import json
from pathlib import Path

import anndata as ad
import h5py
import numpy as np
import pandas as pd
from scipy import sparse

from qc_compare import compare_value


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def compare(directory):
    result = ad.read_h5ad(directory / 'output.h5ad')
    expected = ad.read_h5ad(directory / 'fresh-author.h5ad')
    source = ad.read_h5ad(directory / 'input.h5ad')
    assert result.shape == expected.shape
    finite = compare_value(result.obs, expected.obs) + compare_value(result.var, expected.var)
    if expected.X is None:
        assert result.X is None
    else:
        finite += compare_value(result.X, expected.X)
    for name in ['layers', 'obsm', 'varm', 'obsp', 'varp', 'uns']:
        finite += compare_value(dict(getattr(result, name)), dict(getattr(expected, name)))
    assert (result.raw is None) == (expected.raw is None)
    if expected.raw is not None:
        finite += compare_value(result.raw.X, expected.raw.X)
        finite += compare_value(result.raw.var, expected.raw.var)
        finite += compare_value(dict(result.raw.varm), dict(expected.raw.varm))
    with h5py.File(directory / 'output.h5ad') as actual, h5py.File(directory / 'fresh-author.h5ad') as reference:
        actual_names, expected_names = [], []
        actual.visit(actual_names.append)
        reference.visit(expected_names.append)
        assert actual_names == expected_names
        for name in ['/', *expected_names]:
            assert set(actual[name].attrs) == set(reference[name].attrs)
            for key in reference[name].attrs:
                np.testing.assert_array_equal(actual[name].attrs[key], reference[name].attrs[key])
            if isinstance(reference[name], h5py.Dataset):
                assert actual[name].dtype == reference[name].dtype
                if reference[name].dtype.kind in 'fc':
                    np.testing.assert_allclose(actual[name][()], reference[name][()], atol=1e-12, rtol=0, equal_nan=True)
                else:
                    np.testing.assert_array_equal(actual[name][()], reference[name][()])
    for name in ['pca', 'neighbors', 'umap']:
        path = directory / ('author-' + name + '.h5ad')
        if path.exists():
            stage = ad.read_h5ad(path)
            for key in ['X_pca', 'X_umap']:
                if key in stage.obsm:
                    compare_value(result.obsm[key], stage.obsm[key])
            for key in ['distances', 'connectivities']:
                if key in stage.obsp:
                    compare_value(result.obsp[key], stage.obsp[key])
    settings = json.loads((directory / 'request.json').read_text())
    report = json.loads((directory / 'report.json').read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    assert report['params'] == settings and report['input_sha256'] == digest(directory / 'input.h5ad')
    assert report['pca_computed'] == ('X_pca' not in source.obsm)
    assert report['n_pcs_used'] == settings['n_pcs'] and report['n_pcs_stored'] == result.obsm['X_pca'].shape[1]
    assert report['cells'] == source.n_obs == result.n_obs and report['genes'] == result.n_vars
    cluster_counts = expected.obs['leiden'].value_counts().sort_index()
    assert report['n_clusters'] == len(cluster_counts)
    assert report['cluster_counts'] == {str(key): int(value) for key, value in cluster_counts.items()}
    assert sum(report['cluster_counts'].values()) == source.n_obs
    assert len(report['feature_ledger']) == source.n_vars
    assert [item['gene_id'] for item in report['feature_ledger'] if item['retained']] == list(result.var_names)
    assert report['neighbors_representation'] == 'X_pca_first_requested_components'
    assert expected.uns['neighbors']['params']['use_rep'] == 'X_pca'
    assert expected.uns['neighbors']['params']['n_pcs'] == settings['n_pcs']
    if report['pca_computed']:
        assert report['performed'] == {'normalize': settings['normalize'], 'log1p': settings['log1p'],
            'highly_variable_genes': True, 'scale': settings['scale'], 'pca': True}
        origin = 'EXISTING_COUNTS_LAYER_PRESERVED_NOT_VERIFIED' if 'counts' in source.layers else \
                 'COPY_OF_INPUT_X' if settings['normalize'] else 'NOT_CREATED_NORMALIZE_DISABLED'
        assert report['counts_layer_origin'] == origin
        assert report['pca_method'] == 'CENTERED_ARPACK'
        assert bool(expected.uns['pca']['params']['zero_center'])
        assert expected.obsm['X_pca'].shape[1] == settings['n_pcs']
        assert report['selected_hvg'] == int(expected.var['highly_variable'].sum())
        if source.n_obs <= 100:
            chosen = expected.X[:, expected.var['highly_variable'].to_numpy()]
            chosen = chosen.toarray() if sparse.issparse(chosen) else np.asarray(chosen)
            covariance = np.cov(chosen.astype(float), rowvar=False, ddof=1)
            spectrum = np.linalg.eigvalsh(covariance)[::-1][:settings['n_pcs']]
            np.testing.assert_allclose(expected.uns['pca']['variance'], spectrum, atol=1e-9, rtol=1e-6)
    else:
        assert not any(report['performed'].values())
        assert report['counts_layer_origin'] == 'NOT_USED_BY_REUSED_PCA'
        assert report['pca_method'] == 'REUSED_UNVERIFIED_UPSTREAM_PCA'
        compare_value(result.obsm['X_pca'], source.obsm['X_pca'])
    assert report['feature_ledger'] == [{'input_index': index, 'gene_id': name,
        'retained': name in set(result.var_names)} for index, name in enumerate(source.var_names)]
    assert report['outputs'] == [{'port': 0, 'name': 'output.h5ad', 'bytes': (directory / 'output.h5ad').stat().st_size,
                                  'sha256': digest(directory / 'output.h5ad')}]
    assert report['scientific_release'] == 'NOT_GRANTED' and report['G0'] is False
    return {'pass': True, 'shape': list(result.shape), 'finite_values_checked': int(finite),
            'whole_AnnData_HDF5_and_intermediates_compared': True, 'integer_payloads_exact': True,
            'float_absolute_tolerance': 1e-12, 'float_relative_tolerance': 0,
            'independent_small_PCA_covariance_spectrum_checked': report['pca_computed'] and source.n_obs <= 100,
            'G0': False}
