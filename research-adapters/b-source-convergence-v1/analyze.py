import csv
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile


ROOT = Path('/home/zj-normal/Work/autonomics-plugins')
BASE = '233b5c4eabe31a121420bcd5c738edf9cfb48b5c'
ARCHIVES = Path.home()/'.local/state/autonomics/validation-archives'
PRIOR = '0a56015e6b5b4f7c959b40c7a579a852'
COLLECT = '''import json,sys,unittest
from pathlib import Path
root,output=map(Path,sys.argv[1:])
sys.path.insert(0,str(root))
loader=unittest.TestLoader()
suite=loader.discover(str(root/'tests'),pattern='test_*.py',top_level_dir=str(root))
def flatten(value):
 for item in value:
  if isinstance(item,unittest.TestSuite):yield from flatten(item)
  else:yield item.id()
ids=list(flatten(suite))
output.write_text(json.dumps({'ids':ids,'loader_errors':loader.errors,'test_execution_performed':False},indent=2)+'\\n')
assert not loader.errors and len(ids)==len(set(ids)) and not any('_FailedTest' in name for name in ids)
'''


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(*arguments):
    result = subprocess.run(['git','-C',str(ROOT),*arguments],capture_output=True,timeout=60,
        env=dict(os.environ,GIT_OPTIONAL_LOCKS='0',GIT_NO_REPLACE_OBJECTS='1'))
    require(result.returncode == 0,'Read-only published Git observation failed')
    return result.stdout


def main():
    require(os.environ.get('AUTONOMICS_VALIDATION_PERMANENT') and os.environ.get('TMPDIR'), 'Managed session required')
    os.umask(0o077)
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])/'b-source-convergence'
    output.mkdir(mode=0o700)
    (output/'analyze.py').write_bytes(Path(__file__).read_bytes())
    local_paths = sorted({*ROOT.joinpath('tests').glob('test_*.py'),*ROOT.joinpath('tools').rglob('*.py'),ROOT/'quality/required-tests.json'} - set(ROOT.joinpath('tools').rglob('__pycache__/*.py')))
    before = {str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in local_paths}
    published_names = git('ls-tree','-r','--name-only',BASE,'--','tests').decode().splitlines()
    published_modules = {name for name in published_names if Path(name).name.startswith('test_') and name.endswith('.py')}
    local_modules = {str(path.relative_to(ROOT)) for path in ROOT.joinpath('tests').glob('test_*.py')}
    manifest_bytes = (ARCHIVES/PRIOR/'artifacts/MANIFEST.json').read_bytes()
    require(sha(manifest_bytes) == '081e1e18c0e91df4d8fb7d2fb0ceed63309338f233816157be2f03debc6dbb7e', 'Prior 41-case seal differs')
    manifest = json.loads(manifest_bytes)
    prior_member = 'permanent/required-test-source-increment/verification.json'
    prior_bytes = (ARCHIVES/PRIOR/'artifacts'/prior_member).read_bytes()
    require(sha(prior_bytes) == manifest['files'][prior_member]['sha256'] == '8e80af5dde4c572eda858bac59734c384e00a456f64d7d96972828b7374b048e', 'Prior 41-case evidence differs')
    prior = json.loads(prior_bytes)
    receipt = json.loads((ARCHIVES/PRIOR/'SESSION.json').read_bytes())
    require(receipt['state'] == 'CLEANED' and receipt['worker_exit_status'] == 0 and prior['actual_exit'] == 0, 'Prior actual source-bound execution did not pass')
    known = prior['local_test_and_tool_sources_sha256']
    dependency_changes = [name for name,expected in known.items() if name.startswith('tools/') and (not (ROOT/name).exists() or sha((ROOT/name).read_bytes()) != expected)]
    records = []
    for name in sorted(published_modules|local_modules):
        local = (ROOT/name).read_bytes() if name in local_modules else None
        published = git('show',BASE+':'+name) if name in published_modules else None
        state = 'IDENTICAL' if local == published else 'LOCAL_ONLY' if published is None else 'PUBLISHED_ONLY' if local is None else 'DIFFERENT'
        bound = name in known and local is not None and sha(local) == known[name] and not dependency_changes
        decision = {'IDENTICAL':'REUSE_PUBLISHED_SOURCE', 'LOCAL_ONLY':'UNPUBLISHED_LOCAL_FEATURE_REVIEW_BEFORE_PUBLICATION', 'PUBLISHED_ONLY':'PRESERVE_PUBLIC_MODULE_DO_NOT_DELETE_FROM_RELEASE', 'DIFFERENT':'KEEP_BOTH_IDENTITIES_REQUIRE_EXPLICIT_FORWARD_MERGE'}[state]
        records.append({'path':name,'state':state,'local_sha256':sha(local) if local is not None else None,'published_sha256':sha(published) if published is not None else None,'local_matches_prior_41_execution_source':bound,'decision':decision})
    temporary = Path(os.environ['TMPDIR'])/'b-source-convergence'
    temporary.mkdir()
    inventory = git('ls-tree','-r','-l',BASE).decode().splitlines()
    sizes = []
    selected_paths = []
    excluded_paths = []
    for line in inventory:
        metadata, name = line.split('\t',1)
        parts = metadata.split()
        excluded = set(Path(name).parts) & {'vendor','vendor-src','source-archives','HDL-L','fixtures'} or name.endswith(('.tar.gz','.zip','.RData','.h5ad','.RDS','.parquet','.log'))
        if parts[1] != 'blob' or excluded:
            excluded_paths.append(name)
            continue
        sizes.append(line)
        selected_paths.append(name)
    byte_total = sum(int(line.split('\t',1)[0].split()[3]) for line in sizes)
    require(len(sizes) <= 6000 and byte_total <= 64*1024**2, 'Public source-only snapshot exceeds budget')
    archive = git('archive','--format=tar',BASE,'--',*selected_paths)
    snapshot = temporary/'published-source'
    snapshot.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive),mode='r:') as package:
        require(all(member.isfile() or member.isdir() for member in package.getmembers()), 'Only ordinary public source members allowed')
        package.extractall(snapshot,filter='data')
    collector = temporary/'collect.py'
    collector.write_text(COLLECT)
    (output/'collector.py').write_text(COLLECT)
    environment = {name:value for name,value in os.environ.items() if not name.endswith(('_API_KEY','_TOKEN','_JWT'))}
    collection = {}
    for label, tree in [('published',snapshot),('local',ROOT)]:
        destination = output/(label+'-discovery.json')
        result = subprocess.run([sys.executable,'-B',str(collector),str(tree),str(destination)],env=environment,capture_output=True,timeout=60)
        (output/(label+'-collection.stderr')).write_bytes(result.stderr)
        require(result.returncode == 0, 'Test collection failed: '+label)
        discovered = json.loads(destination.read_bytes())['ids']
        required = json.loads((tree/'quality/required-tests.json').read_bytes())['test_ids']
        require(len(required) == len(set(required)), 'Duplicate required ID: '+label)
        collection[label] = {'discovered_count':len(discovered),'required_count':len(required),
            'required_not_discovered':sorted(set(required)-set(discovered)),
            'discovered_not_required':sorted(set(discovered)-set(required)),
            'exact_gate_set_consistent':sorted(required)==sorted(discovered),
            'test_execution_performed':False}
    run_checks = git('show',BASE+':tools/run_checks.py')
    require(b'sorted(result.executed) == sorted(required)' in run_checks and b'not result.skipped' in run_checks, 'Published gate contract differs')
    require({str(path.relative_to(ROOT)):sha(path.read_bytes()) for path in local_paths} == before, 'Local test/tool source changed during observation')
    states = {state:sum(row['state'] == state for row in records) for state in ['IDENTICAL','LOCAL_ONLY','PUBLISHED_ONLY','DIFFERENT']}
    report = {'schema':'B_SOURCE_CONVERGENCE_V1','published_commit':BASE,'published_tree':git('rev-parse',BASE+'^{tree}').decode().strip(),
        'source_modules':records,'module_counts':states,'collections':collection,
        'prior_41_source_dependency_changes':dependency_changes,'prior_41_source_test_execution_reused':True,
        'local_source_hashes_before_and_after':before,'published_runner_sha256':sha(run_checks),
        'public_source_snapshot':{'selected_source_entries':len(sizes),'blob_bytes':byte_total,'excluded_vendor_or_payload_paths':excluded_paths,'filtered_source_view_not_complete_checkout':True,'dependency_environments_copied':False},
        'old_restore_162_patch_applied':False,'source_lock_or_shared_catalog_modified':False,
        'new_test_or_method_executions':0,'production_changed':False,'scientific_release_granted':False,'g0_granted':False}
    (output/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    buffer = io.StringIO()
    fields = ['path','state','local_sha256','published_sha256','local_matches_prior_41_execution_source','decision']
    writer = csv.DictWriter(buffer,fieldnames=fields,delimiter='\t',lineterminator='\n')
    writer.writeheader()
    writer.writerows(records)
    (output/'convergence.tsv').write_text(buffer.getvalue())
    print(json.dumps({'module_counts':states,'published_discovered':collection['published']['discovered_count'],
        'published_gate_consistent':collection['published']['exact_gate_set_consistent'],
        'local_discovered':collection['local']['discovered_count'],'local_gate_consistent':collection['local']['exact_gate_set_consistent'],
        'new_tests_executed':0}),flush=True)


if __name__ == '__main__':
    main()
