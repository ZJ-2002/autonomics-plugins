"""Permanent independent research MRlap source/ABI checks; no method runs."""
import json
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest

from tools.check_frozen_genetic import check_family

ROOT = Path(__file__).resolve().parents[1]
FAMILY = ROOT/'research-adapters/mrlap-contract'


class MRlapContractTransportTests(unittest.TestCase):
    def test_release_inventory_and_new_source_index_bind_exact_adapter_bytes(self):
        inventory=json.loads((ROOT/'catalog/release-lock.json').read_bytes())
        rows=[r for r in inventory['families'] if r['directory']=='research-adapters/mrlap-contract']
        self.assertEqual(len(rows),1);record=rows[0]
        self.assertFalse(record['scientific_certified']);self.assertFalse(record['auto_enable'])
        for row in record['files']:
            raw=(FAMILY/row['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
            self.assertEqual(len(raw),row['bytes'])
        index=json.loads((ROOT/'provenance/source-index.json').read_bytes())
        rows=[r for r in index['research_adapters'] if r['directory']=='research-adapters/mrlap-contract']
        self.assertEqual(len(rows),1);original=rows[0]
        lock=json.loads((FAMILY/'component-source.json').read_bytes())
        self.assertEqual(original['revision'],lock['source_commit'])
        self.assertFalse(original['scientific_certified']);self.assertFalse(original['auto_enable'])
        self.assertEqual({r['path'] for r in original['files']},set(lock['imported_files']))
        for row in original['files']:
            raw=(FAMILY/row['path']).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),row['sha256'])
            self.assertEqual(len(raw),row['bytes'])
            self.assertEqual(hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest(),row['git_blob'])

    def test_exact_independent_kind_ports_and_source_transport(self):
        report=check_family(FAMILY)
        self.assertEqual(report['kinds'], ['mrlap_official_frozen'])
        self.assertFalse(report['scientific_authorization']);self.assertFalse(report['auto_enable'])
        manifest=tomllib.loads((FAMILY/'manifest.toml').read_text())
        node=manifest['nodes'][0]
        self.assertEqual(len(node['ports']['inputs']),10)
        self.assertEqual([p['path'] for p in node['ports']['outputs']],
            ['estimates.tsv','retention.tsv','audit.json','result.rds','diagnostics.tar'])
        self.assertEqual(manifest['panels'][0]['mount'], '/panels/mrlap_ldsc')
        self.assertEqual(node['resources']['memory'], '8Gi')
        self.assertEqual(node['resources']['pull_policy'], 'never')
        canonical=tomllib.loads((ROOT/'plugins/mrlap/manifest.toml').read_text())
        self.assertEqual(canonical['nodes'][0]['kind'],'mrlap_official')
        self.assertEqual(len(canonical['nodes'][0]['ports']['inputs']),3)
        self.assertEqual(canonical['nodes'][0]['ports']['outputs'][2]['path'],'mrlap_result.txt')
        self.assertNotEqual(manifest['image']['reference'],canonical['image']['reference'])

    def test_generated_shell_preserves_ten_inputs_and_five_outputs(self):
        wrapper=(FAMILY/'scripts/run-mrlap.sh').read_text()
        self.assertEqual(set(re.findall(r'\$\{AUTONOMICS_INPUT(\d+):\?\}',wrapper)),set(map(str,range(10))))
        self.assertEqual(set(re.findall(r'\$\{AUTONOMICS_OUTPUT(\d+):\?\}',wrapper)),set(map(str,range(5))))
        self.assertIn('MRlap::MRlap',wrapper)
        result=subprocess.run(['/bin/sh','-n',str(FAMILY/'scripts/run-mrlap.sh')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_actual_base_r_protocol_and_parent_abi_refuses_both_mismatches(self):
        r=shutil.which('Rscript')
        if r is None:self.skipTest('Rscript absent; actual protocol predicate not executed')
        code=('source(commandArgs(TRUE)[1]);stopifnot('
            'mrlap_parent_protocol_matches("4.2.1","4.2.1"),'
            'mrlap_parent_protocol_matches("4.3.2","4.3.2"),'
            '!mrlap_parent_protocol_matches("4.3.2","4.2.1"),'
            '!mrlap_parent_protocol_matches("4.2.1","4.3.2"),'
            '!mrlap_parent_protocol_matches("4.3.3","4.3.3"));cat("PARENT_ABI_CHECKED")')
        result=subprocess.run([r,'--vanilla','-e',code,str(FAMILY/'scripts/mrlap.R')],
            capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PARENT_ABI_CHECKED',result.stdout)

    def test_rooted_renderer_argument_cannot_redirect_to_a_different_family(self):
        with tempfile.TemporaryDirectory() as temporary:
            family=Path(temporary)/'mrlap-contract';shutil.copytree(FAMILY,family)
            path=family/'component-source.json';lock=json.loads(path.read_bytes())
            lock['programs']['scripts/run-mrlap.sh']['argument']='study_plugins/mr-contract'
            path.write_text(json.dumps(lock))
            with self.assertRaisesRegex(ValueError,'complete renderer'):check_family(family)

    def test_missing_or_modified_method_component_is_never_repaired_or_accepted(self):
        with tempfile.TemporaryDirectory() as temporary:
            family=Path(temporary)/'mrlap-contract';shutil.copytree(FAMILY,family)
            component=family/'components/study_plugins/mrlap-contract/scripts/mrlap.R'
            wrapper=family/'scripts/run-mrlap.sh';before=wrapper.read_bytes()
            component.write_bytes(component.read_bytes()+b'\n# CHANGED\n')
            with self.assertRaisesRegex(ValueError,'source identity differs'):check_family(family)
            self.assertEqual(wrapper.read_bytes(),before)


if __name__ == '__main__':unittest.main()
