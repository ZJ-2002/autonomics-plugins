# Survey technical summary type boundary

This engineering adapter calls official PyArrow 25.0.1 to serialize an explicitly
typed table. It does not compute survey statistics or grant research eligibility.
Two inputs are the complete successful survey TSV summary and its matching audit.
Four outputs are Parquet, audit, log and schema. Test/row/field/status coordinates
remain strings; values are nullable float64; source positions are exact uint32.
`MISSING` and `NAN` become null values but keep their distinct status labels.
Infinities remain explicit. No row is discarded, imputed or selected.

Only the frozen synthetic technical survey profile is supported. Source and raw
contract hashes, lexical coordinates and cardinality must match. A matching audit
is an identity/shape contract, not authentication of arbitrary forged audits or
proof that upstream statistics are scientifically valid. The full author design
and result RDS remain in the upstream node's separately retained file port.

The adapter refuses existing paths and dangling symlinks, writes privately,
publishes exclusively and rolls back only outputs it still owns. Downstream
consumers must preserve `source_position`; physical row order is not a guarantee.
The pinned local image must already be installed. No dependency installation,
production deployment or G0 is implied.
