import json
from pathlib import Path
import shutil
import sys

import anndata as ad

from test_marker_assurance import compare


source = Path(sys.argv[1])
root = Path(sys.argv[2])
compare(source)
records = []
for name in ['large_integer_metadata_plus_one', 'mean_score_plus_micro', 'member_weights_wrong_but_sum_one']:
    directory = root / name
    shutil.copytree(source, directory)
    if name == 'member_weights_wrong_but_sum_one':
        report = json.loads((directory / 'report.json').read_text())
        weights = report['marker_sets']['weighted']['effective_weights']
        assert weights['g1'] != weights['g2']
        weights['g1'], weights['g2'] = weights['g2'], weights['g1']
        (directory / 'report.json').write_text(json.dumps(report, allow_nan=False) + '\n')
    else:
        data = ad.read_h5ad(directory / 'output.h5ad')
        if name == 'large_integer_metadata_plus_one':
            data.var.iloc[0, data.var.columns.get_loc('integer_metadata')] += 1
        else:
            data.obs.iloc[0, data.obs.columns.get_loc('marker_score')] += 1e-6
        data.write_h5ad(directory / 'output.h5ad', compression='lzf')
    try:
        compare(directory)
    except (AssertionError, ValueError) as error:
        (directory / 'REJECTION.txt').write_text(type(error).__name__ + ':' + str(error) + '\n')
    else:
        raise AssertionError('comparison failed to reject ' + name)
    records.append({'mutant': name, 'rejected': True})
    print(name, 'REJECTED', flush=True)
(root / 'MUTANT_COMPARISON.json').write_text(json.dumps({'unchanged_control': 'PASS', 'mutants': records, 'G0': False}, indent=2) + '\n')
