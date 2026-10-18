"""Small offline contracts; these do not certify deployment or public endpoints."""

import csv
import gzip
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).with_name("geo_fetch.py")


class GeoFetchContract(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        environment = {"AUTONOMICS_OUTPUT0": str(self.directory / "payload"),
                       "AUTONOMICS_OUTPUT1": str(self.directory / "fetch.log")}
        with patch.dict(os.environ, environment):
            specification = importlib.util.spec_from_file_location("geo_fetch_contract", SOURCE)
            self.module = importlib.util.module_from_spec(specification)
            specification.loader.exec_module(self.module)
        self.module.ACCESSION = "GSE130563"
        self.module.MODE = "matrix"
        self.module.MATRIX_FILE = ""
        self.module.SRA_CHOICE = ""
        self.module.SUPPL_FILE = ""
        self.module.PROVENANCE = {}
        self.module.ATTEMPTS = []

    def tearDown(self):
        self.module.close_owned_files()
        self.temporary.cleanup()

    def write_gzip(self, content):
        target = self.directory / "fixture.gz"
        target.write_bytes(gzip.compress(content, mtime=0))
        return target

    def matrix(self):
        return (b'!Series_geo_accession\t"GSE130563"\n'
                b'!series_matrix_table_begin\n"ID_REF"\t"GSM1"\n'
                b'"gene"\t1\n!series_matrix_table_end\n')

    def runinfo(self, values=None):
        self.module.MODE = "runinfo"
        self.module.PROVENANCE["resolved_sra_accession"] = "SRR000001"
        columns = ["Run", "Experiment", "SRAStudy", "Sample", "LibraryName", "Extra"]
        row = values or ["SRR000001", "SRX000001", "SRP000001", "SRS000001", "0001", "NA"]
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        writer.writerows([columns, row])
        source = self.directory / "runinfo.csv"
        source.write_text(buffer.getvalue(), encoding="utf-8", newline="")
        return source, columns, row

    def test_small_geo_prefix(self):
        self.module.ACCESSION = "GSE99"
        self.assertIn("/GSEnnn/GSE99/", self.module.build_url())

    def test_explicit_platform_preserves_choice(self):
        self.module.ACCESSION = "GSE99"
        self.module.MATRIX_FILE = "GSE99-GPL221_series_matrix.txt.gz"
        self.assertTrue(self.module.build_url().endswith(self.module.MATRIX_FILE))
        self.assertEqual(self.module.PROVENANCE["platform_selection"], "EXPLICIT_FILENAME")

    def test_wrong_platform_accession_refused(self):
        self.module.MATRIX_FILE = "GSE1-GPL1_series_matrix.txt.gz"
        with self.assertRaises(self.module.FetchError):
            self.module.build_url()

    def test_soft_url_is_official_gzip_not_tar(self):
        self.module.MODE = "soft"
        self.assertTrue(self.module.build_url().endswith("GSE130563_family.soft.gz"))

    def test_direct_sra_uses_runinfo(self):
        self.module.MODE = "runinfo"
        self.module.ACCESSION = "SRX000001"
        self.assertEqual(self.module.build_url(), "https://trace.ncbi.nlm.nih.gov/Traces/sra-db-be/runinfo?acc=SRX000001")

    def test_direct_sra_rejects_gse_choice(self):
        self.module.MODE = "runinfo"
        self.module.ACCESSION = "SRR000001"
        self.module.SRA_CHOICE = "SRP000001"
        with self.assertRaises(self.module.FetchError):
            self.module.build_url()

    def test_safe_filename_preserves_legal_punctuation(self):
        for filename in ["a..b.txt", "safe β (data)+part.tsv", "quote\".txt"]:
            with self.subTest(filename=filename):
                self.assertTrue(self.module.safe_filename(filename))
        for filename in ["", ".", "..", "../x", "x\\y", "x\ny", "x\x00y"]:
            with self.subTest(filename=filename):
                self.assertFalse(self.module.safe_filename(filename))

    def test_matrix_valid_and_raw_bytes_unchanged(self):
        target = self.write_gzip(self.matrix())
        before = target.read_bytes()
        self.module.validate_payload(target)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(self.module.PROVENANCE["gzip_crc_checked"], "true")

    def test_matrix_latin1_identifiers_are_not_transcoded(self):
        target = self.write_gzip(self.matrix().replace(b'"gene"', b'"g\xe8ne"'))
        before = target.read_bytes()
        self.module.validate_payload(target)
        self.assertEqual(target.read_bytes(), before)

    def test_matrix_complete_multiblock_supported(self):
        target = self.write_gzip(self.matrix() * 2)
        self.module.validate_payload(target)
        self.assertEqual(self.module.PROVENANCE["validated_matrix_tables"], 2)

    def test_matrix_bad_crc_refused(self):
        target = self.write_gzip(self.matrix())
        damaged = bytearray(target.read_bytes())
        damaged[-8] ^= 1
        target.write_bytes(damaged)
        with self.assertRaises(gzip.BadGzipFile):
            self.module.validate_payload(target)

    def test_matrix_truncated_refused(self):
        target = self.write_gzip(self.matrix())
        target.write_bytes(target.read_bytes()[:-12])
        with self.assertRaises(EOFError):
            self.module.validate_payload(target)

    def test_matrix_identity_markers_header_width_refused(self):
        for content in [self.matrix().replace(b"GSE130563", b"GSE1"),
                        self.matrix().replace(b"!series_matrix_table_end\n", b""),
                        self.matrix().replace(b"ID_REF", b"WRONG"),
                        self.matrix().replace(b'"gene"\t1', b'"gene"\t1\t2')]:
            with self.subTest(content=content):
                target = self.write_gzip(content)
                with self.assertRaises(self.module.FetchError):
                    self.module.validate_payload(target)

    def test_soft_valid_and_format_explicit(self):
        self.module.MODE = "soft"
        target = self.write_gzip(b"^SERIES = GSE130563\n^SAMPLE = GSM1\n!sample_table_begin\nID_REF\tVALUE\ngene\t1\n!sample_table_end\n")
        self.module.validate_payload(target)
        self.assertEqual(self.module.PROVENANCE["source_format"], "GZIP_SOFT_TEXT_NOT_TAR_LEGACY_OUTPUT_BASENAME")

    def test_soft_incomplete_refused(self):
        self.module.MODE = "soft"
        for content in [b"^SERIES = GSE130563\n", b"not soft\n",
                        b"^SERIES = GSE130563\n^SAMPLE = GSM1\n!sample_table_begin\n"]:
            with self.subTest(content=content):
                target = self.write_gzip(content)
                with self.assertRaises(self.module.FetchError):
                    self.module.validate_payload(target)

    def test_html_whitespace_refused(self):
        self.module.MODE = "suppl"
        target = self.directory / "html"
        target.write_bytes(b" \n<html>error</html>")
        with self.assertRaises(self.module.FetchError):
            self.module.validate_payload(target)

    def test_runinfo_lexical_strings_and_quoted_fields(self):
        source, columns, row = self.runinfo(["SRR000001", "SRX000001", "SRP000001", "SRS000001", "0001", 'NA\ttab\nnewline,"quote" β'])
        target = self.directory / "runinfo.tsv"
        self.module.convert_runinfo(source, target)
        with target.open(newline="", encoding="utf-8") as handle:
            self.assertEqual(list(csv.reader(handle, delimiter="\t", strict=True)), [columns, row])

    def test_runinfo_duplicate_and_wrong_query_refused(self):
        source, columns, row = self.runinfo()
        with source.open("a", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerow(row)
        with self.assertRaises(self.module.FetchError):
            self.module.convert_runinfo(source, self.directory / "duplicate.tsv")
        source.write_text(source.read_text().replace("SRR000001", "SRR000002"))
        with self.assertRaises(self.module.FetchError):
            self.module.convert_runinfo(source, self.directory / "wrong.tsv")

    def test_runinfo_blank_and_header_only_refused(self):
        source, columns, row = self.runinfo()
        for index, content in enumerate(["", source.read_text().splitlines(keepends=True)[0]]):
            source.write_text(content)
            with self.assertRaises(self.module.FetchError):
                self.module.convert_runinfo(source, self.directory / (str(index) + ".tsv"))

    def test_main_failure_diagnostic_and_partial_cleanup(self):
        def controlled_download(url, target, **kwargs):
            content = gzip.compress(b"invalid matrix\n", mtime=0)
            with self.module.create_owned_file(target, "xb") as handle:
                handle.write(content)
            return len(content), hashlib.sha256(content).hexdigest(), 200

        with patch.object(self.module, "download", controlled_download):
            with self.assertRaises(self.module.FetchError):
                self.module.main()
        self.assertFalse(Path(self.module.OUT_FILE).exists())
        self.assertIn("FAILED", Path(self.module.OUT_LOG).read_text())
        self.assertEqual(list(self.directory.glob("*.partial")), [])

    def test_prior_output_and_log_not_overwritten(self):
        Path(self.module.OUT_FILE).write_bytes(b"prior payload")
        Path(self.module.OUT_LOG).write_bytes(b"prior log")
        with self.assertRaises(self.module.FetchError):
            self.module.main()
        self.assertEqual(Path(self.module.OUT_FILE).read_bytes(), b"prior payload")
        self.assertEqual(Path(self.module.OUT_LOG).read_bytes(), b"prior log")

    def test_gse_relations_unique_and_explicit_membership(self):
        self.module.MODE = "runinfo"
        relation = "^SERIES = GSE130563\n!Series_relation = SRA: https://www.ncbi.nlm.nih.gov/sra?term=SRP000001\n"

        def controlled_download(url, target, **kwargs):
            content = relation.encode("utf-8")
            with self.module.create_owned_file(target, "xb") as handle:
                handle.write(content)
            return len(content), hashlib.sha256(content).hexdigest(), 200

        with patch.object(self.module, "download", controlled_download):
            self.assertEqual(self.module.resolve_sra_accession(), "SRP000001")
            relation += "!Series_relation = SRA: https://www.ncbi.nlm.nih.gov/sra?term=SRP000002\n"
            with self.assertRaises(self.module.FetchError):
                self.module.resolve_sra_accession()
            self.module.SRA_CHOICE = "SRP000002"
            self.assertEqual(self.module.resolve_sra_accession(), "SRP000002")
            self.module.SRA_CHOICE = "SRP000003"
            with self.assertRaises(self.module.FetchError):
                self.module.resolve_sra_accession()
        self.assertEqual(list(self.directory.glob("*.partial")), [])
        self.assertIn("SRP000002", self.module.PROVENANCE["relation_raw"])

    def test_gse_missing_wrong_series_or_untrusted_relation_refused(self):
        self.module.MODE = "runinfo"
        for relation in ["^SERIES = GSE130563\n", "^SERIES = GSE1\n",
                         "^SERIES = GSE130563\n!Series_relation = SRA: https://example.org/sra?term=SRP000001\n"]:
            def controlled_download(url, target, **kwargs):
                content = relation.encode("utf-8")
                with self.module.create_owned_file(target, "xb") as handle:
                    handle.write(content)
                return len(content), hashlib.sha256(content).hexdigest(), 200

            with self.subTest(relation=relation), patch.object(self.module, "download", controlled_download):
                with self.assertRaises(self.module.FetchError):
                    self.module.resolve_sra_accession()
            self.assertEqual(list(self.directory.glob("*.partial")), [])

    def test_matrix_missing_header_refused(self):
        content = (b'!Series_geo_accession\t"GSE130563"\n'
                   b'!series_matrix_table_begin\n!series_matrix_table_end\n')
        with self.assertRaisesRegex(self.module.FetchError, "sample header"):
            self.module.validate_payload(self.write_gzip(content))

    def test_foreign_regular_and_symlink_partials_preserved(self):
        for replacement in ("regular", "symlink"):
            with self.subTest(replacement=replacement):
                source = Path(self.module.OUT_FILE).with_name("payload.source.partial")
                referent = self.directory / "referent"
                referent.write_bytes(b"foreign referent")

                def controlled_download(url, target, **kwargs):
                    with self.module.create_owned_file(target, "xb") as handle:
                        handle.write(b"own incomplete body")
                    Path(target).unlink()
                    if replacement == "regular":
                        Path(target).write_bytes(b"foreign replacement")
                    else:
                        Path(target).symlink_to(referent)
                    raise RuntimeError("controlled transport failure")

                with patch.object(self.module, "download", controlled_download):
                    with self.assertRaisesRegex(RuntimeError, "controlled transport failure"):
                        self.module.main()
                self.assertTrue(os.path.lexists(source))
                self.assertEqual(referent.read_bytes(), b"foreign referent")
                if replacement == "regular":
                    self.assertEqual(source.read_bytes(), b"foreign replacement")
                else:
                    self.assertEqual(os.readlink(source), str(referent))
                self.assertFalse(Path(self.module.OUT_FILE).exists())
                self.assertIn("FAILED", Path(self.module.OUT_LOG).read_text())
                self.assertEqual(self.module.OWNED_DESCRIPTORS, {})
                source.unlink()
                Path(self.module.OUT_LOG).unlink()

    def test_foreign_log_replacement_never_truncated(self):
        for replacement in ("regular", "symlink"):
            with self.subTest(replacement=replacement):
                log = Path(self.module.OUT_LOG)
                referent = self.directory / "log-referent"
                referent.write_bytes(b"foreign log referent")

                def controlled_download(url, target, **kwargs):
                    content = gzip.compress(self.matrix(), mtime=0)
                    with self.module.create_owned_file(target, "xb") as handle:
                        handle.write(content)
                    log.unlink()
                    if replacement == "regular":
                        log.write_bytes(b"foreign log")
                    else:
                        log.symlink_to(referent)
                    return len(content), hashlib.sha256(content).hexdigest(), 200

                with patch.object(self.module, "download", controlled_download):
                    with self.assertRaises((self.module.FetchError, OSError)):
                        self.module.main()
                self.assertFalse(Path(self.module.OUT_FILE).exists())
                self.assertEqual(referent.read_bytes(), b"foreign log referent")
                if replacement == "regular":
                    self.assertEqual(log.read_bytes(), b"foreign log")
                else:
                    self.assertEqual(os.readlink(log), str(referent))
                log.unlink()

    def test_unlinked_owned_inode_retained_until_cleanup(self):
        target = self.directory / "owned-partial"
        with self.module.create_owned_file(target, "xb") as handle:
            handle.write(b"own original")
        key = self.module.ownership_key(target)
        descriptor = self.module.OWNED_DESCRIPTORS[key]
        expected_identity = self.module.OWNED_FILES[key]
        target.unlink()
        target.write_bytes(b"foreign")
        retained = os.fstat(descriptor)
        self.assertEqual((retained.st_dev, retained.st_ino), expected_identity)
        foreign = os.lstat(target)
        self.assertNotEqual((foreign.st_dev, foreign.st_ino), expected_identity)
        self.module.remove_owned_file(target)
        self.assertEqual(target.read_bytes(), b"foreign")

    def test_empty_second_matrix_block_refused(self):
        content = self.matrix() + b'!series_matrix_table_begin\n!series_matrix_table_end\n'
        with self.assertRaisesRegex(self.module.FetchError, "sample header"):
            self.module.validate_payload(self.write_gzip(content))

    def test_transport_retry_preserves_foreign_replacements(self):
        for replacement in ("regular", "symlink"):
            with self.subTest(replacement=replacement):
                target = self.directory / "download-partial"
                referent = self.directory / "retry-referent"
                referent.write_bytes(b"foreign referent")
                calls = []

                def stream(*args, **kwargs):
                    yield b"own incomplete chunk"
                    target.unlink()
                    if replacement == "regular":
                        target.write_bytes(b"foreign replacement")
                    else:
                        target.symlink_to(referent)
                    raise RuntimeError("controlled transport interruption")

                class Response:
                    status_code = 200
                    headers = {}
                    raw = SimpleNamespace(stream=stream)

                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return False

                def request(*args, **kwargs):
                    calls.append(args)
                    return Response()

                with patch.dict("sys.modules", {"requests": SimpleNamespace(get=request)}), patch.object(self.module.time, "sleep"):
                    with self.assertRaisesRegex(self.module.FetchError, "replaced or unowned"):
                        self.module.download("https://ftp.ncbi.nlm.nih.gov/test", target)
                self.assertEqual(len(calls), 1)
                self.assertEqual(referent.read_bytes(), b"foreign referent")
                if replacement == "regular":
                    self.assertEqual(target.read_bytes(), b"foreign replacement")
                else:
                    self.assertEqual(os.readlink(target), str(referent))
                target.unlink()
                self.module.close_owned_files()

    def test_foreign_relation_replacement_refused_and_preserved(self):
        self.module.MODE = "runinfo"
        relation = b'^SERIES = GSE130563\n!Series_relation = SRA: https://www.ncbi.nlm.nih.gov/sra?term=SRP000001\n'
        target = Path(self.module.OUT_FILE).with_name("payload.relation.partial")

        def controlled_download(url, target, **kwargs):
            with self.module.create_owned_file(target, "xb") as handle:
                handle.write(relation)
            Path(target).unlink()
            Path(target).write_bytes(b"foreign relation")
            return len(relation), hashlib.sha256(relation).hexdigest(), 200

        with patch.object(self.module, "download", controlled_download):
            with self.assertRaisesRegex(self.module.FetchError, "replaced or unowned"):
                self.module.resolve_sra_accession()
        self.assertEqual(target.read_bytes(), b"foreign relation")

    def test_successful_transport_path_replacement_is_not_published(self):
        target = Path(self.module.OUT_FILE).with_name("payload.source.partial")
        content = gzip.compress(self.matrix(), mtime=0)

        def controlled_download(url, target, **kwargs):
            with self.module.create_owned_file(target, "xb") as handle:
                handle.write(content)
            Path(target).unlink()
            Path(target).write_bytes(content)
            return len(content), hashlib.sha256(content).hexdigest(), 200

        with patch.object(self.module, "download", controlled_download):
            with self.assertRaisesRegex(self.module.FetchError, "replaced or unowned"):
                self.module.main()
        self.assertEqual(target.read_bytes(), content)
        self.assertFalse(Path(self.module.OUT_FILE).exists())
        self.assertIn("FAILED", Path(self.module.OUT_LOG).read_text())

    def test_final_diagnostic_write_failure_removes_only_owned_payload(self):
        content = gzip.compress(self.matrix(), mtime=0)
        original_open = self.module.open_owned_file

        def controlled_download(url, target, **kwargs):
            with self.module.create_owned_file(target, "xb") as handle:
                handle.write(content)
            return len(content), hashlib.sha256(content).hexdigest(), 200

        def controlled_open(filename, mode):
            if str(filename) == self.module.OUT_LOG and mode == "w":
                raise OSError("controlled diagnostic write failure")
            return original_open(filename, mode)

        with patch.object(self.module, "download", controlled_download), patch.object(self.module, "open_owned_file", controlled_open):
            with self.assertRaisesRegex(OSError, "controlled diagnostic write failure"):
                self.module.main()
        self.assertFalse(Path(self.module.OUT_FILE).exists())
        self.assertEqual(list(self.directory.glob("*.partial")), [])
        self.assertEqual(self.module.OWNED_DESCRIPTORS, {})

    def test_final_diagnostic_failure_preserves_foreign_payload(self):
        content = gzip.compress(self.matrix(), mtime=0)
        payload = Path(self.module.OUT_FILE)
        original_open = self.module.open_owned_file

        def controlled_download(url, target, **kwargs):
            with self.module.create_owned_file(target, "xb") as handle:
                handle.write(content)
            return len(content), hashlib.sha256(content).hexdigest(), 200

        def controlled_open(filename, mode):
            if str(filename) == self.module.OUT_LOG and mode == "w":
                key = self.module.ownership_key(payload)
                self.assertIn(key, self.module.OWNED_DESCRIPTORS)
                payload.unlink()
                payload.write_bytes(b"foreign payload")
                raise OSError("controlled diagnostic failure after foreign replacement")
            return original_open(filename, mode)

        with patch.object(self.module, "download", controlled_download), patch.object(self.module, "open_owned_file", controlled_open):
            with self.assertRaisesRegex(OSError, "controlled diagnostic failure"):
                self.module.main()
        self.assertEqual(payload.read_bytes(), b"foreign payload")
        self.assertEqual(self.module.OWNED_DESCRIPTORS, {})

    def metadata_matrix(self, metadata, header):
        return (b'!Series_geo_accession\t"GSE130563"\n'
                + ('!Sample_geo_accession\t' + '\t'.join(metadata) + '\n').encode('ascii')
                + b'!series_matrix_table_begin\n'
                + ('ID_REF\t' + '\t'.join(header) + '\n').encode('ascii')
                + ('gene\t' + '\t'.join('1' for sample in header) + '\n').encode('ascii')
                + b'!series_matrix_table_end\n')

    def test_present_sample_metadata_exact_order_matches(self):
        payload = self.write_gzip(self.metadata_matrix(['GSM1', 'GSM2'], ['GSM1', 'GSM2']))
        original = payload.read_bytes()
        self.module.validate_payload(payload)
        self.assertEqual(payload.read_bytes(), original)
        self.assertEqual(self.module.PROVENANCE['sample_metadata_bound_tables'], 1)
        self.assertEqual(self.module.PROVENANCE['tables_without_sample_metadata'], 0)

    def test_present_sample_metadata_identity_count_order_mismatch_refused(self):
        for metadata in (['GSM1', 'GSM999'], ['GSM1'], ['GSM2', 'GSM1']):
            with self.subTest(metadata=metadata):
                payload = self.write_gzip(self.metadata_matrix(metadata, ['GSM1', 'GSM2']))
                with self.assertRaisesRegex(self.module.FetchError, 'identities/order differ'):
                    self.module.validate_payload(payload)

    def test_present_sample_metadata_duplicates_refused(self):
        payload = self.write_gzip(self.metadata_matrix(['GSM1', 'GSM1'], ['GSM1', 'GSM2']))
        with self.assertRaisesRegex(self.module.FetchError, 'unique GEO sample accessions'):
            self.module.validate_payload(payload)

    def test_multiblock_metadata_is_local_not_inferred_for_next_table(self):
        content = (self.metadata_matrix(['GSM1', 'GSM2'], ['GSM1', 'GSM2'])
                   + self.metadata_matrix(['GSM3'], ['GSM3']) + self.matrix())
        self.module.validate_payload(self.write_gzip(content))
        self.assertEqual(self.module.PROVENANCE['validated_matrix_tables'], 3)
        self.assertEqual(self.module.PROVENANCE['sample_metadata_bound_tables'], 2)
        self.assertEqual(self.module.PROVENANCE['tables_without_sample_metadata'], 1)

    def test_conflicting_or_unconsumed_sample_metadata_refused(self):
        content = self.metadata_matrix(['GSM1'], ['GSM1'])
        inserted = content.replace(b'!series_matrix_table_begin\n', b'!Sample_geo_accession\tGSM2\n!series_matrix_table_begin\n')
        with self.assertRaisesRegex(self.module.FetchError, 'uniquely precede'):
            self.module.validate_payload(self.write_gzip(inserted))
        content += b'!Sample_geo_accession\tGSM2\n'
        with self.assertRaisesRegex(self.module.FetchError, 'no corresponding'):
            self.module.validate_payload(self.write_gzip(content))


if __name__ == "__main__":
    unittest.main()
