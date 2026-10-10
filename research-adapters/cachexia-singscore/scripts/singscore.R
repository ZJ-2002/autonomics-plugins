stopifnot(as.character(utils::packageVersion("singscore")) == "1.32.0")
table <- read.delim(Sys.getenv("AUTONOMICS_INPUT0"), check.names = FALSE, stringsAsFactors = FALSE)
members <- read.delim(Sys.getenv("AUTONOMICS_INPUT1"), check.names = FALSE, stringsAsFactors = FALSE)
samples <- read.delim(Sys.getenv("AUTONOMICS_INPUT2"), check.names = FALSE, stringsAsFactors = FALSE)
if (names(table)[1] != "gene" || nrow(table) < 2 || ncol(table) < 2 ||
    anyNA(table$gene) || any(!nzchar(table$gene)) || anyDuplicated(table$gene) ||
    anyDuplicated(names(table))) stop("Matrix gene/sample identities invalid")
expression <- as.matrix(table[, -1, drop = FALSE])
if (!is.numeric(expression) || any(!is.finite(expression))) stop("Expression matrix must be finite numeric values")
rownames(expression) <- as.character(table$gene)
if (!identical(names(members), c("gene", "direction")) || !nrow(members) || anyNA(members) ||
    any(!nzchar(members$gene)) || anyDuplicated(members$gene) ||
    !all(members$direction %in% c("up", "down")) ||
    !all(members$gene %in% rownames(expression))) stop("Signature identity/direction/coverage input invalid")
if (!identical(names(samples), c("sample", "group")) || anyNA(samples) ||
    any(!nzchar(samples$sample)) || any(!nzchar(samples$group)) || anyDuplicated(samples$sample) ||
    nrow(samples) != ncol(expression) || !setequal(samples$sample, colnames(expression))) {
  stop("Sample metadata must be an exact unique sample set")
}
up_set <- as.character(members$gene[members$direction == "up"])
down_set <- as.character(members$gene[members$direction == "down"])
if (!length(up_set)) stop("Down-only signature is outside the frozen simpleScore call contract")
sink(Sys.getenv("AUTONOMICS_OUTPUT2"), split = TRUE)
cat("singscore 1.32.0; average ties; stableGenes=NULL; knownDirection=TRUE; centerScore=TRUE\n")
ranks <- singscore::rankGenes(expression, tiesMethod = "average", stableGenes = NULL)
scores <- if (length(down_set)) {
  singscore::simpleScore(ranks, upSet = up_set, downSet = down_set,
                         knownDirection = TRUE, centerScore = TRUE)
} else {
  singscore::simpleScore(ranks, upSet = up_set, knownDirection = TRUE, centerScore = TRUE)
}
if (!identical(rownames(scores), colnames(expression)) || nrow(scores) != ncol(expression) ||
    any(!is.finite(scores$TotalScore))) stop("Official score/sample output invalid")
metadata <- samples[match(colnames(expression), samples$sample), ]
output <- data.frame(sample = metadata$sample, group = metadata$group, TotalScore = scores$TotalScore)
write.table(output, Sys.getenv("AUTONOMICS_OUTPUT0"), sep = "\t", quote = FALSE, row.names = FALSE)
saveRDS(list(ranks = ranks, official_scores = scores, scores = output), Sys.getenv("AUTONOMICS_OUTPUT1"))
print(sessionInfo())
sink()
