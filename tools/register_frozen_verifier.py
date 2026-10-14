"""Operator-only private metadata registration. Does not run the verifier.

The registration is not a reviewer, signature, approval, scientific gate or
authorization. Its actual SHA must be pinned in the reviewed plugin deployment.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat

PLUGIN=Path(__file__).resolve().parents[1]/'plugins/frozen-project-verifier'
spec=importlib.util.spec_from_file_location('fixed_verifier',PLUGIN/'scripts/verify.py')
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)


def write_registration(root, output):
    value=verifier.register(root)
    output=Path(output)
    verifier.require(output.is_absolute() and not output.exists() and not output.is_symlink(), 'EXCLUSIVE_PRIVATE_REGISTRATION_REQUIRED')
    directory=verifier.exact_path(output.parent)
    info=directory.stat()
    verifier.require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700 and
        not directory.is_relative_to(Path(value['root'])) and
        not any(directory.iterdir()), 'DEDICATED_EMPTY_PRIVATE_CONTROL_DIRECTORY_REQUIRED')
    raw=verifier.canonical(value)+b'\n'
    descriptor=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'wb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    return dict(schema='FROZEN_PROJECT_REGISTRATION_CREATED_V1',registration_sha256=hashlib.sha256(raw).hexdigest(),
        registration_bytes=len(raw), full_current_contents_verified=False, scientific_authorization=False,G0=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(write_registration(args.project_root,args.output),sort_keys=True))
    except Exception:
        print('Frozen verifier private operator registration refused',file=__import__('sys').stderr)
        raise SystemExit(2)
