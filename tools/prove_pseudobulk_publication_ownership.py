"""Observe only real publication I/O using explicit non-scientific toy tables."""

import ast
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RELATIVE = 'plugins/pseudobulk/scripts/pseudobulk_counts.py'
BASELINE_REVISION = 'd91be9dad535e79c97fb3566b07fe1f68d0954ba'
BASELINE_SHA = '77884036871586b1be564a8c25f9ab72b2939a987db112aecd328cc86e44c83d'
CURRENT_SHA = 'd1bb920dbd2c7a938638724432f38a8f56fd8ecd6b8aeb5d9b6e221ed04be109'
MODES = ('control', 'same-inode-success', 'same-inode-second-link-failure',
    'staging-replaced-after-link', 'destination-replaced-after-link', 'staging-replaced-before-link',
    'staging-replaced-before-writer', 'metadata-staging-replaced-before-writer',
    'log-staging-replaced-before-writer')
FOREIGN = b'EXPLICIT FOREIGN NONSCIENTIFIC PUBLICATION BYTES\n'
PRODUCTS = ('counts.tsv', 'samples.tsv', 'publication.log')
EXPECTED = (
    b'gene_id\tdonor-1__T\tdonor-2__T\nG1\t1\t2\nG2\t3\t4\n',
    b'sample_id\tsample\tcelltype\tn_cells\tcondition\ndonor-1__T\tdonor-1\tT\t2\tctrl\ndonor-2__T\tdonor-2\tT\t2\tcase\n',
    b'EXPLICIT TOY PUBLICATION ONLY; NO AGGREGATION EXECUTED\n',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def identity(path):
    require(not path.is_symlink() and path.is_file(), 'Unaliased regular source required')
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    fields = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_size,
        item.st_mtime_ns, item.st_ctime_ns)
    require(fields(before) == fields(after), 'Source changed during observation')
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), identity=list(fields(after)))


def publication_parts(source):
    module = ast.parse(source)
    helpers = [index for index, node in enumerate(module.body)
        if isinstance(node, ast.FunctionDef) and node.name.startswith('_publication_')]
    boundaries = [min(helpers)] if helpers else []
    if not boundaries:
        boundaries = [index for index, node in enumerate(module.body) if isinstance(node, ast.Assign) and
            any(isinstance(target, ast.Name) and target.id == 'staged' for target in node.targets)]
    require(len(boundaries) == 1, 'Exactly one publication boundary required')
    boundary = boundaries[0]
    prefix = ast.Module(body=module.body[:boundary], type_ignores=[])
    suffix = ast.Module(body=module.body[boundary:], type_ignores=[])
    require(suffix.body and isinstance(suffix.body[-1], ast.Try), 'Original final publication try block required')
    return ast.dump(prefix, include_attributes=False), ast.dump(suffix, include_attributes=False), suffix


class ToyRow(list):
    def tolist(self):
        return list(self)


class ToyBlock:
    def __init__(self, rows):
        self.rows = rows
        self.shape = (len(rows), 2)

    def toarray(self):
        return self

    def __getitem__(self, index):
        return ToyRow(self.rows[index])


class ToyMatrix:
    def __getitem__(self, selection):
        return ToyBlock([[1, 2], [3, 4]][selection])


def trial(source, directory, mode):
    require(mode in MODES, 'Unknown explicit publication control')
    directory.mkdir(mode=0o700)
    _, fragment_sha_source, fragment = publication_parts(source)
    outputs = [directory / name for name in PRODUCTS]
    namespace = dict(csv=csv, os=os, Path=Path, tempfile=tempfile,
        output_paths=outputs, first_col='gene_id', ids=['donor-1__T', 'donor-2__T'],
        genes=['G1', 'G2'], kept=[('donor-1', 'T'), ('donor-2', 'T')], counts_sparse=ToyMatrix(),
        metadata_columns=['sample_id', 'sample', 'celltype', 'n_cells', 'condition'],
        sample_rows=[('donor-1__T', 'donor-1', 'T', 2, 'ctrl'), ('donor-2__T', 'donor-2', 'T', 2, 'case')],
        log_lines=['EXPLICIT TOY PUBLICATION ONLY; NO AGGREGATION EXECUTED'])
    original_link = os.link
    original_open = os.open
    original_path_open = Path.open
    injections = []
    calls = []
    second_link_failure = False

    def foreign_fact(path):
        value = path.lstat()
        return dict(path=path.name, device=value.st_dev, inode=value.st_ino,
            bytes=len(FOREIGN), sha256=hashlib.sha256(FOREIGN).hexdigest())

    def controlled_link(origin, destination, *arguments, **options):
        nonlocal second_link_failure
        origin, destination = Path(origin), Path(destination)
        calls.append(dict(port=outputs.index(destination), origin=origin.name, destination=destination.name))
        if mode == 'same-inode-second-link-failure' and len(calls) == 2:
            second_link_failure = True
            raise OSError('EXPLICIT_SECOND_LINK_FAILURE_AFTER_FOREIGN_MODIFICATION')
        if len(calls) == 1 and mode == 'staging-replaced-before-link':
            origin.unlink()
            origin.write_bytes(FOREIGN)
            injections.append(dict(kind='stage-replaced-before-link', actual_link_succeeded=False,
                foreign=[foreign_fact(origin)]))
        returned = original_link(origin, destination, *arguments, **options)
        if len(calls) == 1 and mode.startswith('same-inode-'):
            before = destination.stat()
            destination.write_bytes(FOREIGN)
            after = destination.stat()
            require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino),
                'Same-inode control did not modify the linked inode in place')
            injections.append(dict(kind='same-inode-content-changed', actual_link_succeeded=True,
                foreign=[foreign_fact(origin), foreign_fact(destination)]))
        elif len(calls) == 1 and mode == 'staging-replaced-after-link':
            origin.unlink()
            origin.write_bytes(FOREIGN)
            injections.append(dict(kind='stage-replaced-after-link', actual_link_succeeded=True,
                foreign=[foreign_fact(origin)]))
        elif len(calls) == 1 and mode == 'destination-replaced-after-link':
            destination.unlink()
            destination.write_bytes(FOREIGN)
            injections.append(dict(kind='destination-replaced-after-link', actual_link_succeeded=True,
                foreign=[foreign_fact(destination)]))
        elif len(calls) == 1 and mode == 'staging-replaced-before-link':
            injections[0]['actual_link_succeeded'] = True
            injections[0]['foreign'].append(foreign_fact(destination))
        return returned

    def replace_before_writer(path):
        path = Path(path)
        writer_modes = {'staging-replaced-before-writer': 0,
            'metadata-staging-replaced-before-writer': 1, 'log-staging-replaced-before-writer': 2}
        stage_index = writer_modes.get(mode)
        staged = namespace.get('staged', [])
        if stage_index is not None and not injections and len(staged) == 3 and path == staged[stage_index] and \
                path.parent == directory and path.name.startswith('.pseudobulk-') and path.is_file():
            path.unlink()
            with original_path_open(path, 'xb') as stream:
                stream.write(FOREIGN)
            injections.append(dict(kind='stage-replaced-before-writer', writer_port=stage_index, actual_writer_open_reached=True,
                actual_link_succeeded=False, foreign=[foreign_fact(path)]))

    def controlled_open(path, flags, *arguments, **options):
        if flags & (os.O_WRONLY | os.O_RDWR) and not flags & os.O_CREAT:
            replace_before_writer(path)
        return original_open(path, flags, *arguments, **options)

    def controlled_path_open(path, mode='r', *arguments, **options):
        if any(value in mode for value in ['w', 'a', 'x']):
            replace_before_writer(path)
        return original_path_open(path, mode, *arguments, **options)

    error = None
    with mock.patch.object(os, 'link', side_effect=controlled_link), \
            mock.patch.object(os, 'open', side_effect=controlled_open), \
            mock.patch.object(Path, 'open', controlled_path_open):
        try:
            exec(compile(fragment, RELATIVE + ':publication-only', 'exec'), namespace)
        except Exception as observed:
            error = dict(type=type(observed).__name__, message=str(observed))
    foreign = [record for injection in injections for record in injection['foreign']]
    preservation = []
    for fact in foreign:
        path = directory / fact['path']
        current = path.lstat() if path.exists() else None
        preserved = current is not None and not path.is_symlink() and path.read_bytes() == FOREIGN and \
            (current.st_dev, current.st_ino) == (fact['device'], fact['inode'])
        preservation.append(dict(**fact, preserved=preserved))
    products = [dict(port=index, path=path.name, exists=path.exists(),
        expected_toy_bytes_equal=path.is_file() and path.read_bytes() == EXPECTED[index],
        actual_sha256=hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None)
        for index, path in enumerate(outputs)]
    return dict(mode=mode, function_returned_normally=error is None, observed_exception=error,
        actual_link_calls=calls, injections=injections, injected_second_link_failure=second_link_failure,
        foreign_preservation=preservation, all_injected_foreign_paths_preserved=all(row['preserved'] for row in preservation),
        output_facts=products, all_declared_toy_bytes_equal=all(row['expected_toy_bytes_equal'] for row in products),
        publication_AST_sha256=hashlib.sha256(fragment_sha_source.encode()).hexdigest(),
        numerical_aggregation_executed=False, AnnData_imported=False, official_method_certified=False,
        actual_node_run_executed=False, g0_granted=False)


def validate_trials(baseline, current):
    require([row['mode'] for row in baseline] == list(MODES) == [row['mode'] for row in current],
        'All explicit controls must execute for both actual publication versions')
    require(all(rows[0]['function_returned_normally'] and rows[0]['all_declared_toy_bytes_equal']
        for rows in [baseline, current]), 'Both no-fault publication controls must preserve every toy byte')
    require(baseline[1]['function_returned_normally'] and not baseline[1]['all_declared_toy_bytes_equal'],
        'Original normal-return content-change counterexample was not observed')
    require(baseline[2]['injected_second_link_failure'] and not baseline[2]['all_injected_foreign_paths_preserved'],
        'Original rollback deletion counterexample was not observed')
    require(baseline[3]['function_returned_normally'] and not baseline[3]['all_injected_foreign_paths_preserved'],
        'Original staging-replacement cleanup counterexample was not observed')
    require(all(len(row['injections']) == 1 and row['injections'][0]['actual_writer_open_reached'] and
        not row['all_injected_foreign_paths_preserved'] for row in baseline[-3:]),
        'Original pre-writer foreign truncation counterexample was not observed')
    require(all(not row['function_returned_normally'] and row['all_injected_foreign_paths_preserved'] and
        len(row['injections']) == 1 and row['injections'][0]['actual_link_succeeded']
        for row in current[1:-3]), 'Current implementation must refuse each injected change and preserve foreign bytes')
    require(all(not row['function_returned_normally'] and row['all_injected_foreign_paths_preserved'] and
        len(row['injections']) == 1 and row['injections'][0]['actual_writer_open_reached'] and
        not row['actual_link_calls'] for row in current[-3:]),
        'Current writer must refuse the substituted stage before truncation and publication')


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed session required')
    require(isinstance(CURRENT_SHA, str) and len(CURRENT_SHA) == 64, 'Current source pin is not frozen')
    current = ROOT / RELATIVE
    before = identity(current)
    require(before['sha256'] == CURRENT_SHA, 'Current source differs from its explicit reviewed pin')
    baseline = subprocess.check_output(['git', '-C', str(ROOT), 'show', BASELINE_REVISION + ':' + RELATIVE])
    require(hashlib.sha256(baseline).hexdigest() == BASELINE_SHA, 'Exact original published Git source required')
    fixed = current.read_bytes()
    old_prefix, _, _ = publication_parts(baseline.decode())
    new_prefix, _, _ = publication_parts(fixed.decode())
    require(old_prefix == new_prefix, 'All original pre-publication imports, validation and aggregation AST must remain exact')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'pseudobulk-publication-ownership'
    output.mkdir(mode=0o700)
    for name, data in [('driver.py', Path(__file__).read_bytes()), ('original-pseudobulk-counts.py', baseline),
            ('fixed-pseudobulk-counts.py', fixed)]:
        with (output / name).open('xb') as handle:
            handle.write(data)
    temporary = Path(os.environ['TMPDIR']) / 'pseudobulk-publication-controls'
    temporary.mkdir(mode=0o700)
    results = {}
    for version, source in [('original', baseline), ('fixed', fixed)]:
        results[version] = [trial(source.decode(), temporary / (version + '-' + mode), mode) for mode in MODES]
        with (output / (version + '-controls.json')).open('x') as handle:
            json.dump(results[version], handle, indent=2, allow_nan=False)
            handle.write('\n')
    validate_trials(results['original'], results['fixed'])
    require(identity(current) == before, 'Current source changed during publication observation')
    verification = dict(scope='PSEUDOBULK_PUBLICATION_AST_STDLIB_IO_ONLY_NOT_AGGREGATION_OR_NODE_CERTIFICATION',
        status='ORIGINAL_COUNTEREXAMPLES_OBSERVED_CURRENT_FOREIGN_CONTENT_PRESERVED',
        baseline_revision=BASELINE_REVISION, baseline_sha256=BASELINE_SHA, current_sha256=CURRENT_SHA,
        original_before_publication_AST_exact=True, before_publication_AST_sha256=hashlib.sha256(old_prefix.encode()).hexdigest(),
        current_source_before=before, current_source_after=identity(current), versions=2, controls_per_version=len(MODES),
        actual_node_run_executed=False, actual_AnnData_method_executed=False, numerical_aggregation_executed=False,
        scientific_inputs_or_results_read=False, containers_started=False, production_restarted=False,
        scientific_authorization_granted=False, g0_granted=False)
    with (output / 'verification.json').open('x') as handle:
        json.dump(verification, handle, indent=2, allow_nan=False)
        handle.write('\n')


if __name__ == '__main__':
    main()
