# PLINK2 clumping plugin

Canonical kind `plink2_clump`, restored from the original
`auto-nomics/plink2-plugin` revision
`a72fe6f6839a8c85137c69499d87a72b58bf0f61`. This is a general offline
LD-clumping plugin, not a cachexia-only statistical implementation.

## Method and identity

The immutable image remains
`ghcr.io/auto-nomics/autonomics/plink2@sha256:998315bf1c34c1c7ef276e93ca6c043dd1982c027c7264325505a9a0adc6d1d2`.
Its actual PLINK2 binary is byte-identical to the freshly downloaded author
release `v2.0.0-a.6.26` Linux AVX2 asset. Binary SHA256:
`6a783e2d5e331f5b1eb7dea9f5331490202053cb3ce217ce227a36171bdb2169`.
Release asset SHA256:
`f578a450af382d7dd6665aecf0ca1d280971c2b3d5bb5556efbf9266c4c8da0f`.
The author tag resolves to `504a7ee92ab454b44255faa259be8f7b7758d32f`.
The old image's source label is incorrect; it is not used as proof of binary
identity. The Dockerfile provenance label is corrected, but this acceptance
does not certify a new rebuild of that Dockerfile.

[Official clumping documentation](https://www.cog-genomics.org/plink/2.0/postproc#clump)
describes greedy index selection, haplotype-based LD and founder handling.
The node invokes the author binary, rather than implementing these formulas
independently. `clump_p1` is an inclusive index P threshold; `clump_p2`
controls SP2 reporting, not a second instrument-eligibility threshold.
The fixed binary requires `clump_r2 < 1 - 2^-44`; the manifest and script
enforce this exact bound. The original node contract additionally requires
`clump_p2 >= clump_p1`. Positive integer kb windows and autosomes 1..22
are supported, not every flag or fractional-kb option of the author CLI.
No allele harmonisation, effect estimation or genome-build conversion occurs.

## Input and output

One File input contains a rectangular report. `twosamplemr` and `plink_assoc`
select SNP/P fields from tab-separated or PLINK whitespace reports;
`ieu_open_gwas` selects variant/pval from CSV. Gzip is detected by its magic
bytes and fully decompressed with integrity checking. IDs stay literal;
leading zeros, the literal ID NA and quoted commas are not cast or lost.
Missing P must be NA, not zero. Duplicate association rows and TEST columns
remain available to the official binary; no hidden deduplication occurs.
Empty ancillary cells become NA explicitly. Empty headers, ragged rows,
invalid P, or fields not representable as single PLINK tokens are rejected.

The original three File ports are preserved:

| Port | File | Meaning |
|---|---|---|
| 0 | plink2_clump.log | Input hash, staging location and official per-chromosome diagnostics |
| 1 | plink2_clump.clumps | One SOURCE_CHR-prefixed header plus complete official clump rows |
| 2 | plink2_clump.chromosomes.tsv | `chr<TAB>number` marker records for processed chromosomes |

Port 1 deliberately fixes the old repeated-header/nonrectangular concatenation.
Empty successful results retain the header; this is a wire-format change,
not a new clumping algorithm. Port 2 is a marker stream, not a headered table.
Raw per-chromosome `.clumps`, missing-ID reports and logs remain in the
unique workspace staging directory named in port 0; they are not extra
declared ports or guaranteed archival exports.

Existing outputs are refused. Analytical tables publish only after all
requested chromosomes finish. Failure diagnostics/intermediates remain;
there is no claimed multi-file atomic transaction or concurrent-writer lock.
The manifest declares isolated networking, 2 CPUs and 2 GiB; the binary
uses two threads and a required 1024 MiB workspace. This is not a global
concurrency/quota guarantee.

## Reference and installation

Binding `plink_ref` mounts
`wjixiang/catalog-plink-ref-1000g-eur-binary` at `/panels/plink_ref`, with
one BED/BIM/FAM triplet per requested chromosome. The isolated acceptance
checks all 66 payloads of the real GRCh37/EUR Phase3 bundle, while its
association P values are synthetic. This does not grant reference/cohort
eligibility for any study.

An explicitly selected deployment proposal uses:

```toml
[[plugin]]
name = "plink2"
git = "https://github.com/ZJ-2002/autonomics-plugins.git"
rev = "<reviewed full 40-hex commit>"
subdir = "plugins/plink2"
```

No production daemon or frozen profile is changed by this repository.

## Mandatory local boundary tests

Provide the executable 22-chromosome synthetic fixture retained in the
acceptance packet and a NEW evidence directory:

```sh
PLINK2_BOUNDARY_PANEL=/path/to/synthetic-panel \
PLINK2_BOUNDARY_EVIDENCE=/path/to/new-evidence ./test_plink2_clump.sh
```

Tests invoke the fixed real image without network access. Missing image,
panel or environment is failure, not a skip. This entry point does not
build/push an image, publish a panel, run Cargo, or read production VFS config.
The shared catalog tests separately validate inventory and source hashes;
they do not execute the statistical method.

## Acceptance limits

See `evidence/canonical-plink2-clump-20261011.json` for versioned technical
evidence. Author binary identity, complete independent author table/raw-file
comparisons, input/output guards and isolated native DAG checks are separate
layers. They do not certify all author options, statistical calibration,
live daemon loading, strict cache identity, persistent recovery, clean remote
installation, full-scale resource budgets, scientific qualification or G0.
A frozen study's strict P cutoff must be enforced upstream; this general
node must not silently change the author's inclusive threshold semantics.
