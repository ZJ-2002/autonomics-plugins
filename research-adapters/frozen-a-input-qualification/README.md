# Frozen v4.3.2 A input qualification

Candidate kind `frozen_a_v432_input_qualification` has no parameters. It is
limited to the current X01/M06 raw sources and the frozen minimum A contract.
It does not grant qualification to the full genetic plan or another edge.
It uses the official Linux amd64 Python 3.14.7 image pinned by manifest digest,
and the original static official PLINK 1.90b7.2 executable as a frozen input.
The wrapper is Python standard-library-only; it does not translate QC,
clumping or LD calculations into R or Rust.

## Input order

The nine ports are raw X GWAS gzip, raw M GWAS gzip, `A_ANALYSIS_CONFIG.json`,
`G0_V432_CERTIFICATE.json`, original `prepare_minimum_g0.py`, original
`verify_minimum_ld.py`, official `plink`, LD panel `manifest.json`, and
`SOFTWARE_LOCK.tsv`. `contracts/source-lock.json` pins every file's full
SHA256 and byte count. The existing catalog LD reference is separately mounted
read-only at `/panels/ld_ref`; all 66 BED/BIM/FAM payloads are checked against
the exact manifest before and after execution, including 489 FAM rows each.
The manifest is supplied on port 7; the runtime's payload-only panel cache need
not contain another manifest file. If one is present in the mounted directory,
its bytes must agree exactly with that independently pinned input.

This new family deliberately declares `stage_in_mode="symlink"`. Local input
references must resolve to ordinary canonical files mounted read-only by the
runtime. The wrapper resolves and hashes those files instead of requiring a
duplicate multi-gigabyte input copy. Existing strict-copy families are unchanged.
Remote inputs or unsafe staging locations may cause the engine to copy instead;
that is outside the demonstrated zero-copy deployment scope and must be audited
at actual DAG admission. Canonical raw inputs and the original panel remain
outside disposable scratch and must never be copied into permanent technical
evidence. Raw input staging does not duplicate their data. For the isolated DAG
proof, the 66 panel payloads are transported into managed `TMPDIR` using
`reflink=always`. A reflink is a separate copy-on-write file, not a hardlink or
a claim that the panel is never copied. Unsupported or failed reflinking must
refuse execution, with no hardlink or ordinary-copy fallback. The runtime mounts
that disposable payload-only cache read-only; all payload hashes remain subject
to the same pre/post checks. The managed session owns and removes that temporary
cache, not the canonical reference.

## Original execution

The original QC source is imported as `prepare_minimum_g0`. Only its I/O globals
ROOT/OUT/DATA/PANEL and its subprocess interface are rebound. Its unchanged
`qualify_a()` executes directly. A private project-shaped staging tree contains
two owned DATA symlinks pointing to the verified raw inputs; no new raw download
or duplicate is created. The original hardcoded Downloads locations must not
be visible. The 42 MB PLINK binary alone is copied into owned scratch, hashed,
chmodded there and version-checked; source executable permissions are unchanged.

The original LD verifier imports that same registered QC module and executes
its unchanged `verify()`. A module-local subprocess proxy permits only the
original complete argv for PLINK clumping or `--r2 dprime`, with exactly one
thread, 1024 MiB and stage-confined output prefixes. It refuses fallback copies,
downloaders, extra flags, another tool or altered scientific parameters. It
does not replace the global `subprocess` module or rewrite either source file.

The frozen recipe uses `--clump-p1 5e-8 --clump-p2 1 --clump-r2 0.001
--clump-kb 10000`, original input order, and the existing GRCh37 BIM coordinates
joined from GRCh38 summary statistics by unique rsID and exact unordered alleles.
It must not be substituted by the separately tested PLINK2 implementation.
Source p=0 is retained according to the original source-underflow rule.

After the original LD verifier, a separate rejection-only envelope requires
every retained same-chromosome pair at distance **at most** 10 Mb. Original
`.ld` rows must have no missing, duplicate, foreign, out-of-window or wrongly
coordinated pairs; R2 must be finite, nonnegative and strictly below 0.001.
The original published summary must match all those original rows. This checks
the original result; it never deletes a pair or changes the algorithm to pass.
The optional historical genotype-correlation diagnostic is absent in this
frozen v4.3.2 directory and is not silently restored from another revision.

## Output order and bounds

Ports 0–8 are `A_INPUT_MANIFEST.json`, `A_GWS_CANDIDATES.tsv`,
`A_LD_EXCLUSIONS.tsv`, `A_OUTCOME_MATCHES.tsv`, `A_CLUMP_INPUT.tsv`,
`A_LD_CLUMPED_INSTRUMENTS.tsv`, `A_RETAINED_HAPLOTYPE_LD.tsv`,
`A_QC_AND_LD.json`, and `A_LD_PAIRWISE_ACCEPTANCE.json`. The first seven must
match the existing frozen bytes. The two original JSON command records contain
new private output paths and are not claimed to be byte-identical to historical
absolute paths; every actual command and original scientific fact is retained.

Ports 9–11 are `INPUT_METHOD_PROVENANCE.json`, `qualification.log`, and
`official-artifacts.tar`. Provenance binds all nine inputs, all 66 reference
files, original code, actual 13 clump plus 13 paircheck executions, complete-pair
envelope and original output hashes. The archive contains all regular files
from the private clumping directory, limited to 128 files and 16 MiB total;
it excludes raw inputs, the reference panel and copied executable. Source
identities are streamed, not loaded wholesale; no new certified peak-memory
or resource-performance claim follows from this code.

The container resource declaration is 2 GiB to leave room for Python, the tool
and charged page cache. The original PLINK argv remains `--memory 1024`; the
container limit is not a change to that frozen method parameter. Actual peak
container memory and suitability of this limit still require managed proof.

All twelve output paths must be fresh, distinct and on the same filesystem.
Computation uses an owned mode-0700 staging directory. The log is exclusively
linked first and remains after ordinary failure. All normal outputs are linked
exclusively only after processing and source rechecks; each destination and the
complete published set are checked for device/inode, size and content. Rollback
removes only still-owned unchanged outputs, preserving replacements. Cleanup
checks ownership of the staging directory. Existing or dangling output links
are refused, and no overwrite-copy fallback exists.

This is not crash-atomic publication, power-loss durability, resumability or
protection from arbitrary adversarial same-UID races. Interrupted partial
directories cannot be treated as success. Technical source qualification does
not run allele harmonisation, MR or MRlap, resolve O2 overlap, authorize a new
study, amend frozen denominators, execute the full-project verifier, establish
resident daemon identity or grant G0. Those remain separate admission steps.

Ordinary self-cleaning tests exercise helper contracts and synthetic publication
callbacks, not actual raw GWAS execution. Real source streaming, official tool
execution, materialized DAG bindings, resource limits and stopped-worker proof
require their own managed acceptance sessions.
