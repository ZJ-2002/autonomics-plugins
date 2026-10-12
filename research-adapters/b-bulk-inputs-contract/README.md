# Normalized bulk B input producer candidate

`b-bulk-inputs-contract/b_bulk_frozen_inputs` prepares nine actual files into
seven source-bound inputs for a later limma method. It performs no fit, family
registration, source/scientific qualification, gate approval or authorization.

| Input port | Actual file |
| --- | --- |
| 0 | Original design ZIP |
| 1 | Exact normalized-bulk request JSON |
| 2 | Complete source expression TSV |
| 3 | Complete source sample map TSV |
| 4 | Explicit analysis sample map TSV |
| 5 | Full feature/probe mapping TSV |
| 6 | Frozen contrast-lock TSV |
| 7 | Original source metadata bytes |
| 8 | Explicit resource-alias JSON |

The seven output ports, in order, are expression.tsv, genes.tsv, samples.tsv,
decisions.tsv, method-template.json, family-proposal.json and input-preparation.json.
The wrapper uses the real `research_b_bulk_limma_inputs.prepare` implementation,
with all original archive/compiler/registry dependencies and pseudobulk helpers
embedded. The research_b_counts shim exposes only that unchanged pb module;
it does not replace any bulk preparation or governance validation.

Every actual source feature and sample decision remains accounted for, including
excluded source samples, zero genes, clinical missingness and legacy SEEN history.
Clinical groups come from explicit maps. Ordinary OLS, TPM/raw-count substitution,
effect-based filtering and upgrading viewing history to UNSEEN are rejected.
The original ZIP and request are rehashed before and after preparation. The real
original static-governance verifier remains embedded and active.

A validated, durable `.b-bulk-inputs-complete` bundle is published without replacing
an existing destination. Seven ports are hard links into it, also without replacement.
If a foreign port appears during publication, execution fails and retains the
complete bundle plus any already-linked diagnostic ports. It never deletes a foreign
file; the engine must reject port publication on nonzero exit.

The manifest specifies copy staging, isolated networking, a read-only root filesystem,
never-pull policy, two CPUs, 2 GiB and a one-hour timeout. Its Python image digest was
actually inspected in the existing protected core-B cache. It is absent from the
ordinary user's default image store. That presence does not qualify this new producer
in a container or protected worker, and does not install or enable it in a preview.

Regenerate with `python -B scripts/build_b_bulk_inputs_wrapper.py`; verify exact source
freshness with its `--check` option. Ten wrapper tests and nine existing bulk preparation
tests passed using explicitly synthetic input fixtures. A separate actual final v4.3.2
ZIP negative QC correctly rejected a SYN resource outside its registry, wrote no output
and preserved the exact ZIP hash. No real differential model or research worker ran.

See `docs/audits/research-execution-2026-10-12/B_BULK_INPUT_PRODUCER_V1.json` for byte-bound
source, test and image identities. Protected execution, real-source eligibility, full
native B family registration, method acceptance, G0 and deployment remain unqualified.
