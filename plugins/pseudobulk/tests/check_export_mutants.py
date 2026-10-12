import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from test_export_assurance import compare


parser = argparse.ArgumentParser()
parser.add_argument('reference', type=Path)
parser.add_argument('output', type=Path)
arguments = parser.parse_args()
arguments.output.mkdir()
results = []
for mutation in ['one-ULP-value', 'gene-axis', 'metadata-null-mask']:
    directory = arguments.output / mutation
    directory.mkdir()
    for filename in ['input.h5ad', 'matrix.parquet', 'obs.tsv', 'var.tsv', 'export.log']:
        shutil.copyfile(arguments.reference / filename, directory / filename)
    outputs = [directory / filename for filename in ['matrix.parquet', 'obs.tsv', 'var.tsv', 'export.log']]
    compare(directory, directory / 'input.h5ad', outputs, 'X')
    if mutation == 'metadata-null-mask':
        lines = outputs[3].read_text().splitlines()
        for index, line in enumerate(lines):
            if line.startswith('metadata_schema_json\t'):
                schema = json.loads(line.split('\t', 1)[1])
                field = next(field for field in schema['obs']['fields'] if field['name'] == 'missing')
                assert field['missing_rows'] == [0]
                field['missing_rows'] = []
                lines[index] = 'metadata_schema_json\t' + json.dumps(schema)
        outputs[3].write_text('\n'.join(lines) + '\n')
    else:
        table = pq.read_table(outputs[0])
        data = table.to_pydict()
        if mutation == 'one-ULP-value':
            data['value'][0] = float(np.nextafter(data['value'][0], np.inf))
        else:
            data['gene'][0] = 'WRONG_LITERAL_GENE'
        pq.write_table(pa.table(data, schema=table.schema), outputs[0])
    rejected = False
    try:
        compare(directory, directory / 'input.h5ad', outputs, 'X')
    except AssertionError:
        rejected = True
    assert rejected, mutation
    results.append({'mutation': mutation, 'unchanged_control_passed': True, 'actual_comparison_rejected': True})
(arguments.output / 'SUMMARY.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results))
