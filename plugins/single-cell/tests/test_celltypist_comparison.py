"""Ensure label/confidence and class-axis errors cannot pass whole comparisons."""

import argparse
import json
from pathlib import Path
import shutil

import anndata as ad

from celltypist_compare import compare, digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('golden', type=Path)
    parser.add_argument('evidence', type=Path)
    arguments = parser.parse_args()
    arguments.evidence.mkdir()
    assert compare(arguments.golden)['pass']
    rows = []
    for variant in ['maximum-confidence-for-voted-label', 'permuted-class-axis', 'false-voting-status']:
        directory = arguments.evidence / variant
        directory.mkdir()
        for name in ['input.h5ad', 'output.h5ad', 'report.json', 'request.json', 'fresh-author.h5ad', 'fresh-author.json']:
            shutil.copyfile(arguments.golden / name, directory / name)
        data = ad.read_h5ad(directory / 'output.h5ad')
        report = json.loads((directory / 'report.json').read_text())
        if variant == 'maximum-confidence-for-voted-label':
            maximum = data.obsm['celltypist_probability'].max(axis=1)
            assert (maximum != data.obs['celltypist_conf_score']).any()
            data.obs['conf_score'] = maximum
            data.obs['celltypist_conf_score'] = maximum
            data.write_h5ad(directory / 'output.h5ad', compression='lzf')
        elif variant == 'permuted-class-axis':
            matrix = data.obsm['celltypist_probability'].copy()
            matrix.columns = matrix.columns[::-1]
            data.obsm['celltypist_probability'] = matrix
            data.write_h5ad(directory / 'output.h5ad', compression='lzf')
        else:
            report['majority_voting_applied'] = False
        report['outputs'][0].update(bytes=(directory / 'output.h5ad').stat().st_size,
                                     sha256=digest(directory / 'output.h5ad'))
        (directory / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        try:
            compare(directory)
        except AssertionError:
            rows.append({'case': variant, 'mutant_refused': True})
        else:
            raise AssertionError('Incorrect annotation result was accepted: ' + variant)
    (arguments.evidence / 'SUMMARY.json').write_text(json.dumps({'cases': len(rows), 'records': rows, 'G0': False}, indent=2) + '\n')


if __name__ == '__main__':
    main()
