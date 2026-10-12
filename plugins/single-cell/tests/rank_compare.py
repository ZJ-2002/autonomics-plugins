import hashlib
import json
from pathlib import Path

import anndata as ad
import h5py
import numpy as np
import pandas as pd

from qc_compare import compare_value


def strict_value(actual, expected):
    if isinstance(expected, np.ndarray) and expected.dtype.names:
        assert actual.dtype == expected.dtype and actual.shape == expected.shape
        return sum(strict_value(actual[field], expected[field]) for field in expected.dtype.names)
    if isinstance(expected, dict):
        assert set(actual) == set(expected)
        return sum(strict_value(actual[key], expected[key]) for key in expected)
    return compare_value(actual, expected)


def compare(directory):
    directory = Path(directory)
    checks = 0
    actual = ad.read_h5ad(directory / 'output.h5ad')
    author = ad.read_h5ad(directory / 'author-output.h5ad')
    for key in ['X', 'obs', 'var', 'uns']:
        checks += strict_value(getattr(actual, key), getattr(author, key))
    for key in ['obsm', 'varm', 'obsp', 'varp', 'layers']:
        checks += strict_value(dict(getattr(actual, key)), dict(getattr(author, key)))
    assert (actual.raw is None) == (author.raw is None)
    if actual.raw is not None:
        for key in ['X', 'var', 'varm']:
            value, expected = getattr(actual.raw, key), getattr(author.raw, key)
            checks += strict_value(dict(value) if key == 'varm' else value, dict(expected) if key == 'varm' else expected)
    with h5py.File(directory / 'output.h5ad') as output, h5py.File(directory / 'author-output.h5ad') as expected:
        output_paths, expected_paths = [], []
        output.visit(output_paths.append)
        expected.visit(expected_paths.append)
        assert output_paths == expected_paths
        for path in ['/'] + output_paths:
            left, right = output[path], expected[path]
            assert type(left) == type(right)
            checks += strict_value(dict(left.attrs), dict(right.attrs))
            if isinstance(left, h5py.Dataset):
                assert left.dtype == right.dtype and left.shape == right.shape
                checks += strict_value(left[()], right[()])
    markers = pd.read_parquet(directory / 'markers.parquet')
    expected_markers = pd.read_parquet(directory / 'author-markers.parquet')
    pd.testing.assert_frame_equal(markers, expected_markers, check_exact=True)
    for column in expected_markers.select_dtypes(include='number'):
        np.testing.assert_array_equal(markers[column].isna().to_numpy(), expected_markers[column].isna().to_numpy())
        np.testing.assert_array_equal(markers[column].to_numpy(dtype=np.float64, na_value=np.nan), expected_markers[column].to_numpy(dtype=np.float64, na_value=np.nan))
    report = json.loads((directory / 'report.json').read_text())
    request = json.loads((directory / 'request.json').read_text())
    source = ad.read_h5ad(directory / 'input.h5ad')
    assert report['method'] == request['method'] and report['reference'] == request['reference']
    assert report['groupby'] == request['groupby'] and report['n_genes'] == request['n_genes']
    assert report['tested_gene_universe'] == source.var_names.tolist()
    assert report['tested_gene_universe_sha256'] == hashlib.sha256(json.dumps(source.var_names.tolist(), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    assert report['effective_n_genes'] == min(source.n_vars, request['n_genes'])
    assert report['matrix_source'] == 'X' and report['use_raw'] is False and report['layer'] is None
    assert report['raw_preserved_but_not_used'] == (source.raw is not None)
    assert report['groups'] == list(author.uns['rank_genes_groups']['names'].dtype.names)
    assert report['marker_rows'] == len(markers)
    for group in report['groups']:
        expected = author.uns['rank_genes_groups']['names'][group].astype(str).tolist()
        assert report['returned_genes_by_group'][group] == expected
        assert report['not_in_marker_view_by_group'][group] == [gene for gene in source.var_names if gene not in set(expected)]
    if request['method'] == 'logreg':
        assert 'pvalue' not in markers and report['pvalue_kind'] == 'NO_GENE_P_VALUES_FOR_LOGREG_COEFFICIENTS'
        assert report['correction'] == 'NOT_PERFORMED;official logreg returns coefficients without gene P values'
    else:
        assert {'score', 'pvalue', 'pvalue_adj', 'logfoldchange'} <= set(markers.columns)
        assert report['correction'].startswith('official BH across complete selected gene axis')
    assert report['G0'] is False and 'NOT_DONOR' in report['statistical_unit']
    assert report['input_sha256'] == hashlib.sha256((directory / 'input.h5ad').read_bytes()).hexdigest()
    return {'case': directory.name, 'whole_H5AD_HDF5_and_tidy_output': 'PASS', 'marker_rows': len(markers), 'finite_value_checks': int(checks), 'integer_metadata_exact': True, 'missing_masks_exact': True, 'data_matrix_source': 'X', 'G0': False}
