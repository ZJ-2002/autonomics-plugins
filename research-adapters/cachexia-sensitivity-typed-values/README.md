# Sensitivity typed-value engineering boundary

This companion converts the complete sensitivity summary TSV and its successful
upstream audit into four declared files: `values.parquet`, `typed_audit.json`,
`typed.log` and `schema.json`. It does not run EValue, metap or a statistical fit.

The fixed Python image is
`ghcr.io/zj-2002/single-cell-preprocessor@sha256:e2f9fcd5ccf9e97b0f0129466df5abb21ae47ed32f123f6953b79fd83d915e20`,
config `3144c037c6da31b27ea8d240e4bf013c45258099f44242193946d209ab24dc7b`.
The declared interpreter runs this adapter's mounted `scripts/typed_values.py`,
not the image's default preprocessing program. PyArrow must be exactly 25.0.1.

## Scoped image-change evidence

The former localhost image and this image are different. This is a new scoped
converter verification, not a same-content image migration or a claim that other
consumers of either image have been requalified. The converter script remains
SHA256 `7572cf2bf2839d147f3b7d60f4e0bc81adff3dc0fca8d08787f4320f20176b2c`;
only the manifest image-reference bytes change. Ports, resource declarations,
network isolation, upstream audit guards and numerical handling are unchanged.

One network-disabled container converted all 101 retained successful summaries
(66 EValue and 35 metap cases), comparing every field with the original Parquet,
schema and log. Finite numbers and infinities were checked at IEEE-754 binary64
precision; missing and NaN tags remain distinct while both materialize as null.
The immutable `source_position` uint32 axis, lexical coordinates, Arrow field
types/nullability, and all four output ports were checked. Historical cases
contain 471 finite values, 136 missing values, eight positive infinities and
three NaN tags.

An additional engineering fixture covers signed zero, both infinities, missing
and NaN tags. Six refusals cover wrong source hash, failed upstream status,
wrong row count, wrong scope, duplicate coordinate and numeric-kind mismatch.
Refusals retain audit/log and do not publish Parquet or schema outputs.

No statistical calculation or scientific hypothesis test was repeated. Only
330 small indexed original members were recovered from the existing cold
archive; its complete 27.5 GB hash was not recomputed. Existing complete metap
members were reused. No full environment was copied or new image built.

## Evidence identity and limits

- Session: `c4b20c559df740d2b17ada0aab2a105b`.
- Manifest seal: `fe08eaead439481a66423f502132e018816731ae103c8cbee18b212eea26d4f5`.
- Verification member: `permanent/sensitivity-typed-public-image/verification.json`.
- Verification SHA256: `3b546c282c0903f6704af6d011f5142d569acd04a4a135ffa430b512442171ac`.
- Worker and launcher exit 0; session CLEANED; its one owned container stopped.

This README and the manifest reference update follow the scoped verification;
they are source/publication increments, not claims that the old manifest selected
the new image during testing. Installation, resident source-pin activation and
gateway-submitted execution are separate deployment facts. This proof does not
grant study eligibility, causal validity, finite primary-result authority or G0.
