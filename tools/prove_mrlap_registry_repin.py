import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


PLUGINS = Path('/home/zj-normal/Work/autonomics-plugins')
ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
OLD = 'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d'
NEW = 'ghcr.io/zj-2002/mrlap-official@sha256:e6e10cddfa1cba8046ee6fbc1492b94cbd70d66b097f5f415845d56f9f925434'
LOCAL = 'localhost/mrlap-official@sha256:e6e10cddfa1cba8046ee6fbc1492b94cbd70d66b097f5f415845d56f9f925434'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    sys.path.insert(0,str(PLUGINS))
    from tools.reconcile_ab_evidence_index import verify_archive
    failure = verify_archive(ARCHIVES,'587358e53cf14c258b10f1d3418e79fb',
        '4f8009bf10229b5d77f57c92254ae76ae4ded05f1ecf38598400376ce5b34728')
    require(failure['worker_exit_status']==1,'Prior failed whole run must remain failed')
    output=Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])/'mrlap-registry-reference-repair'
    output.mkdir(mode=0o700)
    (output/'driver.py').write_bytes(Path(__file__).read_bytes())
    profile=json.loads((Path.home()/'.autonomics/qualified-image-store.json').read_text())
    primary=profile['primary']
    prefix=[os.environ['AUTONOMICS_PODMAN_PROGRAM'],'--storage-opt','additionalimagestore='+profile['additional']['path'],
        '--root',primary['graphroot'],'--runroot',primary['runroot'],'--tmpdir',primary['runroot']+'/libpod-tmp',
        '--storage-driver',primary['driver'],'--cgroup-manager=cgroupfs']
    local=[]
    for reference in [OLD,LOCAL]:
        result=subprocess.run([*prefix,'image','inspect',reference],capture_output=True,timeout=60)
        require(result.returncode==0,'Required prior cached image identity unavailable; do not infer equality')
        metadata=json.loads(result.stdout)
        require(len(metadata)==1,'Exactly one cached image required')
        local.append(dict(reference=reference,config=metadata[0]['Id'].removeprefix('sha256:'),
            diff_ids=metadata[0]['RootFS']['Layers']))
    require(local[0]['config']==local[1]['config'] and local[0]['diff_ids']==local[1]['diff_ids'],
        'Cached old qualified reference and proposed base are not the same runtime')
    queries=[]
    for label,reference,config in [('old-manifest',OLD,False),('new-manifest',NEW,False),('new-config',NEW,True)]:
        command=['skopeo','inspect','--no-creds','--retry-times=0','--raw']+(['--config'] if config else [])+['docker://'+reference]
        response=subprocess.run(command,capture_output=True,timeout=90)
        queries.append(dict(label=label,reference=reference,actual_exit=response.returncode))
        (output/(label+'.stderr')).write_bytes(response.stderr)
        if label=='old-manifest':
            require(response.returncode!=0 and b'manifest unknown' in response.stderr.lower(),
                'Old digest unavailability not reproduced; do not repin for a transient unrelated error')
        else:
            require(response.returncode==0,'Anonymous replacement manifest/config not accessible')
            (output/(label+'.json')).write_bytes(response.stdout)
    manifest_bytes=(output/'new-manifest.json').read_bytes()
    config_bytes=(output/'new-config.json').read_bytes()
    manifest=json.loads(manifest_bytes)
    config=json.loads(config_bytes)
    require('sha256:'+hashlib.sha256(manifest_bytes).hexdigest()==NEW.split('@')[1], 'Immutable replacement manifest hash differs')
    require(manifest['config']['digest']=='sha256:'+hashlib.sha256(config_bytes).hexdigest()=='sha256:'+local[0]['config']
        and config['rootfs']['diff_ids']==local[0]['diff_ids'],'Replacement runtime does not equal prior cached qualified image')
    report=dict(schema='MRLAP_DEAD_REGISTRY_REFERENCE_REPAIR_IDENTITY_V1',passed=True,
        old_reference=OLD,new_reference=NEW,old_manifest_unknown_reproduced=True,
        anonymous_replacement_manifest_and_config_verified=True,local_images=local,
        identical_config_and_uncompressed_layers=True,full_remote_layer_download_claimed=False,
        authentication_used=False,image_rebuilt=False,old_image_deleted=False,
        new_method_executions=0,production_changed=False,new_software_admissions=0,
        prior_source_recovery_session='587358e53cf14c258b10f1d3418e79fb',
        prior_whole_failure_not_relabelled=True,scientific_release_granted=False,g0_granted=False)
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/'query-results.json').write_text(json.dumps(queries,indent=2)+'\n')
    print(json.dumps(dict(replacement_runtime_identical=True,new_method_executions=0,g0_granted=False)),flush=True)


if __name__=='__main__':
    main()
