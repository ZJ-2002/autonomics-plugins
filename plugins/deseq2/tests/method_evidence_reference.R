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
read_table <- function(path) read.delim(path,check.names=FALSE,quote='"')
for (name in c("forward","shuffled","reverse")) {
 dir <- file.path(root,name)
 dds <- readRDS(file.path(dir,"dataset.rds"))
 report <- jsonlite::read_json(file.path(dir,"report.json"),simplifyVector=TRUE)
 stopifnot(identical(attr(DESeq2::dispersionFunction(dds),"fitType"),"parametric"))
 contrast <- c("condition",report$analysis$contrast$test,report$analysis$contrast$reference)
 ref <- DESeq2::results(dds,contrast=contrast,alpha=.05,independentFiltering=TRUE,cooksCutoff=TRUE)
 uncooked <- DESeq2::results(dds,contrast=contrast,alpha=.05,independentFiltering=FALSE,cooksCutoff=FALSE)
 # Independently refit from the declared synthetic inputs with the official API.
 counts_table <- read_table(file.path(dir,"counts.tsv"))
 counts <- as.matrix(counts_table[,-1]);rownames(counts) <- counts_table[[1]]
 metadata <- read_table(file.path(dir,if (name=="shuffled") "shuffled.tsv" else "metadata.tsv"))
 metadata <- metadata[match(colnames(counts),metadata$sample_id),,drop=FALSE]
 rownames(metadata) <- metadata$sample_id
 metadata$condition <- factor(metadata$condition,levels=c(contrast[[3]],contrast[[2]]))
 fresh <- DESeq2::DESeqDataSetFromMatrix(countData=counts,colData=metadata[,"condition",drop=FALSE],design=~condition)
 fresh <- DESeq2::DESeq(fresh,fitType="parametric",quiet=TRUE,parallel=FALSE)
 author <- DESeq2::results(fresh,contrast=contrast,alpha=.05,independentFiltering=TRUE,cooksCutoff=TRUE)
 stopifnot(identical(rownames(author),rownames(ref)))
 for (column in c("baseMean","log2FoldChange","lfcSE","stat","pvalue","padj")) same(ref[[column]],author[[column]])
 # Contrast reversal on the SAME fitted object must negate effect and intervals.
 # Re-levelling and refitting is a different numerical operation: compare that
 # operation to its own independently fitted official reference, above.
 reverse <- DESeq2::results(dds,contrast=c(contrast[[1]],contrast[[3]],contrast[[2]]),alpha=.05,independentFiltering=TRUE,cooksCutoff=TRUE)
 same(reverse$log2FoldChange,-ref$log2FoldChange);same(reverse$lfcSE,ref$lfcSE)
 same(reverse$log2FoldChange-qnorm(.975)*reverse$lfcSE,-(ref$log2FoldChange+qnorm(.975)*ref$lfcSE))
 same(reverse$log2FoldChange+qnorm(.975)*reverse$lfcSE,-(ref$log2FoldChange-qnorm(.975)*ref$lfcSE))
 same(reverse$pvalue,ref$pvalue)
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
# DESeq2's independent reparameterized fits need not be bitwise sign mirrors.
# Record differences without silently relaxing the official-parity tolerance.
relevel_difference <- list(
 max_abs_log2fc_sign_error=max(abs(r$log2FoldChange+f$log2FoldChange),na.rm=TRUE),
 max_abs_ci_reverse_error=max(abs(r$ci_lower+f$ci_upper),abs(r$ci_upper+f$ci_lower),na.rm=TRUE),
 max_abs_p_difference=max(abs(r$raw_p-f$raw_p),na.rm=TRUE))
jsonlite::write_json(list(status="PASS",genes=2001L,samples=8L,numerical_fields=checked,
 comparison="All-row metadata order invariance, fixed-DDS reverse effect/CI, independent official refits for each parameterization, and stats BH/BY",
 reparameterized_fit_differences=relevel_difference,
 official_parity_absolute_tolerance=1e-9,official_parity_relative_tolerance=1e-9,
 reference_scope="Independent R calls with the same pinned package environment; not a separately built numerical stack",
 scientific_authorization=FALSE),file.path(root,"NUMERICAL_ACCEPTANCE.json"),auto_unbox=TRUE,pretty=TRUE,digits=NA)
