"""Independent author calls with saved stage outputs; never imports the node."""

import json
from pathlib import Path
import sys

import anndata as ad
import numba
import numpy as np
import scanpy as sc
from threadpoolctl import threadpool_limits


def reference(directory):
    settings = json.loads((directory / 'request.json').read_text())
    data = ad.read_h5ad(directory / 'input.h5ad')
    numba.set_num_threads(1)
    sc.settings.n_jobs = 1
    with threadpool_limits(limits=1):
        if 'X_pca' not in data.obsm:
            if settings['normalize']:
                if 'counts' not in data.layers:
                    data.layers['counts'] = data.X.copy()
                sc.pp.normalize_total(data, target_sum=10000, exclude_highly_expressed=False, key_added=None, inplace=True)
            if settings['log1p']:
                sc.pp.log1p(data, base=None)
            sc.pp.highly_variable_genes(data, flavor='seurat', subset=settings['subset_hvg'],
                                       n_top_genes=min(settings['n_top_genes'], data.n_vars))
            if settings['scale']:
                sc.pp.scale(data, zero_center=True, max_value=10)
            sc.pp.pca(data, n_comps=settings['n_pcs'], svd_solver='arpack', zero_center=True,
                      random_state=settings['random_state'], mask_var='highly_variable', dtype='float32')
            data.write_h5ad(directory / 'author-pca.h5ad', compression='lzf')
        sc.pp.neighbors(data, use_rep='X_pca', n_pcs=settings['n_pcs'], n_neighbors=settings['n_neighbors'],
                        metric='euclidean', method='umap', knn=True, random_state=settings['random_state'])
        data.write_h5ad(directory / 'author-neighbors.h5ad', compression='lzf')
        sc.tl.umap(data, min_dist=settings['min_dist'], n_components=2, init_pos='spectral',
                   random_state=settings['random_state'])
        data.write_h5ad(directory / 'author-umap.h5ad', compression='lzf')
        sc.tl.leiden(data, flavor='igraph', n_iterations=2, directed=False, use_weights=True,
                     random_state=settings['random_state'], resolution=settings['resolution'], key_added='leiden')
    data.uns['pca_neighbors_umap_leiden_params'] = settings
    data.write_h5ad(directory / 'fresh-author.h5ad', compression='lzf')
    (directory / 'fresh-author.json').write_text(json.dumps({'module_paths': {'scanpy': sc.__file__,
        'anndata': ad.__file__}, 'versions': {'scanpy': sc.__version__, 'anndata': ad.__version__},
        'stages_saved': True, 'nodes_imported': False, 'G0': False}, indent=2)+'\n')


if __name__ == '__main__':
    reference(Path(sys.argv[1]))
