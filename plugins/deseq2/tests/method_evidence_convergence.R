# Deliberately mutated SYNTHETIC fitted-object controls; never a model fit.
options(stringsAsFactors=FALSE,digits=17)
root <- Sys.getenv("METHOD_EVIDENCE_ROOT")
mode <- Sys.getenv("METHOD_CONVERGENCE_CONTROL")
if (!(mode %in% c("nonconverged","unknown","verify"))) stop("explicit synthetic control mode required")
path <- file.path(root,"dataset.rds")
report_path <- file.path(root,"report.json")
dds <- readRDS(path)
report <- jsonlite::read_json(report_path,simplifyVector=FALSE)
contrast <- c("condition",report$analysis$contrast$test,report$analysis$contrast$reference)
res <- DESeq2::results(dds,contrast=contrast,alpha=report$analysis$alpha)
if (mode!="verify") {
 stopifnot(identical(unname(tools::md5sum(path)),report$outputs$dataset$md5))
 selected <- which(!is.na(res$pvalue) & S4Vectors::mcols(dds)$betaConv)[[1]]
 gene <- rownames(dds)[[selected]]
 S4Vectors::mcols(dds)$betaConv[[selected]] <- if (mode=="nonconverged") FALSE else NA
 saveRDS(dds,path)
 report$outputs$dataset$md5 <- unname(tools::md5sum(path))
 report$synthetic_control <- list(scope="DELIBERATELY_MUTATED_SYNTHETIC_DDS_NOT_A_FITTED_MODEL_OR_SCIENTIFIC_RESULT",mode=mode,gene=gene)
 jsonlite::write_json(report,report_path,auto_unbox=TRUE,pretty=TRUE,digits=NA)
} else {
 stopifnot(report$synthetic_control$mode=="nonconverged")
 tab <- read.delim(file.path(root,"diagnostics.tsv"),check.names=FALSE,quote='"')
 selected <- match(report$synthetic_control$gene,tab$gene_id)
 stopifnot(!is.na(selected),tab$p_status[[selected]]=="BETA_NOT_CONVERGED",tab$estimate_status[[selected]]=="NOT_ESTIMABLE",tab$adjustment_p[[selected]]==1)
 raw <- res$pvalue
 beta <- S4Vectors::mcols(dds)$betaConv
 expected <- ifelse(is.na(raw) | (!is.na(beta) & !beta),1,raw)
 stopifnot(identical(is.na(tab$raw_p),is.na(raw)),all(abs(tab$raw_p-raw)<1e-9,na.rm=TRUE))
 for (method in c("BH","BY")) {
  values <- stats::p.adjust(expected,method,n=nrow(dds))
  observed <- tab[[if (method=="BH") "full_family_bh" else "full_family_by"]]
  stopifnot(all(abs(values-observed)<1e-9))
 }
 cat("SYNTHETIC_NONCONVERGENCE_STATUS_AND_CORRECTION_PASS\n")
}
