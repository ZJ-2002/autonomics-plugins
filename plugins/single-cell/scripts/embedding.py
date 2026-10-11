"""Explicit centered-PCA/neighbors/UMAP/igraph-Leiden author-package recipe."""

from contextlib import ExitStack
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import warnings

import anndata as ad
import numba
import numpy as np
import scanpy as sc
from scipy import sparse
from threadpoolctl import threadpool_limits


class ContractError(RuntimeError):
    pass


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def required_path(name):
    value = os.environ.get(name)
    if not value:
        raise ContractError(f'missing required environment variable: {name}')
    return Path(value)


def parameters():
    result = {}
    for name, default, minimum in [('n_pcs', 30, 1), ('n_neighbors', 15, 2),
                                  ('n_top_genes', 2000, 1), ('random_state', 0, 0)]:
        value = os.environ.get('SC_P_INT_' + name.upper(), str(default))
        if not re.fullmatch(r'[+-]?[0-9]+', value) or int(value) < minimum:
            raise ContractError(f'{name} must be an integer >= {minimum}')
        result[name] = int(value)
    if result['random_state'] >= 2**32:
        raise ContractError('random_state must be below 2**32, as required by the author RNG')
    for name, default in [('resolution', 0.5), ('min_dist', 0.5)]:
        try:
            value = float(os.environ.get('SC_P_NUM_' + name.upper(), str(default)))
        except ValueError as error:
            raise ContractError(f'{name} must be finite') from error
        if not math.isfinite(value) or name == 'resolution' and value <= 0 or name == 'min_dist' and not 0 <= value < 1:
            raise ContractError(f'{name} must be finite; resolution > 0; min_dist in [0,1)')
        result[name] = value
    for name, default in [('normalize', True), ('log1p', True), ('subset_hvg', False), ('scale', False)]:
        value = os.environ.get('SC_P_BOOL_' + name.upper(), str(default).lower())
        if value not in ['true', 'false']:
            raise ContractError(f'{name} must be true or false')
        result[name] = value == 'true'
    return result


def finite_numeric(matrix, label, nonnegative=False):
    if matrix is None:
        raise ContractError(f'{label} is missing')
    values = matrix.data if sparse.issparse(matrix) else np.asarray(matrix)
    if values.dtype.kind not in 'biuf' or not np.isfinite(values).all():
        raise ContractError(f'{label} must contain finite real numeric values')
    if nonnegative and (values < 0).any():
        raise ContractError(f'{label} must be nonnegative for log-count Seurat HVG preprocessing')


def recipe(data, settings):
    if data.n_obs <= settings['n_neighbors']:
        raise ContractError('n_neighbors must be smaller than the number of cells')
    if data.obs_names.has_duplicates or data.var_names.has_duplicates:
        raise ContractError('obs_names and var_names must be unique')
    if any(not str(name) for name in data.obs_names) or any(not str(name) for name in data.var_names):
        raise ContractError('obs_names and var_names must be nonempty')
    original_genes = list(data.var_names)
    computed = 'X_pca' not in data.obsm
    selected_hvg = None
    performed = dict.fromkeys(['normalize', 'log1p', 'highly_variable_genes', 'scale', 'pca'], False)
    counts_origin = ('EXISTING_COUNTS_LAYER_PRESERVED_NOT_VERIFIED' if 'counts' in data.layers else
                     'NOT_CREATED_NORMALIZE_DISABLED') if computed else 'NOT_USED_BY_REUSED_PCA'
    if computed:
        if data.n_vars < 2:
            raise ContractError('at least two genes are required to compute PCA')
        finite_numeric(data.X, 'X', nonnegative=True)
        if settings['normalize'] and not settings['log1p']:
            raise ContractError('Seurat HVG requires log-counts: normalize=True requires log1p=True')
        if settings['normalize']:
            counts_origin = 'EXISTING_COUNTS_LAYER_PRESERVED_NOT_VERIFIED' if 'counts' in data.layers else 'COPY_OF_INPUT_X'
            if 'counts' not in data.layers:
                data.layers['counts'] = data.X.copy()
            sc.pp.normalize_total(data, target_sum=1e4, exclude_highly_expressed=False, key_added=None, inplace=True)
            performed['normalize'] = True
        if settings['log1p']:
            sc.pp.log1p(data, base=None)
            performed['log1p'] = True
        finite_numeric(data.X, 'transformed X')
        sc.pp.highly_variable_genes(data, n_top_genes=min(settings['n_top_genes'], data.n_vars),
                                   flavor='seurat', subset=settings['subset_hvg'])
        performed['highly_variable_genes'] = True
        selected_hvg = int(data.var['highly_variable'].sum())
        if settings['n_pcs'] >= min(data.n_obs, selected_hvg):
            raise ContractError('requested n_pcs exceeds the selected-HVG ARPACK rank bound; no silent clamp')
        if settings['scale']:
            sc.pp.scale(data, zero_center=True, max_value=10)
            performed['scale'] = True
        sc.pp.pca(data, n_comps=settings['n_pcs'], zero_center=True, svd_solver='arpack',
                  random_state=settings['random_state'], mask_var='highly_variable', dtype='float32')
        performed['pca'] = True
        for name in ['variance', 'variance_ratio']:
            finite_numeric(data.uns['pca'][name], 'PCA ' + name)
    basis = data.obsm['X_pca']
    if basis.ndim != 2 or basis.shape[1] < settings['n_pcs']:
        raise ContractError('existing X_pca does not contain all requested components')
    finite_numeric(basis[:, :settings['n_pcs']], 'used X_pca')
    sc.pp.neighbors(data, n_neighbors=settings['n_neighbors'], n_pcs=settings['n_pcs'], use_rep='X_pca',
                    random_state=settings['random_state'], knn=True, method='umap', metric='euclidean')
    sc.tl.umap(data, min_dist=settings['min_dist'], random_state=settings['random_state'],
               n_components=2, init_pos='spectral')
    sc.tl.leiden(data, resolution=settings['resolution'], key_added='leiden', random_state=settings['random_state'],
                 flavor='igraph', n_iterations=2, directed=False, use_weights=True)
    for name in ['distances', 'connectivities']:
        finite_numeric(data.obsp[name], name, nonnegative=True)
    finite_numeric(data.obsm['X_umap'], 'X_umap')
    data.uns['pca_neighbors_umap_leiden_params'] = settings
    cluster_counts = data.obs['leiden'].value_counts().sort_index()
    retained = set(data.var_names)
    report = {'schema_version': '2.0', 'operation': 'pca_neighbors_umap_leiden',
        'cells': data.n_obs, 'genes': data.n_vars, 'pca_computed': computed,
        'n_pcs_used': settings['n_pcs'], 'n_pcs_stored': basis.shape[1],
        'n_clusters': len(cluster_counts), 'cluster_counts': {str(name): int(value) for name, value in cluster_counts.items()},
        'params': settings, 'performed': performed, 'selected_hvg': selected_hvg,
        'pca_method': 'CENTERED_ARPACK' if computed else 'REUSED_UNVERIFIED_UPSTREAM_PCA',
        'neighbors_representation': 'X_pca_first_requested_components', 'counts_layer_origin': counts_origin,
        'reused_X_or_unused_components_scientifically_qualified': False,
        'feature_ledger': [{'input_index': index, 'gene_id': name, 'retained': name in retained}
                           for index, name in enumerate(original_genes)],
        'scipy_blas_numba_and_scanpy_threads': 1, 'random_state': settings['random_state'],
        'HVG_input_contract': 'Seurat log-counts;scale/provenance never inferred from numeric values',
        'scientific_release': 'NOT_GRANTED', 'G0': False,
        'packages': {name: importlib.metadata.version(name) for name in ['scanpy', 'anndata', 'scikit-learn',
                     'umap-learn', 'pynndescent', 'igraph', 'numba', 'numpy', 'scipy']}}
    return data, report


def publish(data, report, h5ad_path, report_path):
    published = []
    with ExitStack() as stack:
        h5ad_directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='.embedding-', dir=h5ad_path.parent)))
        report_directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='.embedding-', dir=report_path.parent)))
        staged_h5ad = h5ad_directory / 'output.h5ad'
        staged_report = report_directory / 'report.json'
        data.write_h5ad(staged_h5ad, compression='lzf')
        report['outputs'] = [{'port': 0, 'name': h5ad_path.name, 'bytes': staged_h5ad.stat().st_size,
                              'sha256': digest(staged_h5ad)}]
        report['report_hash_policy'] = 'port_1_hash_recorded_externally_not_recursively'
        staged_report.write_text(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
        for path in [staged_h5ad, staged_report]:
            with path.open('rb') as handle:
                os.fsync(handle.fileno())
        try:
            for staged, destination in [(staged_h5ad, h5ad_path), (staged_report, report_path)]:
                status = staged.stat()
                os.link(staged, destination)
                published.append((destination, (status.st_dev, status.st_ino)))
        except OSError:
            for destination, expected in reversed(published):
                try:
                    status = destination.lstat()
                    if (status.st_dev, status.st_ino) == expected:
                        destination.unlink()
                except FileNotFoundError:
                    pass
            raise


def run():
    settings = parameters()
    source = required_path('AUTONOMICS_INPUT0')
    output = required_path('AUTONOMICS_OUTPUT0')
    report_path = required_path('AUTONOMICS_OUTPUT1')
    if not source.is_file():
        raise ContractError('input must be a readable H5AD file')
    if len({path.resolve() for path in [source, output, report_path]}) != 3:
        raise ContractError('input and output paths must be distinct')
    for path in [output, report_path]:
        if os.path.lexists(path):
            raise ContractError(f'refusing to overwrite existing output: {path}')
        path.parent.mkdir(parents=True, exist_ok=True)
    checksum = digest(source)
    numba.set_num_threads(1)
    sc.settings.n_jobs = 1
    with threadpool_limits(limits=1), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        data, report = recipe(ad.read_h5ad(source), settings)
    if digest(source) != checksum:
        raise ContractError('input changed during embedding')
    report['input_sha256'] = checksum
    report['warnings'] = [f'{warning.category.__name__}: {warning.message}' for warning in caught]
    publish(data, report, output, report_path)


if __name__ == '__main__':
    try:
        run()
    except ContractError as error:
        print(f'h5ad_pca_neighbors_umap_leiden: {error}', file=sys.stderr)
        raise SystemExit(2)
    except Exception as error:
        print(f'h5ad_pca_neighbors_umap_leiden: {error}', file=sys.stderr)
        raise SystemExit(3)
