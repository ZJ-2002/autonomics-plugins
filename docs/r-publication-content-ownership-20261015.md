# Bounded R publication-content ownership repair

The DESeq2 and limma-voom runners use their official R packages. This repair
changes output publication and cleanup, not their statistical computation,
input qualification, method defaults or study design.

## Reproduced defects

The prior implementation identified a file using only device and inode. A
same-inode rewrite after a successful hard link could therefore be accepted,
or removed by a later failure rollback. Its recursive staging-directory cleanup
could also remove an unrelated member inserted into that directory.

These are actual base-R publication-component counterexamples, not conclusions
based only on reading source. Their fixed Git baseline and complete observations
are retained separately from the repaired-source evidence.

## Repair

- Require a regular, non-symlink staged file with stable metadata and SHA256.
- Check every staged file before linking, every target after linking, and all
  five staged and published files before reporting publication complete.
- Roll back only files whose current metadata and contents still match the
  recorded owned output. Preserve changed or unverifiable files.
- Remove only recognized owned staging files, then use nonrecursive `rmdir`.
  Unknown members prevent directory removal and are preserved.

The complete statistical-body AST and original scientific helper definitions
must remain unchanged. Fixed-image execution and isolated DAG execution are
separate evidence layers; a successful component test grants neither one.

Fixed-image regression now executes fourteen complete official R entries across
the two digest-pinned images, using the same synthetic 200-gene, 12-sample count
input. DESeq2 uses mean dispersion fitting without shrinkage; limma uses TMM.
The three DESeq2 TSVs and all five limma ports match their old-source normal
controls byte for byte. Whole DESeqDataSet objects compare with tolerance zero,
excluding R environment identity. Their compressed RDS bytes differ, so the
DESeq2 report comparison verifies each actual dataset MD5 and requires every
other JSON field to match exactly. It does not claim JSON byte equality or a
new independent numerical oracle. `check.environment=FALSE` also excludes
captured environment contents; this comparison alone is not certification of
arbitrary fit-function closure state or other dispersion-fit branches. See the
accompanying evidence card.

The current-source isolated DAG proof now completes four three-node/two-edge
graphs: one positive and one specific noninteger-count refusal per family.
All twelve task receipts, eight input bindings, ten positive output ports and
five stopped containers are checked. R refusals return the observed R exit 1
and publish no normal ports; a Python exit 2 or infrastructure error cannot
substitute. Report comparison admits only independently verified input staging
basenames and the DESeq2 dataset MD5 exception, with every remaining JSON key,
value and type exact. A single read-only RDS comparison container does not fit
a model or generate an independent numerical oracle. Three failed proof-harness
attempts remain archived and are not relabelled as passing method cases.

## Explicit limits

This is not an atomic five-file transaction, durability, crash recovery, or a
defence against arbitrary same-UID concurrent mutation. Writers still reopen
staged paths; exclusive held-descriptor serialization is a separate hardening
task. Path checking and subsequent unlink are not an atomic conditional unlink.
Directory mode 0700 does not exclude other processes of the same user.

The fixed-image regression must use synthetic integer counts. GSE130563 log2-RMA
data are not suitable for either DESeq2 or count/voom entry. Default apeglm and
all dispersion or model branches are not certified by a mean-fit, unshrunk
technical control. Technical evidence does not enable a study contrast, freeze
a new model or grant G0.
