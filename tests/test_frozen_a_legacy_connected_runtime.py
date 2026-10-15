import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

from tools import frozen_a_legacy_connected_runtime as runtime


class ConnectedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='connected-runtime-toy-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.allowed = self.root / 'scratch'
        self.allowed.mkdir()
        self.source = b'APPROVED_TOY_SCRIPT\n'
        self.script_sha = hashlib.sha256(self.source).hexdigest()

    def create(self, role='mr'):
        expected = runtime.SCRIPTS[role]
        workspace = self.allowed / role
        workspace.mkdir()
        (workspace / '.autonomics').mkdir()
        (workspace / '.autonomics/script').write_bytes(self.source)
        staging = workspace / '.autonomics/inputs'
        staging.mkdir()
        inputs, outputs = expected[1:3]
        command = ['create', '--name', 'toy-' + role, '--network', 'none', '--cpus', expected[5],
            '--memory', expected[6], '--pull', 'missing' if role == 'mr' else 'never']
        command.append('--read-only')
        environment = dict(AUTONOMICS_WORKDIR='/work', AUTONOMICS_SCRIPT='/work/.autonomics/script',
            AUTONOMICS_INPUT_COUNT=str(inputs), AUTONOMICS_OUTPUT_COUNT=str(outputs))
        for index in range(inputs):
            filename = 'input-' + str(index) + '.file'
            target = staging / filename
            if role == 'raw':
                canonical = self.root / 'raw-sources'
                canonical.mkdir(exist_ok=True)
                original = canonical / filename
                original.write_bytes(('TOY_RAW_' + str(index)).encode())
                target.symlink_to(original)
            else:
                target.write_bytes(('TOY_INPUT_' + str(index)).encode())
            environment['AUTONOMICS_INPUT' + str(index)] = '/work/.autonomics/inputs/' + filename
        for index in range(outputs):
            name = runtime.MR_OUTPUTS[index] if role == 'mr' else 'result-' + str(index)
            environment['AUTONOMICS_OUTPUT' + str(index)] = '/work/' + name
        if role in {'assemble', 'publish'}:
            environment['FROZEN_A_FAMILY_MODE'] = role
        for name, value in environment.items():
            command.extend(['--env', name + '=' + value])
        command.extend(['--mount', 'type=bind,source=' + str(workspace) + ',destination=/work,rw=true',
            '--workdir', '/work', '--entrypoint', expected[4], expected[3], '/work/.autonomics/script'])
        if role == 'raw':
            command[1:1] = ['--mount', 'type=bind,source=' + str(canonical) + ',destination=' + str(canonical) + ',readonly']
        pins = dict(runtime.SCRIPTS)
        pins[role] = (self.script_sha, *expected[1:])
        return command, workspace, pins

    def prepared(self, command, pins, fault=False):
        raw_sources = [self.root / 'raw-sources' / ('input-' + str(index) + '.file') for index in range(9)]
        with mock.patch.object(runtime, 'SCRIPTS', pins), mock.patch.object(runtime, 'RAW_INPUT_PATHS', raw_sources):
            return runtime.prepare_create(command, self.allowed, fault)

    def test_positive_changes_only_explicit_mr_engineering_caps(self):
        command, workspace, pins = self.create()
        before = list(command)
        changed, record = self.prepared(command, pins)
        self.assertEqual(command, before)
        expected = list(command)
        expected[expected.index('--cpus') + 1] = '1'
        expected[expected.index('--pull') + 1] = 'never'
        self.assertEqual(changed, expected)
        self.assertEqual(changed.count('--read-only'), 1)
        self.assertEqual(record['original_resources'], dict(cpus='2', memory='2147483648', pull='missing', read_only_rootfs=True))
        self.assertFalse(record['fault_injected'])
        self.assertEqual(record['actual_resources'], dict(cpus='1', memory='2147483648', pull='never', read_only_rootfs=True))
        self.assertFalse(any((workspace / name).exists() for name in runtime.MR_OUTPUTS))

    def test_omitted_manifest_rootfs_field_retains_the_sdk_read_only_default(self):
        manifest = Path(runtime.__file__).resolve().parents[1] / 'plugins/twosamplemr-v432-a/manifest.toml'
        resources = tomllib.loads(manifest.read_text())['nodes'][0]['resources']
        self.assertNotIn('read_only_rootfs', resources)
        self.assertEqual(resources['pull_policy'], 'missing')
        command, workspace, pins = self.create()
        changed, record = self.prepared(command, pins)
        self.assertTrue(record['original_resources']['read_only_rootfs'])
        self.assertEqual(changed.count('--read-only'), 1)
        self.assertFalse(any((workspace / name).exists() for name in runtime.MR_OUTPUTS))

    def test_writable_or_duplicate_rootfs_flags_are_refused_before_fault_injection(self):
        command, workspace, pins = self.create()
        missing = [argument for argument in command if argument != '--read-only']
        duplicate = ['create', '--read-only', *command[1:]]
        for invalid in [missing, duplicate]:
            with self.subTest(read_only_flags=invalid.count('--read-only')):
                with self.assertRaisesRegex(ValueError, 'manifest pull/rootfs'):
                    self.prepared(invalid, pins, True)
                self.assertFalse(any((workspace / name).exists() for name in runtime.MR_OUTPUTS))

    def test_negative_creates_exact_foreign_file_without_changing_method(self):
        command, workspace, pins = self.create()
        script = runtime.regular_fact(workspace / '.autonomics/script')
        changed, record = self.prepared(command, pins, True)
        target = workspace / runtime.MR_OUTPUTS[0]
        self.assertEqual(target.read_bytes(), runtime.FOREIGN)
        self.assertEqual(runtime.regular_fact(target), record['foreign_before']['identity'])
        self.assertEqual(runtime.regular_fact(workspace / '.autonomics/script'), script)
        self.assertTrue(record['fault_injected'])
        self.assertEqual(changed[-3:], command[-3:])
        self.assertFalse(any((workspace / name).exists() for name in runtime.MR_OUTPUTS[1:]))

    def test_non_mr_creates_preserve_argv_even_when_fault_requested(self):
        for role in ('raw', 'harmonise', 'gate', 'assemble', 'adjust', 'publish'):
            command, workspace, pins = self.create(role)
            with self.subTest(role=role):
                changed, record = self.prepared(command, pins, True)
                self.assertEqual(changed, command)
                self.assertFalse(record['fault_injected'])
                self.assertIsNone(record['foreign_before'])
                self.assertEqual(set(workspace.iterdir()), {workspace / '.autonomics'})

    def test_output_conflict_injection_never_replaces_existing_or_linked_files(self):
        command, workspace, pins = self.create()
        target = workspace / runtime.MR_OUTPUTS[0]
        target.write_bytes(b'EXISTING_UNRELATED')
        before = runtime.regular_fact(target)
        with self.assertRaisesRegex(ValueError, 'must not replace'):
            self.prepared(command, pins, True)
        self.assertEqual(runtime.regular_fact(target), before)
        target.unlink()
        target.symlink_to(self.root / 'missing')
        with self.assertRaisesRegex(ValueError, 'must not replace'):
            self.prepared(command, pins, True)
        self.assertTrue(target.is_symlink())

    def test_unknown_script_cannot_be_identified_by_output_name_alone(self):
        command, workspace, pins = self.create()
        (workspace / '.autonomics/script').write_bytes(b'FOREIGN_METHOD')
        with self.assertRaisesRegex(ValueError, 'approved script bytes'):
            self.prepared(command, pins)

    def test_source_aliases_are_rejected_before_execution_or_output_injection(self):
        command, workspace, pins = self.create()
        script = workspace / '.autonomics/script'
        source = self.root / 'aliased-source'
        source.write_bytes(script.read_bytes())
        script.unlink()
        script.symlink_to(source)
        with self.assertRaisesRegex(ValueError, 'Unaliased'):
            self.prepared(command, pins, True)
        self.assertFalse((workspace / runtime.MR_OUTPUTS[0]).exists())

    def test_source_image_interpreter_and_abi_cannot_change(self):
        command, workspace, pins = self.create()
        invalid = []
        changed = list(command)
        changed[-2] = runtime.PYTHON_IMAGE
        invalid.append(changed)
        changed = list(command)
        changed[changed.index('--entrypoint') + 1] = 'sh'
        invalid.append(changed)
        invalid.append(command + ['--additional-argument'])
        changed = list(command)
        changed[changed.index('AUTONOMICS_INPUT_COUNT=5')] = 'AUTONOMICS_INPUT_COUNT=4'
        invalid.append(changed)
        for changed in invalid:
            with self.subTest(argv=changed[-3:]), self.assertRaises(ValueError):
                self.prepared(changed, pins, True)
        self.assertFalse((workspace / runtime.MR_OUTPUTS[0]).exists())

    def test_bool_fault_unknown_resource_or_duplicate_option_cannot_be_silently_accepted(self):
        command, workspace, pins = self.create()
        with self.assertRaises(ValueError):
            self.prepared(command, pins, 1)
        for flag, value in (('--memory', '1Gi'), ('--cpus', '4'), ('--network', 'host'), ('--pull', 'always')):
            changed = list(command)
            changed[changed.index(flag) + 1] = value
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                self.prepared(changed, pins)
        with self.assertRaises(ValueError):
            self.prepared(['create', '--memory', '2147483648', *command[1:]], pins)

    def test_workspace_escape_traversal_and_duplicate_mount_are_refused(self):
        command, workspace, pins = self.create()
        mount = command[command.index('--mount') + 1]
        changed = list(command)
        changed[changed.index('--mount') + 1] = mount.replace(str(workspace), str(self.root))
        with self.assertRaisesRegex(ValueError, 'outside'):
            self.prepared(changed, pins, True)
        changed = list(command)
        marker = 'AUTONOMICS_OUTPUT0=/work/' + runtime.MR_OUTPUTS[0]
        changed[changed.index(marker)] = 'AUTONOMICS_OUTPUT0=/work/../' + runtime.MR_OUTPUTS[0]
        with self.assertRaises(ValueError):
            self.prepared(changed, pins, True)
        with self.assertRaisesRegex(ValueError, 'Exactly one owned SDK workspace'):
            self.prepared(['create', '--mount', mount, *command[1:]], pins)

    def test_unknown_credentials_are_forwarded_but_not_recorded(self):
        command, workspace, pins = self.create()
        command[1:1] = ['--env', 'OPENALEX_API_KEY=TOY_MUST_NOT_APPEAR']
        changed, record = self.prepared(command, pins)
        self.assertIn('OPENALEX_API_KEY=TOY_MUST_NOT_APPEAR', changed)
        self.assertNotIn('TOY_MUST_NOT_APPEAR', json.dumps(record))
        self.assertNotIn('OPENALEX_API_KEY', json.dumps(record))

    def test_missing_escaping_or_output_aliased_inputs_refuse_before_any_fault_write(self):
        command, workspace, pins = self.create()
        marker = 'AUTONOMICS_INPUT0=/work/.autonomics/inputs/input-0.file'
        values = ['/outside/not-a-workspace-input', '/work/missing.tsv',
            '/work/' + runtime.MR_OUTPUTS[0], '/work/.autonomics/script',
            '/work/.autonomics/inputs/input-0-missing.file']
        for value in values:
            altered = list(command)
            altered[altered.index(marker)] = 'AUTONOMICS_INPUT0=' + value
            with self.subTest(value=value), self.assertRaises((ValueError, FileNotFoundError)):
                self.prepared(altered, pins, True)
            self.assertFalse((workspace / runtime.MR_OUTPUTS[0]).exists())
        (workspace / '.autonomics/inputs/input-0.file').unlink()
        with self.assertRaises(FileNotFoundError):
            self.prepared(command, pins, True)
        self.assertFalse((workspace / runtime.MR_OUTPUTS[0]).exists())

    def test_raw_source_symlinks_require_exact_roles_and_readonly_bindings(self):
        command, workspace, pins = self.create('raw')
        path = workspace / '.autonomics/inputs/input-0.file'
        target = Path(os.readlink(path))
        changed = list(command)
        mount_index = changed.index('--mount')
        changed[mount_index + 1] = changed[mount_index + 1].removesuffix(',readonly') + ',rw=true'
        with self.assertRaisesRegex(ValueError, 'mounted read-only'):
            self.prepared(changed, pins)
        path.unlink()
        path.symlink_to(target.parent / 'input-1.file')
        with self.assertRaisesRegex(ValueError, 'exact frozen canonical'):
            self.prepared(command, pins)

    def test_copied_inputs_cannot_be_symlinked_or_repeated_inodes(self):
        command, workspace, pins = self.create()
        first = workspace / '.autonomics/inputs/input-0.file'
        second = workspace / '.autonomics/inputs/input-1.file'
        second.unlink()
        second.symlink_to(first)
        with self.assertRaisesRegex(ValueError, 'Unaliased'):
            self.prepared(command, pins, True)
        second.unlink()
        os.link(first, second)
        with self.assertRaisesRegex(ValueError, 'distinct input role'):
            self.prepared(command, pins, True)
        self.assertFalse((workspace / runtime.MR_OUTPUTS[0]).exists())

    def test_record_collisions_do_not_overwrite_previous_evidence(self):
        records = self.root / 'records'
        records.mkdir()
        record = dict(run_name='toy-mr', role='mr')
        runtime.save_record(records, record)
        before = (records / 'toy-mr.json').read_bytes()
        with self.assertRaises(FileExistsError):
            runtime.save_record(records, dict(record, role='foreign'))
        self.assertEqual((records / 'toy-mr.json').read_bytes(), before)

    def test_launcher_executes_the_original_managed_program_and_never_mutates_parent_environment(self):
        original = self.root / 'managed-shim'
        original.write_text('TOY_NEVER_EXECUTED')
        temporary = self.root / 'tmp'
        temporary.mkdir()
        output = self.root / 'evidence'
        output.mkdir()
        canonical = Path.home() / '.autonomics/containers-overlay'
        prefix = [str(original), '--root', str(canonical / 'storage'), '--runroot', str(canonical / 'run'),
            '--tmpdir', str(canonical / 'run/libpod-tmp'), '--storage-driver', 'overlay']
        with mock.patch.dict(os.environ, {'AUTONOMICS_PODMAN_PROGRAM': str(original), 'OPENALEX_API_KEY': 'TOY_ENV_SECRET'}):
            before = dict(os.environ)
            configuration = runtime.install_launcher(prefix, temporary, output, workspace_root=self.allowed)
            child = runtime.child_environment(configuration)
            self.assertEqual(dict(os.environ), before)
            self.assertEqual(child['OPENALEX_API_KEY'], 'TOY_ENV_SECRET')
            self.assertNotIn('environment', configuration)
            self.assertNotIn('TOY_ENV_SECRET', configuration['launcher'].read_text())
            with mock.patch.object(runtime.sys, 'argv', ['podman', 'ps', '-a']), mock.patch.object(runtime.os, 'execv') as execute:
                scope = {'__name__': 'toy_launcher'}
                exec(compile(configuration['launcher'].read_text(), str(configuration['launcher']), 'exec'), scope)
            self.assertEqual(execute.call_args.args, (str(original), [*prefix, 'ps', '-a']))

    def test_observer_rejects_missing_duplicate_extra_and_modified_foreign_evidence(self):
        command, workspace, pins = self.create()
        changed, record = self.prepared(command, pins, True)
        records = self.root / 'records'
        records.mkdir()
        original = self.root / 'shim'
        original.write_bytes(b'TOY_PROGRAM')
        configuration = dict(records=records, workspace_root=self.allowed, fault=True,
            original=original, original_fact=runtime.regular_fact(original), launcher=original,
            launcher_fact=runtime.regular_fact(original), source=original, source_fact=runtime.regular_fact(original))
        with self.assertRaises(ValueError):
            runtime.observations(configuration, expected_roles=['mr'])
        runtime.save_record(records, record)
        observed = runtime.observations(configuration, expected_roles=['mr'])
        self.assertEqual(observed[0]['foreign_after'], record['foreign_before']['identity'])
        runtime.save_record(records, dict(record, run_name='duplicate-mr'))
        with self.assertRaises(ValueError):
            runtime.observations(configuration, expected_roles=['mr'])
        (records / 'duplicate-mr.json').unlink()
        (workspace / runtime.MR_OUTPUTS[0]).write_bytes(b'CHANGED')
        with self.assertRaisesRegex(ValueError, 'foreign-file identity'):
            runtime.observations(configuration, expected_roles=['mr'])


if __name__ == '__main__':
    unittest.main()
