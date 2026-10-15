"""Observe the original publication function with dependency-free, non-scientific toy bytes."""

import ast
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RELATIVE = 'plugins/single-cell/scripts/subset_by_obs.py'
BASELINE_REVISION = 'b4712c853b1a605b3fa9a9cf2c3c6ddf2e7d1536'
BASELINE_SHA = '0db6f4caadbb28f679f2d813c60de33d3c74ca1111934f01389b182306b088ec'
TOY_PAYLOAD = b'EXPLICIT_NON_H5AD_TOY_BYTES\n'
FOREIGN_PAYLOAD = b'EXPLICIT_FOREIGN_TOY_REPLACEMENT\n'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publication_function(source):
    module = ast.parse(source)
    matches = [node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == 'publish']
    require(len(matches) == 1, 'Exactly one original publication function required')
    fragment = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
        matches[0]], type_ignores=[])
    ast.fix_missing_locations(fragment)
    namespace = dict(ExitStack=ExitStack, Path=Path, tempfile=tempfile, os=os, json=json, digest=digest,
        ad=types.SimpleNamespace(AnnData=object))
    exec(compile(fragment, RELATIVE, 'exec'), namespace)
    return namespace['publish'], ast.get_source_segment(source, matches[0])


class ToyWriter:
    def write_h5ad(self, destination, **kwargs):
        require(kwargs == dict(compression='lzf'), 'Original writer call shape changed')
        destination.write_bytes(TOY_PAYLOAD)


def trial(source, directory, replace_port):
    directory.mkdir()
    publish, fragment = publication_function(source)
    outputs = [directory / 'output.h5ad', directory / 'report.json']
    report = dict(scope='NONSCIENTIFIC_FAKE_WRITER_PUBLICATION_CONTROL', g0_granted=False)
    original_link = os.link
    injected = []

    def controlled_link(origin, destination, **kwargs):
        result = original_link(origin, destination, **kwargs)
        position = outputs.index(Path(destination))
        if position == replace_port:
            before = destination.stat()
            destination.unlink()
            destination.write_bytes(FOREIGN_PAYLOAD)
            after = destination.stat()
            injected.append(dict(port=position, actual_link_succeeded=True, exception_injected=False,
                staged_identity=[before.st_dev, before.st_ino], replacement_identity=[after.st_dev, after.st_ino]))
        return result

    error = None
    with mock.patch.object(os, 'link', side_effect=controlled_link):
        try:
            returned = publish(ToyWriter(), report, outputs)
        except Exception as observed:
            error = dict(type=type(observed).__name__, message=str(observed))
            returned = None
    facts = [dict(port=index, exists=path.exists(), bytes=path.stat().st_size if path.exists() else None,
        sha256=digest(path) if path.exists() else None, payload=path.read_text() if path.exists() else None)
        for index, path in enumerate(outputs)]
    try:
        parsed = json.loads(outputs[1].read_text())
    except (ValueError, FileNotFoundError):
        parsed = None
    declared_hash = parsed.get('outputs', [{}])[0].get('sha256') if isinstance(parsed, dict) else None
    valid_payload = outputs[0].read_bytes() == TOY_PAYLOAD
    valid_report = isinstance(parsed, dict) and declared_hash == facts[0]['sha256']
    return dict(replace_port=replace_port, function_returned_normally=error is None, function_returned_none=returned is None,
        observed_exception=error, injected=injected, output_facts=facts, original_toy_payload_preserved=valid_payload,
        report_matches_actual_data=valid_report, output_contract_satisfied=valid_payload and valid_report,
        normal_return_with_broken_contract=error is None and not (valid_payload and valid_report),
        original_function_sha256=hashlib.sha256(fragment.encode()).hexdigest(),
        actual_AnnData_imported=False, actual_H5AD_written=False, official_method_certified=False, g0_granted=False)


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed session required')
    current = ROOT / RELATIVE

    def current_identity():
        before = current.stat()
        checksum = digest(current)
        after = current.stat()
        require((before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
            (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            'Current implementation changed during observation')
        return dict(device=before.st_dev, inode=before.st_ino, mode=before.st_mode, bytes=before.st_size,
            mtime_ns=before.st_mtime_ns, ctime_ns=before.st_ctime_ns, sha256=checksum)

    current_before = current_identity()
    source = subprocess.check_output(['git', '-C', str(ROOT), 'show', BASELINE_REVISION + ':' + RELATIVE])
    require(hashlib.sha256(source).hexdigest() == BASELINE_SHA, 'Fixed published Git baseline differs')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'h5ad-subset-publication-counterexample'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    (output / 'original-subset-by-obs.py').write_bytes(source)
    results = []
    for name, position in [('control', None), ('replace-first-port', 0), ('replace-last-port', 1)]:
        result = trial(source.decode(), output / name, position)
        result['case'] = name
        results.append(result)
        (output / (name + '.json')).write_text(json.dumps(result, indent=2) + '\n')
    require(results[0]['function_returned_normally'] and results[0]['output_contract_satisfied'],
        'No-fault toy control must preserve the original publication contract')
    require(all(len(result['injected']) == 1 and result['injected'][0]['actual_link_succeeded'] and
        result['injected'][0]['exception_injected'] is False for result in results[1:]), 'Actual post-link replacement must occur')
    current_after = current_identity()
    require(current_after == current_before, 'Current implementation changed during baseline observation')
    summary = dict(scope='ORIGINAL_PUBLISH_FUNCTION_NONSCIENTIFIC_STDLIB_TOY_ONLY',
        baseline_revision=BASELINE_REVISION, baseline_script_sha256=BASELINE_SHA,
        baseline_from_published_Git=True, current_source_is_baseline=current_before['sha256'] == BASELINE_SHA,
        current_source_before=current_before, current_source_after=current_after, current_source_unchanged=True,
        actual_cases=results, observed_normal_return_with_broken_contract=sum(result['normal_return_with_broken_contract'] for result in results),
        source_unchanged=True, implementation_modified=False, dependency_imported=False, containers_started=False,
        actual_node_run_executed=False, actual_AnnData_method_executed=False, production_restarted=False,
        scientific_inputs_or_results_read=False, scientific_authorization_granted=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(summary, indent=2) + '\n')


if __name__ == '__main__':
    main()
