"""Exercise output ownership with synthetic files and a recording author entry."""

from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


DRIVER_PATH = Path(__file__).resolve().parents[1] / 'plugins/cellphonedb/driver.py'
SPEC = importlib.util.spec_from_file_location('cellphonedb_publication_driver', DRIVER_PATH)
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)
TABLES = ('pvalues', 'means', 'significant_means', 'deconvoluted',
          'deconvoluted_percents', 'interaction_scores')


class CellPhoneDBOutputPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='cpdb-publication-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.counts = self.root / 'counts.h5ad'
        self.metadata = self.root / 'meta.tsv'
        self.counts.touch()
        self.metadata.touch()
        (self.root / 'database.zip').touch()
        self.called = False

    def table(self, directory, name, stamp='01_01_2026_120000'):
        path = Path(directory) / f'statistical_analysis_{name}_{stamp}.txt'
        path.write_text('OFFICIAL_' + name)
        return path

    def invoke(self, action=None):
        def official(**kwargs):
            self.called = True
            for name in TABLES:
                self.table(kwargs['output_path'], name)
            if action:
                action(Path(kwargs['output_path']))
            return {}

        methods = types.ModuleType('cellphonedb.src.core.methods')
        methods.cpdb_statistical_analysis_method = types.SimpleNamespace(call=official)
        environment = {'AUTONOMICS_INPUT0': str(self.counts),
                       'AUTONOMICS_INPUT1': str(self.metadata),
                       'AUTONOMICS_WORKDIR': str(self.root), 'CPDB_ROOT': str(self.root)}
        with patch.dict(os.environ, environment, clear=True), \
                patch.dict(sys.modules, {'cellphonedb.src.core.methods': methods}), \
                patch.object(DRIVER.importlib.metadata, 'version', return_value='5.0.1'), \
                redirect_stdout(io.StringIO()):
            DRIVER.main()

    def assert_no_results(self):
        self.assertFalse(list(self.root.glob('cpdb_*')))
        self.assertFalse(list(self.root.glob('.cpdb-owned-*')))

    def test_complete_owned_outputs_preserve_author_bytes(self):
        self.invoke()
        self.assertEqual(len(list(self.root.glob('cpdb_*'))), 7)
        for name in TABLES:
            self.assertEqual((self.root / f'cpdb_{name}.txt').read_text(), 'OFFICIAL_' + name)
        self.assertFalse(list(self.root.glob('.cpdb-owned-*')))

    def test_existing_table_refuses_before_author_call(self):
        prior = self.root / 'cpdb_pvalues.txt'
        prior.write_text('FOREIGN_TABLE')
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertFalse(self.called)
        self.assertEqual(prior.read_text(), 'FOREIGN_TABLE')

    def test_existing_provenance_refuses_before_author_call(self):
        prior = self.root / 'cpdb_provenance.json'
        prior.write_text('FOREIGN_PROVENANCE')
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertFalse(self.called)
        self.assertEqual(prior.read_text(), 'FOREIGN_PROVENANCE')

    def test_dangling_destination_symlink_is_preserved(self):
        prior = self.root / 'cpdb_pvalues.txt'
        prior.symlink_to(self.root / 'does-not-exist')
        with self.assertRaises(SystemExit):
            self.invoke()
        self.assertFalse(self.called)
        self.assertTrue(prior.is_symlink())

    def test_prior_timestamped_file_is_not_ingested_or_changed(self):
        prior = self.table(self.root, 'pvalues', '02_02_2026_130000')
        prior.write_text('FOREIGN_TIMESTAMPED')
        self.invoke()
        self.assertEqual(prior.read_text(), 'FOREIGN_TIMESTAMPED')
        self.assertEqual((self.root / 'cpdb_pvalues.txt').read_text(), 'OFFICIAL_pvalues')

    def test_missing_required_table_publishes_nothing(self):
        def missing(directory):
            (directory / 'statistical_analysis_means_01_01_2026_120000.txt').unlink()

        with self.assertRaises(SystemExit):
            self.invoke(missing)
        self.assert_no_results()

    def test_duplicate_table_versions_publish_nothing(self):
        with self.assertRaises(SystemExit):
            self.invoke(lambda directory: self.table(directory, 'pvalues', '03_03_2026_140000'))
        self.assert_no_results()

    def test_author_failure_publishes_nothing(self):
        def fail(directory):
            raise RuntimeError('AUTHOR_FAILURE')

        with self.assertRaisesRegex(RuntimeError, 'AUTHOR_FAILURE'):
            self.invoke(fail)
        self.assert_no_results()

    def test_link_failure_rolls_back_only_owned_results(self):
        original_link = os.link
        created = []

        def fail(source, destination, **kwargs):
            if len(created) == 2:
                raise OSError('INJECTED_LINK_FAILURE')
            original_link(source, destination, **kwargs)
            created.append(Path(destination))

        with patch.object(DRIVER.os, 'link', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'INJECTED_LINK_FAILURE'):
                self.invoke()
        self.assert_no_results()

    def test_foreign_replacement_is_not_deleted_during_rollback(self):
        original_link = os.link
        created = []

        def fail(source, destination, **kwargs):
            if created:
                created[0].unlink()
                created[0].write_text('FOREIGN_REPLACEMENT')
                raise OSError('INJECTED_FOREIGN_REPLACEMENT')
            original_link(source, destination, **kwargs)
            created.append(Path(destination))

        with patch.object(DRIVER.os, 'link', side_effect=fail):
            with self.assertRaisesRegex(OSError, 'INJECTED_FOREIGN_REPLACEMENT'):
                self.invoke()
        self.assertEqual(created[0].read_text(), 'FOREIGN_REPLACEMENT')
        self.assertEqual(list(self.root.glob('cpdb_*')), created)

    def test_symlink_author_output_is_not_published(self):
        def alias(directory):
            path = directory / 'statistical_analysis_pvalues_01_01_2026_120000.txt'
            path.unlink()
            path.symlink_to(self.counts)

        with self.assertRaises(SystemExit):
            self.invoke(alias)
        self.assert_no_results()


if __name__ == '__main__':
    unittest.main()
