# MTAG adapter output-publication repair

The explicit four-output `research-adapters/cachexia-mtag` route now writes its
complete TAR, original log, index and audit into private staging before publishing
each destination with an exclusive hard link. On incomplete publication it
removes only links whose observed device/inode still identify its own files.
Existing regular files and dangling links are refused, normalized aliases are
rejected, and packaging/JSON failures do not publish partial normal outputs.

The same eight self-cleaning filesystem controls reproduce five failures before
the fix and pass after it. Their raw files contain explicitly synthetic bytes;
they are **not** author MTAG numerical references. Existing author command,
parameter, runtime-identity and result-collection functions are AST-identical.
The previous packaging function is unchanged apart from its new internal name.

This is per-file exclusive publication plus identity-checked rollback, **not** an
atomic four-file transaction or protection against a hostile parent-directory
replacement. A cross-filesystem hard-link failure is an error, not permission to
overwrite or fall back to copying. Private stage cleanup is attempted on exit.

No MTAG estimation was performed for this repair. It does not qualify the
original three-output plugin, the adapter's entire parameter domain, a resident
deployment, real-panel research execution, or scientific/G0 approval. Historical
host numerical evidence must be reconciled separately with the frozen image and
an actual isolated execution before the node's remaining ledger slot is closed.

The frozen image `ghcr.io/zj-2002/mtag@sha256:d89f1e607804ec66a26f12151e6f6fcc495a1f67a077d9ac900085a9b77cb7e8`
also executes all eight controls successfully with Python 2.7.18, NumPy 1.16.6,
pandas 0.24.2, SciPy 1.2.3 and joblib 0.14.1. All 11 declared author source-file
hashes are checked inside the image. One owned engineering container is confirmed
stopped; its 512 MiB toy-test limit is not a production resource acceptance.

The first image test exposed a Python 2 test-harness issue: functions returned
from `runpy.run_path` could retain cleared temporary-module globals. The tests now
compile the same unchanged production source into a persistent namespace. The
same eight cases still reproduce five baseline failures and pass after repair.
This was a test-loader correction, not a change to the estimator or wrapper.
The successful combined record is session `80b8c4861dda4ed7a9b81355fe14caff`, seal
`58b713d02f1d365d2df6aca9860aa46fc44cf7ab3860c067909989b81175ad7b`.
Matching package version strings and author source do not establish complete
cross-runtime BLAS/binary identity or replace numerical/DAG qualification.

## Early occupied-output refusal

The entry now validates all four normalized output destinations before parameter
setup, package loading or author estimation. The same validation runs again at
publication time to catch later competitors. This avoids computing a large MTAG
job only to discover a pre-existing result at the end.

A ninth control proves that an occupied output reaches neither parameter setup
nor the author runtime, while preserving foreign bytes. Against the original
entry the same nine controls reproduce six failures; all nine pass in both the
current host harness and frozen Python 2 image. Existing method functions and
raw-packaging body remain AST-identical; the entry differs only by moving its
original output-path assignment forward and adding this explicit preflight.

Current entry SHA256 is
`ebe8c9a89b94a20987b2386d7732e8af3be513afd0ad8b83ce50bdd69b7a8014`.
The combined record is session `43aac6c9228f47e78764ebb57372bf06`, seal
`d18f4e1ee3abee6b0dcd11ee58a2c8c2d0f94dd0e55a987d0deafb41fbe6f5b5`.
It performs zero statistical estimations. Earlier eight-control records are
retained for their exact earlier source identities, not relabelled as this entry.
