"""Check wrapper parameter forwarding, not CellPhoneDB statistical calculations."""

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
SPEC = importlib.util.spec_from_file_location('cellphonedb_contract_driver', DRIVER_PATH)
DRIVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DRIVER)


class OfficialCallObserved(Exception):
    pass


class CellPhoneDBCallContractTests(unittest.TestCase):
    def invoke(self, function, *, seed=None):
        with tempfile.TemporaryDirectory(prefix='cpdb-api-contract-') as temporary:
            root = Path(temporary)
            counts = root / 'counts.h5ad'
            metadata = root / 'meta.tsv'
            counts.touch()
            metadata.touch()
            (root / 'database.zip').touch()
            environment = {'AUTONOMICS_INPUT0': str(counts),
                           'AUTONOMICS_INPUT1': str(metadata),
                           'AUTONOMICS_WORKDIR': str(root), 'CPDB_ROOT': str(root)}
            if seed is not None:
                environment['CPDB_SEED'] = str(seed)
            methods = types.ModuleType('cellphonedb.src.core.methods')
            methods.cpdb_statistical_analysis_method = types.SimpleNamespace(call=function)
            with patch.dict(os.environ, environment, clear=True), \
                    patch.dict(sys.modules, {'cellphonedb.src.core.methods': methods}), \
                    redirect_stdout(io.StringIO()):
                DRIVER.main()

    def test_all_requested_arguments_reach_official_call(self):
        captured = {}

        def official(cpdb_file_path, meta_file_path, counts_file_path, counts_data,
                     threshold, iterations, score_interactions, output_path):
            captured.update(locals())
            raise OfficialCallObserved()

        with self.assertRaises(OfficialCallObserved):
            self.invoke(official)
        self.assertEqual(captured['counts_data'], 'hgnc_symbol')
        self.assertEqual(captured['threshold'], 0.1)
        self.assertEqual(captured['iterations'], 1000)
        self.assertIs(captured['score_interactions'], True)
        self.assertEqual(Path(captured['counts_file_path']).name, 'counts.h5ad')
        self.assertEqual(Path(captured['meta_file_path']).name, 'meta.tsv')
        self.assertEqual(Path(captured['cpdb_file_path']).name, 'database.zip')

    def test_seed_and_single_thread_are_forwarded(self):
        captured = {}

        def official(cpdb_file_path, meta_file_path, counts_file_path, counts_data,
                     threshold, iterations, score_interactions, output_path,
                     debug_seed=-1, threads=4):
            captured.update(debug_seed=debug_seed, threads=threads)
            raise OfficialCallObserved()

        with self.assertRaises(OfficialCallObserved):
            self.invoke(official, seed=17)
        self.assertEqual(captured, {'debug_seed': 17, 'threads': 1})

    def test_unsupported_scoring_argument_refuses_before_call(self):
        def official(cpdb_file_path, meta_file_path, counts_file_path, counts_data,
                     threshold, iterations, output_path):
            raise OfficialCallObserved()

        with self.assertRaisesRegex(SystemExit, 'incompatible'):
            self.invoke(official)

    def test_unsupported_seed_argument_refuses_before_call(self):
        def official(cpdb_file_path, meta_file_path, counts_file_path, counts_data,
                     threshold, iterations, score_interactions, output_path, threads=4):
            raise OfficialCallObserved()

        with self.assertRaisesRegex(SystemExit, 'incompatible'):
            self.invoke(official, seed=17)

    def test_unsupported_threads_argument_refuses_before_call(self):
        def official(cpdb_file_path, meta_file_path, counts_file_path, counts_data,
                     threshold, iterations, score_interactions, output_path, debug_seed=-1):
            raise OfficialCallObserved()

        with self.assertRaisesRegex(SystemExit, 'incompatible'):
            self.invoke(official, seed=17)

    def test_new_required_argument_refuses_before_call(self):
        def official(cpdb_file_path, meta_file_path, counts_file_path, counts_data,
                     threshold, iterations, score_interactions, output_path, new_required):
            raise OfficialCallObserved()

        with self.assertRaisesRegex(SystemExit, 'incompatible'):
            self.invoke(official)

    def test_positional_only_argument_refuses_before_call(self):
        def official(cpdb_file_path, /, meta_file_path, counts_file_path, counts_data,
                     threshold, iterations, score_interactions, output_path):
            raise OfficialCallObserved()

        with self.assertRaisesRegex(SystemExit, 'incompatible'):
            self.invoke(official)

    def test_variadic_official_entry_receives_all_requested_arguments(self):
        captured = {}

        def official(**kwargs):
            captured.update(kwargs)
            raise OfficialCallObserved()

        with self.assertRaises(OfficialCallObserved):
            self.invoke(official, seed=17)
        self.assertEqual(len(captured), 10)
        self.assertIs(captured['score_interactions'], True)
        self.assertEqual(captured['debug_seed'], 17)
        self.assertEqual(captured['threads'], 1)

    def test_absent_seed_preserves_official_rng_defaults(self):
        captured = {}

        def official(cpdb_file_path, meta_file_path, counts_file_path, counts_data,
                     threshold, iterations, score_interactions, output_path,
                     debug_seed=-1, threads=4):
            captured.update(debug_seed=debug_seed, threads=threads)
            raise OfficialCallObserved()

        with self.assertRaises(OfficialCallObserved):
            self.invoke(official)
        self.assertEqual(captured, {'debug_seed': -1, 'threads': 4})


if __name__ == '__main__':
    unittest.main()
