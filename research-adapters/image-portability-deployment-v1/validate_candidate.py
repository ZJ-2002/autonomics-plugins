#!/usr/bin/env python3
"""Pure manifest/patch validation; no registry, container, method or service calls."""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
MAIN = Path('/home/zj-normal/Work/autonomics')
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
PLAN = json.loads((HERE / 'migration-plan.json').read_bytes())
OBSERVATIONS = {}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_identity(relative, expected):
    raw = (ROOT / relative).read_bytes()
    if sha(raw) != expected:
        raise ValueError('source identity changed: ' + relative)
    return raw


def candidate(entry):
    raw = read_identity(entry['manifest'], entry['source_manifest_sha256'])
    before = 'reference = "' + entry['source_reference'] + '"'
    after = 'reference = "' + entry['target_reference'] + '"'
    if raw.count(before.encode()) != 1:
        raise ValueError('exactly one source image reference required')
    changed = raw.replace(before.encode(), after.encode())
    if sha(changed) != entry['candidate_manifest_sha256']:
        raise ValueError('candidate hash changed')
    return raw, changed


def semantic_image_only(before, after, entry):
    old, new = tomllib.loads(before.decode()), tomllib.loads(after.decode())
    if old['image']['reference'] != entry['source_reference']:
        raise ValueError('source image differs')
    if new['image']['reference'] != entry['target_reference']:
        raise ValueError('target image differs')
    old['image'].pop('reference')
    new['image'].pop('reference')
    if old != new:
        raise ValueError('semantic change outside image.reference')


def verify_publication(entry):
    archive = ARCHIVES / entry['publication_session']
    raw = (archive / 'artifacts/MANIFEST.json').read_bytes()
    if sha(raw) != entry['publication_manifest_seal']:
        raise ValueError('publication seal mismatch')
    manifest = json.loads(raw)
    session = json.loads((archive / 'SESSION.json').read_bytes())
    if session['manifest_sha256'] != sha(raw) or session['state'] != 'CLEANED':
        raise ValueError('publication lifecycle incomplete')
    if session['launcher_exit_status'] != 0 or session['worker_exit_status'] != 0:
        raise ValueError('publication process did not succeed')
    expected = manifest['files']
    actual = {str(p.relative_to(archive / 'artifacts')) for p in (archive / 'artifacts').rglob('*') if p.is_file() and p.name != 'MANIFEST.json'}
    if actual != set(expected):
        raise ValueError('publication archive file set differs')
    for relative, identity in expected.items():
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts or path.parts[0] not in {'permanent', 'retained'}:
            raise ValueError('invalid archive path')
        content = (archive / 'artifacts' / path).read_bytes()
        if sha(content) != identity['sha256'] or len(content) != identity['bytes']:
            raise ValueError('publication artifact differs')
    verification_raw = (archive / 'artifacts' / entry['publication_verification_relative']).read_bytes()
    if sha(verification_raw) != entry['publication_verification_sha256']:
        raise ValueError('verification identity differs')
    v = json.loads(verification_raw)
    for field, value in [('local_reference', entry['source_reference']), ('immutable_reference', entry['target_reference']), ('config_sha256', entry['config_sha256']), ('remote_identity_verified', True), ('anonymous_manifest_read_verified', False), ('new_method_executions', 0)]:
        if v[field] != value:
            raise ValueError('sealed verification differs: ' + field)
    if sha(json.dumps(v['ordered_RootFS'], separators=(',', ':')).encode()) != entry['ordered_rootfs_sha256']:
        raise ValueError('ordered RootFS differs')
    OBSERVATIONS[entry['publication_session']] = {'manifest_seal':sha(raw), 'verified_archive_files':len(expected), 'verification_sha256':sha(verification_raw), 'launcher_exit_status':0, 'worker_exit_status':0, 'anonymous_access':'PENDING_NOT_RECHECKED'}


class CandidateTests(unittest.TestCase):
    def test_01_sensitivity_publication_seal_readback(self):
        verify_publication(PLAN['migrations'][0])

    def test_02_permutation_publication_seal_readback(self):
        verify_publication(PLAN['migrations'][1])

    def test_03_current_manifests_scripts_and_implementation_sources(self):
        for entry in PLAN['migrations']:
            candidate(entry)
            for relative, expected in entry['scripts_sha256'].items():
                read_identity(relative, expected)
        for relative, expected in PLAN['implementation_source_sha256'].items():
            self.assertEqual(sha((MAIN / relative).read_bytes()), expected, relative)

    def check_patch(self, entry):
        before, after = candidate(entry)
        expected = ''.join(difflib.unified_diff(before.decode().splitlines(keepends=True), after.decode().splitlines(keepends=True), fromfile='a/' + entry['manifest'], tofile='b/' + entry['manifest'], n=3))
        self.assertEqual((HERE / entry['patch']).read_text(), expected)
        self.assertEqual(sum(line.startswith('-') and not line.startswith('---') for line in expected.splitlines()), 1)
        self.assertEqual(sum(line.startswith('+') and not line.startswith('+++') for line in expected.splitlines()), 1)
        semantic_image_only(before, after, entry)
        with tempfile.TemporaryDirectory(prefix='image-portability-', dir=os.environ['TMPDIR']) as directory:
            target = Path(directory) / entry['manifest']
            target.parent.mkdir(parents=True)
            target.write_bytes(before)
            for args in [['--check'], []]:
                subprocess.run(['git', 'apply', *args, str(HERE / entry['patch'])], cwd=directory, check=True, capture_output=True)
            self.assertEqual(target.read_bytes(), after)
            subprocess.run(['git', 'apply', '--reverse', '--check', str(HERE / entry['patch'])], cwd=directory, check=True, capture_output=True)
            subprocess.run(['git', 'apply', '--reverse', str(HERE / entry['patch'])], cwd=directory, check=True, capture_output=True)
            self.assertEqual(target.read_bytes(), before)

    def test_04_sensitivity_patch_applies_only_image_reference_and_reverses(self):
        self.check_patch(PLAN['migrations'][0])

    def test_05_permutation_patch_applies_only_image_reference_and_reverses(self):
        self.check_patch(PLAN['migrations'][1])

    def test_06_discover_exact_old_reference_consumers(self):
        references = {entry['source_reference']: [] for entry in PLAN['migrations']}
        for path in sorted((ROOT / 'research-adapters').glob('*/manifest.toml')):
            reference = tomllib.loads(path.read_text())['image']['reference']
            if reference in references:
                references[reference].append(str(path.relative_to(ROOT)))
        for entry in PLAN['migrations']:
            self.assertEqual(references[entry['source_reference']], [entry['manifest']])
        OBSERVATIONS['old_reference_consumers'] = references

    def test_07_typed_companion_retains_its_separate_image_and_scripts(self):
        for entry in PLAN['unchanged_companions']:
            raw = read_identity(entry['manifest'], entry['manifest_sha256'])
            self.assertEqual(tomllib.loads(raw.decode())['image']['reference'], entry['image_reference'])
            self.assertNotIn(entry['image_reference'], [e['source_reference'] for e in PLAN['migrations']])
            for relative, expected in entry['scripts_sha256'].items():
                read_identity(relative, expected)

    def test_08_reject_method_command_parameter_port_and_resource_changes(self):
        for entry in PLAN['migrations']:
            before, after = candidate(entry)
            for old, new in [('cpus = 1.0', 'cpus = 2.0'), ('timeout_secs = 600', 'timeout_secs = 601'), ('inputs = [{type="file"}, {type="file"}]', 'inputs = [{type="file"}]'), ('interpreter = ', 'unknown_command_parameter = "changed"\ninterpreter = ')]:
                self.assertIn(old.encode(), after)
                with self.assertRaisesRegex(ValueError, 'outside image.reference'):
                    semantic_image_only(before, after.replace(old.encode(), new.encode(), 1), entry)

    def test_09_reject_stale_source_hash(self):
        for entry in PLAN['migrations']:
            stale = copy.deepcopy(entry)
            stale['source_manifest_sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'source identity changed'):
                candidate(stale)

    def test_10_reject_unsealed_target_digest(self):
        for entry in PLAN['migrations']:
            before, after = candidate(entry)
            wrong = after.replace(entry['target_reference'].encode(), (entry['target_reference'].split('@')[0] + '@sha256:' + '0' * 64).encode())
            with self.assertRaisesRegex(ValueError, 'target image differs'):
                semantic_image_only(before, wrong, entry)


def main():
    destination = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'image-portability-deployment-v1'
    destination.mkdir()
    source = destination / 'candidate-source'
    source.mkdir()
    for path in sorted(HERE.iterdir()):
        if path.is_file():
            shutil.copy2(path, source / path.name)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CandidateTests))
    report = {'schema':'IMAGE_PORTABILITY_CANDIDATE_STRUCTURE_VALIDATION_V1', 'passed':result.wasSuccessful(), 'actual_new_tests':result.testsRun, 'failure_count':len(result.failures), 'error_count':len(result.errors), 'exit_code':0 if result.wasSuccessful() else 1, 'source_files_sha256':{p.name:sha(p.read_bytes()) for p in sorted(source.iterdir())}, 'migrations':PLAN['migrations'], 'unchanged_companions':PLAN['unchanged_companions'], 'implementation_source_sha256':PLAN['implementation_source_sha256'], 'observations':OBSERVATIONS, 'new_method_executions':0, 'new_registry_requests':0, 'image_pulls_or_builds':0, 'installation_performed':False, 'resident_loaded_identity_verified':False, 'cache_invalidation_live_experiment_performed':False, 'scientific_release_granted':False, 'g0_granted':False, 'pending':['anonymous_access_or_explicit_existing_authenticated_installation','published_fixed_revision_containing_patches','production_installation_and_image_admission','resident_loaded_identity_readout','live_cache_invalidation_experiment_not_run_not_required_for_patch_structure']}
    (destination / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    return report['exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
