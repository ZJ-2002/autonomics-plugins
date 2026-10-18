# Official EValue route for the existing `evalue` candidate

## Selected implementation

Use `research-adapters/cachexia-sensitivity`, kind `cachexia_evalue_official`, for the official-package route. It calls the unmodified CRAN EValue 4.1.4 functions through `getExportedValue("EValue", paste0("evalues.", measure))`, on the pinned R 4.6.1 image. This card does not select or certify the native Rust `evalue` implementation, and does not claim a new Rust repair.

Supported scalar measures are RR, OR, HR, OLS and standardized MD. The scientific meaning of an estimate, the rare-outcome assumption, OLS outcome SD/exposure contrast and the target `true` must be supplied explicitly; they are not inferred from a significant result. E-values describe sensitivity to unmeasured confounding, not causal identification.

## Input/output contract

- Input 0: frozen effect JSON with effect ID, measure, estimate, limits/SE, SD/contrast, target and rare-outcome flag.
- Input 1: frozen request JSON binding the exact input hash, lexical effect/test IDs, complete family size, method contract and auxiliary non-causal role.
- Outputs 0–4: `values.tsv`, complete official `state.rds`, `audit.json`, `sensitivity.log`, `input_ledger.tsv`.
- The typed companion preserves original ordinals and `FINITE/MISSING/NAN/POS_INF/NEG_INF` semantics. Missing or infinite author output must not be replaced by a finite value or presented as a scientific qualification.

This is a different interface from the native zero-input/configuration-only scalar node. Do not wire its one DataFrame output as though it were the five-port official route.

## Existing proof reused

The exact current method and typed-companion source bytes match their originally executed snapshots. The sealed record contains 66 positive and 22 refused EValue materializing DAGs. The independent review compared complete official objects, classes, dimensions, attributes, arguments, warnings/messages and typed original-coordinate readback. Its EValue subset reports 260 finite fields, 128 missing fields and zero maximum absolute difference. The 117 namespace-function identities are the combined EValue/metap namespace check, not 117 EValue methods or nodes.

No algorithm or statistical computation is rerun for this source-identical reconciliation. The unrelated `cachexia_combine_pvalues_official` method and its metap omnibus maximum are not certified by this card and must never replace a frozen intersection–union raw `max(p_edge)` path test.

## Current research/deployment boundary

The frozen v4.3.2 active text materials and software-lock rows inspected for this review do not contain an explicit EValue enablement or parameter contract. This is not authority to add the method to the study or silently retire the fixed candidate. A technical agent must not choose its effect, outcome rarity, target or scientific interpretation on behalf of the approved plan.

The image is still the locally named, digest-pinned proof artifact. Portable installation, present runtime availability and resident deployment have not been requalified by metadata reuse. The case evidence covers the tested scalar branches, not the entire EValue API or every unknown input. No scientific release or G0 is granted; this conditional auxiliary candidate does not independently authorize or block unrelated qualified A/B work.

Versioned hashes and the scope-limited evidence reference are in `evidence/evalue-official-route-20261018.json`.
