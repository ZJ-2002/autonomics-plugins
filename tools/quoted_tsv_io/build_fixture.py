import json
from pathlib import Path
import random
import sys

import anndata as ad
import numpy as np
import pandas as pd


root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
for special in [False, True]:
    directory = root / ('quoted-identities' if special else 'simple-identities')
    directory.mkdir()
    generator = random.Random(410612)
    donors = ['d' + str(index + 1) for index in range(12)]
    genes = ['gene' + str(index + 1) for index in range(200)]
    if special:
        donors[:7] = ['"leading', 's"middle', "O'Neil", 'NA', '0001', '中文样本', 'sample,comma']
        genes[:7] = ['"leading', 'g"middle', "O'Gene", 'NA', '0001', '中文基因', 'gene,comma']
    conditions = ['ctrl'] * 6 + ['case'] * 6
    counts = []
    for gene_index in range(200):
        baseline = generator.uniform(70, 1500)
        counts.append([max(1, round(generator.gammavariate(8, baseline / 8) *
            (2 if gene_index < 20 and sample_index >= 6 else 1) * (0.7 + sample_index / 20))) for sample_index in range(12)])
    genes.append('zero_gene')
    counts.append([0] * 12)
    rows = []
    donor_rows, condition_rows = [], []
    for sample_index, donor in enumerate(donors):
        parts = [[value // 3 for value in [row[sample_index] for row in counts]] for number in range(3)]
        for gene_index, row in enumerate(counts):
            parts[2][gene_index] += row[sample_index] % 3
        rows.extend(parts)
        donor_rows.extend([donor] * 3)
        condition_rows.extend([conditions[sample_index]] * 3)
    data = ad.AnnData(np.array(rows, dtype=np.int64),
        obs=pd.DataFrame({'donor': donor_rows, 'celltype': ['A'] * len(rows), 'condition': condition_rows},
            index=['cell' + str(index + 1) for index in range(len(rows))]), var=pd.DataFrame(index=genes))
    data.write_h5ad(directory / 'input.h5ad')
    ordering = sorted(range(len(donors)), key=lambda index: donors[index])
    oracle = {'genes': genes, 'samples': [donors[index] + '__A' for index in ordering],
        'donors': [donors[index] for index in ordering], 'conditions': [conditions[index] for index in ordering],
        'count_rows': [[row[index] for index in ordering] for row in counts],
        'scope': 'Independently generated decoded arrays and lexical donor order; not read from producer artifacts', 'G0': False}
    (directory / 'decoded-oracle.json').write_text(json.dumps(oracle, ensure_ascii=False, indent=2) + '\n')
print('SYNTHETIC_FIXTURES_ONLY')
