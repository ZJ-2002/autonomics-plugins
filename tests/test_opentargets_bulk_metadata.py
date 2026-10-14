import struct
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch

from tools import audit_opentargets_bulk_metadata as audit


class OfficialBulkMetadataTests(unittest.TestCase):
    def test_only_literal_unique_parquet_members_are_accepted(self):
        self.assertEqual(audit.parquet_names(b'<a href="part-1.parquet">part</a>'), ["part-1.parquet"])
        for body in [b'<a href="../part.parquet">bad</a>', b'<a href="https://foreign/part.parquet">bad</a>',
                     b'<a href="part.parquet">a</a><a href="part.parquet">b</a>', b'<a href="folder/">empty</a>']:
            with self.assertRaises(RuntimeError):
                audit.parquet_names(body)

    def test_footer_length_is_bounded_and_never_means_full_file_fallback(self):
        self.assertEqual(audit.footer_length(struct.pack("<I", 10) + b"PAR1", 100), 10)
        for trailer, total in [(b"bad", 100), (struct.pack("<I", 0) + b"PAR1", 100),
                               (struct.pack("<I", audit.FOOTER_LIMIT + 1) + b"PAR1", 99999999),
                               (struct.pack("<I", 100) + b"PAR1", 100)]:
            with self.assertRaises(RuntimeError):
                audit.footer_length(trailer, total)

    def test_author_metadata_scope_cannot_claim_complete_source_or_read_data_rows(self):
        self.assertEqual(audit.DATASETS[:3], ["association_overall_direct", "association_by_datasource_direct", "association_by_datatype_direct"])
        self.assertIn("parquet.read_metadata", audit.READER)
        self.assertNotIn("read_table", audit.READER)
        self.assertIn("complete_membership_verified=False", audit.READER)

    def test_reader_preserves_private_directory_permissions_and_exact_image(self):
        command = audit.reader_command(Path("/private"), audit.READER_IMAGE)
        self.assertIn("--userns=keep-id", command)
        self.assertIn(f"--user={audit.os.getuid()}:{audit.os.getgid()}", command)
        self.assertIn("--network=none", command)
        with self.assertRaises(RuntimeError):
            audit.reader_command(Path("/private"), "mutable:latest")

    def test_range_transport_rejects_full_response_changed_identity_and_extra_bytes(self):
        identity = dict(bytes=100, etag='"original"')
        for status, content_range, etag, body in [
            (206, "bytes 92-99/100", '"original"', b"12345678"),
            (200, "bytes 92-99/100", '"original"', b"12345678"),
            (206, "bytes 92-99/101", '"original"', b"12345678"),
            (206, "bytes 92-99/100", '"changed"', b"12345678"),
            (206, "bytes 92-99/100", '"original"', b"123456789")]:
            with patch.object(audit, "urlopen") as request, patch.object(audit.time, "sleep"):
                response = request.return_value.__enter__.return_value
                response.status = status
                response.url = "https://official/part"
                response.headers = {"Content-Range": content_range, "ETag": etag}
                response.read.return_value = body
                if status == 206 and content_range == "bytes 92-99/100" and etag == '"original"' and len(body) == 8:
                    self.assertEqual(audit.ranged(response.url, 92, 99, identity), body)
                else:
                    with self.assertRaises(RuntimeError):
                        audit.ranged(response.url, 92, 99, identity)
                response.read.assert_called_once_with(9)

    def test_archive_reuse_verifies_every_byte_without_relabeling_the_failed_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / ("a" * 32)
            source = archive / "artifacts/permanent/opentargets-bulk-metadata"
            source.mkdir(parents=True)
            audit.write(source / "predeclared.json", dict(release="26.09", datasets=audit.DATASETS))
            for dataset in audit.DATASETS:
                audit.write(source / (dataset + ".resource.json"), dict(dataset=dataset))
                (source / (dataset + ".footer-only.parquet")).write_bytes(b"toy metadata")
            manifest = dict(session=archive.name, files={})
            for path in source.iterdir():
                body = path.read_bytes()
                manifest["files"][path.relative_to(archive / "artifacts").as_posix()] = dict(
                    bytes=len(body), sha256=hashlib.sha256(body).hexdigest())
            manifest_path = archive / "artifacts/MANIFEST.json"
            audit.write(manifest_path, manifest)
            digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            audit.write(archive / "SESSION.json", dict(session=archive.name, state="CLEANED",
                        manifest_sha256=digest, worker_exit_status=1))
            output = root / "new"
            output.mkdir()
            self.assertEqual(len(audit.archived_metadata(archive, digest, output)), 5)
            record = json.loads((output / "metadata-source.json").read_bytes())
            self.assertEqual(record["source_worker_exit"], 1)
            self.assertFalse(record["source_complete"])
            self.assertTrue(record["original_failure_unchanged"])
            with self.assertRaisesRegex(RuntimeError, "manifest differs"):
                audit.archived_metadata(archive, "0" * 64, output)
            (source / "target.footer-only.parquet").write_bytes(b"changed")
            with self.assertRaisesRegex(RuntimeError, "content differs"):
                audit.archived_metadata(archive, digest, output)


if __name__ == "__main__":
    unittest.main()
