# Official MRlap wrapper: publication repair

## Confirmed defect

The old script checked that final outputs did not exist, then wrote directly to
those paths. A competing summary created after preflight could be overwritten
by the actual serialization tail. The reproduction executes only that tail
with an explicitly synthetic result list: it is not an MR fit, author-method
validation, or scientific result.

## Repair

The unchanged scientific body now receives four private staging paths through
`run_mrlap(outputs)`. It still calls official `MRlap::MRlap`, freezes the same
RNG and seed immediately before that call, retains `do_pruning=FALSE` and the
explicit IV list, and writes the full author result without reinterpretation.
The image, three inputs, four outputs, method parameters and 8 GiB resource
declaration are unchanged.

The outer publisher rejects existing files, directories and dangling links;
writes under a private 0700 staging directory; and creates each final output
with an exclusive hard link. A failed method publishes only its diagnostic log.
Failure-log symlinks are not followed. Partial publication rolls back only paths
whose observed device/inode still matches the created link.

This is exclusive **per-file** publication with inode-checked best-effort
rollback, not an atomic four-file transaction or a guarantee against a hostile
process replacing names between identity checking and unlinking. Cross-device
hard-link failure is fail-closed, not a supported cross-filesystem publish path.

## Executed evidence and limits

Session `72b4cbcdbb624039b17da276fc531fd9`, seal
`56cf7bbc9938ea73ed9bf41ddac552d684d3cbabcf1d7f60c95e263d1697b5de`:

- Reproduces the old foreign-summary overwrite in its actual serialization tail.
- Passes 19 R controls, including complete output, every dangling port, late
  competing files, partial publication rollback, missing/staged-symlink output,
  failure diagnostics and invalid writer status.
- Compares the entire original method AST after normalizing only output-port
  bindings, sink cleanup and final exit handling.
- Exercises the actual Rscript entry twice: missing output ports, and missing
  inputs with only a diagnostic log published.

These are host R 4.6.1 engineering controls. They do not load or run MRlap and
do not replace official-image execution, numerical requalification, connected
DAG or resident-deployment acceptance of the new wrapper. Historical full
author-RDS and 51-field evidence remains historical and is not relabeled as a
fresh proof of this entry. Native Rust `mrlap` remains forbidden. No scientific
release, frozen-design edit, new GWAS analysis or G0 authorization is granted.
