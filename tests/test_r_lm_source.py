import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools import prove_r_lm_source as source


class OfficialReleaseIdentityTests(unittest.TestCase):
    def test_exact_primary_release_and_all_eight_methods_are_required(self):
        self.assertEqual(source.RELEASE_URL, "https://svn.r-project.org/R/tags/R-4-6-1/")
        self.assertEqual(set(source.SOURCE_SHA256), set(source.SOURCE_FILES))
        self.assertEqual(len(source.FUNCTIONS), 8)
        for function in source.FUNCTIONS:
            self.assertIn('"' + function + '"', source.R_COMPARE)
        self.assertIn("identical(formals(official),formals(installed))", source.R_COMPARE)
        self.assertIn("identical(body(official),body(installed))", source.R_COMPARE)
        self.assertIn("compiled_binary_rebuild_or_signed_provenance_verified=FALSE", source.R_COMPARE)

    def test_a_self_consistent_fake_archive_is_not_official_source_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            records = []
            for relative in source.SOURCE_FILES:
                body = b"FORGED SOURCE\n"
                path = directory / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(body)
                records.append(dict(path=relative, url=source.RELEASE_URL + relative,
                                    received_url=source.RELEASE_URL + relative, status=200,
                                    bytes=len(body), sha256=hashlib.sha256(body).hexdigest()))
            (directory / "source-lock.json").write_text(json.dumps(dict(release_url=source.RELEASE_URL, files=records)))
            with self.assertRaisesRegex(RuntimeError, "author-source identity changed"):
                source.archived_sources(directory)

    def test_missing_and_duplicate_source_paths_cannot_satisfy_the_reference_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for records in [[], [{"path": source.SOURCE_FILES[0]}] * 4]:
                (directory / "source-lock.json").write_text(json.dumps(dict(release_url=source.RELEASE_URL, files=records)))
                with self.assertRaisesRegex(RuntimeError, "Incomplete official-source reference lock"):
                    source.archived_sources(directory)


if __name__ == "__main__":
    unittest.main()
