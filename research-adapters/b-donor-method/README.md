# B donor method OCI candidate

The actual offline OCI manifest digest is
`sha256:67cbe8da4412c6fc1c842a4ef3b4b10b412f497b7d57b429ff74f3416826b06d`.
This plugin declares the five-input DESIGN and six-input DESEQ2 nodes consumed
by the existing source-bound donor DAG fragment. It is a built candidate,
not an installed or qualified protected worker image.

The image retains the authenticated cached R-4.6.1 base and adds independently
compiled official DESeq2-1.52.0 runtime source, 43 measured dependency snapshots,
the whole authenticated base Matrix-1.7-5 package, measured lattice/codetools
snapshots, fixed R entry scripts and a fixed
vanilla launcher. The source software bundle and every added file are hashed.
Distribution archive provenance of the installed dependencies remains
unqualified. No inherited MRlap source/revision label represents this image.

The engine inserts the loaded script as argument one after the interpreter.
Putting `--vanilla` in manifest argv would therefore make it a script argument.
The immutable image executable `/opt/autonomics/b-donor/bin/Rscript-vanilla`
instead executes `/usr/local/bin/Rscript --vanilla "$@"`. The image also fixes
the R library directories, disables user/site R profiles and environ files,
and sets BLAS/OMP threads to one. Node resource admission requests two CPUs,
8 GiB, 256 PIDs and a two-hour limit, with no network, read-only root and no
image pulling. These are compiled resource settings; actual enforcement is a
separate protected container/runtime qualification.

The R entries are generated from the same complete `donor.R` bytes as the
locally qualified entries in `b-donor-contract`. `build_b_donor_wrappers.py
--check` verifies both copies. They retain all genes and require the actual
same-source design audit before official fitting. Software versions and GNU
publication binary hash must be measured in the actual image and match the
frozen model config; host measurement is not substituted for that check.

`scripts/research_oci_candidate.py` verifies the original OCI archive, manifest,
config, every compressed layer and each uncompressed diff ID before composing
an image. It hashes the bytes actually copied into its deterministic extra
layer and rechecks sources before no-clobber publication. Its read-only verifier
checks all referenced blobs, diff IDs and the exact added payload inventory.
Both operations explicitly report no protected/runtime/scientific acceptance.

The candidate is prepared under
`results/research-execution-20261009/b-donor-method-oci-candidate-v2/`.
Twelve offline construction/verification tests and three Rust loader/compiler
tests pass. Existing fixed-entry tests also pass. The frozen-source replay and
its content identity are recorded in the preparation capsules. The original
`dba3d620...` candidate and its frozen replay are retained in the v1 capsule and
permanently rejected: the host Matrix binary needs GLIBC_2.43 absent in the
base. The corrected image replaces the complete 119-file package from the
authenticated base, preserving Matrix 1.7-5 and R 4.6.1. All 22 added native
files pass selected static provider/R-API checks. Two actual local numerical
entry tests using the recovered Matrix package also pass. Neither static
checks nor host execution establish the actual image's runtime qualification.

Still required: real image loader/ABI and numerical/failure tests, protected
worker execution and resource enforcement, complete dependency origin review,
full B-family and server lineage integration, actual resource admission and
genuine signed scientific/technical review. All 74 original G0 gates remain
OPEN and reviewers remain undetermined. The plugin is not deployed.
