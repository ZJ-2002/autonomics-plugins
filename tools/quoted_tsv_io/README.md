# Scoped quoted-TSV interoperability regression

This is a technical IO regression for `pseudobulk_counts`, `deseq2_de`, and
`limma_voom`, not study execution or scientific release. It keeps their existing
schemas, parameters, algorithms and frozen numerical tolerances. The producer
sums raw integer counts by donor × cell type. DESeq2 and limma/edgeR are called
through their official packages, not reimplemented.

Both TSV inputs and outputs use tab delimiters, LF records, ASCII double-quote
quoting and doubled embedded quotes. Single quotes are literal. Empty values,
`NA`, `NULL`, Unicode and leading zeros remain strings until existing
method-specific validation. Empty or duplicate headers, malformed quoting,
ragged records, embedded NUL and decoded control characters are rejected.
Multiline fields are outside the existing field contract. Legacy files with
bare quotes must be decoded and re-exported by their owner; these nodes cannot
guess their meaning or silently rewrite frozen input files.

Run the real immutable images from an empty/new evidence path:

```sh
IO_EVIDENCE=/absolute/new/evidence \
IO_AUTHOR_PACKETS=/absolute/parent/of/sealed/author/packets \
PYTHONDONTWRITEBYTECODE=1 python tools/quoted_tsv_io/run_io_matrix.py
```

The author-packet parent must contain `canonical-deseq2-v1-20261012` and
`canonical-limma-voom-v1-20261012`, each with `SEALED_FILES.json` and its separately
installed `official-reference-library`. Every inherited reference-library file
is hash-checked before read-only reuse; this is not a fresh installation.
No missing image or reference causes a skip. Containers are network-isolated,
limited to 2 CPUs and 2 GiB for these small synthetic fixtures.

The two fixtures use independently generated decoded arrays, ordinary and
quote/Unicode/NA/leading-zero IDs. Their author oracle constructs R objects
directly from those arrays and does not read the producer's TSV or invoke the
node parser. DESeq2 uses `fit_type=mean`, `lfc_shrink=none`; limma uses categorical
`ctrl,case` and TMM. Existing absolute+relative tolerances are respectively
`1e-10` and `1e-12`; identities, shapes and NA masks are exact. This regression
does not replace the other methods/parameters' original numerical evidence.

The family boundary suites include quoted-ID and malformed-quote cases. Their
`tests/test_quoted_tsv_reader.R` also exercises the actual production reader
and independent base-R reader with `quote=intToUtf8(34L)`, `colClasses="character"`
and `na.strings=character()`. The default R quote setting additionally treats
single quotes as syntax and is not this dialect.

Consumers must actually decode CSV quoting. Plain tab splitting and `quote=""`
are incompatible. Type inference alone is not a lexical ID contract:
`file_to_dataframe` in the inherited SDK demonstrably turns an all-numeric
`0001,0002` ID column into `1,2`. Successful mixed-ID readback does not certify
that bridge for arbitrary IDs. Explicitly typed reading or an independently
approved bridge is required when identity inference can lose information.

The accompanying local review evidence additionally exercises all 13 File
ports in the actual three-manifest, 4-node/5-edge isolated SDK DAG, re-reads
results with R/Pandas/DataFusion and checks DESeqDataSet semantics. That is not
current daemon deployment, persistent resume, study eligibility, or G0.
