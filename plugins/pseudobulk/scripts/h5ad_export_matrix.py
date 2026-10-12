import hashlib
import importlib.metadata
import json
import os
import sys
import tempfile
from pathlib import Path

import anndata as ad
import h5py
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import scipy.sparse as sp


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def scalar(value):
    return value.item() if isinstance(value, np.generic) else value


def metadata(frame, key):
    require(isinstance(frame, pd.DataFrame), 'metadata must decode as an AnnData dataframe')
    require(frame.index.is_unique and all(isinstance(value, str) and value != '' for value in frame.index), 'axis IDs must be unique nonempty strings')
    require(frame.columns.is_unique and key not in frame.columns, f'metadata conflicts with exported axis key {key}')
    require(all(isinstance(column, str) and column != '' for column in frame.columns), 'metadata columns must be unique nonempty strings')
    fields = []
    for column in frame.columns:
        series = frame[column]
        field = {'name': column, 'dtype': str(series.dtype), 'missing_rows': np.flatnonzero(series.isna().to_numpy()).tolist()}
        if isinstance(series.dtype, pd.CategoricalDtype):
            field['categories'] = [scalar(value) for value in series.cat.categories]
            field['ordered'] = bool(series.cat.ordered)
            field['category_dtype'] = str(series.cat.categories.dtype)
        fields.append(field)
    return {'index_name': frame.index.name, 'axis_key': key, 'fields': fields, 'rows': len(frame)}


def exact_float(values):
    source = np.asarray(values)
    require(source.dtype.kind in 'biufO', 'matrix must contain real numeric values')
    result = source.astype(np.float64)
    if source.dtype.kind in 'iu':
        risky = (source > 2**53) | (source < -(2**53)) if source.dtype.kind == 'i' else source > 2**53
        for original, converted in zip(source[risky], result[risky]):
            require(int(original) == int(converted), 'integer cannot be represented exactly by the original float64 value port')
    elif source.dtype.kind == 'O':
        for original, converted in zip(source, result):
            require(isinstance(original, int) and int(converted) == original, 'summed integer cannot be represented exactly by the original float64 value port')
    else:
        require(source.dtype.itemsize <= 8, 'matrix floating dtype exceeds the original float64 port precision')
    return result


def validate_sparse(group, shape):
    encoding = group.attrs.get('encoding-type', '')
    require(encoding in {'csr_matrix', 'csc_matrix'}, 'selected matrix group is not supported AnnData CSR/CSC encoding')
    require(set(['data', 'indices', 'indptr']) <= set(group), 'sparse matrix storage is incomplete')
    require(all(group[key].ndim == 1 for key in ['data', 'indices', 'indptr']), 'sparse buffers must be one dimensional')
    require(group['data'].shape == group['indices'].shape, 'sparse data/index lengths differ')
    require(group['indices'].dtype.kind in 'iu' and group['indptr'].dtype.kind in 'iu', 'sparse indices and pointers must be integers')
    outer, inner = shape if encoding == 'csr_matrix' else shape[::-1]
    pointers = group['indptr'][:]
    require(len(pointers) == outer + 1 and len(pointers) > 0 and int(pointers[0]) == 0 and int(pointers[-1]) == len(group['data']), 'sparse pointer bounds do not match matrix storage')
    require(not np.any(pointers[1:] < pointers[:-1]), 'sparse pointers are not monotone')
    for start in range(0, len(group['indices']), 1000000):
        indices = group['indices'][start:start + 1000000]
        require(not np.any(indices < 0) and not np.any(indices >= inner), 'sparse coordinate is outside the selected matrix axis')


def coordinates(block):
    if not sp.issparse(block):
        dense = np.asarray(block)
        require(dense.ndim == 2, 'selected row block is not two dimensional')
        rows, columns = np.nonzero(dense)
        return rows, columns, exact_float(dense[rows, columns])
    sparse = block.tocsr(copy=True)
    if sparse.dtype.kind in 'iu' and not sparse.has_canonical_format:
        rows, columns, values = [], [], []
        limits = np.iinfo(sparse.dtype)
        for row in range(sparse.shape[0]):
            totals = {}
            for index in range(sparse.indptr[row], sparse.indptr[row + 1]):
                column = int(sparse.indices[index])
                totals[column] = totals.get(column, 0) + int(sparse.data[index])
            for column, total in sorted(totals.items()):
                require(limits.min <= total <= limits.max, 'sparse integer sum exceeds the original storage dtype')
                if total != 0:
                    rows.append(row)
                    columns.append(column)
                    values.append(total)
        return np.asarray(rows, dtype=np.int64), np.asarray(columns, dtype=np.int64), exact_float(np.asarray(values, dtype=object))
    sparse.sum_duplicates()
    sparse.sort_indices()
    sparse.eliminate_zeros()
    coo = sparse.tocoo()
    return coo.row, coo.col, exact_float(coo.data)


def run():
    chunk_raw = os.environ.get('EXPORT_CHUNK', '2000')
    require(chunk_raw.isdecimal() and int(chunk_raw) > 0, 'EXPORT_CHUNK must be a positive integer')
    chunk = int(chunk_raw)
    layer = os.environ.get('EXPORT_LAYER', 'X').strip() or 'X'
    selection = 'X' if layer == 'X' else layer if layer.startswith('layers/') else 'layers/' + layer
    require(selection == 'X' or (selection.startswith('layers/') and len(selection.split('/')) == 2 and selection.split('/')[1] not in {'', '.', '..'}), 'invalid selected layer path')
    source = Path(os.environ['AUTONOMICS_INPUT0'])
    require(source.is_file(), 'input H5AD file is missing')
    outputs = [Path(os.environ[f'AUTONOMICS_OUTPUT{number}']) for number in range(4)]
    resolved = [path.resolve() for path in outputs]
    require(len(set(resolved)) == 4 and source.resolve() not in resolved, 'output paths overlap each other or the input')
    require(all(not os.path.lexists(path) and path.parent.is_dir() for path in outputs), 'output already exists or output parent is missing')
    source_sha = sha256(source)
    pending, published = [], []
    try:
        for output in outputs:
            descriptor, name = tempfile.mkstemp(prefix='.h5ad-export-', dir=output.parent)
            os.close(descriptor)
            pending.append(Path(name))
        with h5py.File(source, 'r') as handle:
            require('obs' in handle and 'var' in handle and selection in handle, 'selected matrix or obs/var metadata is missing')
            obs, var = ad.io.read_elem(handle['obs']), ad.io.read_elem(handle['var'])
            obs_schema, var_schema = metadata(obs, 'cell_id'), metadata(var, 'gene_id')
            element = handle[selection]
            if isinstance(element, h5py.Group):
                shape = tuple(int(value) for value in element.attrs.get('shape', ()))
                require(shape == (len(obs), len(var)), 'selected matrix shape differs from obs/var axes')
                validate_sparse(element, shape)
                matrix = ad.io.sparse_dataset(element)
            else:
                matrix = element
                require(matrix.ndim == 2 and matrix.shape == (len(obs), len(var)), 'selected matrix shape differs from obs/var axes')
            require(np.dtype(matrix.dtype).kind in 'biuf', 'selected matrix is not real numeric data')
            count, nan_count, positive_infinity, negative_infinity = 0, 0, 0, 0
            schema = pa.schema([('cell_id', pa.string()), ('gene', pa.string()), ('value', pa.float64())])
            with pq.ParquetWriter(pending[0], schema, compression='zstd') as writer:
                for start in range(0, len(obs), chunk):
                    stop = min(start + chunk, len(obs))
                    rows, columns, values = coordinates(matrix[start:stop])
                    table = pa.table({'cell_id': obs.index.to_numpy(dtype=object)[start:stop][rows], 'gene': var.index.to_numpy(dtype=object)[columns], 'value': values}, schema=schema)
                    writer.write_table(table)
                    count += len(values)
                    nan_count += int(np.isnan(values).sum())
                    positive_infinity += int(np.isposinf(values).sum())
                    negative_infinity += int(np.isneginf(values).sum())
                    print(f'rows {start}-{stop}/{len(obs)} nnz_cum={count}', file=sys.stderr)
            obs.to_csv(pending[1], sep='\t', index_label='cell_id')
            var.to_csv(pending[2], sep='\t', index_label='gene_id')
            log = [f'layer\t{layer}', f'selection_path\t{selection}', f'shape\tcells={len(obs)}\tgenes={len(var)}\tdtype={matrix.dtype}', f'entries\t{count}\tnote: nonzero-only export; absent coordinates are zero in this complete selected matrix, not measured missingness or inferential eligibility', 'integer_policy\texact float64 representability required; no silent integer rounding', f'nonfinite_payloads\tnan={nan_count}\tpositive_inf={positive_infinity}\tnegative_inf={negative_infinity}', f'input_sha256\t{source_sha}', 'metadata_schema_json\t' + json.dumps({'obs': obs_schema, 'var': var_schema}, ensure_ascii=False, allow_nan=False), 'versions_json\t' + json.dumps({package: importlib.metadata.version(package) for package in ['anndata', 'numpy', 'pandas', 'scipy', 'h5py', 'pyarrow']}), 'scientific_eligibility\tNOT_VERIFIED; no count-scale, gene-species, donor, mapping or research authorization inferred']
            pending[3].write_text('\n'.join(log) + '\n', encoding='utf-8')
        require(sha256(source) == source_sha, 'input H5AD changed during export')
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
        for staging in pending:
            staging.unlink(missing_ok=True)


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        print(f'h5ad_export_matrix failed: {error}', file=sys.stderr)
        sys.exit(2)
