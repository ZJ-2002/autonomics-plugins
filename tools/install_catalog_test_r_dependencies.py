"""Install only the two exact R test helpers into the CI user library.

No analysis packages or optional dependencies are installed. Source downloads
are bounded and restricted to exact-version official CRAN URLs. DESCRIPTION is
checked before installation and actual package identity/location afterwards.
"""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request

VERSIONS = {'digest': '0.6.39', 'jsonlite': '2.0.0'}
MAX_ARCHIVE = 4 * 1024**2
R_CHECK = '''stopifnot(as.character(getRversion())=="4.6.1",as.character(utils::packageVersion("stats"))=="4.6.1")'''
R_INSTALL = R_CHECK + '''
a<-commandArgs(TRUE); lib<-a[1]; files<-a[-1]
utils::install.packages(files,lib=lib,repos=NULL,type="source",dependencies=FALSE,Ncpus=1L)
expected<-c(digest="0.6.39",jsonlite="2.0.0")
for(package in names(expected)) {
 stopifnot(as.character(utils::packageVersion(package,lib.loc=lib))==expected[[package]])
 stopifnot(normalizePath(find.package(package,lib.loc=lib))==normalizePath(file.path(lib,package)))
 ns<-loadNamespace(package,lib.loc=lib)
 stopifnot(as.character(getNamespaceVersion(ns))==expected[[package]])
}
cat("EXACT_CATALOG_TEST_DEPENDENCIES_OK\\n")
'''


def description(raw, package, version):
    if not 0 < len(raw) <= MAX_ARCHIVE:
        raise ValueError('Bounded source package required')
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        found = [member for member in archive.getmembers() if member.name == package + '/DESCRIPTION']
        if len(found) != 1 or not found[0].isfile() or not 0 < found[0].size <= 65536:
            raise ValueError('Unique regular package DESCRIPTION required')
        data = archive.extractfile(found[0]).read(65537).decode('utf-8')
    fields = {}
    for line in data.splitlines():
        if line and not line[0].isspace():
            key, sep, value = line.partition(':')
            if not sep or key in fields:
                raise ValueError('Invalid or duplicate DESCRIPTION field')
            fields[key] = value.strip()
    if fields.get('Package') != package or fields.get('Version') != version:
        raise ValueError('Exact locked test package/version required')


def acquire(package, version):
    name = package + '_' + version + '.tar.gz'
    urls = ['https://cran.r-project.org/src/contrib/' + name,
            'https://cran.r-project.org/src/contrib/Archive/' + package + '/' + name]
    for index, url in enumerate(urls):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                # urllib may follow redirects: keep the final origin official.
                final = urllib.parse.urlsplit(response.url)
                if final.scheme != 'https' or final.netloc != 'cran.r-project.org':
                    raise ValueError('Official HTTPS CRAN source required')
                raw = response.read(MAX_ARCHIVE + 1)
            description(raw, package, version)
            return raw, url
        except urllib.error.HTTPError as error:
            if error.code != 404 or index == len(urls) - 1:
                raise
    raise ValueError('Exact CRAN source unavailable')


def main():
    library = Path(os.environ['R_LIBS_USER'])
    if not library.is_absolute() or os.pathsep in str(library):
        raise ValueError('One explicit CI user library required')
    library.mkdir(parents=True, exist_ok=True)
    subprocess.run(['Rscript', '--vanilla', '-e', R_CHECK], check=True, timeout=30)
    output = Path('artifacts'); output.mkdir(exist_ok=True)
    records = {}
    with tempfile.TemporaryDirectory() as temporary:
        files = []
        for package, version in VERSIONS.items():
            raw, url = acquire(package, version)
            path = Path(temporary) / (package + '_' + version + '.tar.gz')
            with path.open('xb') as stream:
                stream.write(raw)
            records[package] = {'version': version, 'source_url': url,
                'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            files.append(str(path))
        subprocess.run(['Rscript', '--vanilla', '-e', R_INSTALL, str(library), *files],
                       check=True, timeout=600)
    with (output / 'exact-r-test-dependencies.json').open('x') as stream:
        json.dump({'R_version': '4.6.1', 'stats_version': '4.6.1',
                   'packages': records, 'analysis_method_qualification': False}, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    main()
