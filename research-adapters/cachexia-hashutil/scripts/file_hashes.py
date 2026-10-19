import csv
import hashlib
import os
from pathlib import Path
import re
import stat
import sys


def positive_integer(raw, maximum):
    if not re.fullmatch(r"[1-9][0-9]*", raw) or len(raw) > len(str(maximum)):
        raise ValueError("Expected canonical positive integer")
    value = int(raw)
    if value > maximum:
        raise ValueError("Integer exceeds resource bound")
    return value


def parameters(environment):
    algorithms = environment.get("HASHUTIL_ALGOS", "sha256 blake3").split()
    if not algorithms or len(set(algorithms)) != len(algorithms) or set(algorithms) - {"sha256", "blake3"}:
        raise ValueError("Algorithms must be distinct sha256 and/or blake3")
    chunk = positive_integer(environment.get("HASHUTIL_CHUNK_MB", "16"), 32)
    if environment.get("AUTONOMICS_INPUT_COUNT") != "1":
        raise ValueError("Declared File port requires exactly one staged input")
    return algorithms, chunk * 1024 * 1024


def identity(information):
    return (information.st_dev, information.st_ino, information.st_mode, information.st_size,
            information.st_mtime_ns, information.st_ctime_ns)


def file_digests(filename, algorithms, chunk):
    hashers = {}
    for algorithm in algorithms:
        if algorithm == "blake3":
            import blake3
            hashers[algorithm] = blake3.blake3()
        else:
            hashers[algorithm] = hashlib.sha256()
    before = filename.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("Input must be a regular file")
    size = 0
    with filename.open("rb") as stream:
        if identity(os.fstat(stream.fileno())) != identity(before):
            raise ValueError("File identity changed before reading")
        while True:
            block = stream.read(chunk)
            if not block:
                break
            size += len(block)
            for hasher in hashers.values():
                hasher.update(block)
        if identity(os.fstat(stream.fileno())) != identity(before):
            raise ValueError("File changed while reading")
    if identity(filename.stat()) != identity(before) or size != before.st_size:
        raise ValueError("File identity or size changed while reading")
    return [(filename.name, algorithm, hashers[algorithm].hexdigest(), size) for algorithm in algorithms]


def owned_path(filename, expected):
    try:
        observed = filename.lstat()
    except FileNotFoundError:
        return False
    return stat.S_ISREG(observed.st_mode) and (observed.st_dev, observed.st_ino) == expected


def unlink_owned(filename, expected):
    if expected is not None and owned_path(filename, expected):
        filename.unlink()
        return True
    return False


def main(environment):
    output = None
    temporary = None
    logfile = None
    log_stream = None
    owned = {}
    try:
        output = Path(environment["AUTONOMICS_OUTPUT0"])
        logfile = Path(environment["AUTONOMICS_OUTPUT1"])
        output = output.parent.resolve() / output.name
        logfile = logfile.parent.resolve() / logfile.name
        temporary = output.with_name(output.name + ".partial")
        filename = Path(environment["AUTONOMICS_INPUT0"])
        paths = (filename, output, temporary, logfile)
        if any(os.path.lexists(candidate) for candidate in (output, temporary, logfile)):
            raise ValueError("Output, diagnostic and fixed partial paths must be fresh; existing objects are not replaced")
        existing = [candidate for candidate in paths if candidate.exists()]
        inodes = [(candidate.stat().st_dev, candidate.stat().st_ino) for candidate in existing]
        if len({candidate.resolve() for candidate in paths}) != 4 or len(set(inodes)) != len(inodes):
            raise ValueError("Input, outputs and temporary publication paths must be distinct")
        log_stream = logfile.open("x", encoding="utf-8")
        observed = os.fstat(log_stream.fileno())
        owned[logfile] = (observed.st_dev, observed.st_ino)
        log_stream.write("status\tRUNNING\nidentity_scope\tSTAGED_BYTES_NOT_SOURCE_AUTHENTICITY_NOT_G0\n")
        log_stream.flush()
        algorithms, chunk = parameters(environment)
        rows = file_digests(filename, algorithms, chunk)
        if not owned_path(logfile, owned[logfile]):
            raise ValueError("Diagnostic pathname ownership changed")
        with temporary.open("x", newline="", encoding="utf-8") as stream:
            observed = os.fstat(stream.fileno())
            owned[temporary] = (observed.st_dev, observed.st_ino)
            writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
            writer.writerow(["file", "algorithm", "digest", "size_bytes"])
            writer.writerows(rows)
        if not owned_path(temporary, owned[temporary]) or not owned_path(logfile, owned[logfile]):
            raise ValueError("Temporary or diagnostic pathname ownership changed")
        os.link(temporary, output, follow_symlinks=False)
        owned[output] = owned[temporary]
        if not owned_path(output, owned[output]):
            raise ValueError("Published output pathname ownership changed")
        if not unlink_owned(temporary, owned[temporary]):
            raise ValueError("Temporary pathname changed before retirement")
        log_stream.write(f"status\tPASS\nfiles\t1\nrows\t{len(rows)}\nchunk_bytes\t{chunk}\n")
        log_stream.flush()
        if not owned_path(logfile, owned[logfile]):
            raise ValueError("Diagnostic pathname ownership changed after publication")
        log_stream.close()
        return 0
    except Exception as error:
        for candidate in (output, temporary):
            if candidate is not None:
                try:
                    unlink_owned(candidate, owned.get(candidate))
                except OSError:
                    pass
        message = f"status\tBLOCKED\nerror\t{type(error).__name__}: {error}\n"
        if log_stream is not None and not log_stream.closed:
            try:
                log_stream.write(message)
                log_stream.flush()
            except OSError:
                pass
        print(message, file=sys.stderr)
        return 2
    finally:
        if log_stream is not None and not log_stream.closed:
            try:
                log_stream.close()
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(main(os.environ))
