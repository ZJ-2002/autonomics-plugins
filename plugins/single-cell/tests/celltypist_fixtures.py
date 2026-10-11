"""Synthetic alignment/annotation cases, not qualified biological cohorts."""

import hashlib
from pathlib import Path

import anndata as ad
from celltypist import models
import numpy as np
import pandas as pd
from scipy import sparse


HASHES = {'Immune_All_Low.pkl':'290874d35dac039d4c9218c343fde4aac1077709b72a331ce7266f6828c36502',
          'Immune_All_High.pkl':'a715fec36c2c421f7c4e31cf4cb4bea883eedab7fd7b20a4b76f091c22660448'}


def model(path):
    with path.open('rb') as handle:
        assert hashlib.file_digest(handle, 'sha256').hexdigest() == HASHES[path.name]
    return models.Model.load(str(path))


def fixture(directory, model_path, variant='dense', cells=80):
    reference = model(model_path)
    genes = list(reference.features)
    generator = np.random.default_rng(37)
    counts = generator.poisson(.2, size=(cells, len(genes))).astype(float)
    for index in range(cells):
        top = np.argsort(reference.classifier.coef_[index % len(reference.cell_types)])[-20:]
        counts[index, top] += 40
    values = np.log1p(counts / counts.sum(axis=1)[:, None] * 10000)
    identifiers = ['0001','NA','炎症', *[f'cell-{index}' for index in range(3,cells)]]
    data = ad.AnnData(values, obs=pd.DataFrame({'donor':['0001' if index%2 else 'NA' for index in range(cells)]},
        index=identifiers), var=pd.DataFrame({'gene_id':genes}, index=pd.Index(genes,name='var_name')))
    data.layers['retained_counts'] = sparse.csr_matrix(counts)
    data.obsm['coordinates'] = generator.normal(size=(cells,2))
    data.varm['prior_loading'] = generator.normal(size=(len(genes),2))
    data.obsp['retained_graph'] = sparse.eye(cells,format='csr')
    data.uns['history'] = {'scope':'SYNTHETIC_TECHNICAL_NOT_QUALIFIED_DONORS_OR_COHORT'}
    if variant in ['dense','csr','csc','float32','integer-log','single-group','raw-valid-X-valid','moderate-score-voting']:
        data.obs['leiden'] = ['all']*cells
    if variant in ['csr','csc']:
        data.X = getattr(sparse,variant+'_matrix')(values)
    elif variant == 'float32':
        data.X = values.astype(np.float32)
    elif variant == 'reordered':
        data = data[list(range(cells-1,-1,-1)),list(range(len(genes)-1,-1,-1))].copy()
        data.obs['leiden'] = ['all']*cells
    elif variant == 'partial-genes':
        data = data[:,:1024].copy()
        data.obs['leiden'] = ['all']*cells
    elif variant == 'raw-fallback':
        data.raw = data.copy()
        data.X = data.X - 7
        data.obs['leiden'] = ['all']*cells
    elif variant == 'raw-valid-X-valid':
        raw = data.copy()
        raw.X = np.log1p(np.expm1(raw.X)*2)
        data.raw = raw
    elif variant == 'auto-existing-graph':
        data.obsp['connectivities'] = sparse.csr_matrix(np.ones((cells,cells))-np.eye(cells))
        data.obsp['distances'] = data.obsp['connectivities'].copy()
        data.uns['neighbors'] = {'connectivities_key':'connectivities','distances_key':'distances',
                                 'params':{'n_neighbors':10,'method':'umap','metric':'euclidean'}}
    elif variant == 'auto-existing-pca':
        data.obsm['X_pca'] = generator.normal(size=(cells,60))
    elif variant in ['overwrite-annotation-columns','small-preexisting-annotations']:
        data.obs['predicted_labels'] = 'old-label'
        data.obs['conf_score'] = 0.
        data.obs['celltypist_label'] = 'old-celltypist'
        data.obs['celltypist_conf_score'] = 0.
        data.obs['leiden'] = ['all']*cells
        if variant == 'small-preexisting-annotations':
            data.obs['majority_voting'] = 'stale-not-this-run'
    elif variant == 'moderate-score-voting':
        data.X = np.tile(reference.scaler.mean_,(cells,1))
        for index in range(cells):
            coefficients = reference.classifier.coef_[index%len(reference.cell_types)]
            chosen = np.argsort(coefficients)[-20:]
            data.X[index,chosen] += reference.scaler.scale_[chosen] * 2
        data.X = np.clip(data.X,0,9.21)
    data.write_h5ad(directory/'input.h5ad')
