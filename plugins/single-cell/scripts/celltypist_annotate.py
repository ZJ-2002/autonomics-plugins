"""Verified catalog models and explicit CellTypist 1.7.1 annotation semantics."""

from contextlib import ExitStack
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import tempfile
import warnings

import anndata as ad
import celltypist
from celltypist import models
import numba
import numpy as np
import scanpy as sc
from scipy import sparse
from threadpoolctl import threadpool_limits


OFFICIAL_MODELS = {
    'Immune_All_Low.pkl': '290874d35dac039d4c9218c343fde4aac1077709b72a331ce7266f6828c36502',
    'Immune_All_High.pkl': 'a715fec36c2c421f7c4e31cf4cb4bea883eedab7fd7b20a4b76f091c22660448',
}


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


def model_path():
    directory = required_path('SC_MODEL_DIR').resolve(strict=True)
    name = os.environ.get('SC_MODEL_FILE', 'Immune_All_Low.pkl')
    if name != os.environ.get('SC_P_STR_MODEL_FILE', name):
        raise ContractError('model_file bindings disagree')
    if name not in OFFICIAL_MODELS or Path(name).name != name:
        raise ContractError('model_file must select a verified named model in the declared Pan-immune v2 catalog')
    path = directory / name
    if not path.is_file() or path.resolve(strict=True).parent != directory:
        raise ContractError('model_file must stay inside the declared catalog directory')
    if digest(path) != OFFICIAL_MODELS[name]:
        raise ContractError('model SHA256 differs from the frozen official primary model; refusing pickle deserialization')
    if 'AUTONOMICS_INPUT1' in os.environ:
        raise ContractError('undeclared model input port1 is forbidden;use the declared model catalog')
    return path


def numeric_values(matrix):
    return matrix.data if sparse.issparse(matrix) else np.asarray(matrix)


def selected_expression(data):
    if data.X is None or data.n_obs == 0 or data.n_vars == 0:
        raise ContractError('CellTypist requires nonempty X;metadata-only input is not an annotation matrix')
    prefix = numeric_values(data.X[:1000])
    if prefix.dtype.kind not in 'biuf':
        raise ContractError('X must be a real numeric matrix')
    minimum = min(float(prefix.min()) if prefix.size else 0., 0.) if sparse.issparse(data.X) else float(prefix.min())
    maximum = max(float(prefix.max()) if prefix.size else 0., 0.) if sparse.issparse(data.X) else float(prefix.max())
    use_raw = minimum < 0 or maximum > 9.22
    if use_raw:
        if data.raw is None:
            raise ContractError('invalid X and no raw log-count matrix for the official fallback')
        matrix, names = data.raw.X, data.raw.var_names
    else:
        matrix, names = data.X, data.var_names
    values = numeric_values(matrix)
    if values.dtype.kind not in 'biuf' or not np.isfinite(values).all() or (values < 0).any() or (values > 9.22).any():
        raise ContractError('all selected expression values must be finite log1p-count values in [0,9.22]')
    if names.has_duplicates or any(not str(name) for name in names):
        raise ContractError('selected prediction gene identifiers must be unique and nonempty')
    transformed = matrix.copy()
    if sparse.issparse(transformed):
        transformed.data = np.expm1(transformed.data)
        totals = np.asarray(transformed.sum(axis=1)).ravel()
    else:
        totals = np.expm1(transformed).sum(axis=1)
    return matrix, names, 'raw' if use_raw else 'X', totals


def annotate(data, path, voting):
    if data.obs_names.has_duplicates or data.var_names.has_duplicates or any(not str(name) for name in data.obs_names):
        raise ContractError('obs_names and var_names must be unique;cell identifiers must be nonempty')
    matrix, names, source, totals = selected_expression(data)
    name_set = set(names)
    model = models.Model.load(str(path))
    overlap = np.isin(names, model.features)
    if not overlap.any():
        raise ContractError('no gene symbols overlap the model;no automatic identifier or species mapping')
    over_clustering = 'leiden' if 'leiden' in data.obs else None
    if voting and data.n_obs > 50 and over_clustering is not None:
        if data.obs['leiden'].isna().any() or data.obs['leiden'].astype(str).str.len().eq(0).any():
            raise ContractError('supplied over-clustering labels must cover every cell')
    original_obs = list(data.obs.columns)
    original_obsm = list(data.obsm)
    result = celltypist.annotate(data, model=model, transpose_input=False, mode='best match', p_thres=.5,
        majority_voting=voting, over_clustering=over_clustering, use_GPU=False, min_prop=0)
    applied = voting and 'majority_voting' in result.predicted_labels.columns
    label_column = 'majority_voting' if applied else 'predicted_labels'
    annotated = result.to_adata(insert_labels=True, insert_conf=True, insert_conf_by=label_column,
                               insert_decision=False, insert_prob=False, prefix='')
    annotated.obs['celltypist_label'] = annotated.obs[label_column].astype(str)
    annotated.obs['celltypist_conf_score'] = annotated.obs['conf_score'].astype(float)
    for label, frame in [('decision', result.decision_matrix), ('probability', result.probability_matrix)]:
        if not frame.index.equals(annotated.obs.index) or not np.isfinite(frame.to_numpy()).all():
            raise ContractError(f'nonfinite or misaligned {label} matrix')
        annotated.obsm['celltypist_' + label] = frame.copy()
    confidence = annotated.obs['celltypist_conf_score'].to_numpy()
    if not np.isfinite(confidence).all() or (confidence < 0).any() or (confidence > 1).any():
        raise ContractError('CellTypist returned invalid confidence values')
    annotated.uns['celltypist_params'] = {'model_file': path.name, 'majority_voting': voting}
    report = {'schema_version': '2.0', 'operation': 'celltypist_annotate', 'cells': annotated.n_obs,
        'model_file': path.name, 'model_sha256': OFFICIAL_MODELS[path.name], 'majority_voting': voting,
        'majority_voting_applied': applied, 'majority_voting_status': 'APPLIED' if applied else
            'OFFICIAL_SKIPPED_N_LE_50' if voting and data.n_obs <= 50 else 'NOT_REQUESTED',
        'label_column': label_column, 'confidence_label_column': label_column,
        'confidence': dict(zip(['min', 'p25', 'median', 'p75', 'max'], np.percentile(confidence, [0,25,50,75,100]).tolist())),
        'label_counts': {str(key): int(value) for key, value in annotated.obs['celltypist_label'].value_counts().items()},
        'prediction_source': source, 'selected_expression_genes': len(names), 'model_genes': len(model.features),
        'genes_used': [str(name) for name in names[overlap]], 'missing_model_genes': [str(name) for name in model.features if name not in name_set],
        'all_cell_normalized_count_totals': totals.tolist(), 'cells_outside_10000_plusminus1': list(data.obs_names[np.abs(totals-10000)>1]),
        'scale_policy': 'Official first-1000 X/raw selection preserved;full selected matrix validated;partial-gene normalization flagged,not silently repaired',
        'probability_semantics': 'Per-class sigmoid,not softmax sums or a calibrated probability of biological correctness',
        'model_cell_type_axis': list(result.probability_matrix.columns),
        'prediction_matrices': {'decision': 'obsm/celltypist_decision', 'probability': 'obsm/celltypist_probability'},
        'over_clustering_source': 'leiden' if applied and over_clustering else 'OFFICIAL_AUTO' if applied else 'NOT_USED',
        'overwritten_obs_columns': [name for name in result.predicted_labels.columns if name in original_obs] +
            [name for name in ['conf_score','celltypist_label','celltypist_conf_score'] if name in original_obs],
        'overwritten_prediction_matrices': [name for name in ['celltypist_decision','celltypist_probability'] if name in original_obsm],
        'author_threads': 1, 'scientific_release': 'NOT_GRANTED', 'G0': False,
        'study_species_gene_scale_donor_model_and_reference_calibration': 'NOT_VERIFIED',
        'packages': {name: importlib.metadata.version(name) for name in ['celltypist','scanpy','anndata','scikit-learn','igraph','numpy','scipy']}}
    return annotated, report


def publish(data, report, output, report_path):
    published = []
    with ExitStack() as stack:
        directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='.celltypist-', dir=output.parent)))
        report_directory = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='.celltypist-', dir=report_path.parent)))
        staged = directory / 'output.h5ad'
        staged_report = report_directory / 'report.json'
        data.write_h5ad(staged, compression='lzf')
        report['outputs'] = [{'port': 0, 'name': output.name, 'bytes': staged.stat().st_size, 'sha256': digest(staged)}]
        report['report_hash_policy'] = 'port_1_hash_recorded_externally_not_recursively'
        staged_report.write_text(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)+'\n')
        for path in [staged, staged_report]:
            with path.open('rb') as handle:
                os.fsync(handle.fileno())
        try:
            for source, destination in [(staged, output), (staged_report, report_path)]:
                status = source.stat()
                os.link(source, destination)
                published.append((destination, (status.st_dev, status.st_ino)))
        except OSError:
            for destination, identity in reversed(published):
                try:
                    status = destination.lstat()
                    if (status.st_dev, status.st_ino) == identity:
                        destination.unlink()
                except FileNotFoundError:
                    pass
            raise


def run():
    value = os.environ.get('SC_P_BOOL_MAJORITY_VOTING', 'false')
    if value not in ['true', 'false']:
        raise ContractError('majority_voting must be true or false')
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
    path = model_path()
    checksum = digest(source)
    numba.set_num_threads(1)
    sc.settings.n_jobs = 1
    with threadpool_limits(limits=1), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        data, report = annotate(ad.read_h5ad(source), path, value == 'true')
    if digest(source) != checksum or digest(path) != OFFICIAL_MODELS[path.name]:
        raise ContractError('input or trusted model changed during annotation')
    report['input_sha256'] = checksum
    report['warnings'] = [f'{warning.category.__name__}: {warning.message}' for warning in caught]
    publish(data, report, output, report_path)


if __name__ == '__main__':
    try:
        run()
    except ContractError as error:
        print(f'h5ad_celltypist_annotate: {error}', file=sys.stderr)
        raise SystemExit(2)
    except Exception as error:
        print(f'h5ad_celltypist_annotate: {error}', file=sys.stderr)
        raise SystemExit(3)
