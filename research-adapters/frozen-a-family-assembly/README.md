# Frozen A complete-family technical assembly

This candidate is not registered for production and has no scientific release.
It preserves the existing 88/188 edge and 36/252 path families, without changing
any original study file, O classification, eligibility decision or denominator.

`frozen_a_family_assemble` consumes the nine original sources in the exact order
listed in `scripts/family.py`, followed by a strict technical request JSON.
Only explicit `SYNTHETIC_NOT_RESEARCH` BOUNDARY/INTERIOR requests or mechanical
`FROZEN_LEDGER_MECHANICAL_ONLY_NOT_RESEARCH` missing-ledger transport are allowed.
The original three Python eligibility, IUT and ID helpers are used; the original
Python adjustment helper is never called. Raw missing values remain `NA`.

Official R adjustment is a separate node. `frozen_a_family_publish` consumes its
840-row output and hash-bound RDS/receipt, not a Python reconstruction. It checks
R/stats 4.6.1, complete vector identity/order and the frozen R definition hash.
It does not deserialize RDS or independently certify its contents; the separate
technical driver must perform official R whole-object readback/comparison.

Both kinds have zero parameters, fixed CPython 3.14.7, copy staging and exclusive
four-port publication. Failure rollback removes only the publisher's own inodes;
foreign files are never replaced or removed. Unit tests are toy interface and
failure-path checks, not official runtime, DAG, deployment or G0 certification.
Publication and rollback check the expected size and SHA256 as well as inode.
An externally rewritten same-inode file or replaced stage is preserved and the
operation fails; incomplete or changed stages are not deleted as if unchanged.

Frozen source sizes are checked before their payloads are opened. Requests are
limited to 4 MiB; publication table inputs to 8 MiB, receipts to 4 MiB and RDS to
32 MiB. Registry publication roles additionally require exact frozen sizes.
Reads are bounded and check file-descriptor/path identity again to reject growth
or replacement. These per-input limits are not a process peak-memory guarantee.
