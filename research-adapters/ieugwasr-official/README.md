# Explicit official ieugwasr calls — integration candidate

These are new explicit addresses, **not aliases for the legacy native REST
nodes**. The original request JSON and its hash identify the exact author
operation and arguments. The generic kind name is not itself a method identity.

| Kind | Required files | Allowed author operations |
|---|---|---|
| `official_ieugwasr_call` | request JSON | associations, phewas, tophits, variants_rsid, variants_chrpos, gwasinfo |
| `official_ieugwasr_call_with_dataset` | request JSON + original data.frame RDS | ld_clump_api only |

The framework's input ports are fixed required ports, not optional. No dummy
dataset is required for request-only calls. The dataset variant checks the
actual input count, operation and non-NULL data.frame; a NULL RDS cannot switch
it into a different operation. The author package's internal `ld_clump_api`
helper is called directly; it is not reimplemented or presented as exported.

The thin dispatch prefix enforces only that interface. Its complete suffix is
the unchanged [staged official wrapper](../../staged-adapters/ieugwasr-official/scripts/official.R),
SHA256 `ea7815eef5b9d18681b87c288dc0d7097311a5fe32a2fe16bee5e82ce7e25931`.
The immutable image, thirteen unmodified author source/license files and build
records remain in [the staged runtime source](../../staged-adapters/ieugwasr-official/LOCAL_BUILD_STATUS.md);
no dependency environment is copied into this family.

## Scope and availability

The manifest's `private` wording records the earlier registry state, not a
current visibility guarantee. An anonymous observation recorded at
`2026-10-23T11:44:23.999039Z` fetched the exact image manifest
`ghcr.io/zj-2002/ieugwasr-official@sha256:c8631fb88461135ea1b570f0e08a5bfb04366ef2bc835e874d30c7326fdc2395`
and its configuration with HTTP 200. The raw manifest hash and configuration
hash `38114ac009e0d023c262aa1b67eb459127810a345507b95cbc96ba515e9f5a2e`
matched their immutable descriptors. The small technical observation record has
SHA256 `1dba8cedfde5116ec136af9505abe9505cba77ddeb7932e45185073d4414c138`.
No user credentials were supplied; only an anonymous registry token was used.
No image layers were downloaded. This does not prove a clean host can retrieve
all layers, current production binding or scientific release. The manifest,
dispatcher and pre-build source lock remain unchanged.

Both kinds explicitly pin `R_LIBS` and `R_LIBS_USER` to the isolated author
library. The inherited runtime's normal R startup otherwise puts the retained
1.1.0 site library ahead of 1.2.0, even with user startup files disabled. The
official wrapper still refuses any version other than 1.2.0; the environment
pin fixes library precedence, not author code or the original MRlap image.

This is an HTTP client, so the candidate manifest correctly requests `egress`.
Offline technical DAG tests must use a separate hash-bound fixture manifest
with `isolated` networking and only HTTP transport interception. Such tests do
not prove authenticated live API availability.

The existing manifest/runtime surface has ordinary environment values, not an
audited secret-reference resolver for this family. **Live credential admission
is pending.** JWT values must not be placed in request JSON, DAG parameters,
public environment templates, command arguments or scientific evidence. The
manifest does not claim that inheriting the host's key automatically transfers
it safely into a container.

Outputs 0–3 are full author RDS, typed data.frame JSON, technical audit JSON and
log. Non-atomic/list/classed columns cannot be projected and fail the complete
publication rather than returning a partial success. Original author methods,
errors, defaults, sorting and batching are retained; full method parameter-domain
or live-service certification is not claimed.

`gwasinfo_search` remains unsupported: it has no matching author function.
Legacy REST defaults and parameter names must not be silently translated or
reused. In particular proxies, PheWAS thresholds/batches, top-hit window and
server-clumping controls require explicit author-method migration review.
