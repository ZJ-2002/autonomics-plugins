"""Reproduce only destructive toy I/O behavior of the captured original adapter."""

import json
import os
from pathlib import Path
import subprocess
import tomllib

from generate_toy import generate, sha


HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
INPUT_NAMES = ['input.tsv','config.json','certificate.json','lock.tsv','proof.json']


def main():
    permanent=os.environ.get('AUTONOMICS_VALIDATION_PERMANENT')
    if not permanent:
        raise RuntimeError('Managed technical acceptance required')
    output=Path(permanent)/'v432-a-io-baseline'
    output.mkdir()
    (output/'driver.py').write_bytes(Path(__file__).read_bytes())
    (output/'generate_toy.py').write_bytes((HERE/'generate_toy.py').read_bytes())
    script=output/'original-mr.R'
    script.write_bytes((PLUGIN/'scripts/mr.R').read_bytes())
    image=tomllib.loads((PLUGIN/'manifest.toml').read_text())['image']['reference']
    cases={}
    for name in ['log_alias_input','existing_log_on_invalid_input','late_provenance_directory']:
        directory=output/name;inputs=directory/'inputs';generate(inputs,.001)
        outputs=directory/'outputs';outputs.mkdir()
        paths=[f'/work/outputs/output{position}' for position in range(9)]
        if name=='log_alias_input':
            paths[7]='/work/inputs/input.tsv'
        elif name=='existing_log_on_invalid_input':
            (inputs/'input.tsv').write_text((inputs/'input.tsv').read_text().replace('QUALIFIED','NOT_QUALIFIED',1))
            config=json.loads((inputs/'config.json').read_text());config['program_sha256']=sha(inputs/'input.tsv')
            (inputs/'config.json').write_text(json.dumps(config))
            proof=json.loads((inputs/'proof.json').read_text());proof['input_sha256']=[sha(inputs/filename) for filename in INPUT_NAMES[:4]]
            (inputs/'proof.json').write_text(json.dumps(proof))
            (outputs/'output7').write_text('PREEXISTING_LOG_SENTINEL\n')
        else:
            (outputs/'output8').mkdir()
        before={filename:sha(inputs/filename) for filename in INPUT_NAMES}
        command=['podman','run','--rm','--pull=never','--network=none','--read-only',
            '--userns=keep-id',f'--user={os.getuid()}:{os.getgid()}',
            '--security-opt=no-new-privileges','--cpus=2','--memory=2g',
            '-v',str(directory)+':/work:rw','-v',str(script)+':/original-mr.R:ro']
        for position,filename in enumerate(INPUT_NAMES):
            command+=['-e',f'AUTONOMICS_INPUT{position}=/work/inputs/{filename}']
        for position,path in enumerate(paths):
            command+=['-e',f'AUTONOMICS_OUTPUT{position}={path}']
        command+=['--entrypoint=Rscript',image,'--vanilla','/original-mr.R']
        (directory/'command.json').write_text(json.dumps(command,indent=2)+'\n')
        result=subprocess.run(command,capture_output=True,text=True,timeout=300)
        (directory/'stdout.log').write_text(result.stdout);(directory/'stderr.log').write_text(result.stderr)
        after={filename:sha(inputs/filename) for filename in INPUT_NAMES}
        ports=[]
        for position,path in enumerate(paths):
            actual=directory/path.removeprefix('/work/')
            ports.append(dict(port=position,path=path,is_file=actual.is_file(),is_directory=actual.is_dir(),
                sha256=sha(actual) if actual.is_file() else None,
                bytes=actual.stat().st_size if actual.is_file() else None))
        if result.returncode==0:
            raise RuntimeError('Expected original destructive/refusal case did not fail: '+name)
        if name=='log_alias_input' and before['input.tsv']==after['input.tsv']:
            raise RuntimeError('Original log alias did not reproduce input corruption')
        if name=='existing_log_on_invalid_input' and (outputs/'output7').read_text()=='PREEXISTING_LOG_SENTINEL\n':
            raise RuntimeError('Original existing log was unexpectedly preserved')
        if name=='late_provenance_directory' and not all((outputs/f'output{position}').is_file() for position in range(8)):
            raise RuntimeError('Original late failure did not reproduce all eight partial files')
        cases[name]=dict(exit=result.returncode,input_sha256_before=before,input_sha256_after=after,
            ports=ports,original_script_sha256=sha(script),scientific_data_used=False,g0_granted=False)
        (directory/'verification.json').write_text(json.dumps(cases[name],indent=2)+'\n')
    (output/'verification.json').write_text(json.dumps(dict(
        status='THREE_ORIGINAL_IO_DEFECTS_REPRODUCED_ON_SYNTHETIC_CONTRACTS',cases=cases,
        image=image,original_script_sha256=sha(script),real_frozen_input_read=False,
        official_method_or_scientific_release_granted=False,g0_granted=False),indent=2)+'\n')
    print('THREE_ORIGINAL_IO_DEFECTS_REPRODUCED; SYNTHETIC_ONLY; G0=false')


if __name__=='__main__':
    main()
