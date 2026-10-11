arguments <- commandArgs(trailingOnly = TRUE)
stopifnot(length(arguments) == 1L)
expressions <- parse(arguments[1])
starts <- vapply(expressions, function(expression) {
  is.call(expression) && identical(expression[[1]], as.name("<-")) &&
    identical(expression[[2]], as.name("required_correction_fields"))
}, logical(1))
ends <- vapply(expressions, function(expression) {
  is.call(expression) && identical(expression[[1]], as.name("<-")) &&
    identical(expression[[2]], as.name("mc"))
}, logical(1))
stopifnot(sum(starts) == 1L, sum(ends) == 1L)
guards <- expressions[which(starts):(which(ends) - 1L)]
base_result <- list(MRcorrection = list(observed_effect = 0.1, observed_effect_se = 0.02,
  corrected_effect = 0.15, corrected_effect_se = 0.03, corrected_effect_p = 0.01))
check <- function(value, expected_error) {
  environment <- new.env(parent = baseenv())
  environment$res <- value
  result <- tryCatch({ eval(guards, environment); NULL }, error = function(error) conditionMessage(error))
  if (is.null(expected_error)) stopifnot(is.null(result)) else {
    stopifnot(is.character(result), grepl(expected_error, result, fixed = TRUE))
  }
  environment
}
verified <- 0L
valid <- check(base_result, NULL)
verified <- verified + 1L
for (value in list(NULL, NA_real_, NaN, Inf, -Inf, c(0.1, 0.2), "0.1")) {
  changed <- base_result
  changed$MRcorrection$corrected_effect <- value
  check(changed, "non-estimable")
  verified <- verified + 1L
}
for (change in list(c("observed_effect_se", "0"), c("corrected_effect_se", "-1"),
                    c("corrected_effect_p", "-0.1"), c("corrected_effect_p", "1.1"))) {
  changed <- base_result
  changed$MRcorrection[[change[1]]] <- as.numeric(change[2])
  check(changed, "invalid SE or P")
  verified <- verified + 1L
}
stopifnot(identical(valid$g(NULL), NA_real_), identical(valid$g(numeric()), NA_real_),
          identical(valid$g(NA_real_), NA_real_), identical(valid$g(7L), 7))
verified <- verified + 4L
for (value in list(NaN, Inf, -Inf, c(1, 2), "1")) {
  failure <- tryCatch({ valid$g(value); NULL }, error = function(error) conditionMessage(error))
  stopifnot(is.character(failure), grepl("numeric scalars", failure, fixed = TRUE))
  verified <- verified + 1L
}
stopifnot(verified == 21L)
cat("21 production-source result guard checks passed; no author method invocation or numerical certification\n")
