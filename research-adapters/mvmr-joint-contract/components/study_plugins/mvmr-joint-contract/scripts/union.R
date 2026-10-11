# An explicitly preregistered two-exposure union; no outcome input or LD estimate.
# Min-P anchoring is a candidate adapter policy, not an inferred plan/G0 decision.
ju_fail <- function(message) stop(message, call. = FALSE)
ju_check <- function(ok, message) if (!isTRUE(ok)) ju_fail(message)
ju_sha <- function(path) digest::digest(file = path, algo = "sha256")
ju_keys <- function(x, expected, label) ju_check(is.list(x) && setequal(names(x), expected) &&
  !anyDuplicated(names(x)), paste(label, "schema differs"))
ju_hash <- function(x) is.character(x) && length(x) == 1L && !is.na(x) && grepl("^[0-9a-f]{64}$", x)
ju_ids <- function(x) is.character(x) && length(x) == 2L && !anyNA(x) &&
  all(grepl("^[A-Za-z0-9._:-]+$", x)) && !anyDuplicated(x)
ju_header <- c("snp", "chr", "pos", "beta", "se", "effect_allele", "other_allele", "eaf", "pval")

joint_union_config <- function(path) {
  c <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  ju_keys(c, c("schema_version", "status", "protocol_version", "analysis_id", "exposure_ids",
    "build", "ancestry", "instrument_class", "policy", "source_recipe_sha256_by_id",
    "software_lock", "input_sha256"), "union configuration")
  ju_check(identical(c$schema_version, 1L) && identical(c$status, "FROZEN") && frozen_protocol_supported(c$protocol_version),
    "explicit frozen supported-protocol union configuration required; no implicit MVMR selection policy")
  ids <- unlist(c$exposure_ids, use.names = FALSE)
  ju_check(ju_ids(ids) && is.character(c$analysis_id) && length(c$analysis_id) == 1L &&
    grepl("^[A-Za-z0-9._:-]+$", c$analysis_id) && c$build %in% c("GRCh37", "GRCh38") &&
    is.character(c$ancestry) && length(c$ancestry) == 1L && nzchar(c$ancestry) &&
    identical(c$instrument_class, "COMPLEX_TRAIT"), "joint construct/build/ancestry contract required")
  ju_keys(c$policy, c("p_threshold", "union_rule", "anchor_rule", "tie_order"), "union policy")
  ju_check(identical(c$policy$p_threshold, 5e-8) &&
    identical(c$policy$union_rule, "ANY_EXPOSURE_P_STRICT_LT") &&
    identical(c$policy$anchor_rule, "MIN_EXPOSURE_P_THEN_REGISTERED_EXPOSURE_ORDER") &&
    identical(unlist(c$policy$tie_order, use.names = FALSE), c("pval", "chr", "pos", "snp")),
    "supported explicit union/anchor policy required; no outcome-based selection")
  ju_keys(c$source_recipe_sha256_by_id, ids, "source recipe identities")
  ju_check(all(vapply(c$source_recipe_sha256_by_id, ju_hash, logical(1))), "actual source recipe hashes required")
  ju_keys(c$input_sha256, c("exposure0", "exposure1", "normalization0", "normalization1"), "union input hashes")
  ju_check(all(vapply(c$input_sha256, ju_hash, logical(1))), "complete actual input hashes required")
  ju_keys(c$software_lock, c("R_version", "sort_binary_sha256"), "union software lock")
  ju_check(identical(c$software_lock$R_version, as.character(getRversion())) &&
    identical(c$software_lock$sort_binary_sha256, ju_sha("/usr/bin/sort")), "union software lock mismatch")
  c
}

joint_union_frozen <- function(config, x0, x1, n0, r0, n1, r1, work, outputs) {
  for (pkg in c("jsonlite", "digest")) ju_check(requireNamespace(pkg, quietly = TRUE), paste("package missing:", pkg))
  ju_check(identical(Sys.getenv("LC_ALL"), "C"), "deterministic C locale required")
  c <- joint_union_config(config); ids <- unlist(c$exposure_ids, use.names = FALSE)
  inputs <- c(config, x0, x1, n0, r0, n1, r1)
  before <- vapply(inputs, ju_sha, character(1))
  actual <- list(exposure0 = before[2L], exposure1 = before[3L], normalization0 = before[4L], normalization1 = before[6L])
  ju_check(all(vapply(names(actual), function(k) identical(c$input_sha256[[k]], unname(actual[[k]])), logical(1))), "union input content identity mismatch")
  receipts <- list(normalization_receipt(n0, r0, x0, c$source_recipe_sha256_by_id[[ids[1L]]], ids[1L], c$build, c$ancestry, c$protocol_version),
    normalization_receipt(n1, r1, x1, c$source_recipe_sha256_by_id[[ids[2L]]], ids[2L], c$build, c$ancestry, c$protocol_version))
  ju_check(dir.create(work, mode = "0700"), "fresh union workspace required")
  candidates <- list(); counts <- integer(2L); executions <- list()
  qc <- file(file.path(work, "union-qc.tsv"), "w"); on.exit(close(qc), add = TRUE)
  writeLines("exposure_id\tsnp\tphase\tstatus\treason", qc)
  for (side in 1:2) {
    con <- file(c(x0, x1)[side], "r")
    id_path <- file.path(work, paste0("exposure", side, "-ids.txt")); ids_out <- file(id_path, "w")
    local_count <- 0L; candidate_count <- 0L
    ju_check(identical(readLines(con, n = 1L, warn = FALSE), paste(ju_header, collapse = "\t")), "normalized exposure schema differs")
    repeat {
      lines <- readLines(con, n = 10000L, warn = FALSE)
      if (!length(lines)) break
      ju_check(all(lengths(strsplit(lines, "\t", fixed = TRUE)) == 9L), "malformed normalized exposure row")
      d <- utils::read.delim(text = paste(c(paste(ju_header, collapse = "\t"), lines), collapse = "\n"),
        colClasses = "character", quote = "", comment.char = "", check.names = FALSE, na.strings = c("NA", ""), fill = FALSE)
      ju_check(!anyNA(d$snp) && all(grepl("^[A-Za-z0-9._:+-]+$", d$snp)), "invalid source variant identity")
      writeLines(d$snp, ids_out)
      num <- lapply(d[c("chr", "pos", "beta", "se", "eaf", "pval")], function(x) suppressWarnings(as.numeric(x)))
      valid <- is.finite(num$chr) & num$chr %in% 1:22 & is.finite(num$pos) & num$pos >= 1 & num$pos == floor(num$pos) &
        is.finite(num$beta) & is.finite(num$se) & num$se > 0 & is.finite(num$pval) & num$pval >= 0 & num$pval <= 1 &
        (is.na(d$eaf) | (is.finite(num$eaf) & num$eaf >= 0 & num$eaf <= 1)) &
        !is.na(d$effect_allele) & !is.na(d$other_allele) & d$effect_allele %in% c("A", "C", "G", "T") &
        d$other_allele %in% c("A", "C", "G", "T") & d$effect_allele != d$other_allele
      ju_check(all(!is.na(valid) & valid), "invalid row in normalized joint exposure source")
      significant <- num$pval < 5e-8
      writeLines(paste(ids[side], d$snp, "SOURCE_P", ifelse(significant, "CANDIDATE", "EXCLUDED"),
        ifelse(significant, "", "P_THRESHOLD_NOT_MET"), sep = "\t"), qc)
      if (any(significant)) {
        take <- d[significant, , drop = FALSE]; take$anchor_exposure_index <- side
        candidates[[length(candidates) + 1L]] <- take
        candidate_count <- candidate_count + nrow(take)
        ju_check(candidate_count <= 22L * 4096L, "union candidate source exceeds qualification bound; no truncation permitted")
      }
      local_count <- local_count + nrow(d)
    }
    close(con); close(ids_out)
    ju_check(local_count == receipts[[side]]$retained_rows, "actual normalized source row accounting differs")
    sorted <- file.path(work, paste0("exposure", side, "-sorted-ids.txt"))
    args <- c("--buffer-size=64M", "--parallel=1", "--temporary-directory", work, "--output", sorted, id_path)
    log <- file.path(work, paste0("exposure", side, "-sort.log"))
    status <- system2("/usr/bin/sort", vapply(args, shQuote, character(1)), stdout = log, stderr = log)
    ju_check(identical(status, 0L), "complete source identity sorting failed")
    s <- file(sorted, "r"); last <- NULL
    repeat {
      batch <- readLines(s, n = 10000L, warn = FALSE)
      if (!length(batch)) break
      ju_check(!anyDuplicated(batch) && (is.null(last) || last != batch[1L]), "duplicate identity in complete source, including nonsignificant rows")
      last <- tail(batch, 1L)
    }
    close(s); counts[side] <- local_count
    executions[[side]] <- list(executable = "/usr/bin/sort", argv = args, exit_code = status, log_sha256 = ju_sha(log))
  }
  if (length(candidates)) {
    all <- do.call(rbind, candidates)
    duplicate <- which(duplicated(all$snp)); first <- match(all$snp[duplicate], all$snp)
    pair <- function(a, b) ifelse(a < b, paste0(a, b), paste0(b, a))
    comp <- c(A = "T", C = "G", G = "C", T = "A")
    left <- pair(all$effect_allele[first], all$other_allele[first])
    right <- pair(all$effect_allele[duplicate], all$other_allele[duplicate])
    complement <- pair(unname(comp[all$effect_allele[duplicate]]), unname(comp[all$other_allele[duplicate]]))
    ju_check(all(all$anchor_exposure_index[first] != all$anchor_exposure_index[duplicate]) &&
      all(all$chr[first] == all$chr[duplicate] & all$pos[first] == all$pos[duplicate] &
        (left == right | left == complement)), "cross-exposure candidate coordinates or alleles differ")
    all <- all[order(as.numeric(all$pval), as.numeric(all$chr), as.numeric(all$pos), all$snp,
      all$anchor_exposure_index, method = "radix"), , drop = FALSE]
    union <- all[!duplicated(all$snp), , drop = FALSE]
    anchors <- union$anchor_exposure_index
    union <- union[, ju_header, drop = FALSE]
  } else {
    union <- setNames(as.data.frame(rep(list(character()), 9L)), ju_header); anchors <- integer()
  }
  ju_check(identical(before, vapply(inputs, ju_sha, character(1))), "union input changed during selection")
  close(qc); on.exit(NULL, add = FALSE)
  utils::write.table(union, outputs[1L], sep = "\t", row.names = FALSE, quote = FALSE, na = "NA")
  ju_check(file.copy(file.path(work, "union-qc.tsv"), outputs[3L], overwrite = FALSE), "union QC output publication failed")
  record <- list(schema_version = 1L, type = "MVMR_TWO_EXPOSURE_UNION_COMPLETION", authorization = "NONE",
    analysis_id = c$analysis_id, exposure_ids = ids, build = c$build, ancestry = c$ancestry,
    input_sha256 = as.list(setNames(before, c("config", "exposure0", "exposure1", "normalization0", "recipe0", "normalization1", "recipe1"))),
    source_exposure_sha256_by_id = as.list(setNames(c(ju_sha(x0), ju_sha(x1)), ids)),
    source_recipe_sha256_by_id = c$source_recipe_sha256_by_id,
    frozen_recipe = c, source_normalization_records = receipts, source_rows = counts,
    retained_rows = nrow(union), selected_ids = as.list(union$snp),
    anchor_exposure_ids = as.list(ids[anchors]), selected_exposure_sha256 = ju_sha(outputs[1L]),
    union_rule = c$policy$union_rule, anchor_rule = c$policy$anchor_rule, outcome_used_for_selection = FALSE)
  audit <- list(scope = "EXPOSURE_ONLY_TWO_SOURCE_UNION_NO_LD_OR_G0", record = record,
    full_qc_sha256 = ju_sha(outputs[3L]), sort_executions = executions, scientific_approval_verified = FALSE, formal_authorized = FALSE)
  jsonlite::write_json(audit, outputs[4L], auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
  jsonlite::write_json(record, outputs[2L], auto_unbox = TRUE, pretty = TRUE, digits = NA, null = "null")
}

joint_union_main <- function(args) {
  ju_check(length(args) == 12L, "usage: union.R config x0 x1 norm0 recipe0 norm1 recipe1 work union receipt qc audit")
  out <- args[9:12]
  ju_check(!anyDuplicated(out) && !any(file.exists(out)) &&
    !any(vapply(out, function(p) { a <- Sys.readlink(p); !is.na(a) && nzchar(a) }, logical(1))), "joint output exists or duplicates")
  joint_union_frozen(args[1L], args[2L], args[3L], args[4L], args[5L], args[6L], args[7L], args[8L], out)
}
if (sys.nframe() == 0L) tryCatch(joint_union_main(commandArgs(TRUE)), error = function(e) {
  message("BLOCKED: ", conditionMessage(e)); quit(status = 2L)
})
