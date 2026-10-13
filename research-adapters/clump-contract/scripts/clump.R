# 仅按 exposure 选择工具：流式读取合格输入，再调用官方 PLINK2。
# 本层不接收 outcome，不生成科学签署；正式面板仍须引擎内容准入。
# Formatting only: preserve double values across a TSV parse without changing
# the input frame, scientific calculations, thresholds or missing-value rules.
write_lossless_tsv <- function(x, file, ...) {
  if (!is.data.frame(x)) stop("lossless TSV output requires a data frame", call. = FALSE)
  encoded <- x
  for (i in seq_along(encoded)) {
    value <- encoded[[i]]
    if (is.double(value) && !is.object(value)) {
      text <- sprintf("%.17g", value)
      text[is.na(value)] <- NA_character_
      encoded[[i]] <- text
    }
  }
  utils::write.table(encoded, file, sep = "\t", quote = FALSE,
    row.names = FALSE, na = "NA", ...)
}

fail <- function(message) stop(message, call. = FALSE)
check <- function(ok, message) if (!isTRUE(ok)) fail(message)
sha <- function(path) digest::digest(file = path, algo = "sha256")
is_sha <- function(x) is.character(x) && length(x) == 1L && !is.na(x) && grepl("^[0-9a-f]{64}$", x)
keys <- function(x, expected, label) check(is.list(x) && setequal(names(x), expected) &&
  !anyDuplicated(names(x)), paste(label, "schema differs"))
header <- c("snp", "chr", "pos", "beta", "se", "effect_allele", "other_allele", "eaf", "pval")
read_rows <- function(lines) {
  check(all(lengths(strsplit(lines, "\t", fixed = TRUE)) == length(header)), "malformed normalized SNP row")
  utils::read.delim(text = paste(c(paste(header, collapse = "\t"), lines), collapse = "\n"),
    colClasses = "character", check.names = FALSE, quote = "", comment.char = "", na.strings = c("NA", ""), fill = FALSE)
}

clump_frozen <- function(config_path, exposure_path, panel_path, normalization_path, normalization_recipe_path, panel_root, work, outputs,
                         source_receipt_validator = normalization_receipt, source_mode = "SINGLE_EXPOSURE") {
  for (package in c("jsonlite", "digest")) check(requireNamespace(package, quietly = TRUE), paste("package unavailable:", package))
  check(identical(Sys.getenv("LC_ALL"), "C"), "deterministic C locale required")
  c <- jsonlite::fromJSON(config_path, simplifyVector = FALSE)
  keys(c, c("status", "protocol_version", "exposure_id", "build", "ancestry", "instrument_class",
    "normalization_recipe_sha256", "policy", "panel_prefixes", "software_lock", "input_sha256"), "configuration")
  check(identical(c$status, "FROZEN") && frozen_protocol_supported(c$protocol_version), "frozen supported-protocol configuration required; templates are not runnable")
  check(is.character(c$exposure_id) && length(c$exposure_id) == 1L && grepl("^[A-Za-z0-9._:-]+$", c$exposure_id) &&
    c$build %in% c("GRCh37", "GRCh38") && is.character(c$ancestry) && length(c$ancestry) == 1L && nzchar(c$ancestry) &&
    identical(c$instrument_class, "COMPLEX_TRAIT") && is_sha(c$normalization_recipe_sha256), "source normalization/build/ancestry contract required")
  keys(c$policy, c("p_threshold", "clump_r2", "r2_comparison", "clump_kb", "tie_order", "ld_mode", "threads", "memory_mib"), "policy")
  tie <- unlist(c$policy$tie_order, use.names = FALSE)
  check(identical(c$policy$p_threshold, 5e-8) && identical(c$policy$clump_r2, 0.001) &&
    identical(c$policy$r2_comparison, "STRICT_LT") && identical(c$policy$clump_kb, 10000L) &&
    identical(tie, c("pval", "chr", "pos", "snp")) &&
    identical(c$policy$ld_mode, "HAPLOTYPE_MLE") && identical(c$policy$threads, 1L) &&
    identical(c$policy$memory_mib, 640L), "clumping policy differs from accepted implementation")
  keys(c$panel_prefixes, as.character(1:22), "panel chromosome prefixes")
  check(all(vapply(c$panel_prefixes, function(p) is.character(p) && length(p) == 1L &&
    grepl("^[A-Za-z0-9_-][A-Za-z0-9._-]*$", p) && !grepl("\\.\\.", p), logical(1))) &&
    !anyDuplicated(unlist(c$panel_prefixes)), "unsafe or duplicate panel prefix")
  keys(c$input_sha256, c("exposure", "panel_manifest", "normalization"), "input hashes")
  check(all(vapply(c$input_sha256, is_sha, logical(1))), "complete input hashes required")
  hashes <- list(config = sha(config_path), exposure = sha(exposure_path), panel_manifest = sha(panel_path),
    normalization = sha(normalization_path), normalization_recipe = sha(normalization_recipe_path))
  check(all(vapply(names(c$input_sha256), function(k) identical(hashes[[k]], c$input_sha256[[k]]), logical(1))), "input content identity mismatch")
  check(source_mode %in% c("SINGLE_EXPOSURE", "JOINT_TWO_EXPOSURE_UNION"), "unsupported clump source mode")
  normal <- source_receipt_validator(normalization_path, normalization_recipe_path, exposure_path,
    c$normalization_recipe_sha256, c$exposure_id, c$build, c$ancestry, c$protocol_version)
  keys(c$software_lock, c("R_version", "plink_version", "plink_binary_sha256"), "software lock")
  plink <- Sys.which("plink2")
  check(nzchar(plink) && identical(c$software_lock$R_version, as.character(getRversion())) &&
    is_sha(c$software_lock$plink_binary_sha256) && identical(sha(plink), c$software_lock$plink_binary_sha256), "software lock mismatch")
  version <- system2(plink, "--version", stdout = TRUE, stderr = TRUE)
  check(is.null(attr(version, "status")) && length(version) == 1L && identical(version, c$software_lock$plink_version), "PLINK version mismatch")
  panel <- jsonlite::fromJSON(panel_path, simplifyVector = FALSE)
  check(panel$schema_version %in% c(1L, 2L) && is.character(panel$digest) &&
    grepl("^sha256:[0-9a-f]{64}$", panel$digest) && identical(panel$metadata$genome_build, c$build) &&
    identical(panel$metadata$population, c$ancestry), "panel build/ancestry or digest differs")
  expected <- unlist(lapply(c$panel_prefixes, function(p) paste0(p, c(".bed", ".bim", ".fam"))), use.names = FALSE)
  paths <- vapply(panel$files, function(f) f$path, character(1))
  check(length(paths) == 66L && !anyDuplicated(paths) && setequal(paths, expected), "complete panel file universe differs")
  for (f in panel$files) {
    keys(f, c("path", "size", "sha256"), "panel file")
    path <- file.path(panel_root, f$path)
    check(!nzchar(Sys.readlink(path)) && file.exists(path) && !dir.exists(path) &&
      is.numeric(f$size) && f$size >= 0 && f$size == floor(f$size) && file.info(path)$size == f$size &&
      is.character(f$sha256) && grepl("^sha256:[0-9a-f]{64}$", f$sha256) &&
      identical(paste0("sha256:", sha(path)), f$sha256), paste("panel payload identity mismatch:", f$path))
  }
  check(dir.create(work, mode = "0700"), "fresh clumping workspace required")
  # 官方 clump 只作为诊断；临界值实测证明其快速路径与官方 LD 矩阵不一致。
  # 选择依据为官方 phased LD 双精度矩阵，再按冻结顺序进行严格比较。
  # 资源上限导致整节点拒绝，不截断候选集，不放宽科学阈值。
  matrix_variant_limit <- 4096L
  effective_r2 <- "0.0009999999999999998"
  check(as.numeric(effective_r2) < 0.001 && 0.001 - as.numeric(effective_r2) == 2^-62, "IEEE threshold adapter mismatch")
  calls <- list()
  invoke <- function(binary, args, label) {
    stdout <- file.path(work, paste0(label, ".stdout")); stderr <- file.path(work, paste0(label, ".stderr"))
    status <- system2(binary, args = vapply(args, shQuote, character(1)), stdout = stdout, stderr = stderr)
    check(file.info(stdout)$size <= 16*1024^2 && file.info(stderr)$size <= 16*1024^2, "execution log exceeded evidence bound")
    calls[[length(calls)+1L]] <<- list(executable = binary, argv = args, exit_code = status,
      stdout = paste(readLines(stdout, warn = FALSE), collapse = "\n"), stderr = paste(readLines(stderr, warn = FALSE), collapse = "\n"),
      stdout_sha256 = sha(stdout), stderr_sha256 = sha(stderr))
    check(identical(status, 0L), paste("upstream execution failed:", label))
  }
  con <- file(exposure_path, open = "r"); on.exit(close(con), add = TRUE)
  check(identical(readLines(con, n = 1L, warn = FALSE), paste(header, collapse = "\t")), "normalized exposure schema differs")
  id_path <- file.path(work, "all_ids.txt"); id_con <- file(id_path, open = "w"); on.exit(close(id_con), add = TRUE)
  qc_path <- file.path(work, "qc.tsv"); qc <- file(qc_path, open = "w"); on.exit(close(qc), add = TRUE)
  writeLines("snp\tphase\tstatus\treason", qc)
  candidates <- list(); total <- invalid <- nonsignificant <- 0L
  repeat {
    lines <- readLines(con, n = 10000L, warn = FALSE)
    if (!length(lines)) break
    d <- read_rows(lines)
    check(!anyNA(d$snp) && all(grepl("^[A-Za-z0-9._:+-]+$", d$snp)), "empty or malformed variant identity")
    writeLines(d$snp, id_con)
    num <- lapply(d[c("chr", "pos", "beta", "se", "eaf", "pval")], function(x) suppressWarnings(as.numeric(x)))
    valid <- is.finite(num$chr) & num$chr %in% 1:22 & is.finite(num$pos) & num$pos >= 1 & num$pos == floor(num$pos) &
      is.finite(num$beta) & is.finite(num$se) & num$se > 0 & is.finite(num$pval) & num$pval >= 0 & num$pval <= 1 &
      (is.na(d$eaf) | (is.finite(num$eaf) & num$eaf >= 0 & num$eaf <= 1)) &
      !is.na(d$effect_allele) & !is.na(d$other_allele) & d$effect_allele %in% c("A", "C", "G", "T") &
      d$other_allele %in% c("A", "C", "G", "T") & d$effect_allele != d$other_allele
    valid[is.na(valid)] <- FALSE
    significant <- valid & num$pval < 5e-8; significant[is.na(significant)] <- FALSE
    reason <- ifelse(!valid, "INVALID_NORMALIZED_EXPOSURE_ROW", ifelse(significant, "", "P_THRESHOLD_NOT_MET"))
    writeLines(paste(d$snp, "SOURCE_QC", ifelse(significant, "CANDIDATE", "EXCLUDED"), reason, sep = "\t"), qc)
    if (any(significant)) candidates[[length(candidates)+1L]] <- d[significant, , drop = FALSE]
    total <- total + nrow(d); invalid <- invalid + sum(!valid); nonsignificant <- nonsignificant + sum(valid & !significant)
  }
  close(id_con); on.exit(NULL, add = FALSE); close(qc); close(con)
  check(total == normal$retained_rows && invalid == 0L, "normalized source row count or validity differs from verified transformation")
  # 所有 ID 的重复检查用外排序；不会为几百万非候选行建立内存哈希表。
  sorted_ids <- file.path(work, "sorted_ids.txt")
  invoke("/usr/bin/sort", c("--buffer-size=64M", "--parallel=1", "--temporary-directory", work,
    "--output", sorted_ids, id_path), "identity_sort")
  sorted <- file(sorted_ids, open = "r"); last <- NULL
  repeat {
    ids <- readLines(sorted, n = 10000L, warn = FALSE)
    if (!length(ids)) break
    check(!anyDuplicated(ids) && (is.null(last) || last != ids[1L]), "duplicate variant identity in complete exposure source")
    last <- tail(ids, 1L)
  }
  close(sorted)
  if (length(candidates)) {
    candidate <- do.call(rbind, candidates)
    index <- order(as.numeric(candidate$pval), as.numeric(candidate$chr), as.numeric(candidate$pos), candidate$snp, method = "radix")
    candidate <- candidate[index, , drop = FALSE]
  } else candidate <- setNames(as.data.frame(rep(list(character()), 9L)), header)
  kept <- character(); excluded <- list(); ld_matrices <- list()
  for (chr in sort(unique(as.integer(candidate$chr)))) {
    sub <- candidate[as.integer(candidate$chr) == chr, , drop = FALSE]
    prefix <- file.path(panel_root, c$panel_prefixes[[as.character(chr)]])
    # 先核对 BIM 的 ID/坐标/等位基因；缺面板变异逐条登记，不降阈值补数。
    b <- file(paste0(prefix, ".bim"), "r"); found <- list()
    repeat {
      lines <- readLines(b, n = 10000L, warn = FALSE)
      if (!length(lines)) break
      d <- utils::read.table(text = paste(lines, collapse = "\n"), colClasses = "character", quote = "", comment.char = "", fill = FALSE)
      check(ncol(d) == 6L, "invalid panel BIM schema")
      match_rows <- which(d[[2L]] %in% sub$snp)
      if (length(match_rows)) found[[length(found)+1L]] <- d[match_rows, , drop = FALSE]
    }
    close(b)
    ref <- if (length(found)) do.call(rbind, found) else as.data.frame(rep(list(character()), 6L))
    check(!anyDuplicated(ref[[2L]]), "duplicate candidate identity in reference panel")
    lookup <- match(sub$snp, ref[[2L]])
    available <- !is.na(lookup)
    for (i in which(available)) {
      r <- ref[lookup[i], ]
      alleles <- c(sub$effect_allele[i], sub$other_allele[i])
      complement <- unname(c(A = "T", C = "G", G = "C", T = "A")[alleles])
      check(as.integer(r[[1L]]) == chr && as.numeric(r[[4L]]) == as.numeric(sub$pos[i]) &&
        (setequal(c(r[[5L]], r[[6L]]), alleles) || setequal(c(r[[5L]], r[[6L]]), complement)),
        "reference coordinates or alleles differ")
    }
    absent <- sub$snp[!available]
    if (length(absent)) excluded[[length(excluded)+1L]] <- data.frame(snp = absent, status = "EXCLUDED", reason = "REFERENCE_VARIANT_MISSING")
    sub <- sub[available, , drop = FALSE]
    if (!nrow(sub)) next
    check(nrow(sub) <= matrix_variant_limit, "official LD matrix exceeds qualified resource bound; no candidate truncation permitted")
    ids <- file.path(work, paste0("chr", chr, ".extract")); writeLines(sub$snp, ids)
    pfile <- file.path(work, paste0("chr", chr, ".sorted"))
    invoke(plink, c("--bfile", prefix, "--extract", ids, "--make-pgen", "--sort-vars", "ascii",
      "--threads", "1", "--memory", "640", "require", "--out", pfile), paste0("chr", chr, "_sort"))
    pvar <- utils::read.delim(paste0(pfile, ".pvar"), comment.char = "", check.names = FALSE, stringsAsFactors = FALSE)
    check(all(c("#CHROM", "POS", "ID") %in% names(pvar)) && setequal(pvar$ID, sub$snp) &&
      identical(order(as.integer(pvar[["#CHROM"]]), pvar$POS, pvar$ID, method = "radix"), seq_len(nrow(pvar))), "sorted reference variant order differs")
    association <- file.path(work, paste0("chr", chr, ".assoc"))
    write_lossless_tsv(data.frame(SNP = sub$snp, P = sub$pval), association)
    result <- file.path(work, paste0("chr", chr, ".clump"))
    invoke(plink, c("--pfile", pfile, "--clump", association, "--clump-id-field", "SNP", "--clump-p-field", "P",
      "--clump-p1", "5e-8", "--clump-p2", "5e-8", "--clump-r2", effective_r2, "--clump-kb", "10000",
      "--threads", "1", "--memory", "640", "require", "--out", result), paste0("chr", chr, "_clump"))
    report <- utils::read.delim(paste0(result, ".clumps"), check.names = FALSE, stringsAsFactors = FALSE)
    check("ID" %in% names(report) && !anyDuplicated(report$ID) && all(report$ID %in% sub$snp), "PLINK clump report identity differs")
    ld_prefix <- file.path(work, paste0("chr", chr, ".ld"))
    invoke(plink, c("--pfile", pfile, "--r2-phased", "square", "bin", "--threads", "1",
      "--memory", "640", "require", "--out", ld_prefix), paste0("chr", chr, "_ld"))
    ld_path <- paste0(ld_prefix, ".phased.vcor2.bin")
    ld_ids <- readLines(paste0(ld_path, ".vars"), warn = FALSE)
    check(identical(ld_ids, as.character(pvar$ID)) && !anyDuplicated(ld_ids) &&
      file.info(ld_path)$size == 8 * length(ld_ids)^2, "official LD matrix identity or size differs")
    ld_connection <- file(ld_path, "rb")
    ld_values <- readBin(ld_connection, "double", n = length(ld_ids)^2, size = 8L, endian = .Platform$endian)
    close(ld_connection)
    ld <- matrix(ld_values, nrow = length(ld_ids), byrow = TRUE)
    check(length(ld_values) == length(ld_ids)^2 && all(is.finite(ld_values)) &&
      all(ld_values >= 0 & ld_values <= 1 + 1e-12) &&
      all(abs(diag(ld) - 1) <= 1e-12) && identical(ld, t(ld)),
      "official LD is undefined or invalid; no independence may be inferred")
    positions <- as.numeric(sub$pos)
    indices <- match(sub$snp, ld_ids)
    blocked <- rep(FALSE, nrow(sub)); chosen <- character()
    for (i in seq_len(nrow(sub))) {
      if (blocked[i]) next
      chosen <- c(chosen, sub$snp[i])
      nearby <- abs(positions - positions[i]) <= 10000000
      blocked[nearby & ld[indices[i], indices] >= 0.001] <- TRUE
      blocked[i] <- TRUE
    }
    calls[[length(calls)]]$ld_matrix_sha256 <- sha(ld_path)
    calls[[length(calls)]]$ld_order_sha256 <- sha(paste0(ld_path, ".vars"))
    calls[[length(calls)]]$selected_ids <- chosen
    calls[[length(calls)]]$diagnostic_clump_ids <- as.character(report$ID)
    calls[[length(calls)]]$diagnostic_agrees <- setequal(chosen, report$ID)
    ld_matrices[[length(ld_matrices)+1L]] <- list(chromosome = chr, variant_count = length(ld_ids),
      matrix_path = basename(ld_path), matrix_sha256 = sha(ld_path), matrix_bytes = file.info(ld_path)$size,
      order_path = basename(paste0(ld_path, ".vars")), order_sha256 = sha(paste0(ld_path, ".vars")),
      double_bytes = 8L, endian = .Platform$endian)
    kept <- c(kept, chosen)
    removed <- setdiff(sub$snp, chosen)
    if (length(removed)) excluded[[length(excluded)+1L]] <- data.frame(snp = removed, status = "EXCLUDED", reason = "LD_CLUMPED")
    rm(ld, ld_values); gc(verbose = FALSE)
  }
  selected <- candidate[candidate$snp %in% kept, , drop = FALSE]
  check(!anyDuplicated(kept) && setequal(selected$snp, kept), "selected instrument universe differs")
  write_lossless_tsv(selected, outputs[1L])
  # 完整原始 QC 保留；候选的最后状态是独立追加账本，不覆盖原始行。
  final <- data.frame(snp = candidate$snp, phase = rep("CLUMP_FINAL", nrow(candidate)),
    status = ifelse(candidate$snp %in% kept, "RETAINED", "EXCLUDED"), reason = rep("", nrow(candidate)))
  if (length(excluded)) {
    e <- do.call(rbind, excluded); check(setequal(e$snp, candidate$snp[!candidate$snp %in% kept]) && !anyDuplicated(e$snp), "candidate exclusion universe differs")
    final$reason[match(e$snp, final$snp)] <- e$reason
  }
  check(file.copy(qc_path, outputs[3L], overwrite = FALSE), "cannot publish complete variant QC")
  write_lossless_tsv(final, outputs[3L], col.names = FALSE, append = TRUE)
  # 原始官方矩阵和顺序表也是发布产物，供检查点恢复后独立重推。
  ld_manifest <- file.path(work, "ld-evidence.json")
  jsonlite::write_json(list(schema_version = 1L, input_sha256 = hashes,
    policy = c$policy, selection_algorithm = "FROZEN_GREEDY_ORDER_OFFICIAL_PHASED_LD_MATRIX_STRICT_LT",
    matrices = ld_matrices), ld_manifest, auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
  ld_files <- c("ld-evidence.json", unlist(lapply(ld_matrices, function(m) c(m$matrix_path, m$order_path)), use.names = FALSE))
  invoke("/bin/tar", c("--format=ustar", "--sort=name", "--mtime=@0", "--owner=0", "--group=0",
    "--numeric-owner", "-cf", outputs[5L], "-C", work, "--", ld_files), "ld_evidence_archive")
  audit <- list(scope = if (source_mode == "SINGLE_EXPOSURE") "OFFICIAL_EXPOSURE_ONLY_CLUMPING_NOT_NORMALIZATION_OR_G0" else
      "OFFICIAL_JOINT_EXPOSURE_UNION_CLUMPING_NOT_SOURCE_OR_G0", exposure_id = c$exposure_id,
    input_sha256 = hashes, normalization_evidence_sha256 = hashes$normalization,
    normalization_record = normal,
    panel_digest = panel$digest, software_lock = c$software_lock, policy = c$policy,
    diagnostic_cli_r2_cutoff = effective_r2,
    selection_algorithm = "FROZEN_GREEDY_ORDER_OFFICIAL_PHASED_LD_MATRIX_STRICT_LT",
    matrix_variant_limit = matrix_variant_limit,
    source_rows = total, invalid_rows = invalid, nonsignificant_rows = nonsignificant, candidate_count = nrow(candidate),
    selected_count = nrow(selected), selected_ids = selected$snp, selected_exposure_sha256 = sha(outputs[1L]),
    ld_evidence_archive_sha256 = sha(outputs[5L]),
    qc_ledger_sha256 = sha(outputs[3L]), execution_calls = calls, authorization = "NONE")
  jsonlite::write_json(audit, outputs[4L], auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
  selection <- list(type = "EXPOSURE_ONLY_CLUMP_COMPLETION", exposure_id = c$exposure_id,
    selected_exposure_sha256 = sha(outputs[1L]), source_exposure_sha256 = hashes$exposure, selected_ids = selected$snp,
    p_threshold = 5e-8, clump_r2 = 0.001, clump_kb = 10000L, tie_order = tie, ancestry = c$ancestry, build = c$build,
    panel_manifest_sha256 = hashes$panel_manifest, normalization_evidence_sha256 = hashes$normalization,
    selection_execution_evidence_sha256 = sha(outputs[4L]), outcome_used_for_selection = FALSE)
  if (source_mode == "JOINT_TWO_EXPOSURE_UNION") {
    selection$type <- "MVMR_EXPOSURE_UNION_CLUMP_COMPLETION"
    selection$exposure_ids <- normal$exposure_ids
    selection$source_exposure_sha256_by_id <- normal$source_exposure_sha256_by_id
    selection$source_recipe_sha256_by_id <- normal$source_recipe_sha256_by_id
    selection$union_rule <- normal$union_rule
    selection$anchor_rule <- normal$anchor_rule
  }
  jsonlite::write_json(selection, outputs[2L], auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
}

main <- function(args) {
  check(length(args) == 12L, "usage: clump.R config exposure panel-manifest normalization-receipt normalization-recipe panel-root work selected selection qc audit ld-evidence-tar")
  outputs <- args[8:12]
  check(!anyDuplicated(outputs) && !any(file.exists(outputs)) &&
    !any(vapply(outputs, function(p) { t <- Sys.readlink(p); !is.na(t) && nzchar(t) }, logical(1))), "output exists or duplicates another output")
  clump_frozen(args[1L], args[2L], args[3L], args[4L], args[5L], args[6L], args[7L], outputs)
}
if (sys.nframe() == 0L) tryCatch(main(commandArgs(trailingOnly = TRUE)), error = function(e) {
  message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)
})
