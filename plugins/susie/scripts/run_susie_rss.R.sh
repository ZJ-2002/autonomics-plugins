options(width = 200L)

env_number <- function(name, default, lower = -Inf, upper = Inf, integer = FALSE) {
  value <- Sys.getenv(name, unset = "")
  parsed <- if (nzchar(value)) suppressWarnings(as.numeric(value)) else default
  if (length(parsed) != 1L || !is.finite(parsed) || parsed < lower || parsed > upper ||
      (integer && parsed != floor(parsed))) {
    stop(name, " must be a finite ", if (integer) "integer" else "number",
         " in [", lower, ", ", upper, "]")
  }
  parsed
}

env_logical <- function(name, default) {
  value <- tolower(Sys.getenv(name, unset = ""))
  if (!nzchar(value)) return(default)
  if (!value %in% c("true", "false", "1", "0")) stop(name, " must be true or false")
  value %in% c("true", "1")
}

env_string <- function(name, default) {
  value <- Sys.getenv(name, unset = "")
  if (nzchar(value)) value else default
}

numeric_column <- function(value, name) {
  parsed <- suppressWarnings(as.numeric(value))
  if (any(!is.finite(parsed))) stop(name, " must contain only finite numeric values")
  parsed
}

run <- function(output_paths) {
  if (as.character(packageVersion("susieR")) != "0.16.6") stop("susieR 0.16.6 is required")
  input_path <- Sys.getenv("AUTONOMICS_INPUT0")
  lines <- readLines(input_path, warn = FALSE)
  if (length(lines) < 2L || any(!nzchar(lines))) stop("input must be a nonempty rectangular TSV")
  widths <- lengths(strsplit(lines, "\t", fixed = TRUE))
  if (any(widths != widths[1L])) stop("input must be a rectangular TSV without empty trailing fields")
  headers <- strsplit(lines[1L], "\t", fixed = TRUE)[[1L]]
  if (any(!nzchar(headers)) || anyDuplicated(headers)) stop("input column names must be nonempty and unique")
  sumstats <- read.delim(input_path, check.names = FALSE, stringsAsFactors = FALSE,
                        colClasses = "character", na.strings = character(), quote = "", comment.char = "")
  required <- c("snp", "chrom", "z")
  missing <- setdiff(required, names(sumstats))
  if (length(missing)) stop("input is missing required columns: ", paste(missing, collapse = ", "))
  snps <- sumstats$snp
  if (any(!nzchar(snps)) || anyDuplicated(snps)) stop("SNP keys must be nonempty and unique")
  chroms <- numeric_column(sumstats$chrom, "chrom")
  if (length(unique(chroms)) != 1L || any(chroms != floor(chroms)) || any(chroms < 1 | chroms > 22)) {
    stop("susie_rss container requires exactly one autosomal chromosome per run")
  }
  chrom <- as.integer(chroms[1L])
  identifiers <- strsplit(snps, ":", fixed = TRUE)
  if (any(lengths(identifiers) != 4L)) stop("SNP IDs must use chr:pos:allele1:allele2")
  id_chrom <- numeric_column(vapply(identifiers, `[[`, "", 1L), "SNP chromosome")
  positions <- numeric_column(vapply(identifiers, `[[`, "", 2L), "SNP position")
  if (any(id_chrom != chrom) || any(positions <= 0 | positions != floor(positions))) {
    stop("SNP IDs must agree with chrom and have positive integer positions")
  }
  reference_a1 <- vapply(identifiers, `[[`, "", 3L)
  reference_a2 <- vapply(identifiers, `[[`, "", 4L)
  if (any(!grepl("^[ACGT]+$", reference_a1)) || any(!grepl("^[ACGT]+$", reference_a2)) ||
      any(reference_a1 == reference_a2)) stop("SNP IDs must contain distinct uppercase DNA alleles")
  if (xor("a1" %in% names(sumstats), "a2" %in% names(sumstats))) stop("a1 and a2 must be supplied together")
  allele_a1 <- if ("a1" %in% names(sumstats)) sumstats$a1 else reference_a1
  allele_a2 <- if ("a2" %in% names(sumstats)) sumstats$a2 else reference_a2
  aligned <- allele_a1 == reference_a1 & allele_a2 == reference_a2
  reversed <- allele_a1 == reference_a2 & allele_a2 == reference_a1
  if (any(!aligned & !reversed)) stop("a1/a2 must match the literal BIM-ID alleles or their exact reversal; strand inference is unsupported")
  bim_path <- paste0("/panels/mixer_ref/stage_flat/chr", chrom, ".bim")
  bim <- read.table(bim_path, header = FALSE, colClasses = "character", quote = "", comment.char = "")
  if (ncol(bim) != 6L) stop("signed-LD BIM must have exactly six columns")
  matched_bim <- bim[bim[[2L]] %in% snps, , drop = FALSE]
  if (anyDuplicated(matched_bim[[2L]]) || nrow(matched_bim) != length(snps)) {
    stop("input SNPs must each match exactly one signed-LD BIM row")
  }
  matched_bim <- matched_bim[match(snps, matched_bim[[2L]]), , drop = FALSE]
  panel_a1 <- matched_bim[[5L]]
  panel_a2 <- matched_bim[[6L]]
  if (any(!((panel_a1 == reference_a1 & panel_a2 == reference_a2) |
            (panel_a1 == reference_a2 & panel_a2 == reference_a1))) ||
      any(numeric_column(matched_bim[[1L]], "BIM chromosome") != chrom) ||
      any(numeric_column(matched_bim[[4L]], "BIM position") != positions)) {
    stop("signed-LD BIM coordinates or allele pairs disagree with literal SNP IDs")
  }
  orientation <- ifelse(allele_a1 == panel_a1, 1, -1)
  z_scores <- numeric_column(sumstats$z, "z")
  n_value <- NULL
  if ("n" %in% names(sumstats)) {
    input_n <- numeric_column(sumstats$n, "n")
    if (length(unique(input_n)) != 1L || input_n[1L] <= 1) stop("n must be constant across variants and greater than one")
    n_value <- input_n[1L]
  }
  if (nzchar(Sys.getenv("SUSIE_N", unset = ""))) {
    override_n <- env_number("SUSIE_N", 0, lower = 1)
    if (override_n <= 1) stop("SUSIE_N must be greater than one")
    if (!is.null(n_value) && override_n != n_value) stop("SUSIE_N disagrees with the input n column")
    n_value <- override_n
  }
  effects <- as.integer(env_number("SUSIE_L", 10, lower = 1, integer = TRUE))
  prior_method <- env_string("SUSIE_ESTIMATE_PRIOR_METHOD", "optim")
  if (!prior_method %in% c("optim", "EM", "simple")) stop("estimate_prior_method must be one of: optim, EM, simple")
  z_method <- env_string("SUSIE_Z_METHOD", "wald")
  if (!z_method %in% c("wald", "score")) stop("z_method must be one of: wald, score")
  residual_variance <- env_logical("SUSIE_ESTIMATE_RESIDUAL_VARIANCE", FALSE)
  if (residual_variance) stop("estimate_residual_variance=true requires an in-sample LD route; this node uses external reference LD")
  prior_variance <- env_logical("SUSIE_ESTIMATE_PRIOR_VARIANCE", TRUE)
  coverage <- env_number("SUSIE_COVERAGE", 0.95, lower = 0, upper = 1)
  min_abs_corr <- env_number("SUSIE_MIN_ABS_CORR", 0.5, lower = 0, upper = 1)
  scaled_prior_variance <- env_number("SUSIE_SCALED_PRIOR_VARIANCE", 0.2, lower = 0)
  if (scaled_prior_variance <= 0) stop("scaled_prior_variance must be positive")
  r2_min <- env_number("SUSIE_R2_MIN", 0, lower = 0, upper = 1)
  null_threshold <- env_number("SUSIE_CHECK_NULL_THRESHOLD", 0)
  max_iter <- as.integer(env_number("SUSIE_MAX_ITER", 100, lower = 1, integer = TRUE))
  seed <- as.integer(env_number("SUSIE_SEED", 1, lower = 0, upper = .Machine$integer.max, integer = TRUE))
  workdir <- Sys.getenv("AUTONOMICS_WORKDIR")
  if (!nzchar(workdir)) stop("AUTONOMICS_WORKDIR is required")
  query_path <- file.path(workdir, ".autonomics", "susie_query.tsv")
  dir.create(dirname(query_path), recursive = TRUE, showWarnings = FALSE)
  write.table(data.frame(SNP = snps, A1 = panel_a1, A2 = panel_a2,
                        N = if (is.null(n_value)) 500 else n_value, Z = z_scores * orientation),
              query_path, sep = "\t", row.names = FALSE, quote = FALSE)
  pairs_path <- file.path(workdir, ".autonomics", "susie_ld_pairs.tsv")
  stderr_path <- paste0(pairs_path, ".stderr")
  status <- system2("python3", c("/opt/susie/bin/susie_ld_query.py", "--engine-home", "/opt/mixer",
                   "--lib", "/opt/mixer/lib/libbgmg.so", "--bim-file", "/panels/mixer_ref/stage_flat/chr@.bim",
                   "--ld-file", "/panels/mixer_ref/ld_mixer/1000G.EUR.chr@", "--chrom", as.character(chrom),
                   "--trait1-file", shQuote(query_path), "--r2-min", format(r2_min, scientific = FALSE)),
                    stdout = pairs_path, stderr = stderr_path)
  if (status != 0) {
    diagnostic <- if (file.exists(stderr_path)) paste(readLines(stderr_path, warn = FALSE), collapse = "\n") else ""
    stop("susie LD query failed with status ", status, ": ", diagnostic)
  }
  raw_pairs <- readLines(pairs_path, warn = FALSE)
  matched <- sub("^#matched\t", "", grep("^#matched\t", raw_pairs, value = TRUE))
  if (anyDuplicated(matched) || !setequal(snps, matched)) stop("signed-LD reference did not match the exact input SNP set")
  pair_rows <- raw_pairs[!grepl("^#", raw_pairs) & nzchar(raw_pairs)]
  variant_count <- length(snps)
  ld_matrix <- diag(variant_count)
  dimnames(ld_matrix) <- list(snps, snps)
  observed <- matrix(FALSE, nrow = variant_count, ncol = variant_count)
  diag(observed) <- TRUE
  if (length(pair_rows)) {
    pairs <- read.table(text = paste(pair_rows, collapse = "\n"), sep = "\t", header = FALSE,
                        col.names = c("id_a", "id_b", "r"), colClasses = c("character", "character", "numeric"),
                        quote = "", comment.char = "")
    if (any(!pairs$id_a %in% snps) || any(!pairs$id_b %in% snps) ||
        any(!is.finite(pairs$r)) || any(abs(pairs$r) > 1)) stop("invalid signed-LD pair values or identifiers")
    seen <- new.env(hash = TRUE, parent = emptyenv())
    for (pair_index in seq_len(nrow(pairs))) {
      first <- match(pairs$id_a[pair_index], snps)
      second <- match(pairs$id_b[pair_index], snps)
      correlation <- pairs$r[pair_index]
      key <- paste(sort(c(first, second)), collapse = ":")
      if (exists(key, envir = seen, inherits = FALSE) && abs(get(key, envir = seen) - correlation) > 1e-8) {
        stop("conflicting signed-LD entries for one SNP pair")
      }
      if (first == second && abs(correlation - 1) > 1e-8) stop("signed-LD diagonal must be one")
      assign(key, correlation, envir = seen)
      ld_matrix[first, second] <- ld_matrix[second, first] <- correlation
      observed[first, second] <- observed[second, first] <- TRUE
    }
  }
  if (any(!observed)) stop("signed-LD panel omits variant pairs; absent sparse entries cannot be treated as zero correlations")
  eigenvalues <- eigen(ld_matrix, symmetric = TRUE, only.values = TRUE)$values
  if (min(eigenvalues) < -1e-6 * variant_count) stop("signed-LD matrix is not positive semidefinite; no automatic repair is performed")
  ld_matrix <- ld_matrix * tcrossprod(orientation)
  set.seed(seed)
  fit <- susieR::susie_rss(z = z_scores, R = ld_matrix, n = n_value, L = effects,
                         scaled_prior_variance = scaled_prior_variance,
                         estimate_residual_variance = FALSE, estimate_prior_variance = prior_variance,
                         estimate_prior_method = prior_method, z_method = z_method,
                         check_null_threshold = null_threshold, coverage = coverage,
                         min_abs_corr = min_abs_corr, max_iter = max_iter)
  cat("## susieR susie_rss 0.16.6\nvariants:", variant_count, "\nniter:", fit$niter,
      "\nconverged:", isTRUE(fit$converged), "\nseed:", seed, "\n")
  if (!isTRUE(fit$converged)) stop("official SuSiE fit did not converge; result outputs are not published")
  pip <- susieR::susie_get_pip(fit)
  if (length(pip) != variant_count || any(!is.finite(pip)) || any(pip < 0 | pip > 1) ||
      any(!is.finite(fit$alpha)) || any(!is.finite(fit$mu)) || any(!is.finite(fit$mu2))) {
    stop("official SuSiE fit contains invalid PIP or effect summaries")
  }
  credible_sets <- fit$sets$cs
  cat("credible sets:", length(credible_sets), "\n")
  if (length(credible_sets)) print(credible_sets)
  membership <- integer(variant_count)
  membership_all <- rep("", variant_count)
  if (length(credible_sets)) {
    for (set_index in seq_along(credible_sets)) {
      members <- as.integer(credible_sets[[set_index]])
      membership[members] <- set_index
      membership_all[members] <- ifelse(nzchar(membership_all[members]),
                                       paste(membership_all[members], set_index, sep = ";"), as.character(set_index))
    }
  }
  best_effect <- apply(fit$alpha, 2, which.max)
  effect_indices <- cbind(best_effect, seq_len(variant_count))
  output <- data.frame(snp = snps, pip = pip, cs = membership,
                       alpha = apply(fit$alpha, 2, max), mu = fit$mu[effect_indices],
                       mu2 = fit$mu2[effect_indices], lbf = fit$lbf_variable[effect_indices],
                       cs_all = membership_all, stringsAsFactors = FALSE)
  if (any(is.na(output$lbf)) || any(output$lbf == Inf)) stop("official SuSiE fit has invalid log Bayes factors")
  staged_tsv <- tempfile("susie-", tmpdir = dirname(output_paths[1L]))
  staged_rds <- tempfile("susie-", tmpdir = dirname(output_paths[2L]))
  on.exit(unlink(c(staged_tsv, staged_rds)), add = TRUE)
  write.table(output, staged_tsv, sep = "\t", row.names = FALSE, quote = FALSE)
  saveRDS(fit, staged_rds)
  if (!file.link(staged_tsv, output_paths[1L])) stop("TSV output publication failed; existing output is never replaced")
  if (!file.link(staged_rds, output_paths[2L])) stop("RDS output publication failed; existing output is never replaced")
}

output_paths <- vapply(0:2, function(port) Sys.getenv(paste0("AUTONOMICS_OUTPUT", port)), "")
if (any(!nzchar(output_paths)) || anyDuplicated(normalizePath(output_paths, mustWork = FALSE))) {
  stop("three distinct declared output paths are required")
}
if (any(file.exists(output_paths))) stop("output paths already exist; prior artifacts are never overwritten")
if (any(!dir.exists(dirname(output_paths)))) stop("output directories must already exist")
sink(output_paths[3L], split = TRUE)
exit_code <- tryCatch(withCallingHandlers({ run(output_paths); 0L },
                       warning = function(warning) cat("WARNING:", conditionMessage(warning), "\n")),
                      error = function(error) {
                        cat("ERROR:", conditionMessage(error), "\n")
                        message(conditionMessage(error))
                        1L
                      })
sink()
quit(status = exit_code)
