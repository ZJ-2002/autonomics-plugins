"""Build the explicit author-LDSC-only DAG using an existing canonical compiler cache."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

EXAMPLE = "official_ldsc_dag"
EXAMPLE_PATH = "crates/container-plugin/examples/" + EXAMPLE + ".rs"
SINK_PATH = "crates/node-bundles/nodes-io/src/dataframe_to_file.rs"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024**2), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-repository", required=True, type=Path)
    parser.add_argument("--example-source", required=True, type=Path)
    parser.add_argument("--parent-commit", required=True)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--sink-source", type=Path)
    arguments = parser.parse_args()
    permanent = os.environ.get("AUTONOMICS_VALIDATION_PERMANENT")
    if not permanent:
        raise RuntimeError("Use research_validation_session.py --profile build run")
    session_id = Path(permanent).parent.name
    archive = Path.home() / ".local/state/autonomics/validation-archives" / session_id
    session = json.loads((archive / "SESSION.json").read_text())
    if (session.get("profile") != "build" or session.get("state") != "EXECUTING"
            or session.get("session") != session_id or session.get("workspace") != str(Path(permanent).parent)):
        raise RuntimeError("Exact active managed build-profile admission required")
    if not re.fullmatch(r"[0-9a-f]{40}", arguments.parent_commit) or not arguments.target.is_dir():
        raise RuntimeError("Exact parent and existing canonical target required")
    output = Path(permanent) / "current-ldsc-build"
    output.mkdir(mode=0o700)
    (output / "driver.py").write_bytes(Path(__file__).read_bytes())
    environment = dict(os.environ, GIT_INDEX_FILE=str(Path(os.environ["TMPDIR"]) / "source.index"))

    def git(*parameters):
        return subprocess.check_output(["git", "-C", str(arguments.engine_repository), *parameters],
                                       env=environment).decode().strip()

    git("read-tree", arguments.parent_commit)
    source_hash = digest(arguments.example_source)
    blob = git("hash-object", "-w", str(arguments.example_source))
    git("update-index", "--add", "--cacheinfo", "100644," + blob + "," + EXAMPLE_PATH)
    sink_hash = None
    if arguments.sink_source:
        sink_hash = digest(arguments.sink_source)
        sink_blob = git("hash-object", "-w", str(arguments.sink_source))
        git("update-index", "--add", "--cacheinfo", "100644," + sink_blob + "," + SINK_PATH)
    tree = git("write-tree")
    candidate = git("commit-tree", tree, "-p", arguments.parent_commit,
                    "-m", "Add explicit author LDSC synthetic-panel DAG probe")
    changed = git("diff-tree", "--no-commit-id", "--name-only", "-r", arguments.parent_commit, candidate).splitlines()
    expected_changes = [SINK_PATH] if arguments.sink_source else [EXAMPLE_PATH]
    if changed != expected_changes:
        raise RuntimeError("Unexpected engine or scientific-method changes")
    record = dict(engine_commit=candidate, parent_commit=arguments.parent_commit, git_tree=tree,
                  probe_sha256=source_hash, changed_paths=changed, canonical_target=str(arguments.target),
                  sink_sha256=sink_hash,
                  remote_pushed=False, scientific_authorized=False, g0_granted=False)
    (output / "candidate.json").write_text(json.dumps(record, indent=2) + "\n")
    source_archive = Path(os.environ["TMPDIR"]) / "committed-source.tar"
    subprocess.run(["git", "-C", str(arguments.engine_repository), "archive", "--format=tar", "-o",
                    str(source_archive), candidate], check=True)
    source = Path(os.environ["TMPDIR"]) / "committed-source"
    source.mkdir()
    with tarfile.open(source_archive) as archive_file:
        archive_file.extractall(source, filter="data")
    before = {str(path.relative_to(source)): digest(path) for path in source.rglob("*") if path.is_file() and not path.is_symlink()}
    if digest(source / EXAMPLE_PATH) != source_hash:
        raise RuntimeError("Exported example identity differs")
    if sink_hash is not None and digest(source / SINK_PATH) != sink_hash:
        raise RuntimeError("Exported sink source identity differs")
    (output / "committed-source-files.json").write_text(json.dumps(before, indent=2) + "\n")
    build_environment = dict(os.environ, CARGO_TARGET_DIR=str(arguments.target), CARGO_BUILD_JOBS="2",
                             CARGO_TERM_COLOR="never", AUTONOMICS_SOURCE_REVISION=candidate)
    command = ["cargo", "build", "--release", "--locked", "--offline", "-j", "2", "-p",
               "container-plugin", "--example", EXAMPLE, "--message-format=json"]
    (output / "command.json").write_text(json.dumps(command, indent=2) + "\n")
    with (output / "cargo.stdout.jsonl").open("w") as stdout, (output / "cargo.stderr.log").open("w") as stderr:
        completed = subprocess.run(command, cwd=source, env=build_environment, stdout=stdout,
                                   stderr=stderr, timeout=13500)
    (output / "execution.json").write_text(json.dumps(dict(exit=completed.returncode, g0_granted=False)) + "\n")
    if completed.returncode:
        raise RuntimeError("Exact candidate build failed; no historical executable substitution")
    if sink_hash is not None:
        regression_command = ["cargo", "test", "--release", "--locked", "--offline", "-j", "2", "-p", "nodes-io", "--lib",
                              "dataframe_to_file::tests::normalize_string_views_preserves_qualified_column_names", "--", "--exact"]
        with (output / "qualified-sink-regression.log").open("w") as regression_log:
            regression = subprocess.run(regression_command, cwd=source, env=build_environment,
                                        stdout=regression_log, stderr=subprocess.STDOUT, timeout=13500)
        regression_text = (output / "qualified-sink-regression.log").read_text()
        if regression.returncode or "test result: ok. 1 passed; 0 failed; 0 ignored;" not in regression_text:
            raise RuntimeError("Real qualified-column sink regression missing or failed")
    messages = [json.loads(line) for line in (output / "cargo.stdout.jsonl").read_text().splitlines() if line.startswith("{")]
    executables = [Path(message["executable"]) for message in messages
                   if message.get("reason") == "compiler-artifact" and message.get("executable")
                   and message.get("target", {}).get("name") == EXAMPLE]
    if len(executables) != 1:
        raise RuntimeError("Actual compiler executable identity ambiguous")
    after = {str(path.relative_to(source)): digest(path) for path in source.rglob("*") if path.is_file() and not path.is_symlink()}
    if (before != after or digest(arguments.example_source) != source_hash
            or (sink_hash is not None and digest(arguments.sink_source) != sink_hash)):
        raise RuntimeError("Source changed during compilation")
    executable_hash = digest(executables[0])
    durable = output / EXAMPLE
    shutil.copyfile(executables[0], durable)
    durable.chmod(0o700)
    if digest(durable) != executable_hash or digest(executables[0]) != executable_hash:
        raise RuntimeError("Compiler executable changed during preservation")
    record.update(executable=str(archive / "artifacts/permanent/current-ldsc-build" / EXAMPLE),
                  executable_sha256=executable_hash, committed_source_files=len(before), source_unchanged=True,
                  compiler_artifacts=len(messages), actual_build_exit=0, current_daemon_verified=False)
    (output / "build-record.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record))


if __name__ == "__main__":
    main()
