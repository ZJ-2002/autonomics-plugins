# Official R statistics: repaired output ownership, unchanged methods

The user's direction is official author packages rather than native Rust
estimators. The existing `research-adapters/cachexia-r-stats` already calls
official R/stats 4.5.1 for six vector APIs: t.test, cor.test, var.test,
wilcox.test, prop.test and p.adjust. Do not create another numerical translation
or replace ordinary lm, donor models or signature scoring with these methods.

## Actual defect and repair

The original shared entry opened its declared log and wrote analytical outputs
without rejecting existing files. A preserved copy of that exact original
script reproduced the problem: a pre-existing sentinel in output 0 was
overwritten by a successful invocation. The current entry checks **all five**
port bindings before opening any log: nonempty, distinct absolute paths, no
traversal, existing file or symlink in the output ancestry.

No estimator, input model, official method parameter, NA policy or numerical
formula changed. Only output ownership admission changed. This protects ordinary
sequential reruns; it is **not** a concurrent-creation, crash-atomic publication
or persistent recovery certificate. Retained old script/DAG evidence is not
rewritten or claimed to certify the changed entry.

## New real reference execution

The complete historical 11,737-file/3,118,011,877-byte reference seal was rehashed
without copying its large parent artifacts. Only the small technical inputs and
independent reference argument fixtures were staged into new managed evidence.
The cached original digest image ran official R/stats 4.5.1 offline, and the six
installed function bodies/formals were checked again against the pinned author
source commit `1d95a4c60b0be6766490b1a621610b98a4bf5765`.

All **164 method cases** ran: **122 positive and 42 explicit refusals**. Every
positive complete RDS, argument list, warning sequence and literal row identity
matched an independently invoked official method at tolerance 1e-12. All 122
positive reruns refused and retained the exact hashes of every output. Five
additional single-port sentinels proved refusal before truncation. Four source
unit tests also exercise actual R guard behavior, duplicate/dangling-link/
traversing ports, and mutation identity excluding access time only.

Final managed session `6c469b6c101c472ba60a8b5df077d780` exited 0/CLEANED.
Its manifest is `dca66ac064d61286b5aa1519247113aa40ee720aaa64dc6a76e0c63de0b1f536`.
Its 1,896 mandatory technical files total 673,945 bytes; their complete manifest
membership and content hashes were independently reverified. No environment
clone, additional image build or numbered private vault was created.
The initial source-audit attempt remains failed: the original size/hash matched,
but comparing the complete stat object treated access-time updates as mutation.
The corrected identity still checks device, inode, mode, links, owner, size,
mtime and ctime. No source or reference hash check was bypassed.

## p.adjust route and unclosed layers

`cachexia_r_p_adjust` is the official migration route for the original
`hypothesize.adjust_pvalues` slot; it is not a new function denominator.
[Official p.adjust documentation](https://stat.ethz.ch/R-manual/R-devel/library/stats/html/p.adjust.html)
allows NA and requires n at least the input length. The adapter supplies
explicit method/n_total/alpha, keeps failed rows and literal IDs, and does not
infer the scientific family or fill missing membership. This remains an opt-in
technical adapter, not a default production installation.

The new executions are container/method/interface checks, **not current-engine
DAGs**. The source change still needs its current fixed-engine DAG requalification,
deployment/loading identity and any actual frozen study contract. The route is
therefore recorded as partial, not promoted by its historical pre-guard DAGs.
Frozen design, 276/288/696 denominators, G0 and B-S/GS01 are unchanged.

Source inventory/import checks additionally require recording this source
evolution against an actual Git commit/blob; the original import record remains
immutable. A suite that rejects an unrecorded evolution is retained as a genuine
failed check, not removed or counted as passing.
After recording the real source commit/blob evolution, all 161 required source
tests ran with zero failures/errors/skips and a matching source lock. The actual
successful session is `884367bae7184fd08978c7ce2426a394`, manifest
`879dcad7b9af601ecf760c8a59bf668fb89be5a53a3a4afeed07f898ad133b66`.
These source checks are not current DAGs or scientific certifications.
