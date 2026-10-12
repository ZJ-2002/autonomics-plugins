options(stringsAsFactors = FALSE, digits = 15)
.libPaths(c(Sys.getenv("REFERENCE_LIBRARY"), .libPaths()))
arguments <- commandArgs(TRUE)
kind <- arguments[[1]]
directory <- arguments[[2]]
oracle <- jsonlite::read_json(file.path(directory, "decoded-oracle.json"), simplifyVector = FALSE)
genes <- unlist(oracle$genes, use.names = FALSE)
samples <- unlist(oracle$samples, use.names = FALSE)
counts <- matrix(as.integer(unlist(oracle$count_rows, use.names = FALSE)), byrow = TRUE,
    nrow = length(genes), dimnames = list(genes, samples))
metadata <- data.frame(sample_id = samples, condition = factor(unlist(oracle$conditions), levels = c("ctrl", "case")),
    check.names = FALSE, row.names = samples)
output <- file.path(directory, paste0(kind, "-reference"))
dir.create(output)
if (kind == "deseq2") {
    library(DESeq2)
    stopifnot(startsWith(find.package("DESeq2"), Sys.getenv("REFERENCE_LIBRARY")), packageVersion("DESeq2") == "1.50.2")
    dataset <- DESeqDataSetFromMatrix(counts, metadata[, "condition", drop = FALSE], design = ~ condition)
    dataset <- DESeq(dataset, fitType = "mean", quiet = TRUE, parallel = FALSE)
    result <- results(dataset, contrast = c("condition", "case", "ctrl"), alpha = .1, independentFiltering = TRUE, cooksCutoff = TRUE)
    normalized <- DESeq2::counts(dataset, normalized = TRUE)
    factors <- sizeFactors(dataset)
    write.table(data.frame(gene_id = rownames(result), as.data.frame(result), check.names = FALSE),
        file.path(output, "results.tsv"), sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)
    write.table(data.frame(gene_id = rownames(normalized), as.data.frame(normalized), check.names = FALSE),
        file.path(output, "normalized.tsv"), sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)
    write.table(data.frame(sample_id = names(factors), size_factor = unname(factors)),
        file.path(output, "size_factors.tsv"), sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)
    saveRDS(dataset, file.path(output, "dataset.rds"))
} else {
    library(limma)
    library(edgeR)
    stopifnot(startsWith(find.package("limma"), Sys.getenv("REFERENCE_LIBRARY")), packageVersion("limma") == "3.66.0",
        startsWith(find.package("edgeR"), Sys.getenv("REFERENCE_LIBRARY")), packageVersion("edgeR") == "4.8.2")
    design <- model.matrix(~ 0 + condition, metadata)
    expression <- DGEList(counts = counts)
    retained <- filterByExpr(expression, design = design)
    expression <- expression[retained, , keep.lib.sizes = FALSE]
    expression <- calcNormFactors(expression, method = "TMM")
    voom_result <- voom(expression, design, plot = FALSE)
    fit <- lmFit(voom_result, design)
    contrast <- matrix(c(-1, 1), nrow = 2, dimnames = list(colnames(design), "case_minus_reference"))
    fit <- contrasts.fit(fit, contrast)
    fit <- eBayes(fit)
    result <- topTable(fit, coef = 1, number = Inf, sort.by = "none", confint = FALSE, adjust.method = "BH")
    write.table(data.frame(gene_id = rownames(result), result, check.names = FALSE),
        file.path(output, "results.tsv"), sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)
    weights <- data.frame(gene_id = rownames(voom_result$E), voom_result$weights, check.names = FALSE)
    colnames(weights)[-1] <- colnames(voom_result$E)
    write.table(weights, file.path(output, "weights.tsv"), sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)
    write.table(data.frame(gene_id = rownames(voom_result$E), voom_result$E, check.names = FALSE),
        file.path(output, "normalized.tsv"), sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE)
    saveRDS(list(voom = voom_result, fit = fit, design = design, retained = retained), file.path(output, "complete-reference.rds"))
}
jsonlite::write_json(list(kind = kind, direct_decoded_oracle_no_node_parser = TRUE, genes = genes, samples = samples,
    source_package_path = find.package(if (kind == "deseq2") "DESeq2" else "limma"), G0 = FALSE),
    file.path(output, "reference-identity.json"), auto_unbox = TRUE, pretty = TRUE)
