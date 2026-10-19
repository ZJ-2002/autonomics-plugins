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
