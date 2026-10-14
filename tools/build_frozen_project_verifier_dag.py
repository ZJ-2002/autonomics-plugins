"""Construct the fixed two-input agent DAG; never opens study inputs or runs it."""
import argparse
import json
from pathlib import Path
import re


def build(registration_uri,prefix='project_verify'):
    if not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,60}',prefix):
        raise ValueError('distinct safe node prefix required')
    if not re.fullmatch(r'vfs:///research/verification-control/[A-Za-z0-9_-]+/registration\.json',registration_uri):
        raise ValueError('dedicated approved readonly registration VFS mount required')
    specs=[('anchor','vfs:///research/current/README_START_HERE.md'),('registration',registration_uri)]
    lines=[]
    for name,path in specs:
        lines.append('node('+json.dumps(prefix+'_'+name)+', "core/file_reference", #{path: '+json.dumps(path)+', hash_content: true});')
    lines.append('node('+json.dumps(prefix+'_full')+', "frozen-project-verifier/frozen_v432_readonly_full_verify", #{});')
    for port,(name,_) in enumerate(specs):
        lines.append('edge('+json.dumps(prefix+'_'+name)+', 0, '+json.dumps(prefix+'_full')+', '+str(port)+');')
    lines.append('commit();')
    return dict(script='\n'.join(lines)+'\n',dry_run=True,timeout_ms=5000)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registration-uri',required=True)
    parser.add_argument('--prefix',default='project_verify')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with args.output.open('x') as stream:json.dump(build(args.registration_uri,args.prefix),stream,indent=2);stream.write('\n')
