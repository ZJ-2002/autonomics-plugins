import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request


ROOT = Path('/home/zj-normal/Work/autonomics')
PLUGINS = ROOT.parent / 'autonomics-plugins'
IMAGES = [
    ('survey', '6f3e6f417912b7fb2c2b344ceaa11ff6031cde7848740caf6450c4366b5fbc61',
     'a83c1fd019b14e4bedc2f113d372f4ae97fd38fe08cab1a2a82c84281426e59b'),
    ('mice', 'ff4c166b89842d9bfbcf8d0f8227d05057a3ae57a668d374374a60db1e425516',
     '556d36b4a6b72828c268df82f1a23c61280a2ae365b64f50958dd13b684d8234'),
    ('lcmm', 'dd7f8a68d27a1002d5f6b004ca2ad24fc92cc7db43773500963363f92f8828d5',
     'ef26c21806ef2bddd36601c47a24a8f0ed2423ffe56174779ae7ad3aa450a822'),
]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, address):
        return None


def main():
    output = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'updated-external-access'
    output.mkdir(mode=0o700)
    (output / 'driver.py').write_bytes(Path(__file__).read_bytes())
    images = []
    for family, digest, config in IMAGES:
        reference = f'ghcr.io/zj-2002/{family}-official@sha256:{digest}'
        result = subprocess.run(['skopeo', 'inspect', '--no-creds', '--retry-times=0', '--raw',
            'docker://' + reference], capture_output=True, timeout=90)
        passed = result.returncode == 0 and hashlib.sha256(result.stdout).hexdigest() == digest
        if passed:
            document = json.loads(result.stdout)
            passed = document['config']['digest'] == 'sha256:' + config
        images.append(dict(family=family, reference=reference, anonymous_manifest_verified=passed,
            actual_exit=result.returncode, credentials_used=False, image_layers_downloaded=0))
    launcher = subprocess.run(['git', '-C', str(ROOT), 'show',
        '0a2b87e17261b0ecf80c151568fdffada3058297:scripts/research_preview_launch.py'],
        capture_output=True, check=True, timeout=30).stdout
    require(hashlib.sha256(launcher).hexdigest() == 'c0a142a9a4b1264208c8b4c3c6ac15b44ebd0979c200142225188b75f56d2a60',
            'Pinned credential loader differs')
    namespace = dict(__name__='credential_probe', __file__=str(ROOT / 'scripts/research_preview_launch.py'))
    exec(compile(launcher, '<pinned-credential-loader>', 'exec'), namespace)
    credentials, metadata = namespace['credentials_environment']({})
    token = credentials.get('OPENGWAS_TOKEN', '').strip()
    r_token = credentials.get('OPENGWAS_JWT', '').strip()
    credential_report = dict(private_file_native_token_present=bool(token), private_file_R_JWT_present=bool(r_token),
        both_variables_equal=bool(token and r_token and token == r_token),
        values_or_token_hashes_recorded=False, actual_authentication_requests=0)
    if token:
        opener = urllib.request.build_opener(NoRedirect())
        request = urllib.request.Request('https://api.opengwas.io/api/user',
            headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'})
        try:
            with opener.open(request, timeout=45) as response:
                payload = response.read(65537)
                require(len(payload) <= 65536, 'Bounded user authentication response required')
                document = json.loads(payload)
                credential_report.update(HTTP_status=response.status,
                    valid_user_object=isinstance(document, dict) and bool(document) and 'error' not in document)
        except urllib.error.HTTPError as error:
            credential_report.update(HTTP_status=error.code, valid_user_object=False)
        except (OSError, ValueError):
            credential_report.update(HTTP_status=None, valid_user_object=False)
        credential_report['actual_authentication_requests'] = 1
    specification = importlib.util.spec_from_file_location('live', ROOT / 'results/cachexia-v4.3.2/reload_two_official_ab_plugins_20261019.py')
    live = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(live)
    pid = live.request_metadata('gateway/status')['pid']
    process = dict(entry.split(b'=', 1) for entry in (Path('/proc') / str(pid) / 'environ').read_bytes().split(b'\0') if b'=' in entry)
    credential_report.update(resident_pid=pid, native_token_matches_resident=bool(token) and process.get(b'OPENGWAS_TOKEN') == token.encode(),
        R_JWT_matches_resident=bool(r_token) and process.get(b'OPENGWAS_JWT') == r_token.encode())
    process.clear()
    credentials.clear()
    token = r_token = ''
    report = dict(schema='UPDATED_EXTERNAL_ACCESS_VERIFICATION_V1', images=images,
        all_three_images_public=all(row['anonymous_manifest_verified'] for row in images),
        opengwas=credential_report, production_restarted=False, new_gwas_data_queries=0,
        new_method_executions=0, new_software_admissions=0, scientific_release_granted=False, g0_granted=False)
    (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report), flush=True)
    require(report['all_three_images_public'], 'Anonymous image access not yet verified')
    require(credential_report.get('HTTP_status') == 200 and credential_report.get('valid_user_object')
        and credential_report['both_variables_equal'], 'Credential authentication or variable pairing not ready')


if __name__ == '__main__':
    main()
