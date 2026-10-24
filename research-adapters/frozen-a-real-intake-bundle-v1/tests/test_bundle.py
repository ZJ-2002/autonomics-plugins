import copy
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile


MODULE = Path(__file__).resolve().parents[1] / 'bundle.py'
SPEC = importlib.util.spec_from_file_location('tested_real_bundle', MODULE)
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.study = self.root / 'study'
        self.adapters = self.root / 'adapters'
        self.lock = dict(frozen_sources=[], decision_files=[], implementation_files={})
        for index in range(9):
            self.lock['frozen_sources'].append(self.fixture(self.study, f'frozen/{index}', str(index).encode()))
        for index in range(2):
            self.lock['decision_files'].append(self.fixture(self.study, f'decisions/{index}', b'decision'))
        for name in bundle.IMPLEMENTATIONS:
            entry = self.fixture(self.adapters, name, name.encode())
            self.lock['implementation_files'][name] = {key: entry[key] for key in ('sha256', 'bytes')}
        self.source = self.root / 'source.tsv'
        self.source.write_bytes(b'example\n')
        self.request = dict(schema=bundle.REQUEST_SCHEMA, scope=bundle.REQUEST_SCOPE,
            sources=[dict(source_id='one', path=str(self.source), sha256=bundle.sha(self.source.read_bytes()))],
            seen_history=[], edges=[dict(rds=None)])
        self.request_path = self.root / 'request.json'
        self.archive = self.root / 'input.zip'

    def fixture(self, root, name, payload):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return dict(path=name, bytes=len(payload), sha256=bundle.sha(payload))

    def pack(self):
        self.request_path.write_bytes(bundle.encode(self.request))
        return bundle.pack(self.request_path, self.study, self.adapters, self.archive, self.lock)

    def rewrite(self, transform):
        with zipfile.ZipFile(self.archive) as archive:
            entries = [(entry, archive.read(entry)) for entry in archive.infolist()]
        changed = self.root / 'changed.zip'
        with zipfile.ZipFile(changed, 'w') as archive:
            for information, content in transform(entries):
                archive.writestr(information, content)
        return changed

    def reject(self, archive):
        workspace = self.root / 'rejected'
        with self.assertRaises((ValueError, zipfile.BadZipFile)):
            bundle.unpack(archive, workspace, self.lock)
        self.assertFalse(workspace.exists())

    def test_deterministic_archive_and_exact_roundtrip(self):
        closure = self.pack()
        second = self.root / 'second.zip'
        bundle.pack(self.request_path, self.study, self.adapters, second, self.lock)
        self.assertEqual(self.archive.read_bytes(), second.read_bytes())
        original = self.source.read_bytes()
        request, receipt = bundle.unpack(self.archive, self.root / 'materialized', self.lock)
        relocated = json.loads(request.read_bytes())
        self.assertNotEqual(relocated['sources'][0]['path'], str(self.source))
        self.assertEqual(Path(relocated['sources'][0]['path']).read_bytes(), original)
        self.assertEqual(receipt['original_request_sha256'], bundle.sha(self.request_path.read_bytes()))
        self.assertFalse(receipt['scientific_authorization_granted'])
        self.assertFalse(receipt['g0_granted'])
        for entry in closure['entries']:
            self.assertEqual((request.parent / entry['target']).read_bytes(), Path(entry['original_path']).read_bytes())
        self.assertEqual(self.source.read_bytes(), original)

    def test_more_than_239_dependencies(self):
        self.request['sources'] = []
        for index in range(276):
            source = self.root / f'source-{index}.tsv'
            source.write_bytes(str(index).encode())
            self.request['sources'].append(dict(source_id=str(index), path=str(source), sha256=bundle.sha(source.read_bytes())))
        closure = self.pack()
        self.assertEqual(len(closure['entries']), 292)
        request, receipt = bundle.unpack(self.archive, self.root / 'large-closure', self.lock)
        self.assertEqual(len(json.loads(request.read_bytes())['sources']), 276)
        self.assertFalse(receipt['scientific_authorization_granted'])

    def test_extra_member_rejected(self):
        self.pack()
        self.reject(self.rewrite(lambda entries: entries + [(zipfile.ZipInfo('extra'), b'x')]))

    def test_duplicate_member_rejected(self):
        self.pack()
        self.reject(self.rewrite(lambda entries: entries + [entries[-1]]))

    def test_unsafe_member_rejected(self):
        self.pack()
        def change(entries):
            entries[-1][0].filename = '../escape'
            return entries
        self.reject(self.rewrite(change))

    def test_symlink_member_rejected(self):
        self.pack()
        def change(entries):
            entries[-1][0].external_attr = (stat.S_IFLNK | 0o777) << 16
            return entries
        self.reject(self.rewrite(change))

    def test_compressed_member_rejected(self):
        self.pack()
        def change(entries):
            entries[-1][0].compress_type = zipfile.ZIP_DEFLATED
            return entries
        self.reject(self.rewrite(change))

    def test_wrong_member_bytes_rejected(self):
        self.pack()
        def change(entries):
            information, content = entries[-1]
            entries[-1] = (information, b'x' * len(content))
            return entries
        self.reject(self.rewrite(change))

    def test_forged_role_rejected(self):
        self.pack()
        def change(entries):
            information, content = entries[0]
            closure = json.loads(content)
            closure['entries'][0]['role'] = 'unlocked'
            entries[0] = (information, bundle.encode(closure))
            return entries
        self.reject(self.rewrite(change))

    def test_symlink_source_rejected(self):
        link = self.root / 'linked-source'
        link.symlink_to(self.source)
        self.request['sources'][0]['path'] = str(link)
        with self.assertRaises(ValueError):
            self.pack()
        self.assertFalse(self.archive.exists())

    def test_no_overwrite_and_shared_digest_conflict(self):
        self.pack()
        before = self.archive.read_bytes()
        with self.assertRaises(ValueError):
            bundle.pack(self.request_path, self.study, self.adapters, self.archive, self.lock)
        self.assertEqual(self.archive.read_bytes(), before)
        self.request['sources'].append(dict(source_id='two', path=str(self.source), sha256='0' * 64))
        self.archive = self.root / 'conflict.zip'
        with self.assertRaises(ValueError):
            self.pack()

    def test_source_cardinality_rejected(self):
        self.request['sources'] = self.request['sources'] * 277
        with self.assertRaises(ValueError):
            self.pack()
        self.assertFalse(self.archive.exists())


if __name__ == '__main__':
    unittest.main()
