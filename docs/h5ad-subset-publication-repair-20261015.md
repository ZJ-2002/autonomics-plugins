# H5AD subset output publication repair

This record concerns the two-output publication interface of
`single-cell/h5ad_subset_by_obs`, not an AnnData algorithm certificate, a real
single-cell analysis, a new whole-engine DAG proof, or production admission.

## Observed original defect

The original script is pinned by commit
`b4712c853b1a605b3fa9a9cf2c3c6ddf2e7d1536` and SHA256
`0db6f4caadbb28f679f2d813c60de33d3c74ca1111934f01389b182306b088ec`.
Session `dbf61385738f42dbbc39ec015a160275`, seal
`c41daeb616a88c10ee3fd2f47900140d3ac5ccadfff4483fd9ab0993346dd332`,
preserves all fifteen checked archive members, totaling 24,860 bytes.

The actual original `publish` function was extracted without importing AnnData.
A fake writer produced explicitly non-H5AD toy bytes. The unmodified control
succeeded with consistent outputs. In two additional cases the actual hard link
succeeded, then a controlled hook replaced the first or last destination without
raising an exception. Publication returned normally with inconsistent outputs.
This demonstrates an I/O defect, not an error in official AnnData slicing.

## Bounded repair

The implementation now freezes regular-file identity, size and content hashes
before linking, checks each confirmed publication, and checks every output again
before returning. Failure rolls back only confirmed successful links that still
match the recorded identity and content. Foreign replacements and modified or
uncertain-ownership paths are preserved, not overwritten or deleted.

Review caught an unsafe intermediate repair: registering a link attempt before
success could delete a foreign same-inode hard link after `EEXIST`. That draft
was not published. Ownership is now recorded only after normal link return.
An exception with unconfirmed creation therefore fails safely while preserving
the uncertain path rather than falsely claiming cleanup.

Sixteen self-cleaning standard-library tests cover positive cross-directory
publication, wrong output contracts, existing files and dangling links, staged
symlinks, first/last replacement, same-inode same-size changes, later-link
corruption of an earlier port, link errors, and the foreign same-inode race.
The tests also pin the unchanged non-publication AST without requiring Git
history or AnnData in the ordinary unit-test environment.

The repaired script SHA256 is
`4d1afc22f291ab80b92033308319306db30b1a779ef873466920e6040fa87b5b`.
An independent comparison against the actual original Git source confirms that
all AST outside `publish` is unchanged. The entire manifest remains byte-equal:
SHA256 `5288e9c7ac552f318b93c67f107fd45dcddf12d9396c38e00e6950e3bede9c42`.
The image, parameters, AnnData selection semantics, and frozen study contracts
are not changed.

## Remaining boundaries

These checks establish observations at the checks, not permanent protection
against later external writes or crash-atomic publication across two files.
Foreign or uncertain files preserved on failure are not valid node products.
The new script still needs an official-runtime whole-object replay and a current
isolated DAG proof before its updated runtime interface is qualified. Existing
older method evidence is retained with its original identities and scope.

No container, fit, real H5AD or production service is run by these unit tests.
No research donor, QC, scoring, or spatial null contract is filled in. No daemon
restart, hot reload, frozen-design change, or G0 grant is authorized by this fix.
