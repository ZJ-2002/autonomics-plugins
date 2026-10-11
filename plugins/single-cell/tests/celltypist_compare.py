"""Whole-object and selected-label confidence comparison against author calls."""

import hashlib
import json

import anndata as ad
import h5py
import numpy as np
from scipy import sparse

from qc_compare import compare_value


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle,'sha256').hexdigest()


def compare(directory):
    actual = ad.read_h5ad(directory/'output.h5ad')
    expected = ad.read_h5ad(directory/'fresh-author.h5ad')
    source = ad.read_h5ad(directory/'input.h5ad')
    assert actual.shape == expected.shape == source.shape
    finite = compare_value(actual.X,expected.X)+compare_value(actual.obs,expected.obs)+compare_value(actual.var,expected.var)
    for name in ['layers','obsm','varm','obsp','varp','uns']:
        finite += compare_value(dict(getattr(actual,name)),dict(getattr(expected,name)))
    assert (actual.raw is None)==(expected.raw is None)
    if expected.raw is not None:
        finite += compare_value(actual.raw.X,expected.raw.X)+compare_value(actual.raw.var,expected.raw.var)
        finite += compare_value(dict(actual.raw.varm),dict(expected.raw.varm))
    with h5py.File(directory/'output.h5ad') as result,h5py.File(directory/'fresh-author.h5ad') as author:
        names,author_names = [],[]
        result.visit(names.append);author.visit(author_names.append)
        assert names==author_names
        for name in ['/',*names]:
            assert set(result[name].attrs)==set(author[name].attrs)
            for key in author[name].attrs:
                np.testing.assert_array_equal(result[name].attrs[key],author[name].attrs[key])
            if isinstance(author[name],h5py.Dataset):
                assert result[name].dtype==author[name].dtype
                if author[name].dtype.kind in 'fc':
                    np.testing.assert_allclose(result[name][()],author[name][()],atol=1e-12,rtol=0,equal_nan=True)
                else:
                    np.testing.assert_array_equal(result[name][()],author[name][()])
    report = json.loads((directory/'report.json').read_text(),parse_constant=lambda value:(_ for _ in ()).throw(ValueError(value)))
    request = json.loads((directory/'request.json').read_text())
    assert report['model_file']==request['model_file'] and report['majority_voting']==request['majority_voting']
    applied = request['majority_voting'] and expected.n_obs > 50 and 'majority_voting' in expected.obs
    label = 'majority_voting' if applied else 'predicted_labels'
    assert report['majority_voting_applied']==applied and report['label_column']==report['confidence_label_column']==label
    assert report['input_sha256']==digest(directory/'input.h5ad') and report['cells']==source.n_obs
    assert report['model_cell_type_axis']==list(expected.obsm['celltypist_probability'].columns)
    assert report['label_counts']=={str(key):int(value) for key,value in expected.obs['celltypist_label'].value_counts().items()}
    assert sum(report['label_counts'].values())==source.n_obs
    confidence = expected.obs['conf_score'].to_numpy()
    for key,value in zip(['min','p25','median','p75','max'],np.percentile(confidence,[0,25,50,75,100])):
        np.testing.assert_allclose(report['confidence'][key],value,atol=1e-12,rtol=0)
    matrix,names,prediction_source = (source.raw.X,source.raw.var_names,'raw') if source.X[:1000].min()<0 or source.X[:1000].max()>9.22 else (source.X,source.var_names,'X')
    assert report['prediction_source']==prediction_source and report['selected_expression_genes']==len(names)
    if sparse.issparse(matrix):
        counts=matrix.copy();counts.data=np.expm1(counts.data);totals=np.asarray(counts.sum(axis=1)).ravel()
    else:
        totals=np.expm1(matrix).sum(axis=1)
    np.testing.assert_allclose(report['all_cell_normalized_count_totals'],totals,atol=1e-12,rtol=0)
    assert report['cells_outside_10000_plusminus1']==list(source.obs_names[np.abs(totals-10000)>1])
    assert report['outputs']==[{'port':0,'name':'output.h5ad','bytes':(directory/'output.h5ad').stat().st_size,'sha256':digest(directory/'output.h5ad')}]
    assert report['scientific_release']=='NOT_GRANTED' and report['G0'] is False
    return {'pass':True,'shape':list(actual.shape),'finite_values_checked':int(finite),
        'all_prediction_scores_probabilities_labels_and_confidence_checked':True,
        'whole_AnnData_HDF5_and_raw_components_checked':True,'float_atol':1e-12,'float_rtol':0,'integer_payloads_exact':True,'G0':False}
