options(stringsAsFactors = FALSE, digits = 17)
library_root <- Sys.getenv("WGCNA_REFERENCE_LIBRARY")
if (!nzchar(library_root)) stop("fresh official reference library is required")
.libPaths(c(library_root, .libPaths()))
suppressPackageStartupMessages(library(WGCNA))
packages <- c("WGCNA", "dynamicTreeCut", "fastcluster", "impute", "preprocessCore")
if (any(!startsWith(vapply(packages, find.package, character(1)), paste0(library_root, "/")))) {
  stop("reference package resolution escaped the fresh author library")
}
request <- jsonlite::fromJSON("/case/request.json")
raw <- read.delim("/case/expression.tsv", colClasses = "character", check.names = FALSE,
                  quote = "", comment.char = "", na.strings = character())
expression <- matrix(as.numeric(as.matrix(raw[, -1, drop = FALSE])), nrow = nrow(raw))
dimnames(expression) <- list(raw[[1]], names(raw)[-1])
datExpr <- t(expression)
if (request$threads > 1) enableWGCNAThreads(request$threads) else disableWGCNAThreads()
RNGkind("Mersenne-Twister", "Inversion", "Rejection")
set.seed(request$seed)
rng_before <- .Random.seed
quality <- WGCNA::goodSamplesGenes(datExpr, verbose = 0)
filtered <- datExpr[quality$goodSamples, quality$goodGenes, drop = FALSE]
cor_function <- if (request$cor == "bicor") "bicor" else "cor"
cor_options <- list(use = "p")
cor_text <- "use = 'p'"
if (request$cor == "bicor") {
  cor_options$maxPOutliers <- request$max_p_outliers
  cor_options$pearsonFallback <- "individual"
  cor_text <- sprintf("use = 'p', maxPOutliers = %.17g, pearsonFallback = 'individual'", request$max_p_outliers)
}
scan <- WGCNA::pickSoftThreshold(filtered, RsquaredCut = request$power_cutoff,
  powerVector = c(1:10, seq(12, 30, 2)), networkType = request$network_type,
  corFnc = cor_function, corOptions = cor_options, verbose = 0)
chosen <- if (request$power > 0) request$power else scan$powerEstimate
if (!is.finite(chosen)) stop("official reference has no automatic power estimate")
network <- WGCNA::blockwiseModules(datExpr, checkMissingData = TRUE, power = chosen,
  networkType = request$network_type, corType = request$cor, maxPOutliers = request$max_p_outliers,
  pearsonFallback = "individual", TOMType = request$network_type, TOMDenom = "min",
  deepSplit = request$deep_split, minModuleSize = request$min_module_size,
  mergeCutHeight = request$merge_threshold, maxBlockSize = request$max_block_size,
  pamRespectsDendro = FALSE, numericLabels = TRUE, saveTOMs = TRUE,
  saveTOMFileBase = "/case/reference-TOM", randomSeed = request$seed,
  nThreads = request$threads, verbose = 0)
adjacencies <- lapply(network$blockGenes, function(positions) {
  WGCNA::adjacency(datExpr[quality$goodSamples, positions, drop = FALSE],
    type = request$network_type, power = chosen, corFnc = cor_function, corOptions = cor_options)
})
toms <- lapply(network$TOMFiles, function(filename) {
  environment <- new.env(parent = emptyenv())
  if (!identical(load(filename, envir = environment), "TOM")) stop("reference TOM absent")
  environment$TOM
})
kme <- WGCNA::signedKME(filtered, network$MEs[quality$goodSamples, , drop = FALSE],
  outputColumnName = "kME", corFnc = cor_function, corOptions = cor_text)
saveRDS(list(request = request, scan = scan, network = network, quality = quality,
  adjacencies = adjacencies, toms = toms, kme = kme, chosen = chosen,
  genes = raw[[1]], samples = names(raw)[-1], rng_before = rng_before, rng_after = .Random.seed,
  resolved_packages = as.list(setNames(vapply(packages, find.package, character(1)), packages))),
  "/case/fresh-author-reference.rds", version = 3)
