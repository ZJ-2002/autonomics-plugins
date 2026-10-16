import tomllib
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class PrestartQCContract(unittest.TestCase):
 def test_qc_manifest_has_seven_declared_diagnostic_ports_and_fixed_environment(self):
  m=tomllib.loads((ROOT/'plugins/rnaseq-qc/manifest.toml').read_text());self.assertEqual(m['plugin_name'],'rnaseq-qc');self.assertIn('@sha256:',m['image']['reference'])
  n=m['nodes'][0];self.assertEqual(n['kind'],'rnaseq_prestart_qc');self.assertEqual(len(n['ports']['inputs']),2);self.assertEqual(len(n['ports']['outputs']),7);self.assertEqual(n['resources']['cpus'],1.0)
 def test_no_differential_fit_or_feature_selection_call(self):
  source=(ROOT/'plugins/rnaseq-qc/prestart_qc.R').read_text()
  for name in ['DESeq','estimateDispersions','nbinomWaldTest','nbinomLRT','results']:
   self.assertNotIn('DESeq2::'+name+'(',source)
  self.assertIn('DESeq2::estimateSizeFactors(dds,type="ratio")',source);self.assertIn('center=TRUE,scale.=FALSE',source)
 def test_raw_count_boundary_helpers_preserve_accepted_identity(self):
  qc=(ROOT/'plugins/rnaseq-qc/prestart_qc.R').read_text();de=(ROOT/'plugins/deseq2/deseq2_runner.R').read_text()
  self.assertTrue(qc.startswith(de[:de.index('parse_covariates <-')]))

  self.assertEqual(qc[qc.index("publication_identity <-"):qc.index("main <- function()")],de[de.index("publication_identity <-"):de.index("main <- function()")])
