# Donor candidate source update

The complete B worker loads `research-adapters/b-donor-method` from the unified
catalog. Its R port wrappers embed the candidate implementation; changing the
engine's reference script alone cannot update that candidate.

The five candidate/wrapper files in plugin commit `1e8bd37` are byte-identical to
the corresponding `study_plugins` files in engine commit `400020c7`. They fix the
fit order by jointly sorting count columns and model metadata by observation ID.
The original source-order audits and scientific families are preserved. Four
loaded wrappers are checked against the candidate source in a permanent test.

The original 2026-10-12 import index and each `component-source.json` remain
unchanged. The existing source-evolution ledger now binds these five changed
paths to their actual plugin Git commit and blobs. Catalog verification includes
the eleven explicitly imported governance adapters and validates their preserved
import records before accepting recorded Git evolution. The governance checker
uses the same verification when a current file differs from its original import.
Unrecorded changes, absent Git objects, wrong commits/blobs and unknown imports
continue to fail. Only the two donor families change in the release inventory.

Actual local validation: 40 catalog, source-evolution, governance and wrapper
source-binding tests passed without skips. The current inventory matches the
release lock. Nine new tests, plus the renamed governance test, are explicitly
registered in `quality/required-tests.json`. The entire 894-case gate and remote
CI have not been run for this update.

The loader injects the script into the container at execution time; this source
change does not change the pinned `67cb…` R/package runtime image. New source and
catalog identities must be bound by the next method qualification. This update
does not deploy plugins, qualify DESeq2, certify a clinical model or grant G0.
The prior full-gene numerical failure is retained. The unchanged numerical
tolerances and full native method criterion still require actual validation.
