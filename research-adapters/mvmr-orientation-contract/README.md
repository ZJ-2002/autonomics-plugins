# Source covariance orientation candidate

This component requires explicitly supplied covariance in the effect-allele
directions of two actual complete normalized GWAS sources. It binds the source
hashes and every retained SNP's allele axes to the actual joint harmonization
table, full ledger, audit and identity. It uses the actual exposure signs to
compute `D Sigma D`, including zero exposure effects without inferring signs
from their values. Non-palindromic signs are additionally checked from source
alleles; palindromic signs remain bound to the official producer's frequency
resolution. Both matrix versions are validated against actual unchanged SE,
symmetry, scaled PSD and complete provenance evidence bytes.

SNP/exposure ordering is exact: no projection, missing matrix, implicit zero,
ridge repair or covariance estimation. UNRESOLVED provenance is preserved.
Two no-clobber outputs share a directory-inode flock; exceptions remove only
owned published inodes. A crash leaving an incomplete pair cannot be accepted
as successful container output. The engine must still establish actual source
normalizer and joint producer topology and validate the orientation receipt.

The manifest is an offline candidate with a fixed Python digest and explicit
limits. No scientific reviewer, GA08, dynamic family freeze or production
deployment is supplied here. Generic and candidate MVMR nodes remain blocked
at formal ingress until the complete protected chain is qualified.
