import anndata as ad
import numpy as np
import pandas as pd
import scipy.sparse as sp


def fixture(kind='dense'):
    random = np.random.default_rng(179)
    values = random.uniform(0.1, 2.0, size=(36, 12))
    values[:, 0] = 0
    values[:12, 1] += 0.3
    values[12:24, 2] += 0.3
    if kind == 'tied':
        values = np.round(values * 2) / 2
    if kind == 'float32':
        values = values.astype(np.float32)
    labels = ['0001'] * 12 + ['NA'] * 12 + ['炎症'] * 12
    if kind == 'two-groups':
        labels = ['0001'] * 18 + ['NA'] * 18
    obs = pd.DataFrame({'group': pd.Categorical(labels, categories=['NA', '0001'] if kind == 'two-groups' else ['炎症', 'NA', '0001'], ordered=True), 'donor': ['d1'] * 18 + ['d2'] * 18, 'original_integer': np.arange(36, dtype=np.int64)}, index=pd.Index(['0001', 'NA'] + [f'cell{index}' for index in range(34)], name='cell_id'))
    var = pd.DataFrame({'integer': [2**53 + 1] + list(range(11)), 'highly_variable': [False] * 12}, index=pd.Index(['zero', 'NA', '0001', '炎症'] + [f'g{index}' for index in range(8)], name='gene_id'))
    data = ad.AnnData(values, obs=obs, var=var)
    data.uns['log1p'] = {'base': None}
    data.uns['unrelated_history'] = {'label': 'technical fixture only', 'integer': np.array([2**53 + 1], dtype=np.uint64)}
    data.layers['decoy'] = values * 9
    data.obsm['coordinates'] = np.arange(72, dtype=np.int64).reshape(36, 2)
    data.varm['loadings'] = np.arange(24, dtype=np.float64).reshape(12, 2)
    data.obsp['identity'] = sp.eye(36, format='csr', dtype=np.int64)
    if kind == 'raw-ignored':
        raw = ad.AnnData(random.uniform(5, 8, size=(36, 15)), obs=obs.copy(), var=pd.DataFrame(index=['RAW_' + str(index) for index in range(15)]))
        data.raw = raw
    if kind == 'existing-result':
        data.uns['rank_genes_groups'] = {'previous_unrelated_value': 42}
    if kind in {'csr', 'csc'}:
        data.X = sp.csr_matrix(data.X) if kind == 'csr' else sp.csc_matrix(data.X)
    if kind == 'reordered':
        data = data[np.arange(35, -1, -1), np.arange(11, -1, -1)].copy()
    return data
