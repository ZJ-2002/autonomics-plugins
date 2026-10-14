import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from tools import prove_ldsc_author_reference as proof


class AuthorReferenceArchiveTests(unittest.TestCase):
    def archive(self,root,members):
        path=root/'reference.tgz'
        with tarfile.open(path,'w:gz') as archive:
            for name,content,kind in members:
                info=tarfile.TarInfo(name)
                if kind=='symlink':
                    info.type=tarfile.SYMTYPE
                    info.linkname='/outside'
                    archive.addfile(info)
                else:
                    info.size=len(content)
                    archive.addfile(info,io.BytesIO(content))
        return path

    def expected(self):
        return {'data.gz':dict(size=4,sha256='sha256:'+hashlib.sha256(b'DATA').hexdigest())}

    def test_every_raw_author_member_is_compared_without_extraction(self):
        root=Path(proof.__file__).resolve().parents[1]
        lineage=json.loads((root/'evidence/ldsc-upstream-maintenance-link-20261015.json').read_text())
        self.assertEqual(lineage['linked_repository'],'https://github.com/CBIIT/ldsc')
        self.assertIn(lineage['README_revision'],lineage['README_url'])
        self.assertEqual(lineage['deployed_CBIIT_revision'],'6c673952cee74bd5c57aef1555a03b1c015399a0')
        self.assertFalse(lineage['all_parameter_branches_or_legacy_numerical_equivalence_granted'])
        self.assertFalse(lineage['g0_granted'])
        evidence=json.loads((root/'evidence/ldsc-author-reference-equality-20261015.json').read_text())
        self.assertEqual(proof.digest(Path(proof.__file__)),evidence['proof_driver_sha256'])
        self.assertEqual(sum(len(item['members']) for item in evidence['proof']['archives']),88)
        self.assertEqual(sum(len(item['additional_author_metadata_preserved']) for item in evidence['proof']['archives']),22)
        self.assertFalse(evidence['current_DAG_or_deployment_granted'])
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            path=self.archive(root,[('official/data.gz',b'DATA','file')])
            result=proof.compare_archive(path,self.expected())
            self.assertEqual(len(result['data']),1)
            self.assertEqual(result['data'][0]['author_member'],'official/data.gz')
            self.assertEqual(result['additional_preserved'],[])
            self.assertEqual(list(root.iterdir()),[path])

    def test_unsafe_or_unexpected_members_cannot_be_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for member in [('../data.gz',b'DATA','file'),('/data.gz',b'DATA','file'),
                           ('official/data.gz',b'','symlink'),('extra.gz',b'DATA','file')]:
                with self.subTest(member=member):
                    path=self.archive(root,[member])
                    with self.assertRaises(RuntimeError):
                        proof.compare_archive(path,self.expected())

    def test_generation_metadata_is_explicit_preserved_and_never_arbitrary(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            output=root/'preserved'
            output.mkdir()
            path=self.archive(root,[('official/data.gz',b'DATA','file'),('official/LDscore.1.log',b'AUTHOR LOG','file')])
            result=proof.compare_archive(path,self.expected(),'LDscore',output)
            self.assertEqual((output/'LDscore.1.log').read_bytes(),b'AUTHOR LOG')
            self.assertEqual(len(result['additional_preserved']),1)
            path=self.archive(root,[('official/data.gz',b'DATA','file'),('official/LDscore.1.other',b'UNKNOWN','file')])
            with self.assertRaises(RuntimeError):
                proof.compare_archive(path,self.expected(),'LDscore',output)

    def test_missing_duplicate_and_changed_member_bytes_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            first=('official/data.gz',b'DATA','file')
            for members in [[],[first,first],[('official/data.gz',b'WRNG','file')]]:
                with self.subTest(members=members):
                    path=self.archive(root,members)
                    with self.assertRaises(RuntimeError):
                        proof.compare_archive(path,self.expected())


if __name__ == '__main__':
    unittest.main()
