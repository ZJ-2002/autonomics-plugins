options(stringsAsFactors = FALSE, digits = 15)
.libPaths(c(Sys.getenv("REFERENCE_LIBRARY"), .libPaths()))
config <- jsonlite::read_json(Sys.getenv("REFERENCE_CONFIG"), simplifyVector = TRUE)
config$covariates <- unlist(config$covariates, use.names = FALSE)
library("DESeq2")
library("apeglm")
stopifnot(packageVersion("DESeq2") == "1.50.2", packageVersion("apeglm") == "1.32.0")
for (package in c("DESeq2", "apeglm")) {
  stopifnot(startsWith(find.package(package), Sys.getenv("REFERENCE_LIBRARY")))
}
counts_table <- read.delim(config$counts_path, check.names = FALSE, colClasses = "character", na.strings = character(), quote = intToUtf8(34L))
metadata <- read.delim(config$metadata_path, check.names = FALSE, colClasses = "character", na.strings = character(), quote = intToUtf8(34L))
counts <- matrix(as.numeric(as.matrix(counts_table[, -1])), nrow = nrow(counts_table),
                 dimnames = list(counts_table[[1]], names(counts_table)[-1]))
metadata <- metadata[match(colnames(counts), metadata$sample_id), , drop = FALSE]
rownames(metadata) <- metadata$sample_id
metadata$condition <- factor(metadata$condition, levels = config$levels)
for (name in names(config$column_types)) {
  if (config$column_types[[name]] == "numeric") {
    metadata[[name]] <- as.numeric(metadata[[name]])
  } else {
    metadata[[name]] <- factor(metadata[[name]])
  }
}
design <- as.formula(config$formula)
col_data <- metadata[, c(config$covariates, "condition"), drop = FALSE]
dds <- DESeq2::DESeqDataSetFromMatrix(countData = counts, colData = col_data, design = design)
dds <- DESeq2::DESeq(dds, fitType = config$fit_type, quiet = TRUE, parallel = FALSE)
result <- DESeq2::results(dds, contrast = c("condition", config$levels[[2]], config$levels[[1]]),
                         alpha = config$alpha, independentFiltering = TRUE, cooksCutoff = TRUE)
unshrunk <- result
if (config$lfc_shrink == "apeglm") {
  coefficient <- tail(DESeq2::resultsNames(dds), 1)
  shrunk <- DESeq2::lfcShrink(dds, coef = coefficient, type = "apeglm", quiet = TRUE)
  result$log2FoldChange <- shrunk$log2FoldChange
  result$lfcSE <- shrunk$lfcSE
}
write.table(data.frame(gene_id = rownames(result), as.data.frame(result), check.names = FALSE),
            file.path(config$output, "results.tsv"), sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)
normalized <- DESeq2::counts(dds, normalized = TRUE)
write.table(data.frame(gene_id = rownames(normalized), as.data.frame(normalized), check.names = FALSE),
            file.path(config$output, "normalized.tsv"), sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)
factors <- DESeq2::sizeFactors(dds)
write.table(data.frame(sample_id = names(factors), size_factor = unname(factors)),
            file.path(config$output, "size_factors.tsv"), sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)
saveRDS(list(dds = dds, unshrunk = unshrunk, final = result), file.path(config$output, "complete-author-intermediates.RDS"))
node_dds <- readRDS(config$node_dataset)
numerical_fields <- 0L
compare_numeric <- function(actual, expected, label) {
  stopifnot(identical(dim(actual), dim(expected)), identical(names(actual), names(expected)),
            identical(dimnames(actual), dimnames(expected)), identical(is.na(actual), is.na(expected)))
  stopifnot(!any(is.nan(actual)), !any(is.nan(expected)))
  keep <- !is.na(expected)
  stopifnot(all(is.finite(actual[keep])), all(is.finite(expected[keep])))
  error <- abs(actual[keep] - expected[keep])
  if (any(error > 1e-10 + 1e-10 * abs(expected[keep]))) stop(paste("RDS numerical mismatch:", label))
  numerical_fields <<- numerical_fields + sum(keep)
}
stopifnot(identical(rownames(node_dds), rownames(dds)), identical(colnames(node_dds), colnames(dds)),
          identical(deparse(DESeq2::design(node_dds)), deparse(DESeq2::design(dds))),
          identical(as.data.frame(SummarizedExperiment::colData(node_dds)), as.data.frame(SummarizedExperiment::colData(dds))),
          identical(SummarizedExperiment::assayNames(node_dds), SummarizedExperiment::assayNames(dds)))
compare_numeric(model.matrix(DESeq2::design(node_dds), as.data.frame(SummarizedExperiment::colData(node_dds))),
                model.matrix(DESeq2::design(dds), as.data.frame(SummarizedExperiment::colData(dds))), "model matrix")
for (name in SummarizedExperiment::assayNames(dds)) {
  compare_numeric(SummarizedExperiment::assay(node_dds, name), SummarizedExperiment::assay(dds, name), name)
}
compare_numeric(DESeq2::sizeFactors(node_dds), factors, "sizeFactors")
node_annotations <- as.data.frame(S4Vectors::mcols(node_dds))
annotations <- as.data.frame(S4Vectors::mcols(dds))
stopifnot(identical(names(node_annotations), names(annotations)))
for (name in names(annotations)) {
  if (is.numeric(annotations[[name]])) {
    compare_numeric(node_annotations[[name]], annotations[[name]], name)
  } else {
    stopifnot(identical(node_annotations[[name]], annotations[[name]]))
  }
}
stopifnot(identical(attr(DESeq2::dispersionFunction(node_dds), "fitType"), attr(DESeq2::dispersionFunction(dds), "fitType")))
identity <- list(packages = lapply(c("DESeq2", "apeglm"), function(package) list(name = package,
                  version = as.character(packageVersion(package)), path = find.package(package))),
                 actual_fit_type = attr(DESeq2::dispersionFunction(dds), "fitType"),
                 all_gene_ids = unname(as.list(rownames(dds))),
                 all_zero_gene_ids = unname(as.list(rownames(dds)[rowSums(counts) == 0])),
                 pvalue_unavailable_gene_ids = unname(as.list(rownames(dds)[is.na(result$pvalue)])),
                 independent_filter_only_gene_ids = unname(as.list(rownames(dds)[!is.na(result$pvalue) & is.na(result$padj)])),
                 adjusted_pvalue_available_gene_ids = unname(as.list(rownames(dds)[!is.na(result$padj)])),
                 dataset_semantic_fields_compared = numerical_fields,
                 dataset_axes_design_colData_assays_annotations_exact_or_in_tolerance = TRUE,
                 G0 = FALSE)
jsonlite::write_json(identity, file.path(config$output, "reference-identity.json"), pretty = TRUE, auto_unbox = TRUE)
