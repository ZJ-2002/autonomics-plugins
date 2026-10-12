arguments <- commandArgs(TRUE)
root <- arguments[[1]]
source <- arguments[[2]]
statements <- parse(source)
target <- Filter(function(expression) is.call(expression) && identical(expression[[1]], as.name("<-")) &&
    identical(expression[[2]], as.name("read_literal_tsv")), as.list(statements))
stopifnot(length(target) == 1L)
environment <- new.env(parent = globalenv())
eval(target[[1]], envir = environment)
quote_character <- intToUtf8(34L)
quoted <- function(value) paste0(quote_character, gsub(quote_character, paste0(quote_character, quote_character), value, fixed = TRUE), quote_character)
records <- list()
run_case <- function(name, payload, expected = NULL, fragment = NULL) {
    directory <- file.path(root, name)
    stopifnot(dir.create(directory))
    path <- file.path(directory, "input.tsv")
    writeBin(if (is.raw(payload)) payload else charToRaw(payload), path)
    value <- tryCatch(environment$read_literal_tsv(path), error = function(error) error)
    if (is.null(fragment)) {
        stopifnot(!inherits(value, "error"), identical(colnames(value), expected$columns),
            identical(unname(as.matrix(value)), unname(expected$values)))
        standard <- read.delim(path, check.names = FALSE, colClasses = "character", na.strings = character(),
            quote = quote_character, comment.char = "", strip.white = FALSE)
        stopifnot(identical(colnames(standard), expected$columns), identical(unname(as.matrix(standard)), unname(expected$values)))
    } else {
        stopifnot(inherits(value, "error"), grepl(fragment, conditionMessage(value), fixed = TRUE))
    }
    records[[length(records) + 1L]] <<- list(case = name, status = "PASS", refused = !is.null(fragment),
        diagnostic = if (inherits(value, "error")) conditionMessage(value) else NULL)
}
lexical <- c("NA", "NULL", "0001", "中文基因", "O'Gene", "", " leading space ", "gene,comma", paste0(quote_character, "leading"), paste0("middle", quote_character, "quote"))
payload <- paste0("gene_id\tlabel\n", paste(vapply(lexical, function(value) paste0(quoted(value), "\t", quoted(value)), character(1)), collapse = "\n"), "\n")
run_case("quoted-lexical", payload, list(columns = c("gene_id", "label"), values = cbind(lexical, lexical)))
run_case("plain-lexical", "gene_id\tlabel\nNA\tNULL\n0001\t\n", list(columns = c("gene_id", "label"), values = matrix(c("NA", "0001", "NULL", ""), ncol = 2)))
run_case("crlf", "gene_id\tlabel\r\ng1\tA\r\n", list(columns = c("gene_id", "label"), values = matrix(c("g1", "A"), nrow = 1)))
run_case("bare-quote", paste0("gene_id\tlabel\ng", quote_character, "1\tA\n"), fragment = "bare quote")
run_case("unclosed", paste0("gene_id\tlabel\n", quote_character, "g1\tA\n"), fragment = "unclosed quote")
run_case("post-close", paste0("gene_id\tlabel\n", quote_character, "g1", quote_character, "x\tA\n"), fragment = "after a closing quote")
run_case("multiline", paste0("gene_id\tlabel\n", quote_character, "g1\ng2", quote_character, "\tA\n"), fragment = "unclosed quote")
run_case("quoted-tab", paste0("gene_id\tlabel\n", quoted("g\t1"), "\tA\n"), fragment = "control characters")
run_case("duplicate-header", paste0(quoted("gene_id"), "\tgene_id\ng1\tA\n"), fragment = "unique")
run_case("empty-header", "gene_id\t\ng1\tA\n", fragment = "nonempty")
run_case("width", "gene_id\tlabel\ng1\tA\tB\n", fragment = "header width")
run_case("nul", c(charToRaw("gene_id\tlabel\ng1\tA"), as.raw(0), charToRaw("\n")), fragment = "NUL bytes")
jsonlite::write_json(list(source = source, cases = records, actual_production_function = TRUE,
    official_base_R_reader_double_quote_only = TRUE, no_method_fit = TRUE, G0 = FALSE),
    file.path(root, "PARSER_BOUNDARIES.json"), pretty = TRUE, auto_unbox = TRUE)
