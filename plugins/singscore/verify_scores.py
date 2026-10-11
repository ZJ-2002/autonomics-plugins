import argparse
import csv
import math
from pathlib import Path


def read_scores(filename):
    with Path(filename).open(newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t')
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('Missing or repeated score column headers')
        if not {'sample', 'TotalScore'}.issubset(reader.fieldnames):
            raise ValueError('Scores must carry sample and TotalScore')
        scores = {}
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('Ragged score row')
            sample = row['sample']
            if not sample.strip() or sample != sample.strip() or sample in scores:
                raise ValueError('Empty, whitespace-padded or duplicate sample identity')
            value = float(row['TotalScore'])
            if not math.isfinite(value):
                raise ValueError('Nonfinite score is not an agreement')
            scores[sample] = value
    if not scores:
        raise ValueError('Empty scores cannot pass')
    return scores


def verify(golden, observed, log):
    expected = read_scores(golden)
    actual = read_scores(observed)
    if expected.keys() != actual.keys():
        raise ValueError('Sample identities differ from the independent reference')
    for sample, value in expected.items():
        if not math.isclose(value, actual[sample], rel_tol=0, abs_tol=1e-12):
            raise ValueError('Score differs from the independent reference: ' + sample)
    if not Path(log).is_file() or Path(log).stat().st_size == 0:
        raise ValueError('Declared log port is absent or empty')
    return len(expected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('golden', type=Path)
    parser.add_argument('observed', type=Path)
    parser.add_argument('log', type=Path)
    arguments = parser.parse_args()
    try:
        count = verify(arguments.golden, arguments.observed, arguments.log)
    except (OSError, ValueError) as error:
        parser.exit(1, 'FAIL: ' + str(error) + '\n')
    print(f'PASS: {count} distinct finite sample scores agree at absolute tolerance 1e-12; log present')
