# Host-side reference generation for the singscore_bspec smoke test.
# Produces fixtures + the host golden; the container run (script from
# scripts/singscore.sh) must reproduce the scores exactly (same package
# version 1.32.0/Bioc 3.23, same R). Deliberately NO reimplementation of
# the score math here - the golden IS the official package run on the host
# install, cross-checked against the container image run (independent
# environments, pinned versions on both sides).
set.seed(1)
args <- commandArgs(trailingOnly = TRUE)
dir <- args[1]
dir.create(dir, showWarnings = FALSE, recursive = TRUE)
genes <- as.character(seq(101, 300))
samples <- paste0("S", 1:12)
expr <- matrix(rnbinom(length(genes) * 12, 8, 0.25), nrow = length(genes),
               dimnames = list(paste0(genes, "_at"), samples))
expr[paste0(genes[1:10], "_at"), ] <- expr[paste0(genes[1:10], "_at"), ] + 5   # up block
expr[paste0(genes[11:20], "_at"), ] <- pmax(0, expr[paste0(genes[11:20], "_at"), ] - 3) # down block
write.table(data.frame(gene = rownames(expr), expr, check.names = FALSE),
            file.path(dir, "matrix.tsv"), sep = "\t", row.names = FALSE, quote = FALSE)
gs <- data.frame(gene = paste0(genes[1:20], "_at"),
                 direction = rep(c("up", "down"), each = 10))
write.table(gs, file.path(dir, "geneset.tsv"), sep = "\t", row.names = FALSE, quote = FALSE)
sm <- data.frame(sample = samples, group = rep(c("case", "ctrl"), each = 6))
write.table(sm, file.path(dir, "samples.tsv"), sep = "\t", row.names = FALSE, quote = FALSE)
suppressMessages(library(singscore))
e <- as.matrix(read.delim(file.path(dir, "matrix.tsv"), row.names = 1, check.names = FALSE))
rd <- rankGenes(e, tiesMethod = "average")
ss <- simpleScore(rd, upSet = gs$gene[gs$direction == "up"], downSet = gs$gene[gs$direction == "down"])
write.table(data.frame(sample = rownames(ss), TotalScore = ss$TotalScore),
            file.path(dir, "host_golden.tsv"), sep = "\t", row.names = FALSE, quote = FALSE)
cat("fixtures + host golden written to", dir, "\n")
