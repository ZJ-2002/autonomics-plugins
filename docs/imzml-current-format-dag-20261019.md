# imzML publication repair and current format DAG evidence

Scope: frozen format ingestion, **not full pyimzML API equivalence or scientific
analysis admission**.

The old adapter overwrote late-arriving analytical files and foreign failure
diagnostics after an absence check. Three baseline unit tests reproduced two
failures. The repaired publisher uses exclusive hard links, identity-checked
rollback and non-overwriting failure diagnostics. Seven self-cleaning tests now
pass, including all nine dangling output paths and foreign replacement during
rollback. The numerical calculator is mocked in these publication tests.
This is not an all-port transaction or hostile same-UID race security guarantee.

All 14 old non-entry function ASTs remain identical, including XML validation,
binary decoding, signal sums, and the full calculation. The manifest, image,
frozen requests, inputs, comparison tolerances and independent reference script
are unchanged.

## Actual isolated execution

Six current SDK DAGs completed with all nine file ports and native Parquet
read/materialization: healthy, exact int64 signals, zlib, float16, repeated
coordinates, and signed intensities. Each was checked using the unchanged
independent reader against the original frozen XML/binary pair. Full raw signals,
precision, coordinates, windows, integer shadows, original bytes, and output
materialization passed. Four profiles additionally compared every spectral array
with the installed author pyimzML 1.5.5 parser.

Zlib and float16 are explicitly labeled extensions: their independent format
decoding passed, but **they are not certified equivalent to pyimzML 1.5.5**.
The official parser equality must not be generalized from four profiles to these
two extensions or the entire API. The prior 80-case proof is retained, not
reported as 80 newly executed DAGs.

Four failure graphs rejected a wrong source hash, mismatched XML/ibd UUID,
corrupt zlib stream, and existing foreign analytical file. Each exposed zero
analytical ports and skipped both downstream nodes. Failure audits retained the
specific expected reasons; the foreign file stayed unchanged. All 16 owned
containers were observed stopped.

## Official references and boundaries

- [imzML specification repository](https://github.com/imzML/imzML)
- [Author pyimzML implementation](https://github.com/alexandrovteam/pyimzML)
- [pyimzML 1.5.5 release](https://pypi.org/project/pyimzML/1.5.5/)

This does not establish full XSD validation, arbitrary mixed-precision schemas,
real resource eligibility, donor/organ pairing, physical coordinate conversion,
mass annotation, molecular flux, secretion, ATP interpretation, large-scale
resource admission, resident deployment, or persistent recovery. No new spatial
null model was selected. B-S remains CONDITIONAL_NOT_READY; GS01 remains OPEN.
Technical success is not scientific release or G0 PASS.
