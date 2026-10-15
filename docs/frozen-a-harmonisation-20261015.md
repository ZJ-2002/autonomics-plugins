# Frozen A official harmonisation: bounded direct proof

## Node card

`research-adapters/frozen-a-harmonisation` provides one explicitly scoped kind,
`frozen_a_v432_harmonisation`. It is not automatically enabled, not the generic
0.7.9 harmonisation kind, and not a new MR estimator. It runs the exact original
2,172-byte `qualify-A` body from frozen scientific code
`f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd`.
The block hash is `50be9627766c996714e1c18ef7c32862ed2f9807814a9f61b5b3bd7c476e4f1d`.

| Port | Input | Meaning |
|---|---|---|
| 0 | A_LD_CLUMPED_INSTRUMENTS.tsv | Previously qualified 39 exposure instruments |
| 1 | A_OUTCOME_MATCHES.tsv | Frozen outcome matches, not outcome-selected instruments |
| 2 | A_ANALYSIS_CONFIG.json | Fixed v4.3.2 A contract |
| 3 | G0_V432_CERTIFICATE.json | Existing bounded legacy permission, not a new signature |
| 4 | R_DEPENDENCY_LOCK.tsv | Frozen official package versions |
| 5 | g0_v432_methods.R | Exact original qualification source |

Every input must match its fixed complete SHA256. There are no selectable
parameters or synthetic-data hash bypasses. Outputs are the full harmonised
audit TSV, qualified TSV, qualification JSON, identity/provenance JSON and log.
TwoSampleMR 0.7.11 `format_data` and `harmonise_data(action=2)` perform the
statistical-method operations in R4.6.1. The original body's INFO and palindrome
frequency checks are unchanged. An additional fail-closed envelope refuses any
violation of the current F, INFO or inclusive EAF exclusion contract; it does not
silently alter the original algorithm or select a different instrument set.

This distinction matters: the original frozen qualification body does not itself
explicitly filter F<10 or the closed EAF endpoints. All39 current instruments
pass the additional envelope. This does not establish generic input eligibility
for arbitrary future GWAS data. The node does not rerun raw-source QC, clumping,
pairwise LD, overlap diagnostics, MR estimates or the whole-project verifier.

## Actual package identity, without invented metadata

The first actual container attempt refused execution because this image's
codeload-tar package installation has no `RemoteSha`. Failed session
`1be7771a89c24509a2fe67762a12c6eb`, manifest
`3bdbef0e1127a2429ecc5b70853881dbd332794975d4b718a3f4eb5caff57831`,
is retained as failed, not recast as a successful method guard.

The repair does not ignore the missing identity. Managed session
`4f717274ece54f4396b8097b4db0ad8a`, manifest
`bf9ce79a277c51193bb7a8af3be6ca7c9231f14567d9e7f1d0fbcc7016364f48`,
compared all171 package-owned R functions' names, formals and bodies against the
unchanged frozen official host package with actual RemoteSha
`d4df21929fdabeb2f89686ffaad0db5f56973d64`. Every function hash matched;
the aggregate is `127840d8db8ff340b824c6f882cfa263746f5ab93623629c28d19a15968efe73`.
All41 host package files remained unchanged. All20 archive members were rehashed.

Runtime now requires the exact image digest, package version, actual container
DESCRIPTION hash, null observed RemoteSha/GithubSHA1 and this complete function
inventory/hash. Provenance explicitly distinguishes the null observed field from
the source commit supported by the frozen host identity. It does not manufacture
an installation field. This is R-function identity evidence, not byte identity of
the entire installed package, dependency environment or equivalence for all uses.

## Real direct execution

Session `a685dfe45f9448b78083b7c510844912`, manifest
`90b5a6eabc39f3d24caba443a1c3494a0c3bcc30168b59f0c4c4561fcb8d7e29`,
completed with integer worker exit0 and CLEANED scratch. The root reviewer
rehashed all123 archive members. All six inputs and five outputs were exercised.
The three complete qualification products matched the existing canonical bytes
and a separate official R process executing the unaltered original branch.
This is an interface/source replay, not an independent reimplementation of the
official harmonisation algorithm.

Each of six deliberately modified input copies actually failed with exit2, the
specific frozen-source diagnostic and no normal result publications. A preexisting
foreign output retained its device/inode/content identity and prevented execution
before log mutation. Nine owned containers finished; no owned containers remained.
The six canonical inputs were unchanged. The original whole-root read-only
verifier actually ran after this replay and passed46,786 checks over23,669 files.
No MR effect estimates or new biological analysis were computed.

The twelve self-cleaning tests include source/schema checks, unchanged original
block extraction, EAF/INFO/F refusals, existing-output protection, own-file rollback
and preservation of foreign replacements, plus changed/missing namespace-function
refusals. These tests are not twelve nodes or deployment certificates.

## Remaining admission and documentation corrections

Current disposition is `SCOPED_DIRECT_OFFICIAL_HARMONISATION_PROVEN_DAG_PENDING`.
A dedicated real-input no-fit DAG scope is being added and must actually execute
before claiming graph qualification. The production daemon has not restarted or
hot-loaded this kind. This does not close raw-GWAS QC, official PLINK1.90b7.2
clumping/pairwise completeness, the276-edge/288-path family ledger, all conditional
A/B branches or scientific review. B-S stays CONDITIONAL_NOT_READY; GS01 OPEN.

The generic plugin's two action descriptions are corrected using the
[official 0.7.9 source](https://raw.githubusercontent.com/MRCIEU/TwoSampleMR/v0.7.9/R/harmonise.R):
action1 assumes forward-strand coding, action2 uses frequencies to infer
palindromic strands, and action3 drops all palindromic variants while correcting
non-palindromic strands. Its statistical script and version are unchanged.
The frozen MR README no longer incorrectly calls the current catalog a503-person
panel; that MR node consumes prequalified instruments and loads no panel.

Only code, hashes and sanitized evidence summaries are public. Raw study inputs,
qualification payloads and local launcher archives are not published. Technical
success does not grant G0 or change viewing history, frozen designs or results.
