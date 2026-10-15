"""Compare the frozen PLINK binary with the dated archive on its author's download bucket."""

import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import stat
import urllib.request
import zipfile

OFFICIAL_PAGE = 'https://www.cog-genomics.org/plink/1.9/'
OFFICIAL_ARCHIVE = 'https://s3.amazonaws.com/plink1-assets/plink_linux_x86_64_20231211.zip'
FROZEN_BINARY = Path('/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0/04_SOFTWARE/bin/plink')
EXPECTED_SHA = '03ed6dd8882fddee7a89396c59ea56e4b17bbc4411d3049910e5d713fc8a135f'
EXPECTED_BYTES = 41730792
MAX_ARCHIVE_BYTES = 25 * 1024**2
MAX_BINARY_BYTES = 64 * 1024**2


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def frozen_identity():
    metadata = FROZEN_BINARY.lstat()
    require(stat.S_ISREG(metadata.st_mode) and not FROZEN_BINARY.is_symlink(),
            'Frozen PLINK must remain an unaliased regular file')
    value = dict(device=metadata.st_dev, inode=metadata.st_ino, uid=metadata.st_uid,
                 bytes=metadata.st_size, sha256=digest(FROZEN_BINARY))
    require(value['bytes'] == EXPECTED_BYTES and value['sha256'] == EXPECTED_SHA,
            'Frozen PLINK does not have its reviewed identity')
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        raise RuntimeError('Author-source requests may not redirect')


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.hrefs.extend(value for key, value in attrs if key == 'href' and value)


def fetch(url, destination, maximum):
    opener = urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(url, headers={'User-Agent': 'Autonomics-technical-source-assurance/1'})
    with opener.open(request, timeout=90) as response:
        require(response.status == 200 and response.url == url, 'Exact author URL HTTP 200 required')
        length = response.headers.get('Content-Length')
        require(length is None or 0 < int(length) <= maximum, 'Author artifact exceeds bounded download budget')
        size = 0
        with destination.open('xb') as output:
            while block := response.read(min(1024**2, maximum - size + 1)):
                size += len(block)
                require(size <= maximum, 'Author response exceeded bounded download budget')
                output.write(block)
        require(size > 0 and (length is None or size == int(length)), 'Author response is truncated or empty')
        return dict(url=url, final_url=response.url, status=response.status, bytes=size,
                    sha256=digest(destination), headers={key: response.headers.get(key)
                        for key in ['Date', 'Last-Modified', 'ETag', 'Content-Type', 'Content-Length']})


def extract_plink(archive, destination):
    with zipfile.ZipFile(archive) as source:
        candidates = [member for member in source.infolist() if member.filename == 'plink']
        require(len(candidates) == 1, 'Exactly one top-level author plink member required')
        member = candidates[0]
        require(not member.is_dir() and not stat.S_ISLNK(member.external_attr >> 16)
                and 0 < member.file_size <= MAX_BINARY_BYTES and not member.flag_bits & 1,
                'Bounded regular unencrypted author plink member required')
        size = 0
        with source.open(member) as stream, destination.open('xb') as output:
            while block := stream.read(1024**2):
                size += len(block)
                require(size <= MAX_BINARY_BYTES, 'Extracted author member exceeds budget')
                output.write(block)
        require(size == member.file_size, 'Author plink ZIP member is truncated')
        destination.chmod(0o600)
        return dict(member='plink', bytes=size, sha256=digest(destination),
                    zip_members=[item.filename for item in source.infolist()], executable_executed=False)


def main():
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT']) / 'frozen-a-plink-official-source'
    permanent.mkdir()
    scratch = Path(os.environ['TMPDIR']) / 'plink-author-source'
    scratch.mkdir()
    before = frozen_identity()
    evidence = dict(scope='FROZEN_PLINK_AUTHOR_ARTIFACT_IDENTITY_ONLY_NOT_G0', passed=False,
                    driver_sha256=digest(Path(__file__)), canonical_pre=before,
                    scientific_results_computed=False, installed=False, executable_executed=False,
                    production_restarted=False, frozen_configuration_changed=False, g0_granted=False)
    try:
        page = scratch / 'official-page.html'
        evidence['official_page'] = fetch(OFFICIAL_PAGE, page, 2 * 1024**2)
        text = page.read_text()
        links = Links()
        links.feed(text)
        bucket_links = [value for value in links.hrefs
                        if value.startswith('https://s3.amazonaws.com/plink1-assets/plink_linux_x86_64_')
                        and value.endswith('.zip')]
        require(bucket_links and '11 Dec 2023' in text,
                'Author download bucket link and historical 11 Dec 2023 release must be documented')
        evidence['author_bucket_links'] = bucket_links
        evidence['dated_url_derivation'] = 'Author Linux64 bucket and documented historical 11 Dec 2023 build; dated URL is derived, not asserted to be directly linked today or immutable.'
        archive = scratch / 'plink-author.zip'
        evidence['author_archive'] = fetch(OFFICIAL_ARCHIVE, archive, MAX_ARCHIVE_BYTES)
        evidence['author_binary'] = extract_plink(archive, scratch / 'plink.reference')
        require(evidence['author_binary']['bytes'] == EXPECTED_BYTES
                and evidence['author_binary']['sha256'] == EXPECTED_SHA,
                'Actual author archive binary does not equal the frozen PLINK binary')
        evidence['passed'] = True
    except Exception as error:
        evidence['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        after = frozen_identity()
        evidence['canonical_post'] = after
        evidence['canonical_unchanged'] = before == after
        evidence['passed'] = evidence['passed'] and before == after
        with (permanent / 'EVIDENCE.json').open('x') as output:
            json.dump(evidence, output, indent=2)
            output.write('\n')
    require(evidence['passed'], 'Frozen binary changed during author source verification')
    print(json.dumps(evidence, sort_keys=True))


if __name__ == '__main__':
    main()
