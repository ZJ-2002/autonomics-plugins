options(warn = 1)
outputs <- vapply(0:6, function(port) Sys.getenv(paste0("AUTONOMICS_OUTPUT", port)), character(1))
audit <- list(status = "RUNNING", scientific_G0_granted = FALSE)
writeLines("status\tRUNNING\nidentity_scope\tTECHNICAL_ONLY_NOT_G0", outputs[5])
analytic <- outputs[c(1, 2, 3, 4, 7)]
unlink(analytic)

record <- function(...) cat(..., "\n", file = outputs[5], append = TRUE)
save_audit <- function(value = audit) jsonlite::write_json(value, outputs[6], pretty = TRUE, auto_unbox = TRUE, null = "null")
require_true <- function(condition, message) if (!isTRUE(condition)) stop(message, call. = FALSE)
hash <- function(filename) {
  result <- system2("sha256sum", shQuote(filename), stdout = TRUE, stderr = TRUE)
  require_true(is.null(attr(result, "status")) && length(result) == 1 && grepl("^[a-f0-9]{64} ", result), "Content hash unavailable")
  substr(result, 1, 64)
}
integer_value <- function(raw, maximum) {
  require_true(grepl("^[1-9][0-9]*$", raw) && nchar(raw) <= nchar(as.character(maximum)), "Canonical positive integer required")
  value <- as.numeric(raw)
  require_true(is.finite(value) && value <= maximum, "Integer outside accepted domain")
  as.integer(value)
}
write_tsv <- function(value, filename) write.table(value, filename, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
invoke <- function(arguments, label) {
  record("COMMAND", label, paste(shQuote(arguments), collapse = " "))
  result <- suppressWarnings(system2("plink2", vapply(arguments, shQuote, character(1)), stdout = TRUE, stderr = TRUE))
  cat(paste(result, collapse = "\n"), "\n", file = outputs[5], append = TRUE)
  require_true(is.null(attr(result, "status")) || attr(result, "status") == 0, paste("Official PLINK2 failed:", label))
}

tryCatch({
  require_true(Sys.getenv("AUTONOMICS_INPUT_COUNT") == "4", "Exactly four declared inputs required")
  inputs <- vapply(0:3, function(port) Sys.getenv(paste0("AUTONOMICS_INPUT", port)), character(1))
  required <- c("schema_version", "scope", "input_sha256", "rules_sha256", "panel_manifest_sha256", "panel_digest",
                "panel_population", "input_population", "panel_genome_build", "input_genome_build", "input_format", "chromosomes",
                "clump_p1", "clump_p2", "clump_r2", "clump_kb", "p_boundary", "tie_order", "ld_mode", "threads", "memory_mib")
  request <- read.delim(inputs[2], colClasses = "character", check.names = FALSE, na.strings = character(), quote = "", comment.char = "")
  require_true(identical(names(request), c("key", "value")) && !anyDuplicated(request$key) && setequal(request$key, required), "Frozen contract key set differs")
  contract <- setNames(as.list(request$value), request$key)
  require_true(contract$schema_version == "1" && contract$scope == "TECHNICAL_ONLY_NOT_G0", "Invalid schema or scientific scope")
  require_true(contract$p_boundary == "STRICT_LT" && contract$tie_order == "P_CHR_BP_ASCII_ID" && contract$ld_mode == "HAPLOTYPE_PHASED", "Method convention differs")
  require_true(contract$input_format %in% c("twosamplemr", "plink_assoc", "ieu_open_gwas"), "Unsupported input format")
  require_true(contract$panel_population == contract$input_population && contract$panel_genome_build == contract$input_genome_build, "Declared ancestry/build mismatch")
  chromosomes <- vapply(strsplit(contract$chromosomes, ",", fixed = TRUE)[[1]], integer_value, integer(1), maximum = 22)
  require_true(!anyDuplicated(chromosomes) && identical(chromosomes, sort(chromosomes)), "Chromosomes must be unique ascending autosomes")
  threads <- integer_value(contract$threads, 2)
  memory <- integer_value(contract$memory_mib, 1024)
  require_true(memory >= 640, "PLINK2 workspace must be at least 640 MiB")
  for (name in c("input_sha256", "rules_sha256", "panel_manifest_sha256")) require_true(grepl("^[a-f0-9]{64}$", contract[[name]]), "Noncanonical expected content hash")
  require_true(hash(inputs[1]) == contract$input_sha256 && hash(inputs[3]) == contract$rules_sha256, "Summary statistics or rules hash mismatch")
  rules <- jsonlite::fromJSON(inputs[3])
  p1 <- as.numeric(contract$clump_p1)
  p2 <- as.numeric(contract$clump_p2)
  r2 <- as.numeric(contract$clump_r2)
  kb <- integer_value(contract$clump_kb, 2147483)
  require_true(all(is.finite(c(p1, p2, r2))) && p1 > 0 && p1 < 1 && p2 >= p1 && p2 <= 1 && r2 > 0 && r2 < 1, "Invalid clumping thresholds")
  require_true(p1 == rules$instrument$p_threshold && r2 == rules$instrument$clump_r2 && kb == rules$instrument$clump_kb, "Parameters differ from active instrument rules")
  binary <- Sys.which("plink2")
  require_true(nzchar(binary) && hash(binary) == "6a783e2d5e331f5b1eb7dea9f5331490202053cb3ce217ce227a36171bdb2169", "Official PLINK2 release binary differs")
  audit$binary_sha256 <- hash(binary)
  audit$input_sha256 <- hash(inputs[1])
  audit$rules_sha256 <- hash(inputs[3])
  panel <- "/panels/plink_ref"
  manifest_path <- inputs[4]
  require_true(hash(manifest_path) == contract$panel_manifest_sha256, "Panel manifest content identity differs")
  manifest <- jsonlite::fromJSON(manifest_path)
  require_true(manifest$digest == contract$panel_digest && manifest$metadata$population == contract$panel_population && manifest$metadata$genome_build == contract$panel_genome_build, "Panel identity or declared metadata differs")
  expected <- unlist(lapply(1:22, function(chromosome) paste0("1000G.EUR.QC.", chromosome, c(".bed", ".bim", ".fam"))))
  require_true(nrow(manifest$files) == 66 && !anyDuplicated(manifest$files$path) && setequal(manifest$files$path, expected), "Expected exactly 22 BED/BIM/FAM triplets")
  for (index in seq_len(nrow(manifest$files))) {
    filename <- file.path(panel, manifest$files$path[index])
    require_true(file.info(filename)$size == manifest$files$size[index] && paste0("sha256:", hash(filename)) == manifest$files$sha256[index], "Panel file identity differs")
  }
  audit$panel_files_verified <- 66L
  audit$panel_manifest_sha256 <- hash(manifest_path)
  data <- read.table(inputs[1], header = TRUE, sep = if (contract$input_format == "ieu_open_gwas") "," else "\t",
                     colClasses = "character", check.names = FALSE, quote = "\"", comment.char = "", na.strings = character())
  id_column <- if (contract$input_format == "ieu_open_gwas") "variant" else "SNP"
  p_column <- if (contract$input_format == "ieu_open_gwas") "pval" else "P"
  require_true(all(c(id_column, p_column) %in% names(data)) && nrow(data) > 0 && !anyDuplicated(names(data)), "Invalid summary statistics schema or empty input")
  identifiers <- data[[id_column]]
  require_true(all(grepl("^rs[0-9]+$", identifiers)) && !anyDuplicated(identifiers), "Unique canonical rsIDs required")
  probabilities <- suppressWarnings(as.numeric(data[[p_column]]))
  require_true(all(is.finite(probabilities) & probabilities >= 0 & probabilities <= 1), "Missing or invalid P value; no silent omission")
  zero_text <- grepl("^(0+(\\.0*)?|\\.0+)([eE][+-]?[0-9]+)?$", data[[p_column]])
  require_true(all(probabilities != 0 | zero_text), "Nonzero P underflowed numeric representation")
  ledger <- data.frame(SNP = identifiers, P = probabilities, in_panel = FALSE, passes_strict_p = probabilities < p1,
                       is_index = FALSE, panel_chr = NA_integer_, panel_bp = NA_integer_, stringsAsFactors = FALSE)
  ledger$P_input <- data[[p_column]]
  audit$requested_n <- nrow(ledger)
  save_audit()
  records <- list()
  chromosome_records <- list()
  raw <- "/work/plink-official-artifacts"
  dir.create(raw)
  ledger_indices <- list()
  for (chromosome in chromosomes) {
    prefix <- file.path(panel, paste0("1000G.EUR.QC.", chromosome))
    positions <- data.table::fread(paste0(prefix, ".bim"), header = FALSE, select = c(1, 2, 4), colClasses = "character", data.table = FALSE)
    names(positions) <- c("chr", "SNP", "bp")
    found <- positions[positions$SNP %in% identifiers, , drop = FALSE]
    rm(positions)
    gc(FALSE)
    require_true(!anyDuplicated(found$SNP) && all(found$chr == as.character(chromosome)), "Ambiguous or wrong-chromosome panel variants")
    indices <- match(found$SNP, identifiers)
    require_true(!any(ledger$in_panel[indices]), "Variant maps to multiple panel chromosomes")
    ledger$in_panel[indices] <- TRUE
    ledger$panel_chr[indices] <- chromosome
    ledger$panel_bp[indices] <- as.integer(found$bp)
    if ("CHR" %in% names(data)) require_true(all(data$CHR[indices] == as.character(chromosome)), "Input and panel chromosome differ")
    position_column <- if ("POS" %in% names(data)) "POS" else if ("BP" %in% names(data)) "BP" else NULL
    if (!is.null(position_column)) require_true(all(suppressWarnings(as.numeric(data[[position_column]][indices])) == ledger$panel_bp[indices]), "Input and panel coordinate differ")
    eligible <- indices[ledger$passes_strict_p[indices]]
    chromosome_records[[length(chromosome_records) + 1L]] <- data.frame(chr = chromosome, requested_in_panel = length(indices), strict_p_candidates = length(eligible), selected = 0L, executed = FALSE)
    if (!length(eligible)) next
    work <- file.path(raw, paste0("chr", chromosome))
    dir.create(work)
    writeLines(identifiers[eligible], file.path(work, "extract.txt"))
    report <- data.frame(SNP = identifiers[eligible], P = data[[p_column]][eligible])
    write_tsv(report, file.path(work, "association.tsv"))
    sorted <- file.path(work, "sorted")
    invoke(c("--bfile", prefix, "--extract", file.path(work, "extract.txt"), "--sort-vars", "ascii", "--make-pgen",
             "--threads", as.character(threads), "--memory", as.character(memory), "require", "--out", sorted), paste0("sort-chr", chromosome))
    output_prefix <- file.path(work, "official")
    invoke(c("--pfile", sorted, "--clump", "cols=+chrom,+pos", file.path(work, "association.tsv"), "--clump-id-field", "SNP", "--clump-p-field", "P",
             "--chr", as.character(chromosome), "--clump-p1", contract$clump_p1, "--clump-p2", contract$clump_p2,
             "--clump-r2", contract$clump_r2, "--clump-kb", contract$clump_kb, "--threads", as.character(threads),
             "--memory", as.character(memory), "require", "--out", output_prefix), paste0("clump-chr", chromosome))
    require_true(file.exists(paste0(output_prefix, ".clumps")), "Eligible variants did not produce an official clump table")
    clumps <- read.table(paste0(output_prefix, ".clumps"), header = TRUE, check.names = FALSE, colClasses = "character", comment.char = "", quote = "")
    require_true(nrow(clumps) > 0 && all(c("#CHROM", "POS", "ID", "P") %in% names(clumps)) && !anyDuplicated(clumps$ID), "Official clump table schema differs")
    selected <- match(clumps$ID, identifiers)
    require_true(!anyNA(selected) && all(ledger$passes_strict_p[selected]) && all(ledger$panel_chr[selected] == chromosome), "Official index set violates input qualification")
    ledger$is_index[selected] <- TRUE
    chromosome_records[[length(chromosome_records)]]$selected <- length(selected)
    chromosome_records[[length(chromosome_records)]]$executed <- TRUE
    records[[length(records) + 1L]] <- clumps
    ledger_indices[[length(ledger_indices) + 1L]] <- selected
    if (length(selected) > 1) {
      writeLines(identifiers[selected], file.path(work, "indices.txt"))
      ld_prefix <- file.path(work, "strict-ld")
      invoke(c("--pfile", sorted, "--extract", file.path(work, "indices.txt"), "--r2-phased", "cols=chrom,pos,id",
               "--ld-window", "999999999", "--ld-window-kb", contract$clump_kb, "--ld-window-r2", "0",
               "--threads", as.character(threads), "--memory", as.character(memory), "require", "--out", ld_prefix), paste0("selected-LD-chr", chromosome))
      pairs <- read.table(paste0(ld_prefix, ".vcor"), header = TRUE, check.names = FALSE, comment.char = "", quote = "")
      require_true("PHASED_R2" %in% names(pairs), "Official phased LD schema differs")
      within <- abs(pairs$POS_A - pairs$POS_B) < kb * 1000
      require_true(all(is.finite(pairs$PHASED_R2[within])) && all(pairs$PHASED_R2[within] < r2), "Selected variants do not prove strict LD < frozen threshold at report precision")
    }
  }
  combined <- if (length(records)) do.call(rbind, records) else data.frame(`#CHROM` = character(), POS = character(), ID = character(), P = character(), check.names = FALSE)
  selected <- which(ledger$is_index)
  indices <- data.frame(CHR = ledger$panel_chr[selected], BP = ledger$panel_bp[selected], SNP = identifiers[selected], P = probabilities[selected], P_input = data[[p_column]][selected])
  if (nrow(indices)) indices <- indices[order(indices$P, indices$CHR, indices$BP, indices$SNP, method = "radix"), , drop = FALSE]
  ledger$status <- ifelse(!ledger$in_panel, "NOT_IN_REQUESTED_PANEL_CHROMOSOMES", ifelse(!ledger$passes_strict_p, "P_NOT_STRICTLY_BELOW_THRESHOLD", ifelse(ledger$is_index, "OFFICIAL_INDEX", "ELIGIBLE_NOT_INDEX")))
  write_tsv(indices, outputs[1])
  write_tsv(combined, outputs[2])
  write_tsv(do.call(rbind, chromosome_records), outputs[3])
  write_tsv(ledger, outputs[7])
  old_directory <- getwd()
  setwd(raw)
  files <- list.files(".", recursive = TRUE, all.files = TRUE)
  if (!length(files)) {
    writeLines("No eligible index candidates; all chromosome decisions are recorded separately.", "NO_ELIGIBLE_CANDIDATES.txt")
    files <- "NO_ELIGIBLE_CANDIDATES.txt"
  }
  utils::tar(outputs[4], files = files, tar = "internal")
  setwd(old_directory)
  audit$status <- "PASS"
  audit$estimation_status <- if (length(selected)) "INDICES_SELECTED_NOT_MR_ESTIMATES" else "NO_ELIGIBLE_INDICES_NOT_ESTIMABLE"
  audit$selected_n <- length(selected)
  audit$requested_chromosomes <- chromosomes
  audit$threads <- threads
  audit$workspace_mib <- memory
  audit$p_boundary <- "STRICT_LT"
  audit$tie_order <- "P_CHR_BP_ASCII_ID"
  audit$ld_mode <- "HAPLOTYPE_PHASED"
  audit$output_sha256 <- setNames(lapply(analytic, hash), basename(analytic))
  save_audit()
  record("status\tPASS", "requested", nrow(ledger), "selected", length(selected))
}, error = function(error) {
  unlink(analytic)
  audit$status <- "BLOCKED"
  audit$error <- conditionMessage(error)
  save_audit(audit)
  record("status\tBLOCKED", conditionMessage(error))
  message(conditionMessage(error))
  quit(status = 2)
})
