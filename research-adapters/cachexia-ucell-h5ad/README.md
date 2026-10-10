# H5AD to official UCell and score writeback

These staged adapters do not implement UCell statistics or alter production plugins.
The connected route uses frozen H5AD/signature contracts, official R UCell 2.16.0,
and explicit score-column mapping. Preparation requires exact lexical identities,
nonnegative finite expression, a specified X/layer, fixed parameters and hashes.
Raw counts must additionally be nonnegative int32-compatible integers.

The matrix allocation cap is at most 2,000,000 entries. Whole-H5AD writeback loads
all original components, so this cap is not a guarantee of total memory usage.
Writeback verifies the official node's parameter/input/output identity audit,
requires the exact unique cell set, aligns by cell IDs, and refuses column or
provenance collisions. It preserves the original AnnData content, adding only
the declared obs scores and `uns['cachexia_ucell_chain']`.

Signed features and official impute/skip semantics are retained. At least one
present gene per program is required by this narrower adapter. Missing members
remain in the ledger; this is not scientific signature-coverage approval.
Undefined scores, inconsistent hashes or failed upstream statuses block output.
Audits provide identity linkage, not authentication of biological provenance.

No smoothing, gene mapping, batch handling, donor-level hypothesis test, B-SPEC
singscore substitution, real-cohort qualification, resident daemon deployment
or G0 is granted by these adapters.
