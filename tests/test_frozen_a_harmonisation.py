import json
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest
from unittest import mock

from tools import prove_frozen_a_harmonisation as proof
from tools.prove_frozen_a_package_identity import FUNCTION_IDENTITY_R


ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT / 'research-adapters/frozen-a-harmonisation'
SCRIPT = FAMILY / 'scripts/harmonise.R'
CONTRACT = json.loads((FAMILY / 'contracts/source-lock.json').read_text())


class FrozenAHarmonisationTests(unittest.TestCase):
    def run_r(self, program):
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ)
            library = Path.home() / 'R/library'
            if library.is_dir():
                environment['R_LIBS_USER'] = str(library) + os.pathsep + environment.get('R_LIBS_USER', '')
            result = subprocess.run(['Rscript', '--vanilla', '-e',
                'args<-commandArgs(TRUE);source(args[1],local=environment());root<-args[2];\n' + program,
                str(SCRIPT), directory], capture_output=True, text=True, timeout=30, env=environment)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def io_fixture(self):
        return '''inputs<-file.path(root,paste0("input",0:5));outputs<-file.path(root,OUTPUT_NAMES)
for(filename in inputs) writeLines("toy input",filename)
do.call(Sys.setenv,setNames(as.list(c(inputs,outputs)),c(paste0("AUTONOMICS_INPUT",0:5),paste0("AUTONOMICS_OUTPUT",0:4))))
run_official_harmonisation<-function(inputs,paths) {
 for(i in seq_along(paths)) writeLines(paste("toy output",i),paths[i])
}
'''

    def test_manifest_is_zero_parameter_six_input_five_output_official_scope(self):
        manifest = tomllib.loads((FAMILY / 'manifest.toml').read_text())
        self.assertEqual(manifest['plugin_name'], 'frozen-a-harmonisation')
        self.assertEqual(len(manifest['nodes']), 1)
        node = manifest['nodes'][0]
        self.assertEqual(node['kind'], 'frozen_a_v432_harmonisation')
        self.assertNotIn('params', node)
        self.assertEqual((len(node['ports']['inputs']), len(node['ports']['outputs'])), (6, 5))
        self.assertEqual(node['command'], dict(interpreter='Rscript', script_file='scripts/harmonise.R'))
        self.assertEqual(manifest['image']['reference'],
            'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d')
        self.assertEqual(node['resources']['pull_policy'], 'never')
        self.assertTrue(node['resources']['read_only_rootfs'])

    def test_contract_pins_all_six_inputs_and_original_three_outputs(self):
        self.assertEqual(CONTRACT['schema'], 'FROZEN_V432_A_HARMONISATION_SOURCE_CONTRACT_V1')
        self.assertEqual([item['port'] for item in CONTRACT['inputs']], list(range(6)))
        self.assertEqual([item['name'] for item in CONTRACT['inputs']], ['A_LD_CLUMPED_INSTRUMENTS.tsv',
            'A_OUTCOME_MATCHES.tsv', 'A_ANALYSIS_CONFIG.json', 'G0_V432_CERTIFICATE.json',
            'R_DEPENDENCY_LOCK.tsv', 'g0_v432_methods.R'])
        source = SCRIPT.read_text()
        for item in CONTRACT['inputs']:
            self.assertIn(item['sha256'], source)
        for digest in CONTRACT['existing_expected_outputs'].values():
            self.assertIn(digest, source)
        self.assertEqual(CONTRACT['qualify_A_block_bytes'], 2172)
        self.assertIn(CONTRACT['qualify_A_block_sha256'], source)
        self.assertFalse(CONTRACT['scientific_authorization_granted'])
        self.assertFalse(CONTRACT['g0_granted'])
        self.assertNotIn('SYNTHETIC_METHOD_TEST', source)
        self.assertIn(FUNCTION_IDENTITY_R, source)
        self.assertIsNone(CONTRACT['observed_container_TwoSampleMR_RemoteSha'])
        self.assertEqual(CONTRACT['package_namespace_function_count'], 171)
        self.assertIn(CONTRACT['package_namespace_aggregate_sha256'], source)

    def test_nonfrozen_hashes_have_no_production_test_bypass(self):
        self.run_r('''check_frozen_inputs(FROZEN_INPUT_SHA)
for(value in list(character(),FROZEN_INPUT_SHA[-1],rep("a",6),rev(FROZEN_INPUT_SHA))) {
 result<-tryCatch({check_frozen_inputs(value);NULL},error=identity)
 stopifnot(inherits(result,"error"))
}
''')

    def test_branch_extraction_rejects_incomplete_or_modified_source(self):
        self.run_r('''for(value in c("",'} else if(mode=="qualify-A") {\\nchanged\\n} else if(mode=="test") {',
 '} else if(mode=="qualify-A") {\\nmissing terminator')) {
 result<-tryCatch({extract_qualify_a(value);NULL},error=identity)
 stopifnot(inherits(result,"error"))
}
''')

    def test_envelope_rejects_boundaries_and_weak_inputs_without_reselection(self):
        self.run_r('''cfg<-list(palindromic_EAF_excluded_interval=c(.42,.58),
 palindromic_frequency_difference_max=.1,M_source_INFO_min=.8,F_reference_min=10)
h<-data.frame(SNP=paste0("synthetic",1:39),mr_keep=TRUE,action=2,remove=FALSE,ambiguous=FALSE,
 palindromic=FALSE,eligibility_reason="QUALIFIED",F_exposure=20,source_INFO=.9,
 frequency_difference=0,eaf.exposure=.1,eaf.outcome=.1)
check_current_envelope(h,cfg)
for(field in c("eaf.exposure","eaf.outcome","F_exposure","source_INFO","frequency_difference")) {
 values<-switch(field,eaf.exposure=c(.42,.58),eaf.outcome=c(.42,.58),F_exposure=9.9,
  source_INFO=.79,frequency_difference=.10001)
 for(value in values) {
  changed<-h;changed$palindromic[1]<-TRUE;changed[[field]][1]<-value
  preserved<-changed
  result<-tryCatch({check_current_envelope(changed,cfg);NULL},error=identity)
  stopifnot(inherits(result,"error"),identical(changed,preserved))
 }
}
''')

    def test_existing_output_is_never_truncated(self):
        self.run_r(self.io_fixture() + '''writeLines("old protected log",outputs[5])
before<-readBin(outputs[5],"raw",n=1000)
result<-tryCatch({execute_harmonisation();NULL},error=identity)
stopifnot(inherits(result,"error"),identical(readBin(outputs[5],"raw",n=1000),before),
 !any(file.exists(outputs[1:4])))
''')

    def test_publication_checks_all_five_ports_and_cleans_owned_staging(self):
        self.run_r(self.io_fixture() + '''execute_harmonisation()
stopifnot(all(file.exists(outputs)),all(file.info(outputs)$size>0),
 length(list.files(root,all.files=TRUE,pattern="stage",no..=TRUE))==0L)
for(i in seq_along(outputs)) stopifnot(identical(readLines(outputs[i]),paste("toy output",i)))
''')

    def test_foreign_post_link_replacement_is_preserved_and_owned_ports_rollback(self):
        self.run_r(self.io_fixture() + '''file.link<-function(from,to) {
 result<-base::file.link(from,to)
 if(basename(to)==OUTPUT_NAMES[2]) {unlink(to);writeLines("foreign replacement",to)}
 result
}
result<-tryCatch({execute_harmonisation();NULL},error=identity)
stopifnot(inherits(result,"error"),identical(readLines(outputs[2]),"foreign replacement"),
 !any(file.exists(outputs[c(1,3,4)])),file.exists(outputs[5]),
 any(grepl("BLOCKED:",readLines(outputs[5]),fixed=TRUE)))
''')

    def test_independent_driver_requires_unique_ordered_qualification_markers(self):
        first = '} else if(mode=="qualify-A") {\n'
        last = '\n} else if(mode=="test") {'
        block = '  toy_original_text <- TRUE'
        with mock.patch.object(proof, 'BLOCK_SHA', hashlib.sha256(block.encode()).hexdigest()):
            self.assertEqual(proof.qualification_block('prefix\n' + first + block + last + 'suffix'), block)
            for text in [first + block, block + last, first + first + block + last,
                         first + block + last + last, last + first + block]:
                with self.assertRaises(RuntimeError):
                    proof.qualification_block(text)

    def test_generic_harmonise_action_documentation_matches_official_meaning(self):
        manifest = tomllib.loads((ROOT / 'plugins/twosamplemr/manifest.toml').read_text())
        node = next(item for item in manifest['nodes'] if item['kind'] == 'twosamplemr_harmonise')
        doc = node['params']['harmonise_action']['doc'].lower()
        for text in ['forward', 'frequenc', 'all palindromic']:
            self.assertIn(text, doc)
        for text in ['1 keep', '2 flip', 'drop discordants']:
            self.assertNotIn(text, doc)

    def namespace_fixture(self):
        return '''fixture<-new.env(parent=baseenv())
for(i in 1:171) assign(sprintf("toy_%03d",i),function(value=1) value+1,envir=fixture)
asNamespace<-function(package) {stopifnot(identical(package,"TwoSampleMR"));fixture}
original<-namespace_function_identity()
EXPECTED_FUNCTION_AGGREGATE<-original$aggregate_sha256
check_namespace_identity(original)
'''

    def test_actual_function_body_change_is_rejected_by_namespace_identity(self):
        self.run_r(self.namespace_fixture() + '''fixture$toy_001<-function(value=1) value+2
changed<-namespace_function_identity()
stopifnot(changed$function_count==171L,changed$functions$toy_001!=original$functions$toy_001)
result<-tryCatch({check_namespace_identity(changed);NULL},error=identity)
stopifnot(inherits(result,"error"))
''')

    def test_missing_actual_function_is_rejected_by_namespace_identity(self):
        self.run_r(self.namespace_fixture() + '''rm("toy_001",envir=fixture)
changed<-namespace_function_identity()
stopifnot(changed$function_count==170L)
result<-tryCatch({check_namespace_identity(changed);NULL},error=identity)
stopifnot(inherits(result,"error"))
''')


if __name__ == '__main__':
    unittest.main()
