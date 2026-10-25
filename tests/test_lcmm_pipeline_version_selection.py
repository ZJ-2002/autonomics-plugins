import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
specification = importlib.util.spec_from_file_location('lcmm_pipeline', ROOT / 'tools/prove_lcmm_combined_pipeline.py')
pipeline = importlib.util.module_from_spec(specification)
specification.loader.exec_module(pipeline)


class LcmmPipelineVersionSelectionTests(unittest.TestCase):
    def manifest(self):
        return tomllib.loads((ROOT / 'research-adapters/cachexia-lcmm/manifest.toml').read_text())

    def test_legacy_modes_do_not_silently_select_v2_nodes(self):
        current = self.manifest()
        modes = pipeline.legacy_modes(current)
        self.assertEqual(set(modes), {'fit', 'predict', 'compare', 'bind'})
        self.assertTrue(all(not row['kind'].endswith('_v2') for row in modes.values()))
        self.assertEqual(current, self.manifest())

    def test_manifest_order_does_not_select_v2(self):
        current = self.manifest()
        expected = pipeline.legacy_modes(current)
        current['nodes'].reverse()
        self.assertEqual(pipeline.legacy_modes(current), expected)

    def test_duplicate_or_missing_legacy_mode_is_rejected(self):
        current = self.manifest()
        duplicate = copy.deepcopy(current)
        duplicate['nodes'].append(copy.deepcopy(duplicate['nodes'][0]))
        with self.assertRaises(RuntimeError):
            pipeline.legacy_modes(duplicate)
        current['nodes'] = [row for row in current['nodes'] if row['kind'].endswith('_v2')]
        with self.assertRaises(RuntimeError):
            pipeline.legacy_modes(current)

    def test_template_writer_retains_finite_request_parameters(self):
        self.assertIsNotNone(shutil.which('Rscript'), 'Missing R execution is not a pass')
        with tempfile.TemporaryDirectory(prefix='lcmm-template-precision-') as directory:
            work = Path(directory)
            source = work / 'prepare.R'
            source.write_text(pipeline.PREPARE_R)
            script = work / 'check.R'
            script.write_text(
                'library(jsonlite)\n'
                'expressions <- as.list(parse(' + json.dumps(str(source)) + '))\n'
                'writers <- Filter(function(value)is.call(value)&&identical(value[[1]],as.name("write_json"))&&identical(value[[2]],as.name("request")),expressions)\n'
                'stopifnot(length(writers)==1L)\n'
                'root <- ' + json.dumps(directory) + '\n'
                'request <- list(schema_version=1L,params=list(values=list(1+.Machine$double.eps,.Machine$double.xmax,.Machine$double.xmin,5e-324),nullable=NULL,empty=list()))\n'
                'eval(writers[[1]])\n'
                'stopifnot(identical(fromJSON(file.path(root,"fit2.json"),simplifyVector=FALSE),request))\n'
            )
            environment = {name: value for name, value in os.environ.items()
                           if name in {'PATH', 'HOME', 'LANG', 'LC_ALL', 'TMPDIR', 'R_LIBS', 'R_LIBS_USER', 'R_LIBS_SITE'}}
            result = subprocess.run(['Rscript', '--vanilla', str(script)], env=environment,
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
