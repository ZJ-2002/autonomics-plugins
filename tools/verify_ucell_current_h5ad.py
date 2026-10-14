"""Compare current H5AD outputs against unchanged sealed author fixtures."""

import argparse
import json
from pathlib import Path
import sys

import anndata as ad
import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent / 'source/single-cell/tests'))
from qc_compare import compare_value, digest


def compare(work):
    actual = ad.read_h5ad(work / 'output.h5ad')
    expected = ad.read_h5ad(work / 'fresh-author.h5ad')
    assert actual.shape == expected.shape
    finite = sum(compare_value(getattr(actual, name), getattr(expected, name)) for name in ['X', 'obs', 'var'])
    for name in ['layers', 'obsm', 'varm', 'obsp', 'varp', 'uns']:
        finite += compare_value(dict(getattr(actual, name)), dict(getattr(expected, name)))
    assert (actual.raw is None) == (expected.raw is None)
    if expected.raw is not None:
        finite += compare_value(actual.raw.X, expected.raw.X) + compare_value(actual.raw.var, expected.raw.var)
        finite += compare_value(dict(actual.raw.varm), dict(expected.raw.varm))
    with h5py.File(work / 'output.h5ad') as produced, h5py.File(work / 'fresh-author.h5ad') as reference:
        actual_names, reference_names = [], []
        produced.visit(actual_names.append)
        reference.visit(reference_names.append)
        assert actual_names == reference_names
        for name in ['/', *reference_names]:
            assert set(produced[name].attrs) == set(reference[name].attrs)
            for key in reference[name].attrs:
                np.testing.assert_array_equal(produced[name].attrs[key], reference[name].attrs[key])
            if isinstance(reference[name], h5py.Dataset):
                assert produced[name].dtype == reference[name].dtype
                if reference[name].dtype.kind in 'fc':
                    np.testing.assert_allclose(produced[name][()], reference[name][()], atol=1e-12, rtol=0, equal_nan=True)
                else:
                    np.testing.assert_array_equal(produced[name][()], reference[name][()])
    original = json.loads((work / 'sealed-report.json').read_text())
    report = json.loads((work / 'report.json').read_text(), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    assert original['input_sha256'] == report['input_sha256'] == digest(work / 'input.h5ad')
    assert set(original) == set(report)
    expected_outputs = [{'port': 0, 'name': 'output.h5ad', 'bytes': (work / 'output.h5ad').stat().st_size,
                         'sha256': digest(work / 'output.h5ad')}]
    assert report['outputs'] == expected_outputs
    assert report['scientific_release'] == 'NOT_GRANTED' and report['G0'] is False
    assert {key: value for key, value in report.items() if key != 'outputs'} == {
        key: value for key, value in original.items() if key != 'outputs'}
    return dict(case=work.name, finite_values_checked=int(finite), complete_AnnData_and_HDF5=True,
                complete_report_except_externally_revalidated_output_identity=True,
                numeric_atol=1e-12, numeric_rtol=0, G0=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path)
    arguments = parser.parse_args()
    names = json.loads((arguments.root / 'positive-cases.json').read_text())
    assert len(names) == 20 and len(set(names)) == 20
    records = [compare(arguments.root / name) for name in names]
    destination = arguments.output or arguments.root / 'whole-object-readback.json'
    destination.write_text(json.dumps(dict(
        cases=records, sealed_author_outputs_regenerated=False, G0=False), indent=2) + '\n')
    print('VERIFIED_COMPLETE_H5AD_CASES', len(records), flush=True)


if __name__ == '__main__':
    main()
