import csv
import json
import math
from pathlib import Path
import sys


FIELDS = ['m_IVs','h2_exp','h2_exp_se','h2_out','h2_out_se','rg','rg_se','gcov','gcov_se',
          'int_crosstrait','int_crosstrait_se','mr_naive','mr_naive_se','mr_corrected',
          'mr_corrected_se','mr_corrected_p','egger_intercept_p']
EDGES = [('XM','BMFF->Monocyte'),('XY','BMFF->GripStrength'),('MY','Monocyte->GripStrength')]
TOLERANCE = 1e-12


def read_rows(filename):
    with Path(filename).open() as handle:
        reader = csv.DictReader(handle,delimiter='\t')
        if reader.fieldnames!=['edge']+FIELDS:
            raise ValueError('Exact summary schema is required')
        rows = list(reader)
    if any(set(row)!=set(['edge']+FIELDS) or any(value is None for value in row.values()) for row in rows):
        raise ValueError('Malformed summary row')
    return rows


def compare_rows(reference, actual):
    count = 0
    for field in FIELDS:
        expected = reference[field]
        observed = actual[field]
        if expected=='NA' or observed=='NA':
            if field!='rg_se' or expected!=observed:
                raise ValueError('Unqualified missing value: '+field)
        else:
            expected_number = float(expected)
            observed_number = float(observed)
            if not math.isfinite(expected_number) or not math.isfinite(observed_number):
                raise ValueError('Non-finite comparison is not a pass: '+field)
            if abs(expected_number-observed_number)>TOLERANCE:
                raise ValueError('Summary differs from frozen reference: '+field)
        count += 1
    return count


def verify(reference_path, work):
    reference = read_rows(reference_path)
    if len(reference)!=3 or {row['edge'] for row in reference}!={tag for tag,label in EDGES}:
        raise ValueError('Exactly three distinct frozen reference edges are required')
    mapped = {row['edge']:row for row in reference}
    compared = 0
    missing = 0
    for index, (tag,label) in enumerate(EDGES):
        actual = read_rows(Path(work)/('edge_'+str(index))/'summary.tsv')
        if len(actual)!=1 or actual[0]['edge']!=label:
            raise ValueError('Expected one correctly identified output edge: '+tag)
        compared += compare_rows(mapped[tag],actual[0])
        missing += sum(mapped[tag][field]=='NA' for field in FIELDS)
    if compared!=51:
        raise ValueError('Incomplete comparison census')
    return {'summary_entries_verified':compared,'finite_numeric_comparisons':compared-missing,
            'explicit_missing_rg_se_entries':missing,'tolerance':TOLERANCE,'G0':False}


if __name__=='__main__':
    print(json.dumps(verify(sys.argv[1],sys.argv[2])))
