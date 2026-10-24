args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 4L, as.character(getRversion()) == "4.6.1")
object <- readRDS(args[1])
stopifnot(is.list(object), !anyDuplicated(names(object)),
          is.data.frame(object$mr), is.list(object$contract),
          identical(object$contract$R, "4.6.1"),
          identical(object$contract$TwoSampleMR, "0.7.11"))
columns <- c("id.exposure", "id.outcome", "outcome", "exposure", "method",
             "nsnp", "b", "se", "pval", "role", "p_primary",
             "p_for_family", "p_raw_exploratory")
values <- object$mr
stopifnot(identical(names(values), columns), nrow(values) > 0L,
          !anyDuplicated(values[c("id.exposure", "id.outcome", "method")]))
for (name in c("id.exposure", "id.outcome", "outcome", "exposure", "method", "role")) {
  stopifnot(is.character(values[[name]]), !anyNA(values[[name]]),
            all(nzchar(values[[name]])), !any(grepl("[\t\r\n]", values[[name]])))
}
numeric_columns <- c("nsnp", "b", "se", "pval", "p_for_family", "p_raw_exploratory")
for (name in numeric_columns) {
  stopifnot(is.numeric(values[[name]]), all(is.finite(values[[name]])))
}
stopifnot(all(values$nsnp > 0 & values$nsnp == floor(values$nsnp)),
          all(values$se > 0), all(values$pval >= 0 & values$pval <= 1),
          identical(values$pval, values$p_raw_exploratory),
          all(is.na(values$p_primary)), all(values$p_for_family == 1),
          all(values$role == "EXPLORATORY_OVERLAP_UNRESOLVED"))
canonical <- textConnection("canonical_text", "w", local = TRUE)
write.table(values, canonical, sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
close(canonical)
canonical_bytes <- charToRaw(paste0(paste(canonical_text, collapse = "\n"), "\n"))
original <- readBin(args[2], "raw", n = file.info(args[2])$size)
stopifnot(identical(canonical_bytes, original))
exported <- values
for (name in numeric_columns) exported[[name]] <- sprintf("%.17g", values[[name]])
exported$p_primary <- rep("NA", nrow(values))
write.table(exported, args[3], sep = "\t", quote = FALSE, row.names = FALSE, na = "NA")
reloaded <- read.delim(args[3], colClasses = "character", check.names = FALSE,
                       na.strings = NULL, quote = "", comment.char = "")
stopifnot(identical(names(reloaded), columns), nrow(reloaded) == nrow(values),
          identical(reloaded$p_primary, rep("NA", nrow(values))))
for (name in setdiff(columns, c(numeric_columns, "p_primary"))) {
  stopifnot(identical(reloaded[[name]], values[[name]]))
}
for (name in numeric_columns) {
  restored <- as.numeric(reloaded[[name]])
  stopifnot(identical(writeBin(as.double(restored), raw(), size = 8L, endian = "big"),
                      writeBin(as.double(values[[name]]), raw(), size = 8L, endian = "big")))
}
writeLines(c("A_PRECISE_MR_CARRIER_EXPORT_V1", paste0("rows=", nrow(values)),
             paste0("numeric_cells_binary64_exact=", nrow(values) * length(numeric_columns)),
             "primary_authority_granted=false", "g0_granted=false"), args[4])
