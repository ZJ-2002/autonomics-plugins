"""Fixed read-only verifier. No shell, fit, approval, or research ledger writes."""
import os
import sys

# container_command inserts this script before its argv. Reenter explicitly;
# putting -I after the script would only pass a meaningless script argument.
if __name__ == '__main__' and not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode):
    os.execv(sys.executable, [sys.executable, '-I', '-S', '-B', __file__])

import hashlib
import errno
import fcntl
import importlib.abc
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import re
import stat
import struct
import time
import uuid

SCHEMA = 'FROZEN_READONLY_PROJECT_REGISTRATION_V2'
SCOPE = 'READONLY_CURRENT_PROJECT_BYTES_AND_REGISTRY_STRUCTURE_ONLY'
PROJECT_URI = '/research/current'
MANIFEST = '03_AUDIT/G0_RUNTIME_MANIFEST.json'
ANCHOR = 'README_START_HERE.md'
PINS = {
    MANIFEST: {'sha256':'1bf0699bffde16a419a308d66654610cdca3170aa3fab2b8b50d93656e80e2a5'},
    ANCHOR: {'sha256':'e4d913813d921a0e16573c11d55be89d579ce46fd7edd8d3aa9e78b55045aad7','bytes':3108},
    '02_EXECUTION/verify_g0_v432.py': {'sha256':'1a928da15243316facd63358c9f33dbc69f399de41b1f7b8f341f05c647a1073','bytes':8787},
    '02_EXECUTION/validate_runtime.py': {'sha256':'bca50e7aaa4f53d2b5ea25479a2aef8e4a75fc18787a7f6f9f43c0ba40e988ad','bytes':8507},
    '02_EXECUTION/followup_contracts.py': {'sha256':'0eb2b03d7d000232f49b444bdc1d9091efd15dfd56dd3f260ddc9011c035120e','bytes':9094},
}
MODULES = ['verify_g0_v432','validate_runtime','followup_contracts']


def require(ok, code):
    if not ok:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'DUPLICATE_JSON_KEY')
            out[key] = value
        return out
    def bad(_):
        raise ValueError('NONFINITE_JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)


def exact_path(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve(strict=True) == path and
            not any(p.is_symlink() for p in [path,*path.parents]), 'NONCANONICAL_PATH')
    return path


def identity(path):
    # Btrfs anonymous st_dev numbers change across mounts/boots. Capture the
    # actual filesystem and subvolume from the open directory, not a pathname
    # declaration or an inferred upgrade of a legacy registration. The ioctl
    # layouts match linux/btrfs.h and the engine's research_validation_identity.
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd)
        fs = bytearray(1024)
        try:
            fcntl.ioctl(fd, 0x8400941f, fs, True)
        except OSError as error:
            if error.errno not in {errno.ENOTTY, errno.EOPNOTSUPP, errno.EINVAL}:
                raise
            boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
            require(re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot), 'KERNEL_BOOT_ID_REQUIRED')
            filesystem = dict(kind='BOOT_LOCAL_DEVICE_V1', device=s.st_dev, boot_id=boot)
        else:
            sub = bytearray(504)
            fcntl.ioctl(fd, 0x81f8943c, sub, True)
            fs_uuid = bytes(fs[16:32]);sub_uuid = bytes(sub[296:312])
            tree = struct.unpack_from('=Q', sub)[0]
            require(any(fs_uuid) and tree >= 5 and (tree == 5 or any(sub_uuid)), 'BTRFS_STABLE_ID_REQUIRED')
            filesystem = dict(kind='BTRFS_UUID_SUBVOLUME_V1', filesystem_uuid=str(uuid.UUID(bytes=fs_uuid)),
                subvolume_uuid=str(uuid.UUID(bytes=sub_uuid)), tree_id=tree)
        named = os.stat(path, follow_symlinks=False)
        require((s.st_dev,s.st_ino,s.st_uid,s.st_gid,s.st_mode,s.st_mtime_ns,s.st_ctime_ns) ==
                (named.st_dev,named.st_ino,named.st_uid,named.st_gid,named.st_mode,named.st_mtime_ns,named.st_ctime_ns),
                'ROOT_CHANGED_DURING_IDENTITY_READ')
        return dict(filesystem=filesystem, inode=s.st_ino, uid=s.st_uid, mode=stat.S_IMODE(s.st_mode))
    finally:
        os.close(fd)


def read_pinned(path, pin, limit):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'SOURCE_NOT_BOUNDED_REGULAR_FILE')
        raw = stream.read(limit+1)
        after = os.fstat(stream.fileno())
    require((before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) ==
            (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns), 'SOURCE_CHANGED_DURING_READ')
    require(len(raw) <= limit and hashlib.sha256(raw).hexdigest() == pin['sha256'] and
            ('bytes' not in pin or len(raw) == pin['bytes']), 'PINNED_SOURCE_MISMATCH')
    return raw


def register(root, pins=PINS):
    root = exact_path(root)
    require(root.is_dir(), 'REGISTERED_ROOT_NOT_DIRECTORY')
    manifest_raw = read_pinned(exact_path(root/MANIFEST), pins[MANIFEST], 16*1024**2)
    manifest = strict_json(manifest_raw)
    require(manifest['version'] == '4.3.2' and manifest['scope'] == 'CURRENT_MINIMUM_G0_FROZEN_WORKING_COPY_BYTES', 'WRONG_FROZEN_SCOPE')
    for name, pin in pins.items():
        if name != MANIFEST:
            read_pinned(exact_path(root/name), pin, 1024**2)
    listed = {row['path']:row for row in manifest['files']}
    require(len(listed)==len(manifest['files']), 'DUPLICATE_MANIFEST_PATH')
    for name,pin in pins.items():
        if name != MANIFEST:
            require(listed[name]['sha256']==pin['sha256'] and listed[name]['size_bytes']==pin['bytes'], 'SOURCE_NOT_IN_ORIGINAL_MANIFEST')
    return dict(schema=SCHEMA, scope=SCOPE, project_uri=PROJECT_URI, root=str(root), root_identity=identity(root),
                pins=pins, manifest_bytes=len(manifest_raw), manifest_file_count=len(manifest['files']),
                manifest_content_bytes=sum(row['size_bytes'] for row in manifest['files']),
                scientific_authorization=False, G0=False, human_signature=False)


def registered_root(anchor_input, registration_input, expected_sha, pins=PINS):
    require(re.fullmatch('[0-9a-f]{64}', expected_sha or '') is not None, 'OPERATOR_REGISTRATION_NOT_PINNED')
    # Both inputs must be actual staged symlinks; copy/remote fallback cannot
    # prove a whole-directory bind. The registration lives in its own small
    # private control directory, never beside credentials or research payload.
    require(Path(anchor_input).is_symlink() and Path(registration_input).is_symlink(), 'WHOLE_DIRECTORY_BIND_REQUIRED')
    control = exact_path(Path(registration_input).resolve(strict=True))
    s = control.stat()
    require(stat.S_IMODE(s.st_mode)==0o600 and s.st_uid==os.getuid() and s.st_nlink==1 and
            stat.S_IMODE(control.parent.stat().st_mode)==0o700, 'UNSAFE_OPERATOR_REGISTRATION')
    require(list(control.parent.iterdir())==[control], 'CONTROL_DIRECTORY_NOT_REGISTRATION_ONLY')
    raw = read_pinned(control, {'sha256':expected_sha}, 65536)
    registration = strict_json(raw)
    require(set(registration)=={'schema','scope','project_uri','root','root_identity','pins','manifest_bytes',
        'manifest_file_count','manifest_content_bytes','scientific_authorization','G0','human_signature'}, 'REGISTRATION_SCHEMA')
    require(registration['schema']==SCHEMA and registration['scope']==SCOPE and registration['project_uri']==PROJECT_URI and
            registration['pins']==pins and registration['scientific_authorization'] is False and
            registration['G0'] is False and registration['human_signature'] is False, 'REGISTRATION_SCOPE')
    root = exact_path(registration['root'])
    anchor = exact_path(Path(anchor_input).resolve(strict=True))
    require(anchor==root/ANCHOR and identity(root)==registration['root_identity'], 'REGISTERED_ROOT_IDENTITY_CHANGED')
    require(register(root,pins)==registration, 'REGISTERED_FROZEN_SOURCE_CHANGED')
    return root,registration,control


def require_readonly_mount(root, mountinfo):
    def decode(value):
        return re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),value)
    mounts=[]
    for line in mountinfo.splitlines():
        fields=line.split(' - ',1)[0].split()
        require(len(fields)>=6, 'INVALID_KERNEL_MOUNTINFO')
        mounts.append((Path(decode(fields[4])),set(fields[5].split(','))))
    require(any(path==root and 'ro' in options for path,options in mounts), 'ROOT_NOT_KERNEL_READONLY_BIND')
    require(all('ro' in options for path,options in mounts if path.is_relative_to(root)), 'WRITABLE_DESCENDANT_MOUNT')


class Sources(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    def __init__(self,root,pins=PINS):
        self.root=root
        self.sources={name:read_pinned(exact_path(root/'02_EXECUTION'/(name+'.py')),
            pins['02_EXECUTION/'+name+'.py'],1024**2) for name in MODULES}
    def find_spec(self,fullname,path=None,target=None):
        if fullname in self.sources:
            return importlib.util.spec_from_loader(fullname,self,origin=str(self.root/'02_EXECUTION'/(fullname+'.py')))
        return None
    def create_module(self,spec): return None
    def exec_module(self,module):
        filename=str(self.root/'02_EXECUTION'/(module.__name__+'.py'))
        module.__file__=filename
        exec(compile(self.sources[module.__name__],filename,'exec'),module.__dict__)


class TrustedStdlib(importlib.abc.MetaPathFinder):
    def __init__(self,paths):
        self.paths=list(paths)
        self.roots=[Path(p).resolve() for p in paths]
    def find_spec(self,fullname,path=None,target=None):
        # Ignore later sys.path.insert by the unchanged frozen audit.
        selected=self.paths if path is None else [p for p in path if any(Path(p).resolve().is_relative_to(r) for r in self.roots)]
        return importlib.machinery.PathFinder.find_spec(fullname,selected,target)


def execute_sources(root,pins=PINS):
    require(sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode, 'ISOLATED_SOURCE_ONLY_ENTRY_REQUIRED')
    require(not any(name in sys.modules for name in MODULES), 'PROJECT_MODULE_ALREADY_LOADED')
    loader=Sources(root,pins)
    # Capture trusted paths before the original code inserts project paths.
    stdlib=TrustedStdlib(sys.path)
    previous=list(sys.meta_path);paths=list(sys.path)
    sys.meta_path[:]=[loader,importlib.machinery.BuiltinImporter,importlib.machinery.FrozenImporter,stdlib]
    try:
        module=importlib.import_module('verify_g0_v432')
        return module.audit(root)
    finally:
        sys.meta_path[:]=previous;sys.path[:]=paths
        for name in MODULES:sys.modules.pop(name,None)


def technical_report(result,registration,registration_sha,started):
    require(type(result) is dict and type(result.get('passed')) is bool and result.get('read_only') is True and
            result.get('all_project_scientific_gates_passed') is False and result.get('scientific_truth_certified') is False and
            result.get('scientific_results_computed') is False and type(result.get('errors')) is list, 'ORIGINAL_VERIFIER_RESULT_SCHEMA')
    return dict(schema='FROZEN_CURRENT_PROJECT_TECHNICAL_VERIFICATION_V1',scope=SCOPE,
        original_full_project_byte_verifier_executed=True, current_contents_rehashed=True,
        technical_verification_passed=result['passed'], read_only=True, cache_policy='never',
        started_unix_ns=started, finished_unix_ns=time.time_ns(), operator_registration_sha256=registration_sha,
        manifest_sha256=registration['pins'][MANIFEST]['sha256'], manifest_file_count=registration['manifest_file_count'],
        manifest_content_bytes=registration['manifest_content_bytes'], source_sha256={n:p['sha256'] for n,p in registration['pins'].items() if n.endswith('.py')},
        hash_checks=result['hash_checks'], unique_file_hashes=result['unique_file_hashes'], errors=result['errors'],
        scientific_authorization=False, G0=False, human_signature=False, scientific_gate_granted=False)


def main():
    require(len(sys.argv)==1 and os.environ.get('AUTONOMICS_INPUT_COUNT')=='2' and
            os.environ.get('AUTONOMICS_OUTPUT_COUNT')=='1', 'FIXED_VERIFIER_ABI_REQUIRED')
    expected=os.environ.get('EXPECTED_OPERATOR_REGISTRATION_SHA256','')
    root,registration,control=registered_root(os.environ['AUTONOMICS_INPUT0'],os.environ['AUTONOMICS_INPUT1'],expected)
    mounts=Path('/proc/self/mountinfo').read_text()
    require_readonly_mount(root,mounts);require_readonly_mount(control.parent,mounts)
    started=time.time_ns();result=execute_sources(root)
    require(register(root)==registration,'FROZEN_SOURCE_CHANGED_DURING_VERIFICATION')
    report=technical_report(result,registration,expected,started)
    output=Path(os.environ['AUTONOMICS_OUTPUT0'])
    require(output==Path('/work/technical-verification.json'), 'FIXED_TECHNICAL_OUTPUT_REQUIRED')
    descriptor=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(descriptor,'wb') as stream:stream.write(canonical(report)+b'\n')
    raise SystemExit(0 if report['technical_verification_passed'] else 1)


if __name__=='__main__':
    try:main()
    except Exception:
        print('Frozen project read-only technical verification refused',file=sys.stderr)
        raise SystemExit(2)
