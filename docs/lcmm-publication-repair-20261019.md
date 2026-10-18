# LCMM official adapter: output-ownership repair

## Scope

The `cachexia_hlme`, `cachexia_hlme_predict`, `cachexia_hlme_compare` and
`cachexia_lcmm_bind_contract` adapters retain their existing manifest, image,
input contracts and ports. Scientific methods remain direct calls to the pinned
author's `lcmm::hlme`, `lcmm::predictY` and `lcmm::summarytable` functions.
This change repairs output publication, not the author's algorithms.

The original error handler could unlink foreign normal outputs and overwrite
foreign audit/log files. This was reproduced separately for all 21 declared
output positions across the four modes, without running a model.

The wrapper now rejects existing output paths, dangling symlinks and input/output
aliases before invoking the method. Computation and diagnostic writing occur in
a private staging directory. Publication uses exclusive hard links. Rollback
removes only files whose device/inode identity still matches the wrapper's
published file. An existing `failed_fit.rds` is protected too; an owned diagnostic
fit can still be retained on failure. The original output environment is restored
when the wrapper returns.

## Evidence boundaries

- `tests/lcmm_publication_contract.R` exercises the actual wrapper with explicit
  library-load stubbing and invalid synthetic inputs. It is an engineering test,
  not an official-package numerical comparison.
- `tests/lcmm_method_body_contract.R` compares all 18 pre-existing function ASTs,
  including the official calls and input/summary helpers, with the frozen
  pre-repair source. It does not evaluate an author model.
- `tests/test_lcmm_publication_binding.py` checks five source/manifest bindings.
  These are not five numerical method tests.

Existing October 12 evidence inventories contain 11,217 verified files. The nine
current fit-node/core source files match that evidence exactly, except Rust
formatting and six test-fixture path relocations. However, the host runtime's
`/etc/ld.so.cache` no longer matches its old content lock: 3,055 of 3,056 runtime
files match. The lock was not weakened or rewritten. Historical evidence remains
historical; current host execution is not certified by this check.

The official adapter's image digest remains unchanged. Current repaired-wrapper
official DAG requalification is still required. No original native prediction or
model-record comparison route becomes a complete author-package implementation
because this alternative exists. In particular, native mean-only prediction and
native normalized BIC weights remain separately scoped arithmetic interfaces.

No production restart, scientific input eligibility, class selection, forecast
qualification or G0 approval is granted. The synthetic technical input contract
is not permission to fit actual study observations. B-S remains
`CONDITIONAL_NOT_READY`; GS01 remains `OPEN`; 276/288/696 remain unchanged.
