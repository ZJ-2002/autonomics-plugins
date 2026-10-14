"""Exercise repaired TSV UCell path, method-failure and owned-inode rollback controls."""

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.prove_current_ldsc import digest, write
from tools.prove_ucell_tsv_io import IMAGE, ROOT


CASES = ['output1-alias-input', 'output3-alias-input', 'output-alias', 'normalized-parent-alias',
         'dangling-output', 'hardlinked-output', 'missing-input-path', 'missing-output-path',
         'invalid-rank', 'invalid-weight', 'invalid-policy', 'first-result-link-failure',
         'second-result-link-failure', 'audit-link-failure', 'foreign-replacement', 'input-change']


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    if 'AUTONOMICS_VALIDATION_PERMANENT' not in os.environ:
        raise RuntimeError('Managed validation required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'ucell-tsv-failures'
    output.mkdir()
    shutil.copyfile(Path(__file__), output / 'driver.py')
    shutil.copyfile(ROOT / 'plugins/ucell/scripts/ucell.R', output / 'source.R')
    records = []
    for name in CASES:
        work = output / name
        work.mkdir()
        (work / 'matrix.tsv').write_text('gene\tC1\tC2\nG1\t1\t3\nG2\t4\t2\nG3\t2\t1\n')
        (work / 'signatures.tsv').write_text('signature\tgene\none\tG1\n')
        before = {filename: digest(work / filename) for filename in ['matrix.tsv', 'signatures.tsv']}
        values = dict(AUTONOMICS_INPUT0='/work/matrix.tsv', AUTONOMICS_INPUT1='/work/signatures.tsv',
            AUTONOMICS_OUTPUT0='/work/scores.tsv', AUTONOMICS_OUTPUT1='/work/result.RDS',
            AUTONOMICS_OUTPUT2='/work/log.txt', AUTONOMICS_OUTPUT3='/work/audit.json',
            UCELL_MAX_RANK='3', UCELL_NEGATIVE_WEIGHT='1', UCELL_MISSING_GENES='impute')
        cause = 'Input and output paths must be distinct'
        if name == 'output1-alias-input': values['AUTONOMICS_OUTPUT1'] = values['AUTONOMICS_INPUT1']
        elif name == 'output3-alias-input': values['AUTONOMICS_OUTPUT3'] = values['AUTONOMICS_INPUT0']
        elif name == 'output-alias': values['AUTONOMICS_OUTPUT1'] = values['AUTONOMICS_OUTPUT0']
        elif name == 'normalized-parent-alias':
            (work / 'child').mkdir()
            values['AUTONOMICS_OUTPUT1'] = '/work/child/../scores.tsv'
        elif name == 'dangling-output':
            (work / 'scores.tsv').symlink_to('absent.tsv')
            cause = 'Refusing to overwrite any existing output'
        elif name == 'hardlinked-output':
            os.link(work / 'signatures.tsv', work / 'scores.tsv')
            cause = 'Refusing to overwrite any existing output'
        elif name == 'missing-input-path':
            del values['AUTONOMICS_INPUT1']
            cause = 'All declared input and output paths are required'
        elif name == 'missing-output-path':
            del values['AUTONOMICS_OUTPUT3']
            cause = 'All declared input and output paths are required'
        elif name in ['invalid-rank', 'invalid-weight', 'invalid-policy']:
            values[{'invalid-rank': 'UCELL_MAX_RANK', 'invalid-weight': 'UCELL_NEGATIVE_WEIGHT',
                    'invalid-policy': 'UCELL_MISSING_GENES'}[name]] = 'invalid'
            cause = 'Frozen UCell parameters invalid'
        code = None
        if name in ['first-result-link-failure', 'second-result-link-failure', 'audit-link-failure', 'foreign-replacement']:
            failure = {'first-result-link-failure': 2, 'second-result-link-failure': 3, 'audit-link-failure': 4, 'foreign-replacement': 3}[name]
            replacement = 'unlink(Sys.getenv("AUTONOMICS_OUTPUT0")); writeBin(charToRaw("FOREIGN_REPLACEMENT"), Sys.getenv("AUTONOMICS_OUTPUT0"));' if name == 'foreign-replacement' else ''
            code = f'counter <- 0L\nfile.link <- function(from,to) {{ counter <<- counter+1L; if(counter=={failure}L) {{ {replacement} return(FALSE) }}; base::file.link(from,to) }}\nsource("/program.R")\n'
            cause = 'Fresh result publication refused'
        elif name == 'input-change':
            code = 'counter <- 0L\nread.delim <- function(...) { value <- utils::read.delim(...); counter <<- counter+1L; if(counter==2L) cat("# injected input change\\n",file=Sys.getenv("AUTONOMICS_INPUT0"),append=TRUE); value }\nsource("/program.R")\n'
            cause = 'Input changed during UCell computation'
        if code:
            (work / 'injection.R').write_text(code)
        variables = []
        for key, value in values.items():
            variables += ['-e', key + '=' + value]
        command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--read-only', '--cpus=1', '--memory=1g',
            '--userns=keep-id', '--tmpfs=/tmp:rw,size=32m', '-v', str(work) + ':/work:rw',
            '-v', str(output / 'source.R') + ':/program.R:ro', '--entrypoint=Rscript', *variables, IMAGE,
            '--vanilla', '/work/injection.R' if code else '/program.R']
        completed = subprocess.run(command, capture_output=True, timeout=90)
        (work / 'process.stdout').write_bytes(completed.stdout)
        (work / 'process.stderr').write_bytes(completed.stderr)
        after = {filename: digest(work / filename) for filename in before}
        changed = [filename for filename in before if before[filename] != after[filename]]
        if completed.returncode != 2 or cause not in completed.stderr.decode() or changed != (['matrix.tsv'] if name == 'input-change' else []):
            raise RuntimeError('Specific failure/input protection not enforced: ' + name)
        for filename in ['scores.tsv', 'result.RDS', 'audit.json']:
            path = work / filename
            if name == 'foreign-replacement' and filename == 'scores.tsv':
                if path.read_bytes() != b'FOREIGN_REPLACEMENT':
                    raise RuntimeError('Rollback deleted an unowned replacement')
            elif name == 'hardlinked-output' and filename == 'scores.tsv':
                if digest(path) != before['signatures.tsv']:
                    raise RuntimeError('Protected hardlink changed')
                original = (work / 'signatures.tsv').stat()
                alias = path.stat()
                if (original.st_dev, original.st_ino) != (alias.st_dev, alias.st_ino):
                    raise RuntimeError('Intended hardlink fixture identity differs')
                path.unlink()
                write(work / 'hardlink-receipt.json', dict(shared_device=alias.st_dev, shared_inode=alias.st_ino,
                    unchanged_sha256=before['signatures.tsv'], owned_fixture_alias_removed_for_archive=True))
            elif name == 'dangling-output' and filename == 'scores.tsv':
                if not path.is_symlink() or os.readlink(path) != 'absent.tsv' or path.exists():
                    raise RuntimeError('Protected dangling link changed')
                path.unlink()
                write(work / 'dangling-receipt.json', dict(target='absent.tsv', unchanged=True, owned_fixture_removed_for_archive=True))
            elif path.exists():
                raise RuntimeError('Failed method left a normal artifact: ' + name)
        if list(work.glob('.ucell-stage-*')):
            raise RuntimeError('Owned staging directories not cleaned')
        if code or name.startswith('invalid-'):
            if cause not in (work / 'log.txt').read_text():
                raise RuntimeError('Method/publication failure log was not preserved')
        records.append(dict(case=name, exact_cause=cause, exit_code=2, input_digests_before=before,
                            input_digests_after=after, only_declared_owned_fault_input_changed=changed,
                            ordinary_rollback_not_crash_recovery=True))
    write(output / 'verification.json', dict(status='TSV_UCELL_SPECIFIC_FAILURE_AND_OWNED_ROLLBACK_PROVEN',
        cases=records, method_source_sha256=digest(output / 'source.R'), image=IMAGE, g0_granted=False))
    print('SPECIFIC_FAILURES=16 FOREIGN_INODE_PRESERVED=true G0=false')


if __name__ == '__main__':
    main()
