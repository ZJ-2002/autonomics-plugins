# HDL-L chromosome scan node: iterates the official UKB chr/piece blocks of
# the shared panel. The block loop stays script-side (the legacy Rust
# wrapper built the same loop into the generated script); parameters travel
# through the HDL_L_SCAN_* environment variables declared in manifest.toml.
# Bounds the v0 manifest DSL can express are enforced at compile time; the
# script re-checks the pieces vocabulary, trait-name emptiness, and the
# fill_missing_n enum, with the legacy error messages.

options(stringsAsFactors = FALSE, warn = 1)

env_string <- function(name) {
  value <- Sys.getenv(name, unset = "")
  if (!nzchar(value)) {
    stop("required environment variable ", name, " is empty or unset")
  }
  value
}

env_optional_string <- function(name) {
  value <- Sys.getenv(name, unset = "")
  if (!nzchar(value)) NULL else value
}

env_number <- function(name) {
  value <- env_string(name)
  result <- suppressWarnings(as.numeric(value))
  if (is.na(result)) {
    stop(name, " must be numeric, got: ", value)
  }
  result
}

env_flag <- function(name) {
  value <- tolower(trimws(env_string(name)))
  if (value %in% c("true", "1")) {
    return(TRUE)
  }
  if (value %in% c("false", "0")) {
    return(FALSE)
  }
  stop(name, " must be true or false, got: ", value)
}

chr <- env_number("HDL_L_SCAN_CHR")
if (!chr %in% 1:22) {
  stop("chr must be between 1 and 22")
}

# The manifest declares pieces as an optional string_array; the env renderer
# space-joins it, so the empty string means "every block on chr".
raw_pieces <- env_optional_string("HDL_L_SCAN_PIECES")
requested_pieces <- NULL
if (!is.null(raw_pieces)) {
  tokens <- strsplit(trimws(raw_pieces), "[[:space:]]+")[[1]]
  tokens <- tokens[nzchar(tokens)]
  if (length(tokens) == 0) {
    stop("pieces cannot be empty when provided")
  }
  values <- suppressWarnings(as.numeric(tokens))
  if (any(is.na(values)) || any(values <= 0 | values != trunc(values))) {
    stop("piece values must be positive one-based LD blocks")
  }
  if (anyDuplicated(values) != 0L) {
    stop("pieces must not contain duplicates")
  }
  requested_pieces <- values
}

trait1_name <- env_string("HDL_L_SCAN_TRAIT1_NAME")
trait2_name <- env_string("HDL_L_SCAN_TRAIT2_NAME")
if (nzchar(trimws(trait1_name)) == FALSE ||
  nzchar(trimws(trait2_name)) == FALSE) {
  stop("trait1_name and trait2_name cannot be empty")
}

fill_missing_n <- env_optional_string("HDL_L_SCAN_FILL_MISSING_N")
if (!is.null(fill_missing_n) &&
  !fill_missing_n %in% c("median", "min", "max")) {
  stop("fill_missing_n must be one of median, min, max")
}

n0 <- env_number("HDL_L_SCAN_N0")
if (is.finite(n0) == FALSE || n0 < 0) {
  stop("n0 must be finite and non-negative")
}
nref <- env_number("HDL_L_SCAN_NREF")
if (is.finite(nref) == FALSE || nref <= 0) {
  stop("nref must be finite and greater than zero")
}
eigen_cut <- env_number("HDL_L_SCAN_EIGEN_CUT")
if (is.finite(eigen_cut) == FALSE || eigen_cut < 0 || eigen_cut > 1) {
  stop("eigen_cut must be finite and in [0, 1]")
}
alpha <- env_number("HDL_L_SCAN_ALPHA")
if (is.finite(alpha) == FALSE || alpha <= 0 || alpha > 1) {
  stop("alpha must be finite and in (0, 1]")
}
lim <- env_number("HDL_L_SCAN_LIM")
if (is.finite(lim) == FALSE || lim <= 0) {
  stop("lim must be finite and greater than zero")
}
intercept_output <- env_flag("HDL_L_SCAN_INTERCEPT_OUTPUT")

read_sumstats <- function(path) {
  frame <- as.data.frame(data.table::fread(path, sep = "auto", header = TRUE))
  required <- c("SNP", "A1", "A2", "N")
  missing <- setdiff(required, colnames(frame))
  if (length(missing) > 0) {
    stop("summary statistics are missing required columns: ",
      paste(missing, collapse = ", "))
  }
  if (!"Z" %in% colnames(frame) &&
    !all(c("b", "se") %in% colnames(frame))) {
    stop("summary statistics must contain Z or both b and se")
  }
  frame
}

ld_path <- "/panels/hdl_ref/LD/"
bim_path <- "/panels/hdl_ref/bim/"
marker_path <- file.path(ld_path, "HDLL_LOC_snps.RData")
if (!file.exists(marker_path)) {
  stop("HDL panel is missing LD/HDLL_LOC_snps.RData")
}
if (length(list.files(bim_path, pattern = "\\.bim$")) == 0) {
  stop("HDL panel contains no BIM files")
}

load(marker_path)
blocks <- NEWLOC[NEWLOC$CHR == chr, , drop = FALSE]
if (!is.null(requested_pieces)) {
  matches <- match(requested_pieces, blocks$piece)
  if (any(is.na(matches))) {
    missing <- requested_pieces[is.na(matches)]
    stop("requested HDL pieces are absent on chromosome ", chr, ": ",
      paste(missing, collapse = ", "))
  }
  blocks <- blocks[matches, , drop = FALSE]
}
if (nrow(blocks) == 0) {
  stop("HDL panel declares no blocks on chromosome ", chr)
}

gwas1 <- read_sumstats(Sys.getenv("AUTONOMICS_INPUT0"))
gwas2 <- read_sumstats(Sys.getenv("AUTONOMICS_INPUT1"))
results <- list()
failed <- 0L
for (row_index in seq_len(nrow(blocks))) {
  chr <- blocks$CHR[[row_index]]
  piece <- blocks$piece[[row_index]]
  cat("Processing chromosome", chr, "region", piece, "\n")
  result <- tryCatch(
    HDL::HDL.L(
      gwas1.df = gwas1,
      gwas2.df = gwas2,
      Trait1name = trait1_name,
      Trait2name = trait2_name,
      LD.path = ld_path,
      bim.path = bim_path,
      Nref = nref,
      N0 = n0,
      chr = chr,
      piece = piece,
      output.file = Sys.getenv("AUTONOMICS_OUTPUT2"),
      eigen.cut = eigen_cut,
      intercept.output = intercept_output,
      fill.missing.N = fill_missing_n,
      lim = lim,
      alpha = alpha
    ),
    error = function(error) {
      failed <<- failed + 1L
      message <- paste0("Error in chromosome ", chr, " region ", piece, ": ",
        conditionMessage(error))
      cat(message, "\n", file = Sys.getenv("AUTONOMICS_OUTPUT2"), append = TRUE)
      cat(message, "\n")
      NULL
    }
  )
  if (!is.null(result)) {
    results[[length(results) + 1L]] <- result
  }
}

result_frame <- do.call(rbind, results)
if (is.null(result_frame)) {
  result_frame <- data.frame(
    Trait1 = character(),
    Trait2 = character(),
    chr = integer(),
    piece = integer(),
    eigen_use = numeric(),
    Heritability_1 = numeric(),
    P_value_Heritability_1 = numeric(),
    Heritability_2 = numeric(),
    P_value_Heritability_2 = numeric(),
    Genetic_Covariance = numeric(),
    Genetic_Correlation = numeric(),
    Lower_bound_rg = numeric(),
    Upper_bound_rg = numeric(),
    P = numeric()
  )
}
cat("Processed", nrow(blocks), "official blocks;", failed, "failed\n")
cat("Processed", nrow(blocks), "official blocks;", failed, "failed\n",
  file = Sys.getenv("AUTONOMICS_OUTPUT2"), append = TRUE)
print(result_frame)
write.table(
  result_frame,
  Sys.getenv("AUTONOMICS_OUTPUT0"),
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)
saveRDS(results, Sys.getenv("AUTONOMICS_OUTPUT1"))
