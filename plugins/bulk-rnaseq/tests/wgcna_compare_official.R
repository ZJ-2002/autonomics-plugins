options(stringsAsFactors = FALSE)
reference <- readRDS("/case/fresh-author-reference.rds")
report <- jsonlite::fromJSON("/case/report.json", simplifyVector = TRUE)
numeric_fields <- 0L
missing_fields <- 0L
exact_values <- 0L
close_values <- function(actual, expected, label) {
  actual <- as.numeric(actual)
  expected <- as.numeric(expected)
  if (length(actual) != length(expected) || !identical(is.na(actual), is.na(expected))) {
    stop(paste("shape or missing mask mismatch:", label))
  }
  usable <- !is.na(expected)
  if (any(!is.finite(actual[usable])) || any(!is.finite(expected[usable])) ||
      any(abs(actual[usable] - expected[usable]) > 1e-10 + 1e-10 * abs(expected[usable]))) {
    stop(paste("predeclared numerical tolerance failed:", label))
  }
  numeric_fields <<- numeric_fields + sum(usable)
  missing_fields <<- missing_fields + sum(!usable)
}
same_values <- function(actual, expected, label) {
  if (!identical(as.character(actual), as.character(expected))) stop(paste("exact identity mismatch:", label))
  exact_values <<- exact_values + length(expected)
}
table <- function(name) read.delim(paste0("/case/", name, ".tsv"), colClasses = "character",
  check.names = FALSE, quote = "", comment.char = "", na.strings = "NA")
soft <- table("soft")
columns <- c(power = "Power", scale_free_R2 = "SFT.R.sq", slope = "slope", truncated_R2 = "truncated.R.sq",
             mean_connectivity = "mean.k.", median_connectivity = "median.k.", max_connectivity = "max.k.")
for (column in names(columns)) close_values(soft[[column]], reference$scan$fitIndices[[columns[[column]]]], column)
close_values(soft$chosen_power, rep(reference$chosen, nrow(soft)), "chosen power")
modules <- table("modules")
modules$gene_id <- read.delim("/case/modules.tsv", colClasses = "character", check.names = FALSE,
  quote = "", comment.char = "", na.strings = character())$gene_id
same_values(modules$gene_id, reference$genes, "literal gene axis")
same_values(modules$module_label, reference$network$colors, "official labels")
same_values(modules$module_color, WGCNA::labels2colors(reference$network$colors), "official colors")
statuses <- ifelse(!reference$quality$goodGenes, "OFFICIAL_QC_EXCLUDED",
                   ifelse(reference$network$colors == 0, "UNASSIGNED_GREY", "ASSIGNED_MODULE"))
same_values(modules$gene_status, statuses, "QC and unassigned ledger")
for (column in names(reference$kme)) {
  expected <- rep(NA_real_, length(reference$genes))
  expected[reference$quality$goodGenes] <- reference$kme[[column]]
  close_values(modules[[column]], expected, column)
}
eigengenes <- table("eigengenes")
same_values(eigengenes$sample_id, reference$samples, "literal sample axis")
for (column in names(reference$network$MEs)) close_values(eigengenes[[column]], reference$network$MEs[[column]], column)
adjacency <- table("adjacency")
tom <- table("tom")
if (nrow(adjacency) != length(reference$adjacencies) || nrow(tom) != length(reference$toms)) stop("actual block count mismatch")
full_adjacency_fields <- 0
full_tom_fields <- 0
for (block_index in seq_along(reference$adjacencies)) {
  matrix <- reference$adjacencies[[block_index]]
  adjacent <- matrix[lower.tri(matrix)]
  actual_tom <- as.numeric(reference$toms[[block_index]])
  close_values(adjacency$genes[block_index], nrow(matrix), "adjacency genes")
  close_values(tom$genes[block_index], nrow(matrix), "TOM genes")
  for (kind in c("adjacency", "tom")) {
    values <- if (kind == "adjacency") adjacent else actual_tom
    actual <- if (kind == "adjacency") adjacency else tom
    close_values(actual$edges[block_index], length(values), paste(kind, "edge count"))
    close_values(actual$nonzero_edges[block_index], sum(values != 0), paste(kind, "nonzero count"))
    close_values(actual$mean[block_index], mean(values), paste(kind, "mean"))
    close_values(actual$median[block_index], median(values), paste(kind, "median"))
    close_values(actual$minimum[block_index], min(values), paste(kind, "minimum"))
    close_values(actual$maximum[block_index], max(values), paste(kind, "maximum"))
    expected_hash <- digest::digest(if (kind == "adjacency") as.numeric(matrix) else actual_tom, algo = "sha256")
    same_values(actual$values_sha256[block_index], expected_hash, paste(kind, "entire exact serialized values"))
  }
  close_values(adjacency$mean_connectivity[block_index], mean(rowSums(matrix) - diag(matrix)), "connectivity")
  full_adjacency_fields <- full_adjacency_fields + length(matrix)
  full_tom_fields <- full_tom_fields + length(actual_tom)
  same_values(report$blocks$gene_ids[[block_index]], reference$genes[reference$network$blockGenes[[block_index]]], "block membership")
}
same_values(report$network_semantics_sha256,
  digest::digest(reference$network[setdiff(names(reference$network), "TOMFiles")], algo = "sha256"), "full official network projection")
same_values(report$rng$before, reference$rng_before, "initial RNG state")
same_values(report$rng$after, reference$rng_after, "terminal RNG state")
same_values(report$qc$goodGenes, reference$quality$goodGenes, "gene QC mask")
same_values(report$qc$goodSamples, reference$quality$goodSamples, "sample QC mask")
if (report$node != "wgcna" || report$scientific_release != "NOT_GRANTED" ||
    report$analysis$power_source != if (reference$request$power > 0) "EXPLICIT_FIXED_POWER" else "OFFICIAL_PICK_SOFT_THRESHOLD") {
  stop("identity, power provenance or scientific-release boundary mismatch")
}
jsonlite::write_json(list(status = "PASS", numeric_fields = numeric_fields, missing_fields = missing_fields,
  exact_values = exact_values, full_adjacency_values_exact_hash = full_adjacency_fields,
  full_TOM_values_exact_hash = full_tom_fields, blocks = nrow(tom), tolerance = list(absolute = 1e-10, relative = 1e-10),
  independent_author_packages = reference$resolved_packages, G0 = FALSE),
  "/case/comparison.json", auto_unbox = TRUE, pretty = TRUE, digits = NA)
