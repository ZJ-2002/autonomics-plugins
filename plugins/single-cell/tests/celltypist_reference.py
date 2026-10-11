"""Independent official model/package calls plus complete affine-score checks."""

import json
import os
from pathlib import Path
import sys

import anndata as ad
import celltypist
import numba
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.special import expit
import scanpy as sc
from threadpoolctl import threadpool_limits

from celltypist_fixtures import model


def reference(directory, models_directory):
    expected_library = Path(os.environ['PYTHONPATH'])
    assert Path(celltypist.__file__).is_relative_to(expected_library)
    assert Path(sc.__file__).is_relative_to(expected_library)
    assert Path(ad.__file__).is_relative_to(expected_library)
    request = json.loads((directory/'request.json').read_text())
    data = ad.read_h5ad(directory/'input.h5ad')
    classifier = model(models_directory/request['model_file'])
    expression, genes = (data.raw.X,data.raw.var_names) if data.X[:1000].min()<0 or data.X[:1000].max()>9.22 else (data.X,data.var_names)
    present = np.isin(genes,classifier.features)
    selected = pd.Index(classifier.features).get_indexer(genes[present])
    actual_values = expression[:,present].toarray() if sparse.issparse(expression) else np.asarray(expression[:,present])
    scaled = (actual_values-(classifier.scaler.mean_[selected] if classifier.scaler.with_mean else 0))/classifier.scaler.scale_[selected]
    scaled[scaled>10] = 10
    mathematical_scores = scaled @ classifier.classifier.coef_[:,selected].T + classifier.classifier.intercept_
    numba.set_num_threads(1)
    sc.settings.n_jobs = 1
    with threadpool_limits(limits=1):
        result = celltypist.annotate(data,model=classifier,majority_voting=request['majority_voting'],
            over_clustering='leiden' if 'leiden' in data.obs else None,mode='best match',p_thres=.5,
            transpose_input=False,use_GPU=False,min_prop=0)
    np.testing.assert_allclose(result.decision_matrix.to_numpy(),mathematical_scores,atol=1e-10,rtol=1e-12)
    np.testing.assert_allclose(result.probability_matrix.to_numpy(),expit(mathematical_scores),atol=1e-12,rtol=0)
    label = 'majority_voting' if request['majority_voting'] and 'majority_voting' in result.predicted_labels else 'predicted_labels'
    annotated = result.to_adata(insert_labels=True,insert_conf=True,insert_conf_by=label,
        insert_decision=False,insert_prob=False,prefix='')
    annotated.obs['celltypist_label'] = annotated.obs[label].astype(str)
    annotated.obs['celltypist_conf_score'] = annotated.obs['conf_score'].astype(float)
    annotated.obsm['celltypist_decision'] = result.decision_matrix.copy()
    annotated.obsm['celltypist_probability'] = result.probability_matrix.copy()
    annotated.uns['celltypist_params'] = request
    annotated.write_h5ad(directory/'fresh-author.h5ad',compression='lzf')
    voted_differs = label=='majority_voting' and (annotated.obs['majority_voting'].astype(str)!=annotated.obs['predicted_labels'].astype(str)).any()
    confidence_differs = voted_differs and not np.array_equal(annotated.obs['conf_score'].to_numpy(),result.probability_matrix.max(axis=1).to_numpy())
    (directory/'fresh-author.json').write_text(json.dumps({'module_paths':{'celltypist':celltypist.__file__,'scanpy':sc.__file__},
        'all_affine_scores_and_sigmoid_probabilities_checked':True,'finite_scores':int(mathematical_scores.size),
        'voting_label_differs_from_best_match':bool(voted_differs),'voting_confidence_differs_from_best_match':bool(confidence_differs),
        'confidence_matches_chosen_label':True,'G0':False},indent=2)+'\n')


if __name__=='__main__':
    reference(Path(sys.argv[1]),Path(sys.argv[2]))
