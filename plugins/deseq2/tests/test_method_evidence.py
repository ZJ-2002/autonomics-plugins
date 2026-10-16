"""Real, pinned-image synthetic method evidence. Requires a managed session.

METHOD_EVIDENCE_ROOT is a new permanent evidence directory; optional
METHOD_CONTAINER_BACKEND_JSON declares an existing local Podman backend.
No real study inputs, mutation of a frozen contract, or scientific authorization.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import tomllib
import unittest


class MethodEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path(__file__).resolve().parents[1]
        cls.root = Path(os.environ['METHOD_EVIDENCE_ROOT'])
        permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']).resolve()
        if not cls.root.resolve().is_relative_to(permanent):
            raise RuntimeError('Permanent managed technical evidence required')
        cls.root.mkdir(exist_ok=False)
        cls.image = tomllib.loads((cls.source / 'manifest.toml').read_text())['image']['reference']
        cls.prefix = [os.environ['AUTONOMICS_PODMAN_PROGRAM'], *json.loads(os.environ.get('METHOD_CONTAINER_BACKEND_JSON', '[]'))]
        cls.sources = {str(p.relative_to(cls.source)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in [cls.source / 'deseq2_runner.R', cls.source / 'dds_diagnostics.R',
                                 cls.source / 'manifest.toml', Path(__file__),
                                 cls.source / 'tests/method_evidence_fixture.R', cls.source / 'tests/method_evidence_reference.R',
                                 cls.source / 'tests/method_evidence_convergence.R']}
        (cls.root / 'SOURCE_BINDINGS.json').write_text(json.dumps(cls.sources, indent=2))
        cls.execute('fixture', cls.root, cls.source / 'tests/method_evidence_fixture.R', {'METHOD_FIXTURE_ROOT': '/work'})

    @classmethod
    def execute(cls, label, directory, script, env, expected=0):
        cmd = [*cls.prefix, 'run', '--rm', '--pull=never', '--network=none', '--read-only',
               '--security-opt=no-new-privileges', '--userns=keep-id', '--user', f'{os.getuid()}:{os.getgid()}', '--cpus=1', '--memory=1500m',
               '--tmpfs=/tmp:rw,size=128m', '--mount', f'type=bind,src={directory},dst=/work',
               '--mount', f'type=bind,src={script},dst=/method.R,ro=true', '--entrypoint', '/opt/autonomics/Rscript-vanilla']
        for key, value in env.items():
            cmd += ['--env', key + '=' + value]
        cmd += [cls.image, '/method.R']
        before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in directory.rglob('*') if p.is_file()}
        started = time.monotonic()
        result = subprocess.run(cmd, capture_output=True, timeout=600)
        (directory / (label + '.stdout.txt')).write_bytes(result.stdout)
        (directory / (label + '.stderr.txt')).write_bytes(result.stderr)
        (directory / (label + '.execution.json')).write_text(json.dumps(dict(
            command=cmd, exit=result.returncode, inputs_before=before,
            seconds=time.monotonic()-started, source_sha256=hashlib.sha256(script.read_bytes()).hexdigest(),
            execution_mode='MANIFEST_SOURCE_BIND_WITH_PINNED_DEPENDENCIES', scientific_authorization=False), indent=2))
        if expected == 0 and result.returncode != 0:
            raise AssertionError(label + ': ' + result.stderr.decode())
        if expected != 0 and result.returncode == 0:
            raise AssertionError(label + ': expected rejection')
        return result

    def run_fit(self, name, metadata='metadata.tsv', reverse=False):
        directory = self.root / name
        directory.mkdir()
        for filename in ['counts.tsv', metadata]:
            shutil.copyfile(self.root / filename, directory / filename)
        env = {'AUTONOMICS_INPUT0': '/work/counts.tsv', 'AUTONOMICS_INPUT1': '/work/' + metadata,
               'AUTONOMICS_DESEQ2_CONDITION_REFERENCE': 'case' if reverse else 'ctrl',
               'AUTONOMICS_DESEQ2_CONDITION_TEST': 'ctrl' if reverse else 'case',
               'AUTONOMICS_DESEQ2_COVARIATES': '', 'AUTONOMICS_DESEQ2_FIT_TYPE': 'parametric',
               'AUTONOMICS_DESEQ2_FIT_POLICY': 'exact', 'AUTONOMICS_DESEQ2_LFC_SHRINK': 'none',
               'AUTONOMICS_DESEQ2_ALPHA': '.05', 'AUTONOMICS_DESEQ2_THREADS': '1'}
        names = ['results.tsv', 'normalized.tsv', 'size_factors.tsv', 'dataset.rds', 'report.json']
        env.update({'AUTONOMICS_OUTPUT'+str(i): '/work/'+f for i, f in enumerate(names)})
        self.execute('fit', directory, self.source / 'deseq2_runner.R', env)
        self.diagnose(directory)
        return directory

    def diagnose(self, directory, report='report.json', expected=0, label='diagnostics'):
        return self.execute(label, directory, self.source / 'dds_diagnostics.R', {
            'AUTONOMICS_INPUT0': '/work/dataset.rds', 'AUTONOMICS_INPUT1': '/work/'+report,
            'AUTONOMICS_OUTPUT0': '/work/'+label+'.tsv', 'AUTONOMICS_OUTPUT1': '/work/'+label+'.json',
            'AUTONOMICS_OUTPUT2': '/work/'+label+'-cooks.tsv'}, expected)

    def test_complete_synthetic_method_evidence(self):
        forward = self.run_fit('forward')
        self.run_fit('shuffled', 'shuffled.tsv')
        self.run_fit('reverse', reverse=True)
        self.execute('reference', self.root, self.source / 'tests/method_evidence_reference.R', {'METHOD_EVIDENCE_ROOT': '/work'})
        accepted = json.loads((self.root / 'NUMERICAL_ACCEPTANCE.json').read_text())
        self.assertEqual(accepted['status'], 'PASS')
        self.assertGreater(accepted['numerical_fields'], 40000)
        report = json.loads((forward / 'report.json').read_text())
        report['outputs']['dataset']['md5'] = '0'*32
        (forward / 'wrong-report.json').write_text(json.dumps(report))
        failed = self.diagnose(forward, 'wrong-report.json', 1, 'wrong-identity')
        self.assertIn('DDS does not match the original run report', failed.stderr.decode())
        self.assertFalse((forward / 'wrong-identity.tsv').exists())
        self.assertFalse((forward / 'wrong-identity.json').exists())
        self.assertFalse((forward / 'wrong-identity-cooks.tsv').exists())
        for mode in ['nonconverged', 'unknown']:
            directory = self.root / mode
            directory.mkdir()
            for filename in ['dataset.rds', 'report.json']:
                shutil.copyfile(forward / filename, directory / filename)
            self.execute('mutate', directory, self.source / 'tests/method_evidence_convergence.R',
                         {'METHOD_EVIDENCE_ROOT': '/work', 'METHOD_CONVERGENCE_CONTROL': mode})
            if mode == 'nonconverged':
                self.diagnose(directory)
                self.execute('verify', directory, self.source / 'tests/method_evidence_convergence.R',
                             {'METHOD_EVIDENCE_ROOT': '/work', 'METHOD_CONVERGENCE_CONTROL': 'verify'})
            else:
                rejected = self.diagnose(directory, expected=1)
                self.assertIn('convergence annotation incomplete', rejected.stderr.decode())
                for filename in ['diagnostics.tsv', 'diagnostics.json', 'diagnostics-cooks.tsv']:
                    self.assertFalse((directory / filename).exists())
        for name, expected in self.sources.items():
            self.assertEqual(hashlib.sha256((self.source / name).read_bytes()).hexdigest(), expected)


if __name__ == '__main__':
    unittest.main()
