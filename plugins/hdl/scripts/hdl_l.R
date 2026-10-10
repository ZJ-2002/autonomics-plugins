# HDL-L region node: one official chr/piece block per run.
#
# Plugin-era parameter channel: every spec value travels through the
# HDL_L_* environment variables declared in manifest.toml (the legacy Rust
# wrapper inlined them as literals into this script). Bounds that the v0
# manifest DSL can express are enforced at compile time; the script only
# re-checks what the DSL cannot: trait-name emptiness and the
# fill_missing_n vocabulary.

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

chr <- env_number("HDL_L_CHR")
if (!chr %in% 1:22) {
  stop("chr must be between 1 and 22")
}
piece <- env_number("HDL_L_PIECE")
if (piece <= 0) {
  stop("piece must be a positive one-based LD block")
}

trait1_name <- env_string("HDL_L_TRAIT1_NAME")
trait2_name <- env_string("HDL_L_TRAIT2_NAME")
if (nzchar(trimws(trait1_name)) == FALSE ||
  nzchar(trimws(trait2_name)) == FALSE) {
  stop("trait1_name and trait2_name cannot be empty")
}

fill_missing_n <- env_optional_string("HDL_L_FILL_MISSING_N")
if (!is.null(fill_missing_n) &&
  !fill_missing_n %in% c("median", "min", "max")) {
  stop("fill_missing_n must be one of median, min, max")
}

n0 <- env_number("HDL_L_N0")
if (is.finite(n0) == FALSE || n0 < 0) {
  stop("n0 must be finite and non-negative")
}
nref <- env_number("HDL_L_NREF")
if (is.finite(nref) == FALSE || nref <= 0) {
  stop("nref must be finite and greater than zero")
}
eigen_cut <- env_number("HDL_L_EIGEN_CUT")
if (is.finite(eigen_cut) == FALSE || eigen_cut < 0 || eigen_cut > 1) {
  stop("eigen_cut must be finite and in [0, 1]")
}
alpha <- env_number("HDL_L_ALPHA")
if (is.finite(alpha) == FALSE || alpha <= 0 || alpha > 1) {
  stop("alpha must be finite and in (0, 1]")
}
lim <- env_number("HDL_L_LIM")
if (is.finite(lim) == FALSE || lim <= 0) {
  stop("lim must be finite and greater than zero")
}
intercept_output <- env_flag("HDL_L_INTERCEPT_OUTPUT")

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
if (!file.exists(file.path(ld_path, "HDLL_LOC_snps.RData"))) {
  stop("HDL panel is missing LD/HDLL_LOC_snps.RData")
}
if (length(list.files(bim_path, pattern = "\\.bim$")) == 0) {
  stop("HDL panel contains no BIM files")
}

gwas1 <- read_sumstats(Sys.getenv("AUTONOMICS_INPUT0"))
gwas2 <- read_sumstats(Sys.getenv("AUTONOMICS_INPUT1"))
result <- HDL::HDL.L(
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
)
if (is.null(result) || nrow(result) == 0) {
  stop("official HDL-L returned no result")
}
print(result)
write.table(
  result,
  Sys.getenv("AUTONOMICS_OUTPUT0"),
  sep = "\t",
  quote = FALSE,
  row.names = FALSE
)
saveRDS(result, Sys.getenv("AUTONOMICS_OUTPUT1"))
