"""Compare the complete existing synthetic pseudobulk suite in one locked runtime."""

import argparse
from contextlib import redirect_stdout
import csv
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys


ORIGINAL_SHA = '77884036871586b1be564a8c25f9ab72b2939a987db112aecd328cc86e44c83d'
FIXED_SHA = 'd1bb920dbd2c7a938638724432f38a8f56fd8ecd6b8aeb5d9b6e221ed04be109'
ASSURANCE_SHA = '885cea12225f2468b57216487fd37f14aacf780bbb64dfac5101b232aef8ad25'
VERSIONS = dict(anndata='0.12.19', numpy='2.4.6', scipy='1.17.1', pandas='2.3.3')
POSITIVE_CASES = (
    'dense', 'csr', 'csc', 'uint', 'integer-float', 'boolean', 'named-counts-layer',
    'minimum-filter', 'legacy', 'missing-label-excluded', 'collision-safe-ids',
    'large-safe-independent-gene-sums', 'explicit-noninteger-not-counts',
    'leading-double-quote', 'middle-double-quote', 'single-quote', 'comma',
    'literal-NA', 'leading-zero', 'unicode',
)
NEGATIVE_CASES = {
    'nan': 'non-finite', 'inf': 'non-finite', 'negative': 'negative',
    'noninteger': 'non-integer entries', 'group-overflow': 'group sum exceeds',
    'uint-out-of-range': 'int64-safe range', 'csr_matrix-duplicate-overflow': 'group sum exceeds',
    'csc_matrix-duplicate-overflow': 'group sum exceeds', 'gene-tab': 'gene names must',
    'gene-newline': 'gene names must', 'gene-empty': 'gene names must',
    'gene-duplicate': 'not unique', 'within-group-condition-inconsistency': 'not constant',
    'condition-newline': 'condition values cannot', 'minimum-zero': 'positive integer',
    'invalid-boolean': 'true or false', 'output-sentinel': 'refusing overwrite',
    'output-symlink': 'refusing overwrite', 'output-alias': 'must be distinct',
    'output-input': 'refusing overwrite', 'ordinary-second-publish-failure': 'INJECTED_SECOND_LINK_FAILURE',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fact(path):
    require(path.is_file() and not path.is_symlink() and path.resolve(strict=True) == path,
        'Exact unaliased regular runtime source required')
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    key = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_size,
        value.st_mtime_ns, value.st_ctime_ns)
    require(key(before) == key(after), 'Runtime source changed during hashing')
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), identity=list(key(after)))


def write(path, value):
    with path.open('x') as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write('\n')


def run_suite(assurance, script, output, name):
    specification = importlib.util.spec_from_file_location('pseudobulk_synthetic_assurance_' + name, assurance)
    require(specification is not None and specification.loader is not None, 'Exact suite module cannot be loaded')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    module.SCRIPT = script
    output.mkdir(mode=0o700)
    with (output / 'suite.stdout').open('x') as stdout:
        with redirect_stdout(stdout):
            module.main(output / 'cases')
    summary = json.loads((output / 'cases/SUMMARY.json').read_text())
    records = summary.get('records')
    expected_ids = [*POSITIVE_CASES, *NEGATIVE_CASES]
    require(summary.get('cases') == 41 and isinstance(records, list) and len(records) == 41 and
        [row.get('case') for row in records] == expected_ids and len(set(expected_ids)) == 41 and
        summary.get('versions') == VERSIONS and summary.get('source_sha256') == fact(script)['sha256'] and
        summary.get('G0') is False, 'All exact original forty-one cases and actual package identities required')
    normalized = []
    for row in records:
        case = row['case']
        require(type(row.get('exit')) is int, 'A real integer process exit is required for every case')
        if case in NEGATIVE_CASES:
            expected_exit = 1 if case == 'ordinary-second-publish-failure' else 2
            diagnostic = NEGATIVE_CASES[case]
            stderr = (output / 'cases' / case / 'stderr.txt').read_text()
            require(row.get('refused') is True and row['exit'] == expected_exit and
                row.get('fragment') == diagnostic and diagnostic in stderr,
                'Specific original negative case diagnostic and exact exit required: ' + case)
            normalized.append(dict(case=case, actual_exit=row['exit'], expected_exit=expected_exit,
                expected_diagnostic=diagnostic, actual_diagnostic_matched=True))
        else:
            require(row['exit'] == 0 and row.get('exact_independent_reference') is True and
                row.get('outputs_readable') is True, 'All independent positive suite assertions must complete: ' + case)
            normalized.append(dict(case=case, actual_exit=0, independent_reference_checked=True))
    link = output / 'cases/output-symlink/counts.tsv'
    require(link.is_symlink() and os.readlink(link) == 'absent.tsv' and not link.exists(),
        'The intentional dangling output fixture must remain exact before retirement')
    link_identity = link.lstat()
    link.unlink()
    write(output / 'intentional-dangling-fixture-retirement.json', dict(case='output-symlink',
        literal='absent.tsv', device=link_identity.st_dev, inode=link_identity.st_ino,
        exact_owned_toy_fixture_only=True, scientific_files_deleted=False))
    write(output / 'actual-case-results.json', dict(records=normalized, cases=41,
        positive_cases=20, specific_negative_cases=21, actual_child_processes=41,
        scientific_authorization_granted=False, g0_granted=False))
    return normalized


def normalized_log(directory):
    lines = (directory / 'pseudobulk.log').read_text().splitlines(keepends=True)
    require(lines and lines[0].startswith('input\t'), 'Original input identity log line required')
    first = lines[0].split('\t')
    require(len(first) == 4 and first[1] == str(directory / 'input.h5ad'),
        'Only the exact declared synthetic input path may differ across runs')
    first[1] = '<SYNTHETIC_INPUT_PATH>'
    lines[0] = '\t'.join(first)
    return ''.join(lines)


def compare_suites(original, fixed):
    records = []
    for case in POSITIVE_CASES:
        old_case, new_case = original / 'cases' / case, fixed / 'cases' / case
        products = []
        for name in ['counts.tsv', 'samples.tsv']:
            old, new = old_case / name, new_case / name
            old_data, new_data = old.read_bytes(), new.read_bytes()
            require(old_data == new_data, 'Complete quoted lexical table or numerical value changed: ' + case + '/' + name)
            with old.open(newline='') as handle:
                rows = list(csv.reader(handle, delimiter='\t', strict=True))
            require(rows and len(rows[0]) > 0 and all(len(row) == len(rows[0]) for row in rows),
                'Quoted original TSV must remain fully rectangular')
            products.append(dict(name=name, bytes=len(old_data), sha256=hashlib.sha256(old_data).hexdigest(),
                rows=len(rows), columns=len(rows[0]), complete_quoted_lexical_bytes_equal=True))
        require(normalized_log(old_case) == normalized_log(new_case),
            'Publication repair changed a log field other than the exact input path: ' + case)
        records.append(dict(case=case, products=products, complete_logs_equal_except_exact_input_path=True))
    require(len(records) == 20, 'Every original positive case must receive complete output comparison')
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-script', required=True, type=Path)
    parser.add_argument('--fixed-script', required=True, type=Path)
    parser.add_argument('--assurance-source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    arguments = parser.parse_args()
    require(sys.flags.optimize == 0, 'The original suite assertions must not be disabled')
    paths = [arguments.original_script, arguments.fixed_script, arguments.assurance_source]
    before = [fact(path) for path in paths]
    require([row['sha256'] for row in before] == [ORIGINAL_SHA, FIXED_SHA, ASSURANCE_SHA],
        'Only the exact original, repaired and assurance sources are allowed')
    versions = {key: importlib.metadata.version(key) for key in VERSIONS}
    require(versions == VERSIONS, 'Existing locked official runtime package versions must match exactly')
    require(arguments.output.resolve() == arguments.output and not arguments.output.exists(),
        'A new unaliased evidence directory is required')
    arguments.output.mkdir(mode=0o700)
    original = run_suite(arguments.assurance_source, arguments.original_script, arguments.output / 'original', 'original')
    fixed = run_suite(arguments.assurance_source, arguments.fixed_script, arguments.output / 'fixed', 'fixed')
    require([(row['case'], row['actual_exit']) for row in original] ==
        [(row['case'], row['actual_exit']) for row in fixed], 'All forty-one original/fixed actual process exits must agree')
    comparisons = compare_suites(arguments.output / 'original', arguments.output / 'fixed')
    require([fact(path) for path in paths] == before, 'Original, repaired or assurance source changed during runtime')
    write(arguments.output / 'verification.json', dict(
        scope='EXISTING_SYNTHETIC_PSEUDOBULK_SUITE_ORIGINAL_VS_PUBLICATION_FIX_NOT_RESEARCH',
        status='ALL_41_CASES_PER_SOURCE_COMPLETED_20_COMPLETE_OUTPUT_PAIRS_EQUAL',
        source_inputs=[dict(path=str(path), **record) for path, record in zip(paths, before, strict=True)],
        versions=versions, actual_child_processes=82, positive_cases_per_source=20,
        specific_negative_cases_per_source=21, actual_cases_original=original, actual_cases_fixed=fixed,
        complete_positive_output_comparisons=comparisons, all_original_synthetic_arithmetic_checks_passed=True,
        full_positive_counts_and_quoted_metadata_byte_equal=True,
        all_41_actual_exits_and_specific_refusals_agree=True,
        real_scientific_data_read=False, full_scale_resources_certified=False, donor_eligibility_granted=False,
        isolated_DAG_executed=False, resident_method_execution_proven=False,
        scientific_authorization_granted=False, g0_granted=False))


if __name__ == '__main__':
    main()
