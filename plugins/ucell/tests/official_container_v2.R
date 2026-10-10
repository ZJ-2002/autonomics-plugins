stopifnot(as.character(packageVersion("UCell")) == "2.16.0")
work <- tempfile("ucell-repository-")
dir.create(work)
expression <- matrix(c(1,2,0,4,5, 5,0,3,2,1, 0,4,5,1,2, 2,3,4,0,5), nrow=5,
  dimnames=list(paste0("G", 1:5), paste0("C", 1:4)))
features <- list(positive=c("G1", "G2"), signed=c("G1+", "G3-"), partial=c("G2", "ABSENT"))
write.table(data.frame(gene=rownames(expression), expression, check.names=FALSE),
  file.path(work, "matrix.tsv"), sep="\t", quote=FALSE, row.names=FALSE)
signatures <- do.call(rbind, lapply(names(features), function(name) {
  data.frame(signature=name, gene=features[[name]])
}))
write.table(signatures, file.path(work, "signatures.tsv"), sep="\t", quote=FALSE, row.names=FALSE)
reference <- UCell::ScoreSignatures_UCell(expression, features=features, maxRank=5,
  w_neg=1, missing_genes="impute", ties.method="average", name="_UCell",
  BPPARAM=BiocParallel::SerialParam(), chunk.size=100)
Sys.setenv(AUTONOMICS_INPUT0=file.path(work,"matrix.tsv"), AUTONOMICS_INPUT1=file.path(work,"signatures.tsv"),
  AUTONOMICS_OUTPUT0=file.path(work,"scores.tsv"), AUTONOMICS_OUTPUT1=file.path(work,"result.RDS"),
  AUTONOMICS_OUTPUT2=file.path(work,"log.txt"), AUTONOMICS_OUTPUT3=file.path(work,"audit.json"),
  UCELL_MAX_RANK="5", UCELL_NEGATIVE_WEIGHT="1", UCELL_MISSING_GENES="impute")
status <- system2(file.path(R.home("bin"), "Rscript"), c("--vanilla", "/plugin/scripts/ucell.R"))
stopifnot(status == 0, file.info(file.path(work,"log.txt"))$size > 0)
observed <- read.delim(file.path(work,"scores.tsv"), check.names=FALSE)
stopifnot(identical(observed$cell, rownames(reference)), identical(names(observed)[-1], paste0(sort(names(features)), "_UCell")),
  max(abs(as.matrix(observed[,-1]) - as.matrix(reference[, names(observed)[-1], drop=FALSE]))) <= 1e-12)
audit <- jsonlite::read_json(file.path(work,"audit.json"), simplifyVector=TRUE)
stopifnot(identical(audit$scientific_release, FALSE), identical(audit$g0_granted, FALSE))
Sys.setenv(UCELL_MISSING_GENES="invalid")
status <- system2(file.path(R.home("bin"), "Rscript"), c("--vanilla", "/plugin/scripts/ucell.R"))
stopifnot(status != 0, !file.exists(file.path(work,"scores.tsv")),
  !file.exists(file.path(work,"result.RDS")), !file.exists(file.path(work,"audit.json")),
  grepl("BLOCKED", paste(readLines(file.path(work,"log.txt")), collapse="\n")))
cat("PASS: separate direct official call, 12 scores, exact identities, actual rejection, no scientific certification\n")
