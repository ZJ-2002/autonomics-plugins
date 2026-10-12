arguments <- commandArgs(trailingOnly = TRUE)
.libPaths(c(arguments[1], .libPaths()))
library(UCell)
stopifnot(as.character(packageVersion("UCell")) == "2.16.0",
          normalizePath(find.package("UCell")) == normalizePath(file.path(arguments[1], "UCell")))
data.table::setDTthreads(1)
table <- read.delim(arguments[2], colClasses = "character", check.names = FALSE,
  na.strings = NULL, quote = "", comment.char = "", fileEncoding = "UTF-8")
expression <- matrix(as.numeric(as.matrix(table[, -1, drop = FALSE])), nrow = nrow(table),
  dimnames = list(table[[1]], names(table)[-1]))
features <- jsonlite::fromJSON(arguments[3], simplifyVector = FALSE)
features <- lapply(features, unlist, use.names = FALSE)
reference <- ScoreSignatures_UCell(expression, features = features, maxRank = 1500,
  missing_genes = "impute", w_neg = 1, ties.method = "average", name = "",
  chunk.size = 100, BPPARAM = BiocParallel::SerialParam(), ncores = 1, force.gc = FALSE)
stopifnot(identical(rownames(reference), colnames(expression)), all(is.finite(reference)))
write.table(data.frame(cell = rownames(reference), reference, check.names = FALSE), arguments[4],
            row.names = FALSE, quote = FALSE, sep = "\t", fileEncoding = "UTF-8")
saveRDS(list(scores = reference, features = features, expression = expression,
             method_namespace = find.package("UCell")), arguments[5])
cat("Independent freshly installed UCell namespace:", find.package("UCell"), "\n")
