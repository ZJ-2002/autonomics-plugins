import hashlib
import importlib.metadata
import json
import os
import sys
import tempfile
import warnings
from pathlib import Path

os.environ.setdefault('NUMBA_CACHE_DIR', '/tmp/autonomics-rank-numba')

import anndata as ad
import numba
import numpy as np
import pandas as pd
import scanpy as sc
import scipy.sparse as sp
from threadpoolctl import threadpool_limits


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def rank_table(result):
    names = result['names']
    groups = list(names.dtype.names or [])
    columns = [('score', 'scores'), ('pvalue', 'pvals'), ('pvalue_adj', 'pvals_adj'), ('logfoldchange', 'logfoldchanges')]
    available = [(output, original) for output, original in columns if original in result]
    records = []
    for rank in range(len(names)):
        for group in groups:
            record = {'group': group, 'gene': str(names[rank][group]), 'rank': rank + 1}
            for output, original in available:
                value = result[original][rank][group]
                record[output] = None if pd.isna(value) else float(value)
            records.append(record)
    table = pd.DataFrame.from_records(records)
    for output, original in available:
        table[output] = pd.array(table[output], dtype='Float64')
    return table, groups, available


def run():
    groupby = os.environ.get('SC_P_STR_GROUPBY', '')
    method = os.environ.get('SC_P_STR_METHOD', 'wilcoxon') or 'wilcoxon'
    reference = os.environ.get('SC_P_STR_REFERENCE', 'rest') or 'rest'
    require(groupby.strip() and reference.strip(), 'groupby and reference must be nonempty strings')
    require(method in {'wilcoxon', 't-test', 't-test_overestim_var', 'logreg'}, 'unsupported rank_genes_groups method')
    requested = int(os.environ.get('SC_P_INT_N_GENES', '100') or '100')
    require(requested > 0, 'n_genes must be positive')
    source = Path(os.environ['AUTONOMICS_INPUT0'])
    outputs = [Path(os.environ[f'AUTONOMICS_OUTPUT{number}']) for number in range(3)]
    resolved = [path.resolve() for path in outputs]
    require(len(set(resolved)) == 3 and source.resolve() not in resolved, 'output paths overlap each other or the input')
    require(all(not os.path.lexists(path) and path.parent.is_dir() for path in outputs), 'output already exists or parent is not a directory')
    source_sha = digest(source)
    data = ad.read_h5ad(source)
    require(data.n_obs > 0 and data.n_vars > 0 and data.X is not None, 'nonempty selected X matrix is required; raw is not a fallback')
    require(data.obs_names.is_unique and data.var_names.is_unique, 'H5AD obs_names and var_names must be unique')
    require(all(isinstance(value, str) and value != '' for value in data.obs_names) and all(isinstance(value, str) and value != '' for value in data.var_names), 'cell and gene IDs must be nonempty literal strings')
    require(groupby in data.obs and not data.obs[groupby].isna().any(), 'groupby column is missing or contains missing labels')
    selected = data.X.data if sp.issparse(data.X) else np.asarray(data.X)
    require(np.asarray(selected).dtype.kind in 'biuf' and np.isfinite(selected).all(), 'selected X must be finite real expression')
    if sp.issparse(data.X):
        require(data.X.has_canonical_format, 'selected sparse X must have canonical unique coordinates; no hidden coalescing or dtype overflow')
    observed = data.obs[groupby].drop_duplicates()
    require(len(observed) >= 2, 'at least two observed groups are required for marker comparison')
    require(reference == 'rest' or reference in set(observed.astype(str)), 'reference group is not present')
    input_genes = data.var_names.tolist()
    input_gene_sha = hashlib.sha256(json.dumps(input_genes, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    input_group_counts = [{'label': str(value), 'label_type': type(value).__name__, 'cells': int((data.obs[groupby] == value).sum())} for value in observed]
    overwritten = 'rank_genes_groups' in data.uns
    numba.set_num_threads(1)
    sc.settings.n_jobs = 1
    with warnings.catch_warnings(record=True) as captured, threadpool_limits(limits=1):
        warnings.simplefilter('always')
        sc.tl.rank_genes_groups(data, groupby=groupby, method=method, reference=reference, n_genes=requested, key_added='rank_genes_groups', use_raw=False, layer=None, mask_var=None, groups='all', rankby_abs=False, pts=False, corr_method='benjamini-hochberg', tie_correct=False)
    result = data.uns['rank_genes_groups']
    table, groups, available = rank_table(result)
    effective = len(result['names'])
    require(effective == min(requested, len(input_genes)) and groups, 'official result axes do not match requested marker view')
    returned = {group: result['names'][group].astype(str).tolist() for group in groups}
    require(all(len(set(values)) == effective and set(values) <= set(input_genes) for values in returned.values()), 'official result gene IDs are not unique members of the selected X axis')
    require(table['rank'].min() == 1 and table['rank'].max() == effective, 'marker rank numbering is inconsistent')
    numeric_masks = {output: {'missing': int(table[output].isna().sum()), 'positive_infinity': int(np.isposinf(table[output].to_numpy(dtype=float, na_value=np.nan)).sum()), 'negative_infinity': int(np.isneginf(table[output].to_numpy(dtype=float, na_value=np.nan)).sum())} for output, original in available}
    report = {'schema_version': '2.0', 'operation': 'rank_genes_groups', 'cells': data.n_obs, 'genes': data.n_vars, 'groupby': groupby, 'method': method, 'reference': reference, 'n_genes': requested, 'effective_n_genes': effective, 'groups': groups, 'marker_rows': len(table), 'input_group_counts': input_group_counts, 'tested_gene_universe': input_genes, 'tested_gene_universe_sha256': input_gene_sha, 'returned_genes_by_group': returned, 'not_in_marker_view_by_group': {group: [gene for gene in input_genes if gene not in set(returned[group])] for group in groups}, 'matrix_source': 'X', 'use_raw': False, 'layer': None, 'raw_preserved_but_not_used': data.raw is not None, 'input_scale_verified': False, 'correction': 'NOT_PERFORMED;official logreg returns coefficients without gene P values' if method == 'logreg' else 'official BH across complete selected gene axis separately per group;not complete study tissue/cell/contrast family', 'pvalue_kind': 'NO_GENE_P_VALUES_FOR_LOGREG_COEFFICIENTS' if method == 'logreg' else 'OFFICIAL_CELL_LEVEL_GENE_TEST_NOT_DONOR_DISEASE_P', 'available_official_result_fields': list(result), 'table_columns': table.columns.tolist(), 'numeric_output_masks': numeric_masks, 'existing_rank_uns_overwritten': overwritten, 'warnings': [{'category': type(item.message).__name__, 'message': str(item.message)} for item in captured], 'input_sha256': source_sha, 'versions': {package: importlib.metadata.version(package) for package in ['scanpy', 'anndata', 'numpy', 'pandas', 'scipy', 'scikit-learn', 'pyarrow']}, 'threads': 1, 'statistical_unit': 'CELL;NOT_DONOR_OR_ANIMAL', 'scientific_eligibility': 'NOT_VERIFIED;marker exploration only;no study contrast/family/model or biological inference admission', 'G0': False}
    pending, published = [], []
    try:
        for output in outputs:
            descriptor, name = tempfile.mkstemp(prefix='.rank-genes-', dir=output.parent)
            os.close(descriptor)
            pending.append(Path(name))
        table.to_parquet(pending[0], index=False, engine='pyarrow')
        pending[1].write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + '\n')
        data.write_h5ad(pending[2], compression='lzf')
        require(digest(source) == source_sha, 'input changed during rank_genes_groups')
        for path in pending:
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
        for staging, target in zip(pending, outputs):
            os.link(staging, target)
            published.append((staging, target))
    except BaseException:
        for staging, target in reversed(published):
            try:
                if os.path.samestat(staging.stat(), target.lstat()):
                    target.unlink()
            except FileNotFoundError:
                pass
        raise
    finally:
        for path in pending:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        print(f'rank_genes_groups failed: {error}', file=sys.stderr)
        sys.exit(2)
