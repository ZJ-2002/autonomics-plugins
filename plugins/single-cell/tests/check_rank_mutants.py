import argparse
import json
import shutil
from pathlib import Path

import anndata as ad
import numpy as np
import pandas as pd

from rank_compare import compare


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('evidence', type=Path)
    arguments = parser.parse_args()
    compare(arguments.source)
    records = []
    for name in ['integer_metadata_plus_one', 'marker_score_one_ULP', 'tested_gene_ID_missing']:
        directory = arguments.evidence / name
        shutil.copytree(arguments.source, directory)
        if name == 'integer_metadata_plus_one':
            data = ad.read_h5ad(directory / 'output.h5ad')
            data.var.iloc[0, data.var.columns.get_loc('integer')] += 1
            data.write_h5ad(directory / 'output.h5ad', compression='lzf')
        elif name == 'marker_score_one_ULP':
            table = pd.read_parquet(directory / 'markers.parquet')
            position = next(index for index, value in enumerate(table['score']) if not pd.isna(value) and np.isfinite(value))
            table.loc[position, 'score'] = np.nextafter(float(table.loc[position, 'score']), np.inf)
            table.to_parquet(directory / 'markers.parquet', index=False)
        else:
            path = directory / 'report.json'
            report = json.loads(path.read_text())
            report['tested_gene_universe'].pop()
            path.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False) + '\n')
        try:
            compare(directory)
        except (AssertionError, ValueError) as error:
            (directory / 'REJECTION.txt').write_text(type(error).__name__ + ':' + str(error) + '\n')
        else:
            raise AssertionError('comparison failed to reject ' + name)
        records.append({'mutant': name, 'rejected': True})
        print(name, 'REJECTED', flush=True)
    (arguments.evidence / 'MUTANT_COMPARISON.json').write_text(json.dumps({'unchanged_control': 'PASS', 'mutants': records, 'G0': False}, indent=2) + '\n')


if __name__ == '__main__':
    main()
