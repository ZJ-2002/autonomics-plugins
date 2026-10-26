"""Self-cleaning SYN input/import tests. Not full-project/container acceptance."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest import mock
from types import SimpleNamespace

from tools import build_frozen_project_verifier_dag as graph

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'plugins/frozen-project-verifier/scripts/verify.py'
spec=importlib.util.spec_from_file_location('fixed_verifier_tests',SCRIPT)
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)


def fixture(directory):
    """Only three tiny SYN source modules, never original scientific payload."""
    root=directory/'SYN_ROOT';root.mkdir();(root/'02_EXECUTION').mkdir();(root/'03_AUDIT').mkdir()
    (root/verifier.ANCHOR).write_bytes(b'SYN anchor')
    (root/'non-anchor.txt').write_bytes(b'LOCKED')
    sources={
        'verify_g0_v432': "import sys\nfrom pathlib import Path\ndef audit(root):\n sys.path.insert(0,str(root/'02_EXECUTION'))\n from validate_runtime import audit as other\n return other(root)\n",
        'validate_runtime': "def audit(root):\n from followup_contracts import checked\n return checked(root)\n",
        'followup_contracts': "from pathlib import Path\ndef checked(root):\n import fractions\n import datetime\n return dict(passed=(root/'non-anchor.txt').read_bytes()==b'LOCKED',read_only=True,all_project_scientific_gates_passed=False,scientific_truth_certified=False,scientific_results_computed=False,errors=[],hash_checks=1,unique_file_hashes=1)\n",
    }
    for name,source in sources.items():(root/'02_EXECUTION'/(name+'.py')).write_text(source)
    pins={name:dict(sha256=hashlib.sha256((root/name).read_bytes()).hexdigest(),bytes=(root/name).stat().st_size)
          for name in [verifier.ANCHOR,*['02_EXECUTION/'+n+'.py' for n in verifier.MODULES]]}
    manifest=dict(version='4.3.2',scope='CURRENT_MINIMUM_G0_FROZEN_WORKING_COPY_BYTES',
        files=[dict(path=n,sha256=p['sha256'],size_bytes=p['bytes']) for n,p in pins.items()])
    (root/verifier.MANIFEST).write_bytes(verifier.canonical(manifest))
    pins[verifier.MANIFEST]={'sha256':hashlib.sha256((root/verifier.MANIFEST).read_bytes()).hexdigest()}
    control=directory/'CONTROL';control.mkdir(mode=0o700)
    registration=verifier.register(root,pins)
    binding=control/'registration.json';binding.write_bytes(verifier.canonical(registration)+b'\n');binding.chmod(0o600)
    staged=directory/'STAGED';staged.mkdir()
    anchor=staged/'anchor';anchor.symlink_to(root/verifier.ANCHOR)
    registered=staged/'registration';registered.symlink_to(binding)
    return root,pins,registration,binding,anchor,registered


def execute(root,pins):
    code="""import importlib.util,json,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('under_test',sys.argv[1]);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
result=module.execute_sources(Path(sys.argv[2]),json.loads(sys.argv[3]));print(json.dumps(result))
"""
    return subprocess.run([sys.executable,'-I','-S','-B','-c',code,str(SCRIPT),str(root),json.dumps(pins)],capture_output=True)


class FrozenProjectVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        self.root,self.pins,self.registration,self.binding,self.anchor,self.registered=fixture(self.directory)
        self.sha=hashlib.sha256(self.binding.read_bytes()).hexdigest()
    def test_actual_source_loader_runs_three_modules_and_rechecks_non_anchor(self):
        first=execute(self.root,self.pins);self.assertEqual(first.returncode,0,first.stderr.decode())
        self.assertTrue(json.loads(first.stdout)['passed'])
        (self.root/'non-anchor.txt').write_bytes(b'BROKEN')
        second=execute(self.root,self.pins);self.assertEqual(second.returncode,0,second.stderr.decode())
        self.assertFalse(json.loads(second.stdout)['passed'])
        self.assertEqual((self.root/verifier.ANCHOR).read_bytes(),b'SYN anchor')
    def test_real_pyc_and_project_stdlib_shadows_are_never_imported(self):
        marker=self.directory/'POISON_EXECUTED'
        poison="from pathlib import Path\nPath("+repr(str(marker))+").write_text('bad')\nraise RuntimeError('poison')\n"
        import py_compile
        for name in ['validate_runtime','followup_contracts']:
            source=self.directory/(name+'.py');source.write_text(poison)
            py_compile.compile(str(source),cfile=str(self.root/'02_EXECUTION'/(name+'.pyc')),doraise=True)
            cache=self.root/'02_EXECUTION/__pycache__';cache.mkdir(exist_ok=True)
            py_compile.compile(str(source),cfile=str(cache/(name+'.'+sys.implementation.cache_tag+'.pyc')),doraise=True)
        for name in ['fractions','datetime']:(self.root/'02_EXECUTION'/(name+'.py')).write_text(poison)
        actual=execute(self.root,self.pins);self.assertEqual(actual.returncode,0,actual.stderr.decode())
        self.assertTrue(json.loads(actual.stdout)['passed']);self.assertFalse(marker.exists())
    def test_changed_source_is_refused_before_any_execution(self):
        marker=self.directory/'SOURCE_EXECUTED'
        (self.root/'02_EXECUTION/followup_contracts.py').write_text("from pathlib import Path\nPath("+repr(str(marker))+").touch()\n")
        actual=execute(self.root,self.pins);self.assertNotEqual(actual.returncode,0);self.assertFalse(marker.exists())
    def test_nonisolated_source_loader_refuses(self):
        with self.assertRaises(ValueError):verifier.execute_sources(self.root,self.pins)
    def test_registration_binds_real_root_identity_and_all_three_sources(self):
        root,value,_=verifier.registered_root(self.anchor,self.registered,self.sha,self.pins)
        self.assertEqual(root,self.root);self.assertEqual(value,self.registration)
        self.assertEqual(len([n for n in value['pins'] if n.endswith('.py')]),3)
        self.assertFalse(value['scientific_authorization']);self.assertFalse(value['G0'])
    def test_btrfs_device_changes_preserve_identity_but_filesystem_and_subvolume_changes_refuse(self):
        original_fstat,original_stat=os.fstat,os.stat
        state=dict(device=56,filesystem=b'A'*16,subvolume=b'B'*16,tree=257)
        def changed(s):
            values={n:getattr(s,n) for n in dir(s) if n.startswith('st_')}
            values['st_dev']=state['device'];return SimpleNamespace(**values)
        def ioctl(fd,request,buffer,mutate):
            self.assertTrue(mutate)
            if request==0x8400941f:buffer[16:32]=state['filesystem']
            elif request==0x81f8943c:
                import struct
                struct.pack_into('=Q',buffer,0,state['tree']);buffer[296:312]=state['subvolume']
            else:self.fail('unexpected filesystem query')
        with mock.patch.object(verifier.fcntl,'ioctl',side_effect=ioctl), \
             mock.patch.object(verifier.os,'fstat',side_effect=lambda fd:changed(original_fstat(fd))), \
             mock.patch.object(verifier.os,'stat',side_effect=lambda *a,**kw:changed(original_stat(*a,**kw))):
            initial=verifier.identity(self.root)
            self.registration['root_identity']=initial
            self.binding.write_bytes(verifier.canonical(self.registration))
            sha=hashlib.sha256(self.binding.read_bytes()).hexdigest()
            state['device']=31
            self.assertEqual(verifier.identity(self.root),initial)
            verifier.registered_root(self.anchor,self.registered,sha,self.pins)
            for key,value in [('filesystem',b'C'*16),('subvolume',b'D'*16),('tree',258)]:
                old=state[key];state[key]=value
                with self.assertRaises(ValueError):verifier.registered_root(self.anchor,self.registered,sha,self.pins)
                state[key]=old
    def test_legacy_registration_is_not_upgraded_and_identity_failures_are_not_defaults(self):
        old=copy.deepcopy(self.registration);old['schema']='FROZEN_READONLY_PROJECT_REGISTRATION_V1'
        self.binding.write_bytes(verifier.canonical(old));sha=hashlib.sha256(self.binding.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):verifier.registered_root(self.anchor,self.registered,sha,self.pins)
        with mock.patch.object(verifier.fcntl,'ioctl',side_effect=PermissionError('not permitted')):
            with self.assertRaises(PermissionError):verifier.identity(self.root)
        with mock.patch.object(verifier.fcntl,'ioctl',return_value=0):
            with self.assertRaises(ValueError):verifier.identity(self.root)
    def test_copies_cannot_claim_whole_directory_bind(self):
        copied=self.directory/'copied';copied.write_bytes((self.root/verifier.ANCHOR).read_bytes())
        with self.assertRaises(ValueError):verifier.registered_root(copied,self.registered,self.sha,self.pins)
    def test_missing_wrong_or_self_reported_registration_sha_refuses(self):
        for value in ['', 'UNREGISTERED', 'a'*64]:
            with self.assertRaises(ValueError):verifier.registered_root(self.anchor,self.registered,value,self.pins)
    def test_registration_mode_hardlink_and_wrong_parent_permissions_refuse(self):
        self.binding.chmod(0o644)
        with self.assertRaises(ValueError):verifier.registered_root(self.anchor,self.registered,self.sha,self.pins)
        self.binding.chmod(0o600);extra=self.binding.parent/'extra';os.link(self.binding,extra)
        with self.assertRaises(ValueError):verifier.registered_root(self.anchor,self.registered,self.sha,self.pins)
        extra.unlink();self.binding.parent.chmod(0o755)
        with self.assertRaises(ValueError):verifier.registered_root(self.anchor,self.registered,self.sha,self.pins)
    def test_control_parent_cannot_expose_other_files_or_payload(self):
        (self.binding.parent/'unexpected').write_text('SYN unrelated metadata')
        with self.assertRaises(ValueError):verifier.registered_root(self.anchor,self.registered,self.sha,self.pins)
    def test_root_identity_and_scope_drift_refuse_even_when_json_hash_is_supplied(self):
        for key,value in [('root_identity',dict(self.registration['root_identity'],inode=0)),('G0',True),('command','python')]:
            bad=copy.deepcopy(self.registration);bad[key]=value;self.binding.write_bytes(verifier.canonical(bad))
            changed=hashlib.sha256(self.binding.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):verifier.registered_root(self.anchor,self.registered,changed,self.pins)
    def test_alias_registration_and_wrong_anchor_root_refuse(self):
        alias=self.directory/'ALIAS';alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError):verifier.register(alias,self.pins)
        wrong=self.directory/'wrong-anchor';wrong.symlink_to(self.root/'non-anchor.txt')
        with self.assertRaises(ValueError):verifier.registered_root(wrong,self.registered,self.sha,self.pins)
    def test_kernel_mount_proof_requires_ro_and_no_rw_descendant(self):
        root=Path('/approved/root')
        ro='1 0 0:1 / /approved/root ro,nosuid - ext4 /dev/x rw\n'
        verifier.require_readonly_mount(root,ro)
        for value in [ro.replace('ro,nosuid','rw,nosuid'),'1 0 0:1 / /another ro - ext4 /dev/x rw\n',
                      ro+'2 1 0:2 / /approved/root/nested rw - tmpfs tmpfs rw\n']:
            with self.assertRaises(ValueError):verifier.require_readonly_mount(root,value)
    def test_original_failure_stays_failed_and_no_original_g0_status_is_published(self):
        actual=json.loads(execute(self.root,self.pins).stdout);actual['passed']=False
        actual['status']='G0_V432_MINIMUM_COMPLETE'
        report=verifier.technical_report(actual,self.registration,self.sha,1)
        self.assertFalse(report['technical_verification_passed'])
        self.assertNotIn('status',report)
        for name in ['G0','scientific_gate_granted','human_signature','scientific_authorization']:self.assertIs(report[name],False)
        bad=copy.deepcopy(actual);bad['scientific_results_computed']=True
        with self.assertRaises(ValueError):verifier.technical_report(bad,self.registration,self.sha,1)
    def test_duplicate_json_and_extra_scientific_scope_refuse(self):
        with self.assertRaises(ValueError):verifier.strict_json(b'{"root":1,"root":2}')
        with self.assertRaises(ValueError):verifier.strict_json(b'{"value":NaN}')
    def test_manifest_declares_server_never_policy_and_fixed_two_port_abi(self):
        manifest=tomllib.loads((SCRIPT.parent.parent/'manifest.toml').read_text())
        node=manifest['nodes'][0]
        self.assertEqual(node['cache_policy'],'never');self.assertEqual(node['stage_in_mode'],'symlink')
        self.assertIs(node['canonical_input_sources'],True)
        self.assertEqual(len(node['ports']['inputs']),2);self.assertEqual(len(node['ports']['outputs']),1)
        self.assertEqual(node['resources']['network'],'isolated');self.assertTrue(node['resources']['read_only_rootfs'])
        self.assertEqual(node['resources']['pull_policy'],'never');self.assertNotIn('params',node)
        self.assertEqual(node['command']['env']['EXPECTED_OPERATOR_REGISTRATION_SHA256'],'UNREGISTERED')
    def test_fixed_agent_graph_cannot_redirect_current_root_or_inject_code(self):
        request=graph.build('vfs:///research/verification-control/current/registration.json')
        self.assertIn('vfs:///research/current/README_START_HERE.md',request['script'])
        self.assertIn('frozen-project-verifier/frozen_v432_readonly_full_verify',request['script'])
        self.assertEqual(request['script'].count('node('),3);self.assertEqual(request['script'].count('edge('),2)
        for value in ['vfs:///tmp/registration.json','vfs:///research/verification-control/../registration.json','file:///root']:
            with self.assertRaises(ValueError):graph.build(value)
        with self.assertRaises(ValueError):graph.build('vfs:///research/verification-control/current/registration.json',prefix='x;exec()')


if __name__=='__main__':unittest.main()
