import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import zipfile


SOURCE = Path(__file__).resolve().parent / 'test_bundle.py'
SPECIFICATION = importlib.util.spec_from_file_location('bundle_boundary_fixtures', SOURCE)
fixtures = importlib.util.module_from_spec(SPECIFICATION)
SPECIFICATION.loader.exec_module(fixtures)
bundle = fixtures.bundle


class BundleBoundaryTests(unittest.TestCase):
    setUp = fixtures.BundleTests.setUp
    fixture = fixtures.BundleTests.fixture
    pack = fixtures.BundleTests.pack

    def test_full_828_dependency_transport_and_every_materialized_hash(self):
        self.request['sources'] = []
        self.request['seen_history'] = []
        self.request['edges'] = []
        for index in range(276):
            bindings = []
            for role in ('source', 'history', 'rds'):
                dependency = self.root / f'{role}-{index}.input'
                content = f'{role}:{index}\n'.encode()
                dependency.write_bytes(content)
                bindings.append(dict(path=str(dependency), sha256=bundle.sha(content)))
            self.request['sources'].append(dict(source_id=str(index), **bindings[0]))
            self.request['seen_history'].append(dict(history_file=bindings[1]))
            self.request['edges'].append(dict(rds=bindings[2]))
        closure = self.pack()
        self.assertEqual(len(closure['entries']), 844)
        with zipfile.ZipFile(self.archive) as archive:
            self.assertEqual(len(archive.infolist()), 845)
        request, receipt = bundle.unpack(self.archive, self.root / 'maximum-cardinality', self.lock)
        self.assertEqual(len(receipt['relocated_original_paths']), 844)
        for entry in closure['entries']:
            materialized = request.parent / entry['target']
            self.assertEqual(bundle.sha(materialized.read_bytes()), entry['sha256'])
            self.assertEqual(materialized.stat().st_size, entry['bytes'])
        relocated = json.loads(request.read_bytes())
        self.assertEqual([len(relocated[key]) for key in ('sources', 'seen_history', 'edges')], [276, 276, 276])
        self.assertFalse(receipt['scientific_authorization_granted'])
        self.assertFalse(receipt['g0_granted'])

    def test_aggregate_byte_limit_equal_and_one_byte_over(self):
        self.request_path.write_bytes(bundle.encode(self.request))
        entries = bundle.records(self.request, self.study, self.adapters, str(self.request_path),
            bundle.sha(self.request_path.read_bytes()), self.lock)
        total = sum(Path(entry['original_path']).stat().st_size for entry in entries)
        with patch.object(bundle, 'MAX_TOTAL_BYTES', total):
            self.pack()
            bundle.unpack(self.archive, self.root / 'exact-limit', self.lock)
        self.archive = self.root / 'over-limit.zip'
        with patch.object(bundle, 'MAX_TOTAL_BYTES', total - 1):
            with self.assertRaisesRegex(ValueError, 'Aggregate source byte budget exceeded'):
                self.pack()
        self.assertFalse(self.archive.exists())

    def test_aggregate_unpack_budget_rejected_before_materialization(self):
        closure = self.pack()
        total = sum(entry['bytes'] for entry in closure['entries'])
        workspace = self.root / 'over-budget-unpack'
        with patch.object(bundle, 'MAX_TOTAL_BYTES', total - 1):
            with self.assertRaisesRegex(ValueError, 'Source byte budget exceeded'):
                bundle.unpack(self.archive, workspace, self.lock)
        self.assertFalse(workspace.exists())

    def test_archive_byte_limit_equal_and_one_byte_over(self):
        self.pack()
        size = self.archive.stat().st_size
        with patch.object(bundle, 'MAX_BUNDLE_BYTES', size):
            bundle.unpack(self.archive, self.root / 'archive-exact-limit', self.lock)
        workspace = self.root / 'archive-over-limit'
        with patch.object(bundle, 'MAX_BUNDLE_BYTES', size - 1):
            with self.assertRaisesRegex(ValueError, 'File type or byte budget differs'):
                bundle.unpack(self.archive, workspace, self.lock)
        self.assertFalse(workspace.exists())

    def test_each_member_role_has_enforced_hash_before_materialization(self):
        self.pack()
        with zipfile.ZipFile(self.archive) as archive:
            members = [(entry, archive.read(entry)) for entry in archive.infolist()]
        for changed_index in range(1, len(members)):
            with self.subTest(member=changed_index):
                changed = self.root / f'corrupt-{changed_index}.zip'
                with zipfile.ZipFile(changed, 'w') as archive:
                    for index, (information, content) in enumerate(members):
                        if index == changed_index:
                            content = bytes([content[0] ^ 1]) + content[1:]
                        archive.writestr(information, content)
                workspace = self.root / f'corrupt-workspace-{changed_index}'
                with self.assertRaises(ValueError):
                    bundle.unpack(changed, workspace, self.lock)
                self.assertFalse(workspace.exists())

    def test_invalid_bundle_does_not_create_normal_outputs(self):
        self.archive.write_bytes(b'not an archive')
        outputs = [self.root / f'output-{index}' for index in range(6)]
        with self.assertRaises(zipfile.BadZipFile):
            bundle.assemble(self.archive, outputs, self.root / 'invalid-workspace', self.lock)
        self.assertFalse(any(output.exists() for output in outputs))
        self.assertFalse((self.root / 'invalid-workspace').exists())

    def test_analysis_failure_does_not_create_normal_outputs(self):
        name = bundle.IMPLEMENTATIONS[2]
        source = b'def assemble(paths, request):\n    raise ValueError("expected toy failure")\n'
        (self.adapters / name).write_bytes(source)
        self.lock['implementation_files'][name] = dict(bytes=len(source), sha256=bundle.sha(source))
        self.pack()
        outputs = [self.root / f'output-{index}' for index in range(6)]
        with self.assertRaisesRegex(ValueError, 'expected toy failure'):
            bundle.assemble(self.archive, outputs, self.root / 'failed-analysis-workspace', self.lock)
        self.assertFalse(any(output.exists() for output in outputs))

    def test_exact_six_distinct_new_outputs_are_required(self):
        self.pack()
        outputs = [self.root / f'output-{index}' for index in range(6)]
        for candidate in (outputs[:5], [outputs[0]] * 6):
            with self.subTest(candidate=str(candidate)):
                with self.assertRaisesRegex(ValueError, 'Six distinct new output Files required'):
                    bundle.assemble(self.archive, candidate, self.root / 'must-not-exist', self.lock)
                self.assertFalse((self.root / 'must-not-exist').exists())
        outputs[5].write_bytes(b'preserve existing')
        with self.assertRaisesRegex(ValueError, 'Six distinct new output Files required'):
            bundle.assemble(self.archive, outputs, self.root / 'must-not-exist', self.lock)
        self.assertEqual(outputs[5].read_bytes(), b'preserve existing')
        self.assertFalse(any(output.exists() for output in outputs[:5]))


if __name__ == '__main__':
    unittest.main()
