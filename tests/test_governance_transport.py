"""Offline source/manifest ABI checks; no native/container/R or clinical read."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from tools.catalog import verify_import_detailed
from tools.check_governance_transport import ROOT, FAMILIES, NORMALIZED, IMAGE, IMAGE_SHA, check, check_family

class GovernanceTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.family=Path(self.temp.name)/NORMALIZED;shutil.copytree(ROOT/'research-adapters'/NORMALIZED,self.family)
    def test_exact11_optin_families18_unique_kinds_canonical_scope_unchanged(self):
        report=check();self.assertEqual(len(report['selected_families']),11);self.assertEqual(report['new_unique_kinds'],18)
        self.assertEqual((report['canonical_families'],report['canonical_kinds']),(31,62))
        with_a=(ROOT/'plugins/twosamplemr-v432-a/manifest.toml').is_file()
        with_lm=(ROOT/'plugins/r-stats-lm/manifest.toml').is_file()
        with_verifier=(ROOT/'plugins/frozen-project-verifier/manifest.toml').is_file()
        with_qc=(ROOT/'plugins/rnaseq-qc/manifest.toml').is_file()
        if with_qc:self.assertEqual([n['kind'] for n in tomllib.loads((ROOT/'plugins/rnaseq-qc/manifest.toml').read_text())['nodes']],['rnaseq_prestart_qc'])
        with_dds=any(n['kind']=='deseq2_dds_diagnostics' for n in tomllib.loads((ROOT/'plugins/deseq2/manifest.toml').read_text())['nodes'])
        self.assertEqual(report['current_family_extensions'],{'deseq2':['deseq2_dds_diagnostics']} if with_dds else {})
        self.assertEqual((report['current_canonical_families'],report['current_canonical_kinds']),
            (33+int(with_a)+int(with_lm)+int(with_verifier)+int(with_qc),66+int(with_a)+int(with_lm)+int(with_verifier)+int(with_dds)+int(with_qc)))
        self.assertEqual(report['current_official_method_additions'],['r-stats-lm'] if with_lm else [])
        self.assertEqual(report['current_technical_additions'],(['frozen-project-verifier'] if with_verifier else [])+(['rnaseq-qc'] if with_qc else []))
        self.assertEqual(report['current_legacy_additions'],['bulk-limma-normalized','frozen-b-project']+
            (['twosamplemr-v432-a'] if with_a else []))
        self.assertFalse(report['auto_enable']);self.assertFalse(report['loaded_worker_registration_verified'])
        self.assertFalse(report['native_loader_construct_verified'])
    def test_original_index_is_preserved_and_current_sources_require_git_evolution(self):
        path=ROOT/'provenance/p0-load-source-imports-20261012.json';before=path.read_bytes();index=json.loads(before)
        self.assertFalse(index['original_source_index_rewritten'])
        report=verify_import_detailed(ROOT)
        self.assertGreaterEqual(report['imported_files_verified'],sum(len(row['files']) for row in index['research_adapters']))
        self.assertTrue(report['git_object_verification_required_for_evolution'])
        self.assertFalse(report['scientific_method_certified']);self.assertFalse(report['auto_enable'])
        self.assertEqual(path.read_bytes(),before)
    def test_normalized_fixed_ports_vanilla_copy_and_all8_installed_source_shas(self):
        self.assertTrue(check_family(self.family,normalized=True)['normalized_eight_source_hashes_checked'])
        manifest=tomllib.loads((self.family/'manifest.toml').read_text());self.assertEqual(manifest['image']['reference'],IMAGE)
        self.assertEqual([len(n['ports']['inputs']) for n in manifest['nodes']],[5,6])
        self.assertEqual([[o['path'] for o in n['ports']['outputs']] for n in manifest['nodes']],[['audit.json'],['results.tsv','audit.json','official.rds']])
        lock=json.loads((self.family/'component-source.json').read_bytes());self.assertEqual(len(lock['image_sources']),8)
        self.assertEqual({p:r['sha256'] for p,r in lock['image_sources'].items()},IMAGE_SHA)
    def test_unpinned_wrong_digest_wrong_ports_or_unsafe_resource_mutations_refused(self):
        path=self.family/'manifest.toml';original=path.read_text()
        mutations=[original.replace(IMAGE,IMAGE.split('@')[0]+':latest'),original.replace(IMAGE,IMAGE.replace('6932','0000',1)),
            original.replace('path="results.tsv",format="tsv"','path="WRONG.tsv",format="tsv"'),
            original.replace('interpreter = "/opt/b-bulk/bin/Rscript-vanilla"','interpreter = "Rscript"'),
            original.replace('read_only_rootfs = true','read_only_rootfs = false'),original.replace('pull_policy = "never"','pull_policy = "always"'),
            original.replace('network = "isolated"','network = "host"')]
        for body in mutations:
            path.write_text(body)
            with self.assertRaises(ValueError):check_family(self.family,normalized=True)
        path.write_text(original)
    def test_historical_full_syn_caps_or_rds_format_cannot_replace_micro_manifest(self):
        path=self.family/'manifest.toml';original=path.read_text()
        substitutions=[('cpus = 1.0','cpus = 2.0'),('memory = "1Gi"','memory = "2Gi"'),
            ('pids_limit = 64','pids_limit = 128'),('timeout_secs = 1200','timeout_secs = 3600'),
            ('format="r_rds"','format="rds"')]
        for old,new in substitutions:
            self.assertIn(old,original)
            with self.subTest(field=old):
                path.write_text(original.replace(old,new))
                with self.assertRaises(ValueError):check_family(self.family,normalized=True)
        path.write_text(original)

    def test_changed_measured_source_or_removed_hash_cannot_be_repaired_or_accepted(self):
        path=self.family/'image-source/SOURCE_LOCK.json';before=path.read_bytes();path.write_bytes(before+b'\n')
        with self.assertRaisesRegex(ValueError,'image-source bytes'):check_family(self.family,normalized=True)
        path.write_bytes(before);lockfile=self.family/'component-source.json';lock=json.loads(lockfile.read_bytes());lock['image_sources'].pop('/opt/b-bulk-build/probe-toolchain.R');lockfile.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError,'all8'):check_family(self.family,normalized=True)
    def test_source_or_science_autoenable_promotion_is_refused(self):
        path=self.family/'component-source.json';original=json.loads(path.read_bytes())
        for field in ['auto_enable','scientific_authorization','method_acceptance_verified','source_distribution_provenance_qualified','full_method_qualification_verified','loaded_worker_registration_verified']:
            changed=copy.deepcopy(original);changed[field]=True;path.write_text(json.dumps(changed))
            with self.subTest(field=field),self.assertRaises(ValueError):check_family(self.family,normalized=True)

if __name__=='__main__':unittest.main()
