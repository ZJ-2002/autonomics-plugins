options(stringsAsFactors=FALSE, digits=17)
required <- function(key) { value <- Sys.getenv(key); if (!nzchar(value)) stop(paste("missing", key)); value }
publication_identity <- function(filename) {
  identity <- suppressWarnings(system2("/usr/bin/stat", c("-c", shQuote("%d:%i"), "--", shQuote(filename)), stdout = TRUE, stderr = FALSE))
  status <- attr(identity, "status")
  if ((!is.null(status) && status != 0L) || length(identity) != 1L || !grepl("^[0-9]+:[0-9]+$", identity)) return(NA_character_)
  unname(identity)
}

publication_file_identity <- function(filename) {
  link <- Sys.readlink(filename)
  if (!is.na(link) && nzchar(link)) return(NA_character_)
  metadata <- function() {
    result <- suppressWarnings(system2("/usr/bin/stat", c("-c", shQuote("%d:%i:%f:%u:%g:%s:%y"), "--", shQuote(filename)), stdout = TRUE, stderr = FALSE))
    status <- attr(result, "status")
    if ((!is.null(status) && status != 0L) || length(result) != 1L) return(NA_character_)
    fields <- strsplit(result, ":", fixed = TRUE)[[1]]
    if (length(fields) < 7L || is.na(strtoi(fields[[3]], base = 16L)) ||
        bitwAnd(strtoi(fields[[3]], base = 16L), 61440L) != 32768L) return(NA_character_)
    unname(result)
  }
  before <- metadata()
  if (is.na(before)) return(NA_character_)
  checksum <- tryCatch(suppressWarnings(system2("/usr/bin/sha256sum", stdin = filename, stdout = TRUE, stderr = FALSE)), error = function(condition) character())
  status <- attr(checksum, "status")
  after <- metadata()
  link <- Sys.readlink(filename)
  if ((!is.null(status) && status != 0L) || length(checksum) != 1L ||
      !grepl("^[0-9a-f]{64}  -$", checksum) || is.na(after) || !identical(before, after) ||
      (!is.na(link) && nzchar(link))) return(NA_character_)
  paste0(before, ":", substr(checksum, 1L, 64L))
}

publication_remove_owned_file <- function(filename, expected) {
  if (is.na(expected)) return(invisible(FALSE))
  current <- publication_file_identity(filename)
  if (is.na(current) || !identical(current, expected)) return(invisible(FALSE))
  invisible(unlink(filename) == 0L)
}

main <- function() {
input <- required("AUTONOMICS_INPUT0")
source_report <- required("AUTONOMICS_INPUT1")
outputs <- c(required("AUTONOMICS_OUTPUT0"), required("AUTONOMICS_OUTPUT1"), required("AUTONOMICS_OUTPUT2"))
links <- Sys.readlink(outputs)
if (anyDuplicated(outputs) || any(file.exists(outputs)) || any(!is.na(links) & nzchar(links))) stop("diagnostic outputs must be distinct and absent")
if (any(!dir.exists(dirname(outputs)))) stop("diagnostic output parent must exist")
report <- jsonlite::fromJSON(source_report, simplifyVector=FALSE)
expected <- report$outputs$dataset$md5
if (length(expected)!=1L || !identical(unname(tools::md5sum(input)), expected)) stop("DDS does not match the original run report")
dds <- readRDS(input)
if (!inherits(dds, "DESeqDataSet")) stop("expected a fitted DESeqDataSet")
actual_fit <- attr(DESeq2::dispersionFunction(dds), "fitType")
if (!identical(actual_fit, report$analysis$actual_dispersion_fit_type)) stop("DDS fit identity differs from run report")
if (nrow(dds)!=report$dimensions$genes || ncol(dds)!=report$dimensions$samples ||
    !identical(colnames(dds), unlist(report$sample_ids, use.names=FALSE)) ||
    !identical(rownames(dds), unlist(report$gene_ledger$all_gene_ids, use.names=FALSE))) stop("DDS axes differ from original run report")
if (as.character(utils::packageVersion("DESeq2"))!=report$engine$version) stop("DDS readback requires the original DESeq2 version")
contrast <- c(report$analysis$contrast$variable, report$analysis$contrast$test, report$analysis$contrast$reference)
if (length(contrast)!=3L || contrast[[1]]!="condition") stop("invalid original contrast")
alpha <- report$analysis$alpha
if (length(alpha)!=1L || !is.finite(alpha) || alpha<=0 || alpha>=1) stop("invalid original alpha")
result <- DESeq2::results(dds, contrast=contrast, alpha=alpha, independentFiltering=TRUE, cooksCutoff=TRUE)
unfiltered <- DESeq2::results(dds, contrast=contrast, alpha=alpha, independentFiltering=FALSE, cooksCutoff=FALSE)
ids <- rownames(dds)
if (anyNA(ids) || any(!nzchar(ids)) || anyDuplicated(ids) || !identical(ids, rownames(result))) stop("invalid DDS gene identity")
if (!("cooks" %in% SummarizedExperiment::assayNames(dds))) stop("fitted DDS has no Cook's assay; diagnostics incomplete")
cooks <- SummarizedExperiment::assay(dds,"cooks")
if (!identical(dimnames(cooks),dimnames(dds))) stop("Cook's assay axes differ from DDS")
annotations <- S4Vectors::mcols(dds)
required_annotations <- c("dispGeneEst","dispFit","maxCooks")
if (!all(required_annotations %in% names(annotations))) stop("fitted DDS dispersion/Cook annotations incomplete")
raw <- result$pvalue
all_zero <- rowSums(DESeq2::counts(dds))==0
beta_conv <- S4Vectors::mcols(dds)$betaConv
if (is.null(beta_conv) || length(beta_conv)!=length(ids) || anyNA(beta_conv[!all_zero])) stop("fitted DDS convergence annotation incomplete")
cooks_filtered <- is.na(raw) & !is.na(unfiltered$pvalue) & !all_zero
independent_filtered <- !is.na(raw) & is.na(result$padj)
reason <- rep("AVAILABLE", length(ids))
reason[is.na(raw)] <- "UNRESOLVED_MISSING_P"
reason[cooks_filtered] <- "COOKS_FILTERED"
reason[!is.na(beta_conv) & !beta_conv] <- "BETA_NOT_CONVERGED"
reason[all_zero] <- "ALL_ZERO"
if (any(is.na(raw) & reason=="UNRESOLVED_MISSING_P")) stop("unresolved per-gene missing P reason; diagnostic acceptance incomplete")
family_p <- ifelse(is.na(raw) | reason!="AVAILABLE", 1, raw)
z <- stats::qnorm(0.975)
table <- data.frame(gene_id=ids, baseMean=result$baseMean,
 log2FoldChange=result$log2FoldChange, lfcSE=result$lfcSE,
 ci_lower=result$log2FoldChange-z*result$lfcSE,
 ci_upper=result$log2FoldChange+z*result$lfcSE,
 raw_p=raw, official_padj=result$padj, adjustment_p=family_p,
 full_family_bh=stats::p.adjust(family_p, method="BH", n=length(ids)),
 full_family_by=stats::p.adjust(family_p, method="BY", n=length(ids)),
 gene_dispersion_estimate=annotations$dispGeneEst, fitted_dispersion=annotations$dispFit,
 final_dispersion=DESeq2::dispersions(dds), max_cooks=annotations$maxCooks,
 all_zero=all_zero, beta_converged=beta_conv, cooks_filtered=cooks_filtered,
 independent_filtered=independent_filtered, p_status=reason,
 estimate_status=ifelse(reason=="AVAILABLE","ESTIMATED","NOT_ESTIMABLE"))
info <- list(schema_version=1L, operation="FITTED_DDS_READBACK_NO_REFIT",
 scientific_authorization=FALSE, diagnostic_status="COMPLETE",
 genes=length(ids), samples=ncol(dds), actual_fit_type=actual_fit,
 cooks_assay="Complete gene x sample original DDS cooks assay, without refitting or sample exclusion",
 original_contrast=as.list(contrast), alpha=alpha,
 effect_semantics="unshrunk DESeq2 Wald MLE diagnostics; 95% normal confidence interval; estimate_status gates eligible estimates",
 family_semantics="All DDS genes, missing raw P retained as NA, missing or non-estimable correction input 1. Not a study family authorization.",
 input_md5=as.list(unname(tools::md5sum(c(input,source_report)))),
 session=utils::capture.output(sessionInfo()))
stages <- character(); stage_identities <- character(); staged <- character()
owned <- rep(NA_character_, length(outputs)); published <- integer(); complete <- FALSE
on.exit({
 if (!complete) for (i in published) publication_remove_owned_file(outputs[[i]], owned[[i]])
 for (i in seq_along(stages)) {
  if (identical(publication_identity(stages[[i]]), stage_identities[[i]])) {
   if (length(staged)>=i) publication_remove_owned_file(staged[[i]], owned[[i]])
   suppressWarnings(system2("/usr/bin/rmdir", c("--", shQuote(stages[[i]])), stdout=FALSE, stderr=FALSE))
  }
 }
}, add=TRUE)
for (parent in dirname(outputs)) {
 path <- tempfile(".dds-diagnostic-", tmpdir=normalizePath(parent,mustWork=TRUE))
 if (!dir.create(path,mode="0700")) stop("cannot create diagnostic staging")
 stages <- c(stages,path); stage_identities <- c(stage_identities,publication_identity(path))
 if (is.na(tail(stage_identities,1))) stop("cannot verify diagnostic staging")
}
staged <- file.path(stages,c("genes.tsv","report.json","cooks.tsv"))
write.table(table, staged[[1]], sep="\t", quote=TRUE, row.names=FALSE, na="NA")
jsonlite::write_json(info, staged[[2]], auto_unbox=TRUE, pretty=TRUE, null="null", na="null", digits=NA)
write.table(data.frame(gene_id=ids,as.data.frame(cooks,check.names=FALSE),check.names=FALSE), staged[[3]], sep="\t", quote=TRUE, row.names=FALSE, na="NA")
for (i in seq_along(outputs)) {
 owned[[i]] <- publication_file_identity(staged[[i]])
 if (is.na(owned[[i]])) stop("cannot bind diagnostic output")
}
for (i in seq_along(outputs)) {
 if (!identical(publication_identity(stages[[i]]),stage_identities[[i]]) ||
     !identical(publication_file_identity(staged[[i]]),owned[[i]])) stop("diagnostic staging changed")
 if (!file.link(staged[[i]],outputs[[i]])) stop("diagnostic publication refused")
 published <- c(published,i)
}
for (i in seq_along(outputs)) {
 if (!identical(publication_file_identity(outputs[[i]]),owned[[i]])) stop("diagnostic output changed")
}
complete <- TRUE
}
main()
