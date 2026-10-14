# Official lm release-function provenance supplement

The exact R 4.6.1 primary author release tag was fetched over TLS-verified HTTPS:
`https://svn.r-project.org/R/tags/R-4-6-1/`. The release VERSION and three R
source files are hash-bound, not inferred from a Dockerfile or package name.

The installed `lm`, `lm.fit`, `lm.wfit`, `summary.lm`, `confint.lm`, `vcov.lm`,
`vcov.summary.lm` and `.vcov.aliased` were each compared to separately sourced
author definitions in a private R environment: **8/8 formals and bodies match**.
R and stats.so executable hashes were captured. This closes the R-function
source-identity gap; it does not prove a binary rebuild or signed OCI supply
chain, every numerical input, or formal scientific authorization.

The first follow-up failed on incorrect cgroup option placement. A later fetch
failed on TLS EOF. Both failures remain recorded; certificate checks were not
disabled and no mirror, method or software version was substituted. The final
run reused the already verified exact author-source bytes with fixed hashes.
It also proved the container is a descendant of its recorded technical service:
parent memory.max=2 GiB, container memory.max=1 GiB. A separate live probe
confirmed both actual container and conmon PID cgroups are under that service.
All these sessions stopped their consumers and cleaned their own scratch.

The managed runtime now uses Delegate=yes/DelegateSubgroup=worker-native;
worker admission permits only its exact recorded service or exact native
subgroup, not arbitrary descendants or another unit. The Podman shim binds
the cgroupfs parent and refuses caller cgroup overrides. The committed source
candidate passed 92 lifecycle tests. No daemon/study configuration, global
scientific concurrency guarantee, frozen family or G0 state is changed.

The full plugin source/catalog suite now executes 128 required tests without
failures, errors or skips. Three new reference-lock countertests prevent
incomplete paths or a self-consistent forged archive from becoming source proof.
The runtime fix is published in engine commit `3b0dc962b93fcd5f899d64696d1f4636ed1a3158`;
the source-function supplement does not silently upgrade the earlier DAG scope.

This supplement updates only the release-function provenance gap in
`evidence/r-stats-lm-20261014.json`; its original method/DAG source hashes and
historical-harness scope remain unchanged. Current-engine compilation is still
pending the separately live shared build slot. An uncompiled probe is not
counted as a completed DAG or deployment proof.

Detailed scoped identities: `evidence/r-stats-lm-source-20261014.json`.
The public driver `tools/prove_r_lm_source.py` supports new primary fetches and
reuse of the exact hash-bound author bytes; a self-consistent forged local
source-lock cannot satisfy the approved hashes.
