# singscore_bspec - official Bioconductor singscore (frozen) for the v4.0
# B-SPEC main score. Pure R source run by the `Rscript` interpreter
# (mrlap.sh/harmonise.sh pattern).
#
# Contract: per-sample ranking score - rankGenes (type="internal",
# average ranks, ties kept - the package default; non-stable-gene
# reference mode is the package behavior when no reference is supplied)
# then simpleScore (known directions, mean-centered, non-signature
# "all" background). SC04 rule: score per sample first; never rank genes
# across subjects, never train the score on case/control labels.
#
# Inputs:  port 0 expression matrix TSV (row names = gene ids matching the
#          gene-set ids; columns = samples; already normalized to the
#          frozen dataset-common background)
#          port 1 gene set TSV (columns: gene, direction - "up"/"down")
#          port 2 samples TSV (columns: sample, group) - kept for lineage
#          only; the score itself never reads group.
# Outputs: port 0 per-sample score TSV (sample, group, TotalScore),
#          port 1 full rankData+scores RDS, port 2 run log.
#
# Parameter-free statistical surface on purpose: the v4.0 G0 lock fixes
# rankGenes/simpleScore defaults; adding a tunable here would reopen the
# "挑结果" door the plan forbids. The gene-set file MUST already be in
# matrix-id space (entrez ids per the B-SPEC mapping contract); this node
# never performs id mapping.

suppressMessages(library(singscore))

mat_path <- Sys.getenv("AUTONOMICS_INPUT0")
gs_path  <- Sys.getenv("AUTONOMICS_INPUT1")
smp_path <- Sys.getenv("AUTONOMICS_INPUT2")
score_path <- Sys.getenv("AUTONOMICS_OUTPUT0")
rds_path <- Sys.getenv("AUTONOMICS_OUTPUT1")
log_path <- Sys.getenv("AUTONOMICS_OUTPUT2")

expr <- as.matrix(read.delim(mat_path, row.names = 1, check.names = FALSE))
geneSet <- read.delim(gs_path, check.names = FALSE, stringsAsFactors = FALSE)
samples <- read.delim(smp_path, check.names = FALSE, stringsAsFactors = FALSE)

for (col in c("gene", "direction")) {
  if (!col %in% names(geneSet)) stop(paste0("gene set file missing column `", col, "`"), call. = FALSE)
}
if (!all(c("sample", "group") %in% names(samples))) {
  stop("samples file must carry sample and group columns", call. = FALSE)
}
if (!all(geneSet$direction %in% c("up", "down"))) {
  stop("gene set direction column must be up/down only", call. = FALSE)
}
missing_genes <- setdiff(geneSet$gene, rownames(expr))
if (length(missing_genes) > 0) {
  stop(paste0("gene set contains ", length(missing_genes),
              " ids absent from the expression matrix rows (mapping is upstream contract, not this node): ",
              paste(head(sort(missing_genes), 8), collapse = ",")), call. = FALSE)
}
unmatched_samples <- setdiff(samples$sample, colnames(expr))
if (length(unmatched_samples) > 0) {
  stop(paste0("samples file lists ", length(unmatched_samples),
              " samples absent from the matrix columns"), call. = FALSE)
}

sink(log_path, split = TRUE)
cat("singscore version:", as.character(packageVersion("singscore")), "\n")
cat("matrix:", nrow(expr), "genes x", ncol(expr), "samples; gene set:",
    sum(geneSet$direction == "up"), "up +", sum(geneSet$direction == "down"), "down\n")
flush.console()

# Plan-fixed contract: average ranks (the package default is min-tie -
# rankGenes gets tiesMethod = "average" explicitly per v4.0 section 5),
# known-direction centered simpleScore(upSet, downSet).
upSet <- geneSet$gene[geneSet$direction == "up"]
downSet <- geneSet$gene[geneSet$direction == "down"]
rank_data <- rankGenes(expr, tiesMethod = "average")
# One-directional signatures: the official simpleScore treats a MISSING
# downSet as one-sided; passing an empty vector instead silently yields a
# zero-row score table (review counterexample). Branch explicitly - the
# call shape follows the gene set, it is never a tunable.
ss <- if (length(downSet) == 0) {
  simpleScore(rank_data, upSet = upSet)
} else if (length(upSet) == 0) {
  # simpleScore's only required set is upSet; a DOWN-only signature has no
  # documented single-set form, and reusing the up slot would silently flip
  # the direction. Refuse instead of guessing - the study-plan side must
  # express such sets explicitly.
  stop("down-only gene sets are not expressible through simpleScore without guessing direction; refuse", call. = FALSE)
} else {
  simpleScore(rank_data, upSet = upSet, downSet = downSet)
}
# singscore 1.32.0 returns the per-sample score data.frame directly
# (TotalScore/UpScore/DownScore columns, rownames = samples).
scores <- as.data.frame(ss)
scores$sample <- rownames(scores)
scores <- merge(scores[, c("sample", "TotalScore")], samples[, c("sample", "group")], by = "sample", all.x = TRUE)
write.table(scores, score_path, sep = "\t", row.names = FALSE, quote = FALSE)
saveRDS(list(rank_data = rank_data, simple = ss, scores = scores), rds_path)
cat("\n== singscore_bspec summary ==\n")
print(head(scores[order(scores$sample), ], 5))
sink()
q(status = 0)
