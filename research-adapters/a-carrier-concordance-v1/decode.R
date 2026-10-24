args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 2L, as.character(getRversion()) == "4.6.1")
object <- readRDS(args[1])
stopifnot(is.list(object), !anyDuplicated(names(object)),
          is.data.frame(object$mr), is.list(object$contract),
          identical(object$contract$R, "4.6.1"),
          identical(object$contract$TwoSampleMR, "0.7.11"))
columns <- c("id.exposure", "id.outcome", "outcome", "exposure", "method",
             "nsnp", "b", "se", "pval", "role", "p_primary",
             "p_for_family", "p_raw_exploratory")
stopifnot(identical(names(object$mr), columns), nrow(object$mr) > 0L,
          !anyDuplicated(object$mr[c("id.exposure", "id.outcome", "method")]))
for (field in c("id.exposure", "id.outcome", "outcome", "exposure", "method", "role")) {
  stopifnot(is.character(object$mr[[field]]), !anyNA(object$mr[[field]]))
}
for (field in c("nsnp", "b", "se", "pval", "p_for_family", "p_raw_exploratory")) {
  stopifnot(is.numeric(object$mr[[field]]))
}
stopifnot(all(is.na(object$mr$p_primary)),
          all(object$mr$p_for_family == 1),
          all(object$mr$role == "EXPLORATORY_OVERLAP_UNRESOLVED"))
write.table(object$mr, args[2], sep = "\t", quote = FALSE,
            row.names = FALSE, na = "NA")
