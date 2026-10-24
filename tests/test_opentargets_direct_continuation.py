import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools import continue_opentargets_direct_reference as proof


class DirectContinuationTests(unittest.TestCase):
    def archive(self, root, worker_exit=None):
        session = 'a' * 32
        artifacts = root / session / 'artifacts'
        artifacts.mkdir(parents=True)
        member = artifacts / 'permanent/toy.parquet'
        member.parent.mkdir()
        member.write_bytes(b'PAR1dataPAR1')
        manifest = dict(session=session, files={'permanent/toy.parquet': dict(
            bytes=12, sha256=hashlib.sha256(member.read_bytes()).hexdigest())})
        body = json.dumps(manifest).encode()
        (artifacts / 'MANIFEST.json').write_bytes(body)
        seal = hashlib.sha256(body).hexdigest()
        (root / session / 'SESSION.json').write_text(json.dumps(dict(session=session,
            state='CLEANED', manifest_sha256=seal, worker_exit_status=worker_exit)))
        return session, seal, artifacts, manifest

    def test_interrupted_old_archive_only_establishes_bytes_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            session, seal, _, _ = self.archive(root)
            _, _, record = proof.verify_archive(root, session, seal, False)
            self.assertIsNone(record['worker_exit_status'])
            with self.assertRaises(RuntimeError):
                proof.verify_archive(root, session, seal, True)

    def test_new_archive_requires_recorded_zero_exit(self):
        for exit_status in [None, 1, False, '0', 0]:
            with self.subTest(exit_status=exit_status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                session, seal, _, _ = self.archive(root, exit_status)
                if type(exit_status) is int and exit_status == 0:
                    proof.verify_archive(root, session, seal, True)
                else:
                    with self.assertRaises(RuntimeError):
                        proof.verify_archive(root, session, seal, True)

    def test_complete_membership_hash_and_no_symlinks_are_required(self):
        for defect in ['extra', 'mutate', 'symlink', 'seal']:
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                session, seal, artifacts, _ = self.archive(root)
                if defect == 'extra':
                    (artifacts / 'extra').write_bytes(b'unlisted')
                elif defect == 'mutate':
                    (artifacts / 'permanent/toy.parquet').write_bytes(b'PAR1DIFFPAR1')
                elif defect == 'symlink':
                    (artifacts / 'foreign').symlink_to('/etc/passwd')
                else:
                    seal = 'b' * 64
                with self.assertRaises(RuntimeError):
                    proof.verify_archive(root, session, seal, False)

    def test_receipts_bind_exact_metadata_measured_hash_and_classified_member(self):
        with tempfile.TemporaryDirectory() as directory:
            artifacts = Path(directory)
            relative = proof.PREFIX + 'files/target/part-00000.parquet'
            path = artifacts / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(b'PAR1dataPAR1')
            record = dict(url=proof.original.BASE + 'target/part-00000.parquet', status=200,
                bytes=12, etag='"fixed"', last_modified='fixed')
            receipt = dict(record, dataset='target', sha256=proof.digest_file(path),
                relative_path='files/target/part-00000.parquet',
                sha256_is_measured_not_author_published=True)
            manifest = dict(files={relative: dict(bytes=12, sha256=receipt['sha256'])})
            planned = [('target', path.name, record)]
            result = proof.check_receipts(artifacts, manifest, 'a'*32, 'b'*64, proof.PREFIX, [receipt], planned)
            self.assertEqual(result[0]['relative_path'], relative)
            self.assertEqual(result[0]['source_session'], 'a'*32)
            for key, value in [('etag', 'changed'), ('bytes', 13), ('sha256', 'c'*64),
                    ('relative_path', '../foreign'), ('sha256_is_measured_not_author_published', False)]:
                changed = dict(receipt)
                changed[key] = value
                with self.subTest(key=key), self.assertRaises(RuntimeError):
                    proof.check_receipts(artifacts, manifest, 'a'*32, 'b'*64, proof.PREFIX, [changed], planned)
            with self.assertRaises(RuntimeError):
                proof.check_receipts(artifacts, manifest, 'a'*32, 'b'*64, proof.PREFIX, [receipt, receipt], planned)

    def test_redirect_is_refused_before_any_followup_request(self):
        with self.assertRaisesRegex(RuntimeError, 'no fallback request'):
            proof.NoRedirect().redirect_request(None, None, 302, 'Found', {}, 'https://example.invalid/')

    def test_batch_scope_is_maximum_two_files_and_old_exit_is_not_inferred(self):
        self.assertEqual(proof.BATCH_SIZE, 2)
        self.assertEqual(proof.OLD_SESSION, '3a35db8dda8e44018860e7e1895e9c7d')
        self.assertEqual(proof.OLD_SEAL, 'c60029a5a4a7c20c2375b0b37ba32f629d17603d984f8bf1474cd9afe56f685a')


if __name__ == '__main__':
    unittest.main()
