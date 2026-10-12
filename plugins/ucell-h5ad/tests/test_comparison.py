"""Verify that the whole-object comparison rejects scientifically wrong outputs."""

import argparse
import json
from pathlib import Path
import shutil

import anndata as ad
import numpy as np
from scipy.stats import rankdata

from test_official import compare


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('evidence', type=Path)
    arguments = parser.parse_args()
    arguments.evidence.mkdir()
    records = []
    for name in ['legacy-rank-approximation', 'reversed-cell-scores', 'lost-layer', 'wrong-report-identity']:
        directory = arguments.evidence / name
        shutil.copytree(arguments.source, directory)
        programs = json.loads((directory / 'request.json').read_text())
        if name == 'wrong-report-identity':
            report = json.loads((directory / 'report.json').read_text())
            report['input_sha256'] = '0' * 64
            (directory / 'report.json').write_text(json.dumps(report) + '\n')
        else:
            actual = ad.read_h5ad(directory / 'output.h5ad')
            if name == 'legacy-rank-approximation':
                expression = np.asarray(actual.X)
                ranks = (actual.n_vars + 1) - rankdata(expression, axis=1, method='average')
                positions = [actual.var_names.get_loc(gene) for gene in programs['positive']]
                margin = max(1., (actual.n_vars - len(positions)) / 2.)
                actual.obs['positive'] = (margin / (margin + ranks[:, positions])).mean(axis=1)
            elif name == 'reversed-cell-scores':
                actual.obs['positive'] = actual.obs['positive'].to_numpy()[::-1]
            else:
                del actual.layers['original_integer_layer']
            actual.write_h5ad(directory / 'output.h5ad', compression='lzf')
        try:
            compare(directory, programs)
        except (AssertionError, ValueError, KeyError) as error:
            records.append({'case': name, 'mutant_refused': True,
                            'failure_type': type(error).__name__, 'message': str(error)[:1000]})
        else:
            raise AssertionError('comparison accepted mutant: ' + name)
    (arguments.evidence / 'SUMMARY.json').write_text(json.dumps({'cases': len(records),
        'records': records, 'production_calculation_changed': False, 'G0': False}, indent=2) + '\n')


if __name__ == '__main__':
    main()
