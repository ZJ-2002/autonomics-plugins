"""Source evolution must be proved by original identities and real Git objects."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools import catalog


class SourceEvolutionTests(unittest.TestCase):
    def git(self, *args):
        return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.DEVNULL).decode().strip()

    def commit(self):
        self.git('add','.')
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','synthetic source fixture')
        return self.git('rev-parse','HEAD')

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.git('init','--quiet')
        self.path='plugins/example/README.md'
        target=self.root/self.path;target.parent.mkdir(parents=True);target.write_bytes(b'ORIGINAL TEST SOURCE\n')
        self.original=catalog._identity(target.read_bytes())
        source={'directory':'plugins/example','repository':'https://example.invalid/original.git',
                'revision':'a'*40,'files':[{'path':'README.md',**self.original}]}
        index={'plugins':[source],'research_adapters':[]}
        (self.root/'provenance').mkdir()
        self.index=self.root/'provenance/source-index.json';self.index.write_text(json.dumps(index))
        self.original_revision=self.commit()
        target.write_bytes(b'CURRENT TEST SOURCE\n');self.current=catalog._identity(target.read_bytes())
        self.current_revision=self.commit()
        self.ledger={'schema_version':1,'scope':catalog.EVOLUTION_SCOPE,'scientific_certified':False,
            'auto_enable':False,'changes':[{'path':self.path,
            'original':{'repository':source['repository'],'revision':source['revision'],**self.original},
            'current':{'repository':catalog.EVOLUTION_REPOSITORY,'revision':self.current_revision,
                       'path':self.path,**self.current}}]}
        self.write_ledger()

    def write_ledger(self):
        (self.root/'provenance/source-evolution.json').write_text(json.dumps(self.ledger))

    def test_original_import_is_preserved_and_new_source_is_independently_verified(self):
        before=self.index.read_bytes()
        report=catalog.verify_import_detailed(self.root)
        self.assertEqual(report['imported_files_verified'],1)
        self.assertEqual(report['original_import_files_verified'],0)
        self.assertEqual(report['recorded_source_evolution_files_verified'],1)
        self.assertFalse(report['scientific_method_certified']);self.assertFalse(report['auto_enable'])
        self.assertEqual(self.index.read_bytes(),before)
        (self.root/'provenance/source-evolution.json').unlink()
        with self.assertRaisesRegex(ValueError,'without recorded'):catalog.verify_import(self.root)

    def test_fake_commit_and_unrelated_real_commit_are_rejected(self):
        for revision in ['0'*40,self.original_revision]:
            with self.subTest(revision=revision):
                self.ledger['changes'][0]['current']['revision']=revision;self.write_ledger()
                with self.assertRaises(ValueError):catalog.verify_import(self.root)

    def test_fake_blob_cannot_be_accepted_by_self_reported_ledger_sha(self):
        self.ledger['changes'][0]['current']['git_blob']='0'*40;self.write_ledger()
        with self.assertRaisesRegex(ValueError,'path/blob'):catalog.verify_import(self.root)

    def test_original_identity_mismatch_and_duplicate_path_fail_closed(self):
        original=copy.deepcopy(self.ledger)
        self.ledger['changes'][0]['original']['sha256']='b'*64;self.write_ledger()
        with self.assertRaisesRegex(ValueError,'original identity'):catalog.verify_import(self.root)
        self.ledger=original;self.ledger['changes'].append(copy.deepcopy(self.ledger['changes'][0]));self.write_ledger()
        with self.assertRaisesRegex(ValueError,'Duplicate source evolution'):catalog.verify_import(self.root)

    def test_actual_drift_and_source_snapshot_without_git_refuse_evolution(self):
        target=self.root/self.path;target.write_bytes(b'UNREGISTERED DRIFT\n')
        with self.assertRaisesRegex(ValueError,'differs from independently'):catalog.verify_import(self.root)
        target.write_bytes(b'CURRENT TEST SOURCE\n');shutil.rmtree(self.root/'.git')
        with self.assertRaisesRegex(ValueError,'Git object verification'):catalog.verify_import(self.root)

    def test_ledger_cannot_grant_scientific_certification_or_auto_enable(self):
        for field in ['scientific_certified','auto_enable']:
            with self.subTest(field=field):
                self.ledger[field]=True;self.write_ledger()
                with self.assertRaisesRegex(ValueError,'unapproved'):catalog.verify_import(self.root)
                self.ledger[field]=False


if __name__ == '__main__':unittest.main()
