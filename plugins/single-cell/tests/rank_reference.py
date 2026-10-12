import json
import os
import sys
from pathlib import Path

import anndata as ad
import numba
import numpy as np
import pandas as pd
import scanpy as sc
from threadpoolctl import threadpool_limits


directory = Path(sys.argv[1])
library = Path(os.environ['PYTHONPATH']).resolve()
assert Path(sc.__file__).resolve().is_relative_to(library)
assert Path(ad.__file__).resolve().is_relative_to(library)
request = json.loads((directory / 'request.json').read_text())
data = ad.read_h5ad(directory / 'input.h5ad')
numba.set_num_threads(1)
sc.settings.n_jobs = 1
with threadpool_limits(limits=1):
    sc.tl.rank_genes_groups(data, groupby=request['groupby'], method=request['method'], reference=request['reference'], n_genes=request['n_genes'], key_added='rank_genes_groups', use_raw=False)
result = data.uns['rank_genes_groups']
groups = list(result['names'].dtype.names)
frames = []
for position, group in enumerate(groups):
    frame = sc.get.rank_genes_groups_df(data, group=group, key='rank_genes_groups')
    frame = frame.rename(columns={'names': 'gene', 'scores': 'score', 'pvals': 'pvalue', 'pvals_adj': 'pvalue_adj', 'logfoldchanges': 'logfoldchange'})
    frame['group'] = str(group)
    frame['rank'] = np.arange(1, len(frame) + 1, dtype=np.int64)
    frame['_group_order'] = position
    frames.append(frame)
table = pd.concat(frames).sort_values(['rank', '_group_order'], kind='stable').reset_index(drop=True)
columns = ['group', 'gene', 'rank'] + [column for column in ['score', 'pvalue', 'pvalue_adj', 'logfoldchange'] if column in table]
table = table[columns]
for column in columns[3:]:
    table[column] = pd.array(table[column].astype(np.float64), dtype='Float64')
table.to_parquet(directory / 'author-markers.parquet', index=False)
data.write_h5ad(directory / 'author-output.h5ad', compression='lzf')
(directory / 'author-result.json').write_text(json.dumps({'groups': groups, 'effective_n_genes': len(result['names']), 'result_fields': list(result), 'official_reference_packages': {'scanpy': sc.__version__, 'anndata': ad.__version__}, 'source': 'Fresh previously primary-payload-verified independent author prefix;direct Scanpy/get dataframe;not production wrapper'}, indent=2) + '\n')
