# Independent official-R readback assertions. No wrapper helper is sourced.
options(stringsAsFactors=FALSE,digits=17)
root <- Sys.getenv("METHOD_EVIDENCE_ROOT")
checked <- 0L
same <- function(actual,expected) {
 stopifnot(identical(is.na(actual),is.na(expected)))
 keep <- !is.na(expected)
 stopifnot(all(is.finite(actual[keep])),all(is.finite(expected[keep])))
 stopifnot(all(abs(actual[keep]-expected[keep])<=1e-9+1e-9*abs(expected[keep])))
 checked <<- checked+sum(keep)
}
read_table <- function(path) read.delim(path,check.names=FALSE,quote='"',colClasses=NULL)
for (name in c("forward","shuffled","reverse")) {
 dir <- file.path(root,name)
 dds <- readRDS(file.path(dir,"dataset.rds"))
 report <- jsonlite::read_json(file.path(dir,"report.json"),simplifyVector=TRUE)
 stopifnot(identical(attr(DESeq2::dispersionFunction(dds),"fitType"),"parametric"))
 contrast <- c("condition",report$analysis$contrast$test,report$analysis$contrast$reference)
 ref <- DESeq2::results(dds,contrast=contrast,alpha=.05,independentFiltering=TRUE,cooksCutoff=TRUE)
 uncooked <- DESeq2::results(dds,contrast=contrast,alpha=.05,independentFiltering=FALSE,cooksCutoff=FALSE)
 tab <- read_table(file.path(dir,"diagnostics.tsv"))
 stopifnot(identical(tab$gene_id,rownames(dds)),nrow(tab)==2001L)
 for (column in c("baseMean","log2FoldChange","lfcSE")) same(tab[[column]],ref[[column]])
 same(tab$raw_p,ref$pvalue);same(tab$official_padj,ref$padj)
 same(tab$ci_lower,ref$log2FoldChange-qnorm(.975)*ref$lfcSE)
 same(tab$ci_upper,ref$log2FoldChange+qnorm(.975)*ref$lfcSE)
 p <- ifelse(is.na(ref$pvalue),1,ref$pvalue)
 same(tab$adjustment_p,p)
 same(tab$full_family_bh,stats::p.adjust(p,"BH",n=nrow(dds)))
 same(tab$full_family_by,stats::p.adjust(p,"BY",n=nrow(dds)))
 zero <- rowSums(DESeq2::counts(dds))==0
 cook <- is.na(ref$pvalue)&!is.na(uncooked$pvalue)&!zero
 stopifnot(identical(tab$all_zero,unname(zero)),identical(tab$cooks_filtered,unname(cook)),
           identical(tab$independent_filtered,unname(!is.na(ref$pvalue)&is.na(ref$padj))))
 stopifnot(any(zero),any(cook),all(tab$p_status[zero]=="ALL_ZERO"),all(tab$p_status[cook]=="COOKS_FILTERED"))
 stopifnot(!any(tab$p_status=="UNRESOLVED_MISSING_P"))
}
f <- read_table(file.path(root,"forward/diagnostics.tsv"))
s <- read_table(file.path(root,"shuffled/diagnostics.tsv"))
r <- read_table(file.path(root,"reverse/diagnostics.tsv"))
stopifnot(identical(f$gene_id,s$gene_id),identical(f$gene_id,r$gene_id))
for (column in names(f)) {
 if (is.numeric(f[[column]])) same(s[[column]],f[[column]]) else stopifnot(identical(s[[column]],f[[column]]))
}
same(r$log2FoldChange,-f$log2FoldChange)
same(r$ci_lower,-f$ci_upper);same(r$ci_upper,-f$ci_lower)
for (column in c("raw_p","full_family_bh","full_family_by","lfcSE")) same(r[[column]],f[[column]])
jsonlite::write_json(list(status="PASS",genes=2001L,samples=8L,numerical_fields=checked,
 comparison="All-row metadata order invariance, reverse effect/CI, independent official-R DDS readback and stats BH/BY",
 reference_scope="Independent R calls with the same pinned package environment; not a separately built numerical stack",
 scientific_authorization=FALSE),file.path(root,"NUMERICAL_ACCEPTANCE.json"),auto_unbox=TRUE,pretty=TRUE)
