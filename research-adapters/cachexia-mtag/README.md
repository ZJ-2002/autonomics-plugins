# Fixed-source MTAG guard

The two inputs use the original frozen CLI column names: `snpid`, `z`, `n`,
`freq`, `chr`, `bpos`, `a1`, `a2`, and the default `p` column. MTAG's munge
stage needs P values even when Z statistics are used for estimation. Missing
P values are not invented; an upstream caught-error log blocks publication.

All 48 legal combinations of the six flags remain available. The original
Python2 MTAG statistical implementation is unchanged. Normal mode emits two
trait tables; equal-h2/perfect-gencov mode emits one meta table and no Omega
file. The four output ports preserve the complete raw bundle, log, index and
audit. This is not drop-in compatible with the old three output ports.

Numerical Omega must have exactly one explicit successful-termination marker;
finite tables and a completion marker alone do not certify convergence. The
meta branch bypasses this optimizer in official code, even if numerical_omega
is requested, so it does not manufacture an optimizer-success marker.

The fixed upstream parser declares `--time_limit`, but the optimization body
does not read it. It is passed through unchanged and must not be represented
as a wall-time limit. Engine timeout and deployment resource acceptance are
separate from this official argument.

The full host proof uses synthetic GWAS and simulated LD scores, actual
Python2.7.18 and pinned image packages, and unchanged official source. It is
not an actual container run, real-panel qualification, resident-daemon
deployment, study release, or G0. Production configuration is untouched.
