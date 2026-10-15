import copy
from contextlib import ExitStack, contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'h5ad_subset_official_runtime_contract', ROOT / 'tools/prove_h5ad_subset_official_runtime.py')
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)


class H5ADSubsetRuntimeContractTests(unittest.TestCase):
    @contextmanager
    def cgroup_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session = 'a' * 32
            unit = 'autonomics-validation-' + session + '.service'
            permanent = root / 'workspace' / session / 'permanent'
            permanent.mkdir(parents=True)
            archives = root / 'archives'
            record_path = archives / session / 'SESSION.json'
            record_path.parent.mkdir(parents=True)
            record = dict(schema='TECHNICAL_VALIDATION_SESSION_V1', session=session, unit=unit,
                workspace=str(permanent.parent), profile='light')
            record_path.write_text(json.dumps(record))
            cgroups = root / 'cgroups'
            suffix = '/user.slice/user-1000.slice/' + unit + '/worker-native'
            leaf = cgroups / suffix.lstrip('/')
            leaf.mkdir(parents=True)
            service = leaf.parent
            for name, value in {'memory.max': '2147483648', 'memory.current': '1024',
                    'memory.peak': '2048', 'memory.events': 'oom 0\noom_kill 0\n'}.items():
                (service / name).write_text(value)
            proc = root / 'proc-cgroup'
            proc.write_text('0::' + suffix + '\n')
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(DRIVER, 'PROC_CGROUP', proc))
                stack.enter_context(mock.patch.object(DRIVER, 'CGROUP_ROOT', cgroups))
                stack.enter_context(mock.patch.object(DRIVER, 'ARCHIVES', archives))
                stack.enter_context(mock.patch.dict(DRIVER.os.environ,
                    AUTONOMICS_VALIDATION_PERMANENT=str(permanent)))
                yield dict(session=session, unit=unit, service=service, leaf=leaf,
                    record_path=record_path, record=record, proc=proc, suffix=suffix)

    def summaries(self):
        def summary(mode, records):
            return dict(mode=mode, cases=len(records), records=records,
                whole_current_engine=False, resident_daemon=False, G0=False)
        positives = [dict(case=name, whole_container_checks=10, hdf5_datasets_checked=2,
            complete_cell_ledger_rows_checked=6, full_report_checked=True, G0=False)
            for name in sorted(DRIVER.POSITIVES)]
        boundaries = [dict(case=name, ordinary_rollback=True, crash_atomicity_claimed=False)
            if name == 'ordinary-second-link-failure' else dict(case=name,
                exit=3 if name == 'corrupt-selection' else 2, specific_refusal='explicit toy diagnostic')
            for name in sorted(DRIVER.BOUNDARIES)]
        mutants = []
        for name, expected in sorted(DRIVER.MUTANTS.items()):
            accepted = expected['old_accepted']
            item = dict(case=name, comparison_scope=expected['comparison_scope'],
                old_comparison=dict(accepted=accepted, refusal_type=None if accepted else 'AssertionError',
                    diagnostic=None if accepted else 'old comparator refused'),
                current_comparison=dict(accepted=False, refusal_type='AssertionError', diagnostic='new comparator refused'),
                G0=False)
            if expected['comparison_scope'] == 'SHARED_COMPARE_VALUE_ONLY':
                item['old_whole_object_comparison_executed'] = False
            else:
                item['baseline_source_sha256'] = dict(DRIVER.BASELINE_SOURCES)
            mutants.append(item)
        return [summary('positive', positives), summary('boundary', boundaries), summary('mutants', mutants)]

    @contextmanager
    def payload_fixture(self, mutate=None, *, wrong_entry=False):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            records = [dict(package=name, version=version, files_exact=1,
                files=[dict(path=name + '/payload.py', bytes=3, sha256='a' * 64)])
                for name, version in DRIVER.VERSIONS.items()]
            value = dict(records=records)
            if mutate is not None:
                mutate(value)
            payload = json.dumps(value).encode()
            payload += b' ' * (910879 - len(payload))
            self.assertEqual(len(payload), 910879)
            (root / 'INHERITED_AUTHOR_PAYLOADS.json').write_bytes(payload)
            checksum = hashlib.sha256(payload).hexdigest()
            seal = json.dumps(dict(files=[dict(path='INHERITED_AUTHOR_PAYLOADS.json',
                size=910878 if wrong_entry else 910879, sha256=checksum)])).encode()
            (root / 'ROOT_REVIEW_SEALED_FILES.json').write_bytes(seal)
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(DRIVER, 'HISTORICAL', root))
                stack.enter_context(mock.patch.object(DRIVER, 'HISTORICAL_SEAL', hashlib.sha256(seal).hexdigest()))
                stack.enter_context(mock.patch.object(DRIVER, 'PAYLOAD_LOCK_SHA', checksum))
                stack.enter_context(mock.patch.object(DRIVER, 'PAYLOAD_COUNTS', dict.fromkeys(DRIVER.VERSIONS, 1)))
                yield

    def test_strict_json_rejects_duplicate_keys_at_every_depth(self):
        for value in ['{"a":1,"a":2}', '{"outer":{"a":1,"a":2}}']:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
                DRIVER.strict_json(value)
        self.assertEqual(DRIVER.strict_json('{"ok":[1,null,true]}'), dict(ok=[1, None, True]))

    def test_strict_json_rejects_nonfinite_constants(self):
        for value in ['NaN', 'Infinity', '-Infinity', '{"value":NaN}']:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Nonfinite JSON constant'):
                DRIVER.strict_json(value)

    def test_fact_records_actual_regular_file_identity_and_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'source'
            source.write_bytes(b'bounded non-scientific fixture')
            before = source.stat()
            actual = DRIVER.fact(source)
            self.assertEqual(actual['bytes'], before.st_size)
            self.assertEqual(actual['sha256'], hashlib.sha256(source.read_bytes()).hexdigest())
            self.assertEqual((actual['device'], actual['inode']), (before.st_dev, before.st_ino))
            self.assertEqual((actual['mtime_ns'], actual['ctime_ns']), (before.st_mtime_ns, before.st_ctime_ns))

    def test_fact_rejects_leaf_and_parent_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / 'real'
            directory.mkdir()
            source = directory / 'source'
            source.write_bytes(b'toy')
            (root / 'leaf').symlink_to(source)
            (root / 'parent').symlink_to(directory, target_is_directory=True)
            for path in [root / 'leaf', root / 'parent/source']:
                with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'Unaliased regular file'):
                    DRIVER.fact(path)

    def test_positive_and_boundary_inventories_are_complete_and_disjoint(self):
        positives = {'dense', 'csr', 'csc', 'group-many-to-one', 'all-cells', 'lexical-numeric', 'single-cell',
            'prior-params', 'no-raw', 'no-X', 'nonfinite-X'}
        boundaries = {'unknown', 'unknown-partial', 'unknown-group', 'duplicate-request', 'duplicate-group',
            'empty-request', 'null-request', 'integer-request', 'empty-string', 'tab-request', 'numeric-group',
            'absent-column', 'duplicate-obs', 'duplicate-var', 'missing-group', 'zero-cells', 'zero-genes',
            'missing-selection-column', 'corrupt-selection', 'existing-h5ad', 'existing-report',
            'aliased-outputs', 'input-overwrite', 'ordinary-second-link-failure'}
        self.assertEqual(DRIVER.POSITIVES, positives)
        self.assertEqual(DRIVER.BOUNDARIES, boundaries)
        self.assertEqual((len(positives), len(boundaries)), (11, 24))
        self.assertFalse(positives & boundaries)

    def test_all_current_source_pins_are_explicit_sha256(self):
        self.assertEqual(set(DRIVER.SOURCES), {'manifest.toml', 'scripts/subset_by_obs.py',
            'tests/test_subset_by_obs.py', 'tests/qc_compare.py', 'test_subset_assurance.sh'})
        for name, checksum in DRIVER.SOURCES.items():
            with self.subTest(source=name):
                self.assertIsInstance(checksum, str)
                self.assertIsNotNone(re.fullmatch('[0-9a-f]{64}', checksum))

    def test_payload_lock_rejects_duplicate_or_escaping_paths(self):
        for path in ['../escape.py', '/absolute.py', 'package/../escape.py', 'package//file.py',
                     'package/./file.py', 'package\\file.py', '']:
            def mutate(value, path=path):
                value['records'][0]['files'][0]['path'] = path
            with self.subTest(path=path), self.payload_fixture(mutate), self.assertRaisesRegex(
                    ValueError, 'Unique bounded lexical official payload identity'):
                DRIVER.payload_lock()
        def duplicate(value):
            value['records'][1]['files'][0]['path'] = value['records'][0]['files'][0]['path']
        with self.payload_fixture(duplicate), self.assertRaisesRegex(
                ValueError, 'Unique bounded lexical official payload identity'):
            DRIVER.payload_lock()

    def test_payload_lock_rejects_wrong_schema_counts_and_sealed_identity(self):
        def wrong_version(value):
            value['records'][0]['version'] = 'unapproved'
        with self.payload_fixture(wrong_version), self.assertRaisesRegex(ValueError, 'Exact six official inherited package versions'):
            DRIVER.payload_lock()
        def wrong_count(value):
            value['records'][0]['files_exact'] = 2
        with self.payload_fixture(wrong_count), self.assertRaisesRegex(ValueError, 'Full package payload count'):
            DRIVER.payload_lock()
        with self.payload_fixture(wrong_entry=True), self.assertRaisesRegex(ValueError, 'Sealed author payload record differs'):
            DRIVER.payload_lock()

    def test_summary_inventory_rejects_missing_duplicate_wrong_counts_and_authority(self):
        original = self.summaries()
        self.assertEqual(DRIVER.validate_summaries(*original),
            dict(positive_cases=11, boundary_cases=24, comparator_controls=12))
        for position in range(3):
            for mutation in ['missing', 'duplicate', 'boolean-count', 'wrong-mode', 'whole-engine', 'deployment', 'G0']:
                altered = copy.deepcopy(original)
                selected = altered[position]
                if mutation == 'missing':
                    selected['records'].pop()
                elif mutation == 'duplicate':
                    selected['records'][-1] = copy.deepcopy(selected['records'][0])
                elif mutation == 'boolean-count':
                    selected['cases'] = True
                elif mutation == 'wrong-mode':
                    selected['mode'] = 'not-executed'
                else:
                    selected[{'whole-engine': 'whole_current_engine', 'deployment': 'resident_daemon', 'G0': 'G0'}[mutation]] = True
                with self.subTest(position=position, mutation=mutation), self.assertRaises(ValueError):
                    DRIVER.validate_summaries(*altered)

    def test_summary_rejects_false_method_checks_failed_runtime_and_mislabelled_mutants(self):
        original = self.summaries()
        mutations = [
            (0, 0, 'whole_container_checks', 0),
            (0, 0, 'hdf5_datasets_checked', True),
            (0, 0, 'complete_cell_ledger_rows_checked', 5),
            (0, 0, 'full_report_checked', False),
        ]
        refusal = next(index for index, row in enumerate(original[1]['records']) if row['case'] == 'unknown')
        rollback = next(index for index, row in enumerate(original[1]['records']) if row['case'] == 'ordinary-second-link-failure')
        mutations.extend([(1, refusal, 'exit', 137), (1, refusal, 'exit', True),
            (1, refusal, 'specific_refusal', ''), (1, rollback, 'crash_atomicity_claimed', True)])
        helper = next(index for index, row in enumerate(original[2]['records'])
            if row['comparison_scope'] == 'SHARED_COMPARE_VALUE_ONLY')
        whole = next(index for index, row in enumerate(original[2]['records'])
            if row['comparison_scope'] == 'WHOLE_CURRENT_FIXTURE_AND_REPORT')
        mutations.extend([(2, helper, 'old_whole_object_comparison_executed', True),
            (2, whole, 'baseline_source_sha256', {}), (2, whole, 'comparison_scope', 'SHARED_COMPARE_VALUE_ONLY'),
            (2, whole, 'current_comparison', dict(accepted=True, refusal_type=None, diagnostic=None)),
            (2, whole, 'current_comparison', dict(accepted=False, refusal_type='MemoryError', diagnostic='OOM'))])
        for position, index, field, value in mutations:
            altered = copy.deepcopy(original)
            altered[position]['records'][index][field] = value
            with self.subTest(position=position, field=field, value=value), self.assertRaises(ValueError):
                DRIVER.validate_summaries(*altered)

    def test_cgroup_uses_exact_recorded_service_when_worker_leaf_has_no_controllers(self):
        with self.cgroup_fixture() as fixture:
            self.assertEqual(list(fixture['leaf'].iterdir()), [])
            observed = DRIVER.cgroup_observation()
            self.assertEqual(observed['path'], str(fixture['service']))
            self.assertEqual(observed['worker_leaf_path'], str(fixture['leaf']))
            self.assertEqual(observed['recorded_unit'], fixture['unit'])
            self.assertEqual(observed['session'], fixture['session'])
            self.assertEqual(observed['memory_max_bytes'], 2147483648)
            self.assertEqual(observed['memory_current_bytes'], 1024)
            self.assertEqual(observed['memory_peak_bytes'], 2048)
            self.assertEqual(observed['session_record_sha256'],
                hashlib.sha256(fixture['record_path'].read_bytes()).hexdigest())
            self.assertEqual(observed['worker_leaf_controller_observations'],
                dict.fromkeys(['memory.max', 'memory.current', 'memory.peak', 'memory.events']))

    def test_cgroup_rejects_wrong_session_and_nonrecorded_ancestor(self):
        with self.cgroup_fixture() as fixture:
            changed = dict(fixture['record'], session='b' * 32)
            fixture['record_path'].write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, 'Exact recorded light service ownership'):
                DRIVER.cgroup_observation()
            fixture['record_path'].write_text(json.dumps(fixture['record']))
            for suffix in ['/unrelated.service/worker-native',
                           fixture['suffix'].replace(fixture['unit'], 'autonomics-validation-' + 'b' * 32 + '.service'),
                           fixture['suffix'] + '/nested', fixture['suffix'].replace('/worker-native', '/./worker-native')]:
                fixture['proc'].write_text('0::' + suffix + '\n')
                with self.subTest(suffix=suffix), self.assertRaisesRegex(ValueError,
                        'exact recorded delegated worker subgroup'):
                    DRIVER.cgroup_observation()

    def test_cgroup_rejects_unlimited_or_wrong_service_memory_limit(self):
        with self.cgroup_fixture() as fixture:
            for value in ['max', '1073741824', '4294967296']:
                (fixture['service'] / 'memory.max').write_text(value)
                with self.subTest(limit=value), self.assertRaisesRegex(ValueError,
                        'Exact recorded service cgroup must enforce two GiB'):
                    DRIVER.cgroup_observation()


if __name__ == '__main__':
    unittest.main()
