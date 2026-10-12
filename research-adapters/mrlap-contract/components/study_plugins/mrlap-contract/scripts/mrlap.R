# Frozen official MRlap transport. Statistics are supplied only by MRlap::MRlap.
fail <- function(message) stop(message, call. = FALSE)
check <- function(ok, message) if (!isTRUE(ok)) fail(message)
exact <- function(value, names_expected, label) {
  check(is.list(value) && !anyDuplicated(names(value)) &&
    setequal(names(value), names_expected), paste("unexpected keys:", label))
}
is_string <- function(value) is.character(value) && length(value) == 1L && !is.na(value)
is_sha <- function(value) is.character(value) && length(value) == 1L &&
  !is.na(value) && grepl("^[a-f0-9]{64}$", value)
hash_file <- function(path) {
  link <- Sys.readlink(path)
  check(file.exists(path) && !dir.exists(path) && (is.na(link) || !nzchar(link)), "regular materialized file required")
  digest::digest(file = path, algo = "sha256")
}
positive <- function(value) is.numeric(value) && length(value) == 1L &&
  !is.na(value) && is.finite(value) && value > 0
read_tsv <- function(path) data.table::fread(path, sep = "\t", header = TRUE,
  quote = "", na.strings = c("NA", ""), data.table = FALSE, showProgress = FALSE)
normal_columns <- c("snp", "chr", "pos", "beta", "se", "effect_allele", "other_allele", "eaf", "pval")
input_keys <- c("full_exposure", "full_outcome", "sample_sizes", "selected_exposure", "selected_outcome",
  "harmonized", "mr_audit", "panel_manifest", "mr_config")

# v4.3.2 原件保留 v4.2 的 O0–O3、工具与区域规则；版本仍须与实际上游合同逐字一致。
# 此消费面支持不是方法验收、科学签署或 G0 准入。
mrlap_protocol_supported <- function(x) {
  is_string(x) && x %in% c("4.2.1", "4.3.2")
}
mrlap_parent_protocol_matches <- function(current, parent) {
  mrlap_protocol_supported(current) && mrlap_protocol_supported(parent) && identical(current, parent)
}

read_normal <- function(path) {
  d <- read_tsv(path)
  if (is.logical(d$eaf) && all(is.na(d$eaf))) d$eaf <- as.numeric(d$eaf)
  check(identical(names(d), normal_columns) && nrow(d) > 0L && !anyDuplicated(d$snp) &&
    is.character(d$snp) && all(grepl("^rs[0-9]+$", d$snp)), "complete unique normalized rsID GWAS required")
  for (name in c("chr", "pos", "beta", "se", "eaf", "pval")) {
    check(is.numeric(d[[name]]), paste("numeric GWAS column required:", name))
  }
  check(all(is.finite(d$chr) & d$chr == floor(d$chr) & d$chr >= 1 & d$chr <= 22) &&
    all(is.finite(d$pos) & d$pos == floor(d$pos) & d$pos > 0) &&
    all(is.finite(d$beta)) && all(is.finite(d$se) & d$se > 0) &&
    all(is.finite(d$pval) & d$pval >= 0 & d$pval <= 1) &&
    all(is.na(d$eaf) | (is.finite(d$eaf) & d$eaf >= 0 & d$eaf <= 1)), "normalized GWAS values invalid")
  check(all(d$effect_allele %in% c("A", "C", "G", "T")) &&
    all(d$other_allele %in% c("A", "C", "G", "T")) &&
    all(d$effect_allele != d$other_allele), "normalized biallelic GWAS required")
  d
}

check_projection <- function(subset, full, label) {
  index <- match(subset$snp, full$snp)
  check(!anyNA(index), paste(label, "contains a SNP absent from full GWAS"))
  for (column in normal_columns) {
    a <- subset[[column]]; b <- full[[column]][index]
    check(all((is.na(a) & is.na(b)) | (!is.na(a) & !is.na(b) & a == b)),
      paste(label, "differs from full GWAS:", column))
  }
}

validate_config <- function(c) {
  exact(c, c("status", "protocol_version", "analysis_id", "exposure_id", "outcome_id", "overlap_class",
    "build", "ancestry", "effect_scale", "seed", "instrument_policy", "N_policy", "diagnostic_policy",
    "software_lock", "input_sha256"), "configuration")
  check(identical(c$status, "FROZEN") && mrlap_protocol_supported(c$protocol_version) &&
    identical(c$overlap_class, "O1") && identical(c$build, "GRCh37") && identical(c$ancestry, "EUR") &&
    identical(c$effect_scale, "MRLAP_STANDARDIZED_OBSERVED_Z_OVER_SQRT_N"), "frozen O1 EUR/GRCh37 contract required")
  for (field in c("analysis_id", "exposure_id", "outcome_id"))
    check(is_string(c[[field]]) &&
      grepl("^[A-Za-z][A-Za-z0-9_.+-]{0,127}$", c[[field]]), "construct identity invalid")
  check(positive(c$seed) && c$seed == floor(c$seed) && c$seed <= .Machine$integer.max, "seed invalid")
  exact(c$instrument_policy, c("do_pruning", "source", "complex_trait_min_iv", "retain_main_regions"), "instrument policy")
  check(identical(c$instrument_policy$do_pruning, FALSE) &&
    identical(c$instrument_policy$source, "UPSTREAM_FROZEN_DIRECT_HARMONIZATION") &&
    identical(c$instrument_policy$complex_trait_min_iv, 3L) &&
    identical(c$instrument_policy$retain_main_regions, TRUE), "prespecified user-IV method required")
  exact(c$N_policy, c("exposure", "outcome"), "N policies")
  for (p in c$N_policy) {
    exact(p, c("mode", "trait_type", "definition", "constant_n", "beta_scale"), "N policy")
    check(all(vapply(p[c("mode", "trait_type", "definition", "beta_scale")], is_string, logical(1))) &&
      p$mode %in% c("CONSTANT", "PER_SNP") && p$trait_type %in% c("CONTINUOUS", "CASE_CONTROL") &&
      p$definition %in% c("TOTAL_SAMPLE_SIZE", "EFFECTIVE_SAMPLE_SIZE") &&
      !(p$trait_type == "CASE_CONTROL" && p$definition != "TOTAL_SAMPLE_SIZE"), "case-control requires total N, not effective N")
    check(p$beta_scale %in% c("LINEAR_BETA", "LOG_ODDS_BETA") &&
      ((p$trait_type == "CASE_CONTROL" && p$beta_scale == "LOG_ODDS_BETA") ||
      (p$trait_type == "CONTINUOUS" && p$beta_scale == "LINEAR_BETA")), "case-control requires normalized log-odds beta")
    check(if (p$mode == "CONSTANT") positive(p$constant_n) else is.null(p$constant_n), "N mode/constant differs")
    if (p$mode == "CONSTANT" && p$trait_type == "CASE_CONTROL")
      check(p$constant_n == floor(p$constant_n), "case-control total N must be an integer")
  }
  exact(c$diagnostic_policy, c("min_full_exposure_rows", "min_full_outcome_rows", "min_common_hm3_rows",
    "min_cross_trait_ldsc_snps", "require_positive_outcome_h2", "bounds", "allowed_warning_messages"), "diagnostic policy")
  for (field in c("min_full_exposure_rows", "min_full_outcome_rows", "min_common_hm3_rows", "min_cross_trait_ldsc_snps"))
    check(positive(c$diagnostic_policy[[field]]) && c$diagnostic_policy[[field]] == floor(c$diagnostic_policy[[field]]),
      "prospective diagnostic coverage limits required")
  check(is.logical(c$diagnostic_policy$require_positive_outcome_h2) && length(c$diagnostic_policy$require_positive_outcome_h2) == 1L &&
    !is.na(c$diagnostic_policy$require_positive_outcome_h2), "prospective outcome heritability criterion required")
  expected <- c("h2_exp", "h2_exp_se", "h2_out", "h2_out_se", "int_crosstrait", "int_crosstrait_se",
    "polygenicity", "perSNP_heritability")
  exact(c$diagnostic_policy$bounds, expected, "prospective diagnostic bounds")
  for (b in c$diagnostic_policy$bounds)
    check(is.numeric(b) && length(b) == 2L && all(is.finite(b)) && b[1L] < b[2L], "diagnostic bounds invalid")
  allowed <- c$diagnostic_policy$allowed_warning_messages
  check(!is.null(allowed) && (is.character(allowed) || (is.list(allowed) && length(allowed) == 0L)) &&
    !anyNA(allowed) && !anyDuplicated(allowed), "exact warning allowlist required")
  exact(c$software_lock, c("R_version", "MRlap_version", "MRlap_revision", "GenomicSEM_version",
    "GenomicSEM_revision", "TwoSampleMR_version"), "software lock")
  check(identical(c$software_lock$MRlap_version, "0.0.3.3") &&
    identical(c$software_lock$MRlap_revision, "660f026864f8bfbbad5a8206bdff7d58f5d5d05b") &&
    identical(c$software_lock$GenomicSEM_version, "0.0.5") &&
    identical(c$software_lock$GenomicSEM_revision, "da95d431a4709693d07eae55e172ade55526948b") &&
    identical(c$software_lock$TwoSampleMR_version, "0.7.11"), "official method source lock differs")
  exact(c$input_sha256, input_keys, "input identities")
  check(all(vapply(c$input_sha256, is_sha, logical(1))), "complete actual input hashes required")
  invisible(c)
}

sample_sizes <- function(table, trait, full, policy) {
  part <- table[table$trait == trait, , drop = FALSE]
  check(nrow(part) > 0L && !anyDuplicated(part$snp) && is.numeric(part$N) &&
    all(is.finite(part$N) & part$N > 0), "sample sizes invalid or missing")
  if (policy$mode == "CONSTANT") {
    check(nrow(part) == 1L && identical(part$snp, "ALL") && part$N == policy$constant_n,
      "constant N must match its frozen source row")
    n <- rep(part$N, nrow(full))
  } else {
    check(setequal(part$snp, full$snp), "per-SNP N must cover the entire full GWAS exactly")
    n <- part$N[match(full$snp, part$snp)]
  }
  if (policy$trait_type == "CASE_CONTROL") check(all(n == floor(n)), "case-control total N must be integer")
  n
}

preflight <- function(paths, panel_root) {
  check(length(paths) == 10L && all(file.exists(paths)), "ten declared inputs required")
  c <- jsonlite::fromJSON(paths[1L], simplifyVector = TRUE); validate_config(c)
  hashes <- as.list(setNames(vapply(paths, hash_file, character(1)), c("config", input_keys)))
  check(all(vapply(names(c$input_sha256), function(k) identical(hashes[[k]], c$input_sha256[[k]]), logical(1))),
    "frozen content identity mismatch")
  full_x <- read_normal(paths[2L]); full_y <- read_normal(paths[3L])
  selected_x <- read_normal(paths[5L]); selected_y <- read_normal(paths[6L])
  check_projection(selected_x, full_x, "selected exposure"); check_projection(selected_y, full_y, "selected outcome")
  sizes <- read_tsv(paths[4L])
  check(identical(names(sizes), c("trait", "snp", "N")) &&
    all(sizes$trait %in% c("EXPOSURE", "OUTCOME")) && !anyNA(sizes), "sample-size source schema invalid")
  nx <- sample_sizes(sizes, "EXPOSURE", full_x, c$N_policy$exposure)
  ny <- sample_sizes(sizes, "OUTCOME", full_y, c$N_policy$outcome)
  audit <- jsonlite::fromJSON(paths[8L], simplifyVector = TRUE)
  mr_config <- jsonlite::fromJSON(paths[10L], simplifyVector = TRUE)
  check(identical(audit$scope, "OFFICIAL_HARMONIZATION_AND_IVW_NOT_CLUMP_ACCEPTANCE_OR_G0") &&
    identical(audit$analysis_id, c$analysis_id) && identical(audit$input_sha256$config, hashes$mr_config) &&
    identical(audit$input_sha256$exposure, hashes$selected_exposure) &&
    identical(audit$input_sha256$outcome, hashes$selected_outcome) &&
    identical(audit$selection_evidence$source_exposure_sha256, hashes$full_exposure) &&
    identical(audit$selection_evidence$exposure_id, c$exposure_id) &&
    identical(audit$selection_evidence$selected_exposure_sha256, hashes$selected_exposure), "upstream MR provenance differs")
  check(identical(mr_config$status, "FROZEN") && mrlap_parent_protocol_matches(c$protocol_version, mr_config$protocol_version) &&
    identical(mr_config$overlap_class, "O1") && identical(mr_config$instrument_class, "COMPLEX_TRAIT") &&
    identical(mr_config$analysis_id, c$analysis_id) && identical(mr_config$exposure_id, c$exposure_id) &&
    identical(mr_config$outcome_id, c$outcome_id) && identical(mr_config$build, c$build) &&
    identical(mr_config$ancestry, c$ancestry) &&
    identical(mr_config$input_sha256$exposure, hashes$selected_exposure) &&
    identical(mr_config$input_sha256$outcome, hashes$selected_outcome), "upstream frozen construct/overlap contract differs")
  h <- read_tsv(paths[7L])
  check(all(c("SNP", "mr_keep", "beta.exposure", "beta.outcome", "se.exposure", "se.outcome", "id.exposure", "id.outcome") %in% names(h)) &&
    !anyDuplicated(h$SNP) && setequal(h$SNP, selected_x$snp) && is.logical(h$mr_keep) && !anyNA(h$mr_keep),
    "complete upstream harmonic instrument ledger required")
  ivs <- h$SNP[h$mr_keep]
  check(length(ivs) >= 3L && all(ivs %in% full_x$snp) && all(ivs %in% full_y$snp) &&
    all(h$id.exposure[h$mr_keep] == c$exposure_id) && all(h$id.outcome[h$mr_keep] == c$outcome_id),
    "three qualified direct IVs and construct identity required")
  x <- full_x[match(ivs, full_x$snp), ]; y <- full_y[match(ivs, full_y$snp), ]
  check(all(x$chr == y$chr & x$pos == y$pos), "direct IV coordinates differ")
  check(all(x$pval < 5e-8), "retained instruments violate the frozen exposure significance threshold")
  aligned <- x$effect_allele == y$effect_allele & x$other_allele == y$other_allele
  swapped <- x$effect_allele == y$other_allele & x$other_allele == y$effect_allele
  check(all(aligned | swapped), "official MRlap requires strand-normalized GWAS for retained IVs")
  check(all(h$beta.exposure[h$mr_keep] == x$beta) &&
    all(h$beta.outcome[h$mr_keep] == ifelse(aligned, y$beta, -y$beta)) &&
    all(h$se.exposure[h$mr_keep] == x$se) && all(h$se.outcome[h$mr_keep] == y$se), "upstream harmonized effects differ from full GWAS")
  # Upstream already applied frozen inclusive palindrome/frequency rules;
  # actual DAG producer binding must prove this audit and harmonic table came
  # from the accepted MR implementation, not an invented receipt JSON.
  panel <- jsonlite::fromJSON(paths[9L], simplifyVector = FALSE)
  check(identical(panel$build, c$build) && identical(panel$ancestry, c$ancestry) && is.list(panel$files), "LD/LDSC panel build/ancestry missing")
  names_panel <- vapply(panel$files, function(r) r$path, character(1))
  required <- c("w_hm3.noMHC.snplist", unlist(lapply(1:22, function(ch) paste0("eur_w_ld_chr/", ch, c(".l2.ldscore.gz", ".l2.M_5_50")))))
  check(!anyDuplicated(names_panel) && all(required %in% names_panel) &&
    all(grepl("^[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)*$", names_panel)) &&
    !any(grepl("(^|/)\\.\\.(/|$)", names_panel)), "panel file universe invalid")
  for (r in panel$files) {
    expected <- sub("^sha256:", "", r$sha256)
    check(is_sha(expected) && identical(hash_file(file.path(panel_root, r$path)), expected), "panel content identity mismatch")
  }
  hm3 <- read_tsv(file.path(panel_root, "w_hm3.noMHC.snplist"))
  check("SNP" %in% names(hm3) && !anyNA(hm3$SNP) && !anyDuplicated(hm3$SNP), "HM3 identities invalid")
  common <- Reduce(intersect, list(full_x$snp, full_y$snp, hm3$SNP))
  d <- c$diagnostic_policy
  check(nrow(full_x) >= d$min_full_exposure_rows && nrow(full_y) >= d$min_full_outcome_rows &&
    length(common) >= d$min_common_hm3_rows, "full-GWAS/HM3 coverage below frozen applicability limits")
  convert <- function(g, n) data.frame(rsid = g$snp, chr = g$chr, pos = g$pos,
    a1 = g$effect_allele, a2 = g$other_allele, beta = g$beta, se = g$se, N = n)
  list(config = c, input_sha256 = hashes, exposure = convert(full_x, nx), outcome = convert(full_y, ny),
    ivs = ivs, source_iv_ids = selected_x$snp, common_hm3_rows = length(common), panel_manifest = panel)
}

numeric_result <- function(x, label) {
  check(is.numeric(x) && length(x) == 1L && !is.na(x) && is.finite(x), paste("official result malformed:", label))
  as.numeric(x)
}

inspect_official_result <- function(result, ivs, policy, warnings_seen, log_directory) {
  mc <- result$MRcorrection; ld <- result$LDSC; architecture <- result$GeneticArchitecture
  check(is.character(mc$IVs) && !anyDuplicated(mc$IVs) && setequal(mc$IVs, ivs) &&
    numeric_result(mc$m_IVs, "m_IVs") == length(ivs), "official retained IVs differ from frozen direct-harmonized set")
  fields <- c("h2_exp", "h2_exp_se", "h2_out", "h2_out_se", "int_crosstrait", "int_crosstrait_se")
  diagnostics <- setNames(vapply(fields, function(k) numeric_result(ld[[k]], k), numeric(1)), fields)
  for (field in c("polygenicity", "perSNP_heritability")) diagnostics[[field]] <- numeric_result(architecture[[field]], field)
  logs <- c("exposure_munge.log", "outcome_munge.log", "exposure.sumstats.gz_outcome.sumstats.gz_ldsc.log", "official-call.log")
  check(all(file.exists(file.path(log_directory, logs))), "complete official LDSC diagnostics required")
  lines <- readLines(file.path(log_directory, logs[3L]), warn = FALSE)
  pattern <- "^([0-9]+) SNPs remain after merging exposure[.]sumstats[.]gz and outcome[.]sumstats[.]gz summary statistics$"
  matches <- grep(pattern, lines, value = TRUE)
  check(length(matches) == 1L, "official cross-trait SNP count unavailable or ambiguous")
  count <- as.numeric(sub(pattern, "\\1", matches)); check(positive(count), "invalid official cross-trait SNP count")
  b <- numeric_result(mc$corrected_effect, "corrected_effect"); se <- numeric_result(mc$corrected_effect_se, "corrected_effect_se")
  pv <- numeric_result(mc$corrected_effect_p, "corrected_effect_p")
  check(se > 0 && pv >= 0 && pv <= 1, "official corrected estimate invalid")
  accepted <- diagnostics[["h2_exp"]] > 0 && (!policy$require_positive_outcome_h2 || diagnostics[["h2_out"]] > 0) &&
    diagnostics[["h2_exp_se"]] > 0 && diagnostics[["h2_out_se"]] > 0 && diagnostics[["int_crosstrait_se"]] > 0 &&
    diagnostics[["polygenicity"]] > 0 && diagnostics[["polygenicity"]] <= 1 && diagnostics[["perSNP_heritability"]] > 0 &&
    count >= policy$min_cross_trait_ldsc_snps &&
    all(warnings_seen %in% policy$allowed_warning_messages)
  for (field in names(diagnostics)) {
    bounds <- policy$bounds[[field]]
    accepted <- accepted && diagnostics[[field]] >= bounds[1L] && diagnostics[[field]] <= bounds[2L]
  }
  list(mc = mc, diagnostics = diagnostics, count = count, beta = b, se = se, p = pv, accepted = accepted, primary_p = if (accepted) pv else NA_real_, logs = logs)
}

write_audit <- function(audit, path) {
  if (!is.null(audit$diagnostic_policy))
    audit$diagnostic_policy$allowed_warning_messages <- as.list(audit$diagnostic_policy$allowed_warning_messages)
  if ("warnings" %in% names(audit)) audit$warnings <- as.list(audit$warnings)
  jsonlite::write_json(audit, path, auto_unbox = TRUE, pretty = TRUE, null = "null", digits = 17)
}

main <- function(args) {
  check(length(args) == 15L, "usage: mrlap.R ten inputs five outputs")
  outputs <- args[11:15]
  check(!anyDuplicated(outputs) && !any(file.exists(outputs)) &&
    !any(vapply(outputs, function(p) {link <- Sys.readlink(p); !is.na(link) && nzchar(link)}, logical(1))), "output already exists")
  for (package in c("jsonlite", "digest", "data.table", "MRlap", "GenomicSEM", "TwoSampleMR"))
    check(requireNamespace(package, quietly = TRUE), paste("official package unavailable:", package))
  p <- preflight(args[1:10], "/panels/mrlap_ldsc"); c <- p$config
  check(identical(as.character(getRversion()), c$software_lock$R_version), "R lock differs")
  for (package in c("MRlap", "GenomicSEM", "TwoSampleMR"))
    check(identical(as.character(utils::packageVersion(package)), c$software_lock[[paste0(package, "_version")]]), "method version differs")
  data.table::setDTthreads(2L)
  work <- tempfile("mrlap-work-"); check(dir.create(work), "private scratch unavailable")
  previous <- getwd(); setwd(work); on.exit({setwd(previous); unlink(work, recursive = TRUE)}, add = TRUE)
  warnings_seen <- character()
  connection <- file("official-call.log", "wt"); sink(connection, split = TRUE)
  RNGkind("Mersenne-Twister", "Inversion", "Rejection"); set.seed(as.integer(c$seed))
  result <- tryCatch(withCallingHandlers(MRlap::MRlap(exposure = p$exposure, outcome = p$outcome,
    exposure_name = "exposure", outcome_name = "outcome", ld = "/panels/mrlap_ldsc/eur_w_ld_chr",
    hm3 = "/panels/mrlap_ldsc/w_hm3.noMHC.snplist", do_pruning = FALSE, user_SNPsToKeep = p$ivs,
    save_logfiles = TRUE, verbose = TRUE), warning = function(w) warnings_seen <<- c(warnings_seen, conditionMessage(w))),
    finally = {sink(); close(connection)})
  inspected <- inspect_official_result(result, p$ivs, c$diagnostic_policy, warnings_seen, work)
  mc <- inspected$mc; diagnostics <- inspected$diagnostics; count <- inspected$count
  b <- inspected$beta; se <- inspected$se; pv <- inspected$p; accepted <- inspected$accepted; logs <- inspected$logs
  # Any scientific applicability failure keeps raw official quantities in the
  # private result, but never substitutes the observed IVW P for primary P.
  estimate <- data.frame(analysis_id = c$analysis_id, exposure_id = c$exposure_id, outcome_id = c$outcome_id,
    overlap_class = "O1", analysis_scope = "MAIN", method = "MRlap_corrected", n_iv = length(p$ivs),
    effect_scale = c$effect_scale, status = if (accepted) "ESTIMATED" else "NOT_ESTIMABLE",
    reason = if (accepted) "" else "FROZEN_MRLAP_DIAGNOSTICS_REJECTED", beta = b, se = se, p = pv,
    primary_p = inspected$primary_p, primary_source = if (accepted) "O1_MRLAP_CORRECTED" else "NOT_SUPPLIED",
    observed_beta = numeric_result(mc$observed_effect, "observed_effect"),
    observed_se = numeric_result(mc$observed_effect_se, "observed_effect_se"))
  retention <- data.frame(snp = p$source_iv_ids, requested = p$source_iv_ids %in% p$ivs,
    retained = p$source_iv_ids %in% mc$IVs,
    status = ifelse(p$source_iv_ids %in% mc$IVs, "RETAINED_BY_OFFICIAL_MRLAP", "EXCLUDED_BY_UPSTREAM_FROZEN_HARMONIZATION"))
  check(identical(vapply(args[1:10], hash_file, character(1), USE.NAMES = FALSE), unname(unlist(p$input_sha256, use.names = TRUE))), "input changed during official execution")
  audit <- list(scope = "OFFICIAL_FROZEN_MRLAP_NOT_G0_OR_SCIENTIFIC_SIGNOFF", authorization = "NONE",
    analysis_id = c$analysis_id, exposure_id = c$exposure_id, outcome_id = c$outcome_id, overlap_class = "O1",
    input_sha256 = p$input_sha256, software_lock = c$software_lock, diagnostic_policy = c$diagnostic_policy,
    source_revision_check = "REQUIRES_INDEPENDENT_PINNED_IMAGE_FUNCTION_AST_QUALIFICATION",
    diagnostics = as.list(diagnostics), cross_trait_ldsc_snps = count, pre_munge_common_hm3_rows = p$common_hm3_rows,
    warnings = warnings_seen, diagnostic_pass = accepted, requested_iv_ids = p$ivs, retained_iv_ids = mc$IVs,
    internal_pruning = FALSE, internal_reverse_filter_applied = FALSE, main_region_removal = FALSE,
    seed = c$seed, effect_scale = c$effect_scale, session_info = capture.output(sessionInfo()))
  for (output in outputs) dir.create(dirname(output), recursive = TRUE, showWarnings = FALSE)
  utils::write.table(estimate, outputs[1L], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  utils::write.table(retention, outputs[2L], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
  write_audit(audit, outputs[3L])
  saveRDS(result, outputs[4L])
  status <- system2("tar", c("--sort=name", "--mtime=@0", "--owner=0", "--group=0", "--numeric-owner",
    "-cf", shQuote(outputs[5L]), shQuote(logs)))
  check(identical(status, 0L), "official diagnostic archive publication failed")
}

if (sys.nframe() == 0L) tryCatch(main(commandArgs(trailingOnly = TRUE)), error = function(e) {
  message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)
})
