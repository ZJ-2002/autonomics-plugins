import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from urllib.parse import urlsplit


ARCHIVES = Path.home() / '.local/state/autonomics/validation-archives'
ROOT = Path('/home/zj-normal/Work/autonomics-plugins')
COLD = Path('/run/media/zj-normal/新加卷/Autonomics-cold-results-v41-20261017-v1/cachexia-v4.1.squashfs')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    sys.path.insert(0, str(ROOT))
    from tools.reconcile_ab_evidence_index import verify_archive
    for session, seal in [
        ('a6138597ca8c4919b86d730585f5e0a5', 'a327284b27759736492c7eb6ba1600bcb0acffcbe15ef92cf7f1bd0f58571870'),
        ('a1332a09bff14bedbd2c4966a5f858b6', '0e051e1516935fdf26c5c92176e4cd209dd4d5d016a4754fc5d656bcd14638fd'),
    ]:
        require(verify_archive(ARCHIVES, session, seal)['positive_worker_exit_verified'], 'Prior content evidence invalid')
    source = ARCHIVES / 'a6138597ca8c4919b86d730585f5e0a5/artifacts/permanent/conditional-source-payloads/verification.json'
    raw = source.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == '5c386d8026b631d99442cb36efda0115c05489be77e4312f79af9ece65b68337', 'Image payload evidence differs')
    selection = json.loads(raw)['additional_payloads_pending_content_review']
    require(len(selection) == 12 and sum(item['bytes'] for item in selection) < 16000, 'Bounded known log selection required')
    index = ARCHIVES / 'a1332a09bff14bedbd2c4966a5f858b6/artifacts/permanent/mice-cold-case-records/files/node-proof-mice-20261007/proof-seal.json'
    raw = index.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == '76e92e7abcdf18ba969fdc15927db0b5609c19e8aa88a08ea614f701ce0f14be', 'Original record inventory differs')
    records = {item['path']: item for item in json.loads(raw)['artifacts']}
    mount = json.loads(subprocess.check_output(['findmnt', '--json', '-T', str(COLD), '-o', 'TARGET,UUID']))['filesystems']
    require(len(mount) == 1 and mount[0]['uuid'] == 'D2F694CAF694B069'
            and mount[0]['target'] == '/run/media/zj-normal/新加卷', 'Exact cold volume required')

    def identity():
        value = COLD.stat()
        return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]

    before = identity()
    require(before[2] == 27543273472, 'Exact frozen archive required')
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'conditional-build-log-review'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    raw_directory = output / 'private-original-logs'
    raw_directory.mkdir(mode=0o700)
    reviewed = []
    public_hosts = {'archive.ubuntu.com', 'security.ubuntu.com', 'ports.ubuntu.com'}
    for entry in selection:
        name = PurePosixPath(entry['path']).name
        require(re.fullmatch(r'(SHA256SUMS(?:-v[23])?|apt-(download|policy|update)(-v[23])?\.log)', name) is not None,
                'Unexpected additional payload')
        original_path = 'mice-proof-v5/official-build/runtime-debs/' + name
        record = records[original_path]
        require(record['sha256'] == entry['sha256'] and record['size_bytes'] == entry['bytes'], 'Image and original log differ')
        extracted = subprocess.run(['unsquashfs', '-processors', '1', '-mem', '32M', '-no-wildcards', '-cat',
            str(COLD), 'node-proof-mice-20261007/' + original_path], capture_output=True, timeout=90)
        require(extracted.returncode == 0 and len(extracted.stdout) == entry['bytes']
                and hashlib.sha256(extracted.stdout).hexdigest() == entry['sha256'] and identity() == before,
                'Frozen log extraction identity differs')
        (raw_directory / name).write_bytes(extracted.stdout)
        text = extracted.stdout.decode('utf-8', errors='strict')
        urls = re.findall(r'https?://[^\s\x1b<>"\']+', text)
        parsed = [urlsplit(url) for url in urls]
        non_public_urls = any(url.hostname not in public_hosts or url.username is not None or url.password is not None
                              or url.query or url.fragment for url in parsed)
        credential_pattern = bool(re.search(r'gh[pousr]_[A-Za-z0-9]{20,}|Bearer\s+[A-Za-z0-9._-]{20,}'
            r'|(?:API_KEY|PASSWORD|TOKEN|SECRET)\s*[=:]|BEGIN [A-Z ]*PRIVATE KEY', text, re.I))
        private_paths = bool(re.search(r'/home/|/run/media/|/mnt/|\.autonomics|private-vault|data_sets/|GSM\d+|GSE\d+', text))
        control_characters = any(ord(character) < 32 and character not in '\n\r\t' for character in text)
        checksum_format = not name.startswith('SHA256SUMS') or all(
            re.fullmatch(r'[0-9a-f]{64}\s+[A-Za-z0-9_%+.:-]+\.deb', line) is not None
            for line in text.splitlines())
        safe_to_render = not any([non_public_urls, credential_pattern, private_paths, control_characters])
        reviewed.append(dict(name=name, bytes=entry['bytes'], sha256=entry['sha256'],
            image_original_identity_equal=True, non_public_urls=bool(non_public_urls),
            credential_pattern=credential_pattern, private_research_path_pattern=private_paths,
            control_characters=control_characters, checksum_format_valid=checksum_format,
            public_url_hosts=sorted({url.hostname for url in parsed if url.hostname in public_hosts}),
            review_lines=re.sub(r'https?://[^\s\x1b<>"\']+', '[PUBLIC_APT_URL]', text).splitlines()
                         if safe_to_render else [], safe_to_render=safe_to_render))
    passed = all(item['safe_to_render'] and item['checksum_format_valid'] for item in reviewed)
    report = dict(schema='CONDITIONAL_BUILD_LOG_CONTENT_REVIEW_V1',
        content_rules_passed=passed, files=reviewed, reviewed_files=len(reviewed),
        raw_log_publication_authorized=False, complete_secret_absence_certified=False,
        whole_image_publication_authorized=False, original_archive_unchanged=identity() == before,
        new_method_executions=0, new_software_admissions=0, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    require(passed, 'Content review requires manual follow-up; no raw log disclosure')
    print(json.dumps(dict(reviewed_files=len(reviewed), content_rules_passed=True,
        new_method_executions=0, whole_image_publication_authorized=False)), flush=True)


if __name__ == '__main__':
    main()
