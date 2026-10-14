"""Build one exact committed engine probe in managed scratch, never an environment clone."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import shutil
import tarfile

EXAMPLE_PATH = "crates/container-plugin/examples/official_lm_dag.rs"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-repository", required=True, type=Path)
    parser.add_argument("--example-source", required=True, type=Path)
    parser.add_argument("--parent-commit", required=True)
    parser.add_argument("--target", required=True, type=Path)
    arguments = parser.parse_args()
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Use research_validation_session.py --profile build run")
    session_id = Path(permanent).parent.name
    session_path = Path.home() / ".local/state/autonomics/validation-archives" / session_id / "SESSION.json"
    session = json.loads(session_path.read_text())
    if (session.get("profile") != "build" or session.get("state") != "EXECUTING"
            or session.get("session") != session_id or session.get("workspace") != str(Path(permanent).parent)):
        raise RuntimeError("Exact active managed build-profile admission required")
    if not re.fullmatch("[0-9a-f]{40}", arguments.parent_commit) or not arguments.target.is_dir():
        raise RuntimeError("Exact parent commit and an existing canonical target cache required")
    output = Path(permanent) / "current-lm-build"
    output.mkdir(mode=0o700)
    environment = dict(os.environ, GIT_INDEX_FILE=str(Path(os.environ["TMPDIR"]) / "source.index"))

    def git(*parameters):
        return subprocess.check_output(["git", "-C", str(arguments.engine_repository), *parameters], env=environment).decode().strip()

    git("read-tree", arguments.parent_commit)
    example_hash = digest(arguments.example_source)
    blob = git("hash-object", "-w", str(arguments.example_source))
    git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + EXAMPLE_PATH)
    tree = git("write-tree")
    commit = git("commit-tree", tree, "-p", arguments.parent_commit,
                 "-m", "Add explicit official lm current-engine synthetic DAG probe")
    changed = git("diff-tree", "--no-commit-id", "--name-only", "-r", arguments.parent_commit, commit).splitlines()
    if changed != [EXAMPLE_PATH]:
        raise RuntimeError("Unexpected scientific/engine source changes in probe candidate")
    record = dict(engine_commit=commit, parent_commit=arguments.parent_commit, git_tree=tree,
                  probe_sha256=example_hash, changed_paths=changed, remote_pushed=False,
                  canonical_target=str(arguments.target), scientific_authorized=False, g0_granted=False)
    (output / "candidate.json").write_text(json.dumps(record, indent=2) + "\n")
    (output / "driver.py").write_bytes(Path(__file__).read_bytes())
    archive_path = Path(os.environ["TMPDIR"]) / "committed-source.tar"
    subprocess.run(["git", "-C", str(arguments.engine_repository), "archive", "--format=tar", "-o", str(archive_path), commit], check=True)
    source = Path(os.environ["TMPDIR"]) / "committed-source"
    source.mkdir()
    with tarfile.open(archive_path) as archive:
        archive.extractall(source, filter="data")
    before = {str(path.relative_to(source)): digest(path) for path in source.rglob("*") if path.is_file() and not path.is_symlink()}
    (output / "committed-source-files.json").write_text(json.dumps(before, indent=2) + "\n")
    if digest(source / EXAMPLE_PATH) != example_hash:
        raise RuntimeError("Exported committed probe differs")
    build_env = dict(os.environ, CARGO_TARGET_DIR=str(arguments.target), CARGO_BUILD_JOBS="2",
                     CARGO_TERM_COLOR="never", AUTONOMICS_SOURCE_REVISION=commit)
    command = ["cargo", "build", "--release", "--locked", "--offline", "-j", "2", "-p", "container-plugin",
               "--example", "official_lm_dag", "--message-format=json"]
    (output / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (output / "cargo.stdout.jsonl").open("w") as stdout, (output / "cargo.stderr.log").open("w") as stderr:
        completed = subprocess.run(command, cwd=source, env=build_env, stdout=stdout, stderr=stderr, timeout=13500)
    (output / "execution.json").write_text(json.dumps(dict(exit=completed.returncode, g0_granted=False)) + "\n")
    if completed.returncode:
        raise RuntimeError("Exact committed engine build failed; do not substitute a historical executable")
    artifacts = [json.loads(line) for line in (output / "cargo.stdout.jsonl").read_text().splitlines() if line.startswith("{")]
    executables = [Path(entry["executable"]) for entry in artifacts
                   if entry.get("reason") == "compiler-artifact" and entry.get("executable")
                   and entry.get("target", {}).get("name") == "official_lm_dag"]
    if len(executables) != 1:
        raise RuntimeError("Actual compiler executable identity missing or ambiguous")
    executable = executables[0]
    after = {str(path.relative_to(source)): digest(path) for path in source.rglob("*") if path.is_file() and not path.is_symlink()}
    if before != after or digest(arguments.example_source) != example_hash:
        raise RuntimeError("Committed source mutated during build")
    compiled_hash = digest(executable)
    durable = output / "official_lm_dag"
    shutil.copyfile(executable, durable)
    durable.chmod(0o700)
    if digest(durable) != compiled_hash or digest(executable) != compiled_hash:
        raise RuntimeError("Compiler executable changed during durable preservation")
    archived_executable = session_path.parent / "artifacts/permanent/current-lm-build/official_lm_dag"
    record.update(executable=str(archived_executable), staged_executable=str(durable),
                  compiler_cache_executable=str(executable), executable_sha256=compiled_hash,
                  committed_source_files=len(before), source_unchanged=True,
                  compiler_artifacts=len(artifacts), actual_build_exit=completed.returncode,
                  current_daemon_verified=False)
    (output / "build-record.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
