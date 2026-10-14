"""Assemble two locked installed R packages into the existing R4.6.1 image.

Managed technical build only. No package installation, network pull, study data,
whole-environment copy or scientific execution.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tarfile

ROOT = Path(__file__).resolve().parents[1]
BASE = 'ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d'
VERSIONS = {'R': '4.6.1', 'limma': '3.68.5', 'statmod': '1.5.2', 'jsonlite': '2.0.0', 'digest': '0.6.39', 'stats': '4.6.1'}


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while data := stream.read(1024 ** 2):
            digest.update(data)
    return digest.hexdigest()


def execute(command, output, *, check=True):
    result = subprocess.run(command, capture_output=True, text=True)
    output.with_suffix('.stdout.txt').write_text(result.stdout)
    output.with_suffix('.stderr.txt').write_text(result.stderr)
    if check and result.returncode:
        raise RuntimeError('technical command failed: ' + result.stderr[-3000:])
    return result


def packages(library):
    records = {}
    for name, version in [('limma', '3.68.5'), ('statmod', '1.5.2')]:
        folder = library / name
        description = (folder / 'DESCRIPTION').read_text()
        if '\nVersion: ' + version + '\n' not in '\n' + description:
            raise ValueError('locked installed package version differs: ' + name)
        files = {}
        for path in sorted(folder.rglob('*')):
            if path.is_symlink():
                raise ValueError('installed package symlinks need separate review')
            if path.is_file():
                files[path.relative_to(folder).as_posix()] = dict(sha256=sha(path), bytes=path.stat().st_size)
        if not files or sum(r['bytes'] for r in files.values()) > 64 * 1024 ** 2:
            raise ValueError('bounded installed package identity required')
        records[name] = dict(version=version, files=files)
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, required=True)
    parser.add_argument('--frozen-code', type=Path, required=True)
    parser.add_argument('--reuse-archive', type=Path)
    args = parser.parse_args()
    if not os.environ.get('AUTONOMICS_PODMAN_PROGRAM'):
        parser.error('execute with latest managed python-script driver and its Podman shim')
    permanent = Path(os.environ['AUTONOMICS_VALIDATION_PERMANENT'])
    dest = permanent / 'frozen-b-thin-environment'; dest.mkdir()
    initial = packages(args.library)
    (dest / 'INSTALLED_PACKAGE_SOURCE_IDENTITIES.json').write_text(json.dumps(initial, indent=2) + '\n')
    inspected = execute(['podman', 'image', 'inspect', BASE], dest / 'base-inspection')
    base_info = json.loads(inspected.stdout)[0]
    if base_info['Digest'] != BASE.split('@')[1]:
        raise ValueError('actual cached base manifest digest differs')
    base_probe = 'cat(jsonlite::toJSON(list(R=as.character(getRversion()),jsonlite=as.character(packageVersion("jsonlite")),digest=as.character(packageVersion("digest"))),auto_unbox=TRUE))'
    measured = execute(['podman', 'run', '--rm', '--pull=never', '--network=none', '--entrypoint=Rscript', BASE,
                        '--vanilla', '-e', base_probe], dest / 'base-versions')
    if json.loads(measured.stdout) != {k: VERSIONS[k] for k in ['R', 'jsonlite', 'digest']}:
        raise ValueError('actual cached base software differs')
    with tempfile.TemporaryDirectory(prefix='frozen-b-thin-', dir=os.environ['TMPDIR']) as scratch:
        context = Path(scratch) / 'context'; context.mkdir()
        for name in initial:
            shutil.copytree(args.library / name, context / 'libraries' / name)
        if packages(args.library) != initial or packages(context / 'libraries') != initial:
            raise ValueError('installed package changed during source capture')
        launcher = ROOT / 'research-adapters/b-bulk-limma-contract/image-source/Rscript-vanilla'
        shutil.copyfile(launcher, context / 'Rscript-vanilla')
        (context / 'Rscript-vanilla').chmod(0o555)
        containerfile = ('FROM ' + BASE + '\nUSER 0:0\n'
            'ENV R_PROFILE_USER=/dev/null R_ENVIRON_USER=/dev/null R_LIBS=/opt/b-bulk-library R_LIBS_USER=/opt/b-bulk-library OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1\n'
            'COPY libraries /opt/b-bulk-library\nCOPY Rscript-vanilla /opt/b-bulk/bin/Rscript-vanilla\n'
            'WORKDIR /work\nENTRYPOINT []\nCMD ["Rscript", "--vanilla"]\n')
        footprint = sum(r['bytes'] for p in initial.values() for r in p['files'].values()) + len(containerfile.encode()) + launcher.stat().st_size
        if footprint > 128 * 1024 ** 2:
            raise ValueError('bounded two-package build context exceeds128MiB')
        (context / 'Containerfile').write_text(containerfile)
        (dest / 'Containerfile').write_text(containerfile)
        (dest / 'Rscript-vanilla').write_bytes(launcher.read_bytes())
        tag = 'localhost/autonomics/frozen-b-normalized:v432-two-package-layer'
        if args.reuse_archive:
            archive = args.reuse_archive.resolve(strict=True)
            if json.loads((archive.parent / 'INSTALLED_PACKAGE_SOURCE_IDENTITIES.json').read_bytes()) != initial:
                raise ValueError('reused software archive installed source identities differ')
            info = json.loads((archive.parent / 'new-image-inspection.stdout.txt').read_bytes())[0]
        else:
            execute(['podman', 'build', '--format=oci', '--pull=never', '--network=none', '--layers', '--force-rm', '--iidfile', str(dest / 'image-id.txt'),
                     '-t', tag, str(context)], dest / 'build')
            image_id = (dest / 'image-id.txt').read_text().strip()
            inspected = execute(['podman', 'image', 'inspect', image_id], dest / 'new-image-inspection')
            info = json.loads(inspected.stdout)[0]
        digest = info.get('Digest', '')
        if not digest.startswith('sha256:') or len(digest) != 71 or digest == BASE.split('@')[1]:
            raise ValueError('new layer needs an independently measured manifest digest')
        image = 'localhost/autonomics/frozen-b-normalized@' + digest
        build_manifest_digest = digest
        if not args.reuse_archive:
            archive = dest / 'frozen-b-normalized.oci.tar'
            execute(['podman', 'save', '--format=oci-archive', '--output', str(archive), image], dest / 'oci-export')
        if archive.stat().st_size >= 2 * 1024 ** 3:
            raise ValueError('single software OCI archive exceeds permanent technical scope')
        with tarfile.open(archive, 'r:') as bundle:
            index = json.load(bundle.extractfile('index.json'))
            if len(index['manifests']) != 1:
                raise ValueError('one exact exported OCI manifest required')
            descriptor = index['manifests'][0]
            exported_digest = descriptor['digest']
            manifest_raw = bundle.extractfile('blobs/sha256/' + exported_digest.split(':')[1]).read()
            if 'sha256:' + hashlib.sha256(manifest_raw).hexdigest() != exported_digest:
                raise ValueError('exported OCI manifest digest differs from actual bytes')
            manifest = json.loads(manifest_raw)
            config_digest = manifest['config']['digest']
            config_raw = bundle.extractfile('blobs/sha256/' + config_digest.split(':')[1]).read()
            if 'sha256:' + hashlib.sha256(config_raw).hexdigest() != config_digest or config_digest.removeprefix('sha256:') != info['Id'].removeprefix('sha256:'):
                raise ValueError('exported OCI and inspected config identity differ')
            config = json.loads(config_raw)
            if config['rootfs']['diff_ids'] != info['RootFS']['Layers']:
                raise ValueError('exported ordered diffIDs differ from inspected image')
        # The exported OCI can retain an obsolete source ref.name annotation.
        # An explicit destination preserves the actual manifest without editing
        # any byte of the sealed original software archive.
        import_command = ['skopeo', 'copy', '--preserve-digests',
                          'oci-archive:' + str(archive),
                          'containers-storage:localhost/autonomics/frozen-b-normalized:v432-export-verified']
        (dest / 'exact-oci-import-command.json').write_text(json.dumps(import_command, indent=2) + '\n')
        execute(import_command, dest / 'exact-oci-import')
        image = 'localhost/autonomics/frozen-b-normalized@' + exported_digest
        inspected = execute(['podman', 'image', 'inspect', image], dest / 'exact-export-image-inspection')
        info = json.loads(inspected.stdout)[0]
        if (info['Digest'] != exported_digest or info['Id'].removeprefix('sha256:') != config_digest.removeprefix('sha256:') or
                info['RootFS']['Layers'] != config['rootfs']['diff_ids']):
            raise ValueError('imported actual manifest/config/ordered diffIDs differ from exported OCI')
        probe = ('p<-c("limma","statmod","jsonlite","digest","stats");'
                 'stopifnot(all(vapply(p,requireNamespace,logical(1),quietly=TRUE)));'
                 'dependencies<-function(field){if(is.null(field)||length(field)==0L||is.na(field)||!nzchar(trimws(field)))return(character());'
                 'items<-trimws(strsplit(field,",")[[1]]);items<-trimws(gsub("\\\\([^)]*\\\\)","",items));'
                 'stopifnot(all(grepl("^[A-Za-z][A-Za-z0-9.]*$",items)));items};'
                 'paths<-setNames(lapply(c("limma","statmod"),find.package),c("limma","statmod"));'
                 'stopifnot(all(vapply(paths,function(x)startsWith(x,"/opt/b-bulk-library/"),logical(1))));'
                 'imports<-setNames(lapply(c("limma","statmod"),function(n)dependencies(packageDescription(n)$Imports)),c("limma","statmod"));'
                 'stopifnot(all(vapply(unlist(imports),requireNamespace,logical(1),quietly=TRUE)));'
                 'cat(jsonlite::toJSON(list(software_lock=c(list(R=as.character(getRversion())),setNames(lapply(p,function(n)as.character(packageVersion(n))),p)),library_paths=paths,imports=imports),auto_unbox=TRUE))')
        measured = execute(['podman', 'run', '--rm', '--pull=never', '--network=none', '--entrypoint=Rscript', image,
                            '--vanilla', '-e', probe], dest / 'new-image-versions-imports')
        measured_runtime = json.loads(measured.stdout)
        if measured_runtime['software_lock'] != VERSIONS:
            raise ValueError('new image measured software differs')
        python_probe = execute(['podman', 'run', '--rm', '--pull=never', '--network=none', '--entrypoint=python3', image,
            '-c', 'import json,sys;assert sys.version_info>=(3,11);print(json.dumps(dict(version=sys.version,executable=sys.executable)))'],
            dest / 'python-runtime-probe', check=False)
        python_runtime = None
        if python_probe.returncode == 0:
            python_runtime = json.loads(python_probe.stdout)
            execute(['podman', 'run', '--rm', '--pull=never', '--network=none',
                '-e', 'PYTHONDONTWRITEBYTECODE=1', '-v', str(ROOT) + ':' + str(ROOT) + ':ro', '--workdir', str(ROOT),
                '--entrypoint=python3', image, '-B', '-m', 'unittest', 'tests.test_frozen_b_project',
                'tests.test_normalized_bulk_interface', '-v'], dest / 'python-intake-family-toy')
        spec = importlib.util.spec_from_file_location('b_method_toy', ROOT / 'plugins/bulk-limma-normalized/tests/run_method_toy.py')
        toy = importlib.util.module_from_spec(spec); spec.loader.exec_module(toy)
        real_run = subprocess.run
        counter = 0
        method_dir = Path(scratch) / 'method'
        # The same method/oracle driver runs every R invocation in the new OCI.
        def container_run(command, **options):
            nonlocal counter
            if command[0] != 'Rscript':
                return real_run(command, **options)
            counter += 1
            podman = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--security-opt=no-new-privileges',
                      '--cpus=1', '--memory=1g', '-v', str(ROOT) + ':' + str(ROOT) + ':ro',
                      '-v', str(method_dir) + ':' + str(method_dir) + ':rw']
            for key, value in options.get('env', {}).items():
                if key.startswith('AUTONOMICS_INPUT') or key.startswith('AUTONOMICS_OUTPUT'):
                    podman.extend(['-e', key + '=' + value])
            podman.extend(['--entrypoint=/opt/b-bulk/bin/Rscript-vanilla', image, *command[1:]])
            return real_run(podman, **options)
        try:
            subprocess.run = container_run
            toy.run(args.library, method_dir, args.frozen_code, execution_scope='OCI')
        finally:
            subprocess.run = real_run
        shutil.copytree(method_dir, dest / 'method')
        record = dict(scope='SYNTHETIC_OCI_TWO_INSTALLED_PACKAGE_LAYER_NOT_SCIENTIFIC_AUTHORIZATION',
            base_image=BASE, base_config_id=base_info['Id'], image_reference=image, image_config_id=info['Id'],
            actual_current_store_identity_verified=True, actual_container_versions_imports_and_abi_verified=True,
            software_lock=VERSIONS, actual_oci_method_runs=counter, same_host_toy_driver_used=True,
            installed_source_packages=['limma', 'statmod'], whole_environment_copied=False,
            copied_two_package_context_bytes=footprint,
            actual_package_library_paths=measured_runtime['library_paths'], actual_imports=measured_runtime['imports'],
            python_runtime=python_runtime, actual_python_intake_family_toy_verified=python_runtime is not None,
            exported_oci_archive=dict(path=str(archive), sha256=sha(archive), bytes=archive.stat().st_size),
            original_build_manifest_sha256=build_manifest_digest,
            export_media_identity_change_not_relabelled=True,
            exported_oci_manifest_sha256=exported_digest, exported_oci_config_sha256=config_digest,
            offline_exact_manifest_import_command=import_command,
            ordered_diff_ids=config['rootfs']['diff_ids'],
            scientific_authorization=False, formal_authorized=False, G0=False)
        (dest / 'ENVIRONMENT_RESULT.json').write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record))


if __name__ == '__main__':
    main()
