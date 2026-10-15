# Frozen v4.3.2 A harmonisation adapter

This candidate exposes only `frozen_a_v432_harmonisation`, with no parameters.
It accepts six exact frozen files in manifest order: the existing 39-row clumped
instrument table, the 3,139-row outcome-match table, A config, certificate,
R dependency lock and original `g0_v432_methods.R`. The contract lists their
SHA256 values. The existing digest-pinned image provides official R 4.6.1 and
TwoSampleMR 0.7.11. It was installed from a pinned source tarball and its actual
`RemoteSha` and `GithubSHA1` fields are absent, not the host's Git metadata.
Runtime checks bind its exact DESCRIPTION SHA256 and all 171 namespace-owned
function names, formals and bodies to a fixed aggregate. The identical function
inventory was independently compared with the frozen host package whose actual
`RemoteSha` is `d4df21929fdabeb2f89686ffaad0db5f56973d64`.
That identity proof is session `4f717274ece54f4396b8097b4db0ad8a`, with its
seal in the contract. It is not whole-environment certification. Provenance
retains observed container `TwoSampleMR_RemoteSha=null` and distinguishes the
source commit supported by host identity from observed container metadata.

The adapter extracts the exact 2,172-byte `qualify-A` branch from the supplied
frozen scientific source, checks its own fixed SHA256, and evaluates that
unaltered text. Only the frozen read/write helpers redirect I/O. Its real calls
remain official `format_data` twice and `harmonise_data(action=2)`, with seed
432202610 and the original INFO/frequency qualification logic. There is no
Rust implementation or copied statistical formula.

The first three ports reproduce the original full harmonisation audit,
qualified input and qualification JSON; each must match the existing frozen
output hash. Port 3 records six input identities, original branch identity,
actual software identity and explicit unexecuted stages. Port 4 is the log.
The provenance is not an execution signature or scientific authorization.

## Deliberately narrow contract

The original branch computes F but does not exclude F below 10. Official
TwoSampleMR 0.7.11 uses the open ambiguous EAF interval `(0.42,0.58)`, whereas
the active project requires inclusive boundaries. The frozen current 39 IVs
contain neither a boundary case nor F below 10. After the original branch runs,
the adapter independently requires all 39 rows to satisfy the active inclusive
EAF, INFO and F envelope. A mismatch refuses publication; it never silently
changes the branch or selects a replacement set. This does not qualify a
generic harmonisation route for different inputs.

Raw GWAS streaming/QC, PLINK 1.90b7.2 clumping and LD checks have existing
frozen execution records, but this node does **not** reexecute or independently
prove those stages. It does not fit MR, use proxies, correct unresolved O2
overlap, enable another edge, alter family denominators or grant G0. Original
whole-project byte verification, resource admission and any required scientific
review remain separate caller obligations. Current source availability is not
proof that a resident production daemon loaded or executed this candidate.

## I/O lifecycle

All six inputs must be regular files. Five output paths must be distinct,
fresh and separate from inputs; existing files, directories and dangling
symlinks are refused before writes. Computation uses owned mode-0700 staging
directories beside each output. A fresh log is linked exclusively first;
the four normal outputs are linked only after computation and input rechecks.
Each link and the complete published set are checked for device/inode and
content. On an ordinary caught failure, rollback removes only still-owned,
unchanged normal outputs, preserving foreign replacements and the diagnostic
log. Replaced staging directories and logs are not blindly removed or appended.

This reuses the separately tested A numerical adapter's publication design,
not its scientific implementation or deployment certificate. Hard-link support
and writable existing destination parents are required. Multi-file crash
atomicity, power-loss durability, adversarial concurrent replacement and resume
are not certified. An interrupted or incomplete output directory is not success.

Ordinary toy tests cover structure, fixed contracts and publication control
with a deliberately replaced non-scientific test callback. They do not relax
production source hashes or perform real harmonisation. Actual official
container parity and isolated DAG execution require a separate managed proof.
