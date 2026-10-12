import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

from test_export_assurance import fixture


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--expect-replacement-lost', action='store_true')
    arguments = parser.parse_args()
    arguments.evidence.mkdir()
    source = arguments.evidence / 'input.h5ad'
    fixture().write_h5ad(source)
    outputs = [arguments.evidence / name for name in ['matrix.parquet', 'obs.tsv', 'var.tsv', 'export.log']]
    variables = {'AUTONOMICS_INPUT0': str(source), 'EXPORT_LAYER': 'X', 'EXPORT_CHUNK': '100'}
    variables.update({f'AUTONOMICS_OUTPUT{number}': str(path) for number, path in enumerate(outputs)})
    os.environ.update(variables)
    script = Path(__file__).resolve().parents[1] / 'scripts/h5ad_export_matrix.py'
    spec = importlib.util.spec_from_file_location('subject', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original_link = os.link
    publications = []

    def replace_then_fail(staging, destination):
        if publications:
            prior_staging, prior_destination = publications[0]
            prior_destination.unlink()
            prior_destination.symlink_to(prior_staging)
            raise OSError('INJECTED_FAILURE_AFTER_OTHER_WRITER_REPLACEMENT')
        original_link(staging, destination)
        publications.append((Path(staging), Path(destination)))

    module.os.link = replace_then_fail
    try:
        module.run()
    except OSError as error:
        assert 'INJECTED_FAILURE_AFTER_OTHER_WRITER_REPLACEMENT' in str(error)
    else:
        raise AssertionError('publication failure did not run')
    finally:
        module.os.link = original_link
    kept = outputs[0].is_symlink()
    if arguments.expect_replacement_lost:
        assert not os.path.lexists(outputs[0]), 'original failure was not reproduced'
    else:
        assert kept and os.readlink(outputs[0]) == str(publications[0][0])
    assert all(not os.path.lexists(path) for path in outputs[1:])
    assert not list(arguments.evidence.glob('.h5ad-export-*'))
    (arguments.evidence / 'CHECKS.json').write_text(json.dumps({
        'expected_original_failure': arguments.expect_replacement_lost,
        'replacement_owned_by_other_writer_retained': kept,
        'other_normal_artifacts_absent': True, 'staging_cleaned': True,
        'crash_or_resume_claim': False, 'G0': False}, indent=2) + '\n')


if __name__ == '__main__':
    main()
