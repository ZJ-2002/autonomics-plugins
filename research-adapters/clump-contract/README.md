# Exposure-only official PLINK adapter — qualification candidate

This candidate accepts a frozen v4.2.1 clumping configuration, an independently
admitted normalized **complete exposure** SNP TSV and the original admitted
panel manifest. No outcome input or outcome parameter exists. It does not
normalize a raw GWAS, approve its phenotype definition, sign G0 or register
itself in production. Correlated/cis instruments need another qualification.

The fixed image contains R4.5.1 and official PLINK2 a.6.26. PLINK binary content
is checked against the frozen lock before use. The actual source tag resolves
to `504a7ee92ab454b44255faa259be8f7b7758d32f`. Original reference manifest bytes,
all 66 BED/BIM/FAM file hashes and sizes, ancestry, build and complete file
universe must match. Full biological reference-panel QC still needs independent
acceptance; filename, digest and population labels alone do not supply it.

Input columns are exactly `snp`, `chr`, `pos`, `beta`, `se`, `effect_allele`,
`other_allele`, `eaf`, `pval`. The source is read in 10,000-line chunks. Invalid
normalized rows and strict P>=5e-8 exclusions remain in SOURCE_QC. All source
IDs, including nonsignificant ones, undergo external sorting and duplicate
checks; candidates alone stay in memory. Missing reference variants are
explicit exclusions, without weakening the P threshold to fill an IV count.
Reference coordinates and strand-equivalent biallelic SNP alleles are checked.

The variant ledger has explicit `SOURCE_QC` and `CLUMP_FINAL` phases, each with
its own universe. Two phases can contain the same variant ID; they are not
independent statistical tests or a reduced family denominator. Main family
membership remains the separately frozen edge/estimand universe.

PLINK's actual tie comparator uses its reference allele index. The adapter
therefore uses official `--make-pgen --sort-vars ascii` on the candidate
reference subset before official LD calculation. Direct sorted BED output is
unsupported in this version. This enforces P/chromosome/position/ASCII-ID ties
without changing input P values. Haplotype MLE is explicitly locked, consistent
with the existing PLINK2 route; it must not be conflated with unphased genotype
correlation or silently switched to another reference/LD method.

The protocol's retained r2<0.001 is strict. A real pinned-image regression found
that this PLINK version's fast clump path and phased LD matrix disagree at a
mathematically exact boundary. Lowering its clump CLI cutoff by one IEEE754
step did **not** solve that example. Selection now uses official
`--r2-phased square bin` values and the frozen greedy P/chromosome/position/ID
order, rejecting r2>=0.001 within an inclusive 10 Mb window. Every candidate
participates; a rejected lead does not remove a later candidate. Official clump
still runs as a diagnostic with its original predecessor cutoff, and differences
are explicitly recorded. No input P or scientific threshold is perturbed.

The qualified matrix resource bound is 4096 available candidates per chromosome.
Exceeding it blocks the entire node; it never truncates candidates. Matrix order,
dimensions and hashes are checked. Undefined, nonfinite, asymmetric or invalid LD
(including monomorphic variants) blocks publication; missing LD never implies
independence. This adapter uses the official estimator's numeric result, rather
than claiming exact rational LD for arbitrary phased/ambiguous genotypes.

Outputs are selected exposure TSV, actual selection evidence JSON, complete
phase-labelled QC ledger, execution audit JSON and the original official LD
matrices/order tables in a deterministic tar archive. The latter can be rehashed
and independently used to reconstruct selection after checkpoint recovery.
The audit includes exact
input/software/panel identities and executed commands/logs. Selection evidence
binds the actual audit bytes and selected exposure bytes; it is written after
the audit to avoid a circular self-hash. Container publication still requires
successful exit, strict engine evidence and separate signed method acceptance.
An empty selection is a valid terminal result: downstream MR retains an
unestimable edge and supplies NA, rather than relaxing thresholds or deleting
its family row.

`clump.R` is the sole method source; regenerate the manifest-hashed wrapper
using `python3 scripts/generate_clump_contract_wrapper.py`. Offline and actual
OCI regressions are in `scripts/tests/test_clump_contract.py`. Missing or
different software is an explicit skip, never qualification. Synthetic panels
and normalization evidence cannot be used as a real study approval.

Current acceptance covers explicit synthetic reference/genotype cases and
actual OCI wrapper handover. It is not a frozen-worker full A DAG acceptance.
Complete real source normalization/panel science admission, larger candidate
universes beyond the matrix resource bound, MRlap diagnostics and further MR
sensitivities remain required before declaring the full formal A chain ready.
