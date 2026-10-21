"""Small real Git fixtures: original p0 imports and verified current evolution."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from tools import catalog
from tools.check_governance_transport import check_family


class P0Evolution(unittest.TestCase):
    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.DEVNULL).decode().strip()

    def commit(self):
        self.git('add', '.')
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'SYN source only')
        return self.git('rev-parse', 'HEAD')

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name); self.git('init', '--quiet')
        (self.root/'provenance').mkdir()
        (self.root/'provenance/source-index.json').write_text(json.dumps({'plugins': [], 'research_adapters': []}))
        rows = []
        for name in sorted(catalog.P0_IMPORT_FAMILIES):
            directory = 'research-adapters/' + name
            family = self.root/directory; family.mkdir(parents=True)
            target = family/'source.R'; target.write_bytes(b'ORIGINAL SYN SOURCE\n')
            files = {'source.R': {**catalog._identity(target.read_bytes()), 'source_path': 'study_plugins/'+name+'/source.R', 'executable': False}}
            lock = {'source_commit': catalog.P0_IMPORT_COMMIT, 'source_repository': catalog.P0_IMPORT_REPOSITORY,
                    'source_family': 'study_plugins/'+name, 'imported_files': files, 'status': 'ENGINEERING_CANDIDATE',
                    **dict.fromkeys(('auto_enable','scientific_authorization','method_acceptance_verified','loaded_worker_registration_verified'), False)}
            (family/'component-source.json').write_text(json.dumps(lock))
            (family/'manifest.toml').write_text('plugin_name="'+name+'"\n[image]\nreference="SYN@sha256:'+'a'*64+'"\n[[nodes]]\nkind="SYN_TEST"\n')
            rows.append({'directory': directory, 'source_commit': catalog.P0_IMPORT_COMMIT, 'files': files,
                         'source_inventory_only': True, 'auto_enable': False, 'scientific_certified': False})
        self.index = {'schema_version': 1, 'scope': 'ADDITIONAL_EXPLICIT_OPT_IN_SOURCE_TRANSPORT_NOT_DEFAULT_PROFILE_OR_METHOD_CERTIFICATION',
                      'source_commit': catalog.P0_IMPORT_COMMIT, 'source_repository': catalog.P0_IMPORT_REPOSITORY,
                      'auto_enable': False, 'scientific_certified': False, 'original_source_index_rewritten': False,
                      'research_adapters': rows}
        self.index_path = self.root/'provenance/p0-load-source-imports-20261012.json'
        self.index_path.write_text(json.dumps(self.index)); self.old_commit = self.commit()
        self.path = 'research-adapters/b-donor-contract/source.R'; self.target = self.root/self.path
        self.original = catalog._identity(self.target.read_bytes()); self.target.write_bytes(b'CURRENT SYN SOURCE\n')
        self.current = catalog._identity(self.target.read_bytes()); self.revision = self.commit()
        self.ledger = {'schema_version': 1, 'scope': catalog.EVOLUTION_SCOPE, 'scientific_certified': False, 'auto_enable': False,
                      'changes': [{'path': self.path, 'original': {'repository': catalog.P0_IMPORT_REPOSITORY,
                      'revision': catalog.P0_IMPORT_COMMIT, **self.original}, 'current': {'repository': catalog.EVOLUTION_REPOSITORY,
                      'revision': self.revision, 'path': self.path, **self.current}}]}
        self.save()

    def save(self):
        (self.root/'provenance/source-evolution.json').write_text(json.dumps(self.ledger))

    def test_p0_real_commit_and_governance_consumer_preserve_originals(self):
        original_index = self.index_path.read_bytes(); lock = self.target.parent/'component-source.json'; original_lock = lock.read_bytes()
        report = catalog.verify_import_detailed(self.root)
        self.assertEqual((report['original_import_files_verified'], report['recorded_source_evolution_files_verified']), (10,1))
        self.assertEqual(catalog.read_verified_import(self.root, self.path), b'CURRENT SYN SOURCE\n')
        self.assertFalse(check_family(self.target.parent)['scientific_authorization'])
        self.assertEqual(self.index_path.read_bytes(), original_index); self.assertEqual(lock.read_bytes(), original_lock)

    def test_governance_rejects_missing_ledger_and_unrecorded_drift(self):
        (self.root/'provenance/source-evolution.json').unlink()
        with self.assertRaisesRegex(ValueError, 'without recorded'): check_family(self.target.parent)
        self.save(); self.target.write_bytes(b'UNREGISTERED DRIFT\n')
        with self.assertRaisesRegex(ValueError, 'independently verified'): check_family(self.target.parent)

    def test_wrong_original_current_commit_blob_and_path_reject(self):
        original = copy.deepcopy(self.ledger)
        for mode in ('original', 'commit', 'blob', 'path', 'unrelated_commit'):
            with self.subTest(mode=mode):
                self.ledger = copy.deepcopy(original); row = self.ledger['changes'][0]
                if mode == 'original': row['original']['sha256'] = '0'*64
                elif mode == 'commit': row['current']['revision'] = '0'*40
                elif mode == 'blob': row['current']['git_blob'] = '0'*40
                elif mode == 'path': row['path'] = row['current']['path'] = 'research-adapters/b-donor-contract/unknown.R'
                else: row['current']['revision'] = self.old_commit
                self.save()
                with self.assertRaises(ValueError): check_family(self.target.parent)

    def test_unknown_additional_family_cannot_be_enrolled(self):
        self.index['research_adapters'][0]['directory'] = 'research-adapters/UNREGISTERED'
        self.index_path.write_text(json.dumps(self.index))
        with self.assertRaisesRegex(ValueError, 'eleven'): catalog.verify_import_detailed(self.root)

    def test_component_original_mismatch_and_index_promotion_reject(self):
        lock = self.target.parent/'component-source.json'; raw = lock.read_bytes(); value = json.loads(raw)
        value['imported_files']['source.R']['sha256'] = '0'*64; lock.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'index/component'): catalog.verify_import_detailed(self.root)
        lock.write_bytes(raw); self.index['scientific_certified'] = True; self.index_path.write_text(json.dumps(self.index))
        with self.assertRaisesRegex(ValueError, 'preserved additional'): catalog.verify_import_detailed(self.root)

    def test_no_git_and_unknown_requested_path_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'original import path'): catalog.read_verified_import(self.root, 'foreign/source.R')
        shutil.rmtree(self.root/'.git')
        with self.assertRaisesRegex(ValueError, 'Git object'): check_family(self.target.parent)

    def test_unmodified_p0_stays_original_and_duplicate_base_import_rejects(self):
        self.target.write_bytes(b'ORIGINAL SYN SOURCE\n'); self.ledger['changes'] = []; self.save()
        self.assertEqual(catalog.verify_import_detailed(self.root)['original_import_files_verified'],11)
        # Duplicate immutable provenance must never get silently overwritten.
        (self.root/'provenance/source-index.json').write_text(json.dumps({'plugins': [], 'research_adapters': [{
            'directory': 'research-adapters/b-donor-contract', 'repository': 'SYN', 'revision': 'a'*40,
            'files': [{'path': 'source.R', **self.original}]}]}))
        with self.assertRaisesRegex(ValueError, 'Duplicate original'): catalog.verify_import_detailed(self.root)


if __name__ == '__main__': unittest.main()
