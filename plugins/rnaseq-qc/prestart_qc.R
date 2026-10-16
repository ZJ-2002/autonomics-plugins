options(stringsAsFactors = FALSE, digits = 15)

required_env <- function(name) {
  value <- Sys.getenv(name)
  if (!nzchar(value)) {
    stop(sprintf("missing required environment variable: %s", name), call. = FALSE)
  }
  value
}

read_literal_tsv <- function(filename) {
  if (!file.exists(filename) || dir.exists(filename) ||
      system2("/usr/bin/test", c("-f", shQuote(filename)), stdout = FALSE, stderr = FALSE) != 0L) {
    stop("input must be an existing regular file", call. = FALSE)
  }
  connection <- file(filename, open = "rb")
  on.exit(close(connection), add = TRUE)
  repeat {
    block <- readBin(connection, what = "raw", n = 1024L * 1024L)
    if (!length(block)) break
    if (any(block == as.raw(0))) {
      stop("input must not contain embedded NUL bytes", call. = FALSE)
    }
  }
  lines <- readLines(filename, warn = FALSE)
  lines <- sub("\r$", "", lines)
  if (length(lines) < 2L || any(!nzchar(lines))) {
    stop("input must contain a header and nonempty data rows", call. = FALSE)
  }
  parse_record <- function(line) {
    quote_character <- intToUtf8(34L)
    if (!grepl(quote_character, line, fixed = TRUE)) {
      tokens <- strsplit(paste0(line, "\t__END__"), "\t", fixed = TRUE)[[1]]
      return(tokens[-length(tokens)])
    }
    characters <- strsplit(line, "", fixed = TRUE)[[1]]
    buffer <- character(length(characters))
    size <- 0L
    tokens <- character()
    state <- "start"
    position <- 1L
    while (position <= length(characters)) {
      character <- characters[[position]]
      if (state == "quoted") {
        if (character == quote_character) {
          if (position < length(characters) && characters[[position + 1L]] == quote_character) {
            size <- size + 1L
            buffer[[size]] <- character
            position <- position + 1L
          } else {
            state <- "closed"
          }
        } else {
          size <- size + 1L
          buffer[[size]] <- character
        }
      } else if (character == "\t") {
        tokens <- c(tokens, paste0(buffer[seq_len(size)], collapse = ""))
        size <- 0L
        state <- "start"
      } else if (state == "closed") {
        stop("quoted TSV has characters after a closing quote", call. = FALSE)
      } else if (character == quote_character) {
        if (state != "start") stop("quoted TSV has a bare quote inside an unquoted field", call. = FALSE)
        state <- "quoted"
      } else {
        size <- size + 1L
        buffer[[size]] <- character
        state <- "unquoted"
      }
      position <- position + 1L
    }
    if (state == "quoted") stop("quoted TSV has an unclosed quote or multiline field", call. = FALSE)
    c(tokens, paste0(buffer[seq_len(size)], collapse = ""))
  }
  fields <- lapply(lines, parse_record)
  header <- fields[[1]]
  if (any(grepl("[[:cntrl:]]", unlist(fields, use.names = FALSE)))) {
    stop("input fields must not contain control characters", call. = FALSE)
  }
  if (any(!nzchar(header)) || anyDuplicated(header)) {
    stop("input headers must be nonempty and unique", call. = FALSE)
  }
  if (any(lengths(fields) != length(header))) {
    stop("input rows must match the header width", call. = FALSE)
  }
  frame <- as.data.frame(do.call(rbind, fields[-1]), check.names = FALSE, stringsAsFactors = FALSE)
  colnames(frame) <- header
  frame
}

exact_integer_token <- function(token) {
  token <- trimws(token)
  match <- regmatches(token, regexec(
    "^([+-]?)([0-9]*)(?:[.]([0-9]*))?(?:[eE]([+-]?[0-9]+))?$", token, perl = TRUE
  ))[[1]]
  if (length(match) != 5L || !nzchar(paste0(match[[3]], match[[4]]))) return(FALSE)
  digits <- sub("^0+", "", paste0(match[[3]], match[[4]]))
  if (!nzchar(digits)) return(TRUE)
  if (match[[2]] == "-") return(FALSE)
  exponent <- if (nzchar(match[[5]])) suppressWarnings(as.numeric(match[[5]])) else 0
  if (!is.finite(exponent)) return(FALSE)
  decimal_places <- nchar(match[[4]]) - exponent
  if (decimal_places > 0) {
    if (decimal_places >= nchar(digits)) return(FALSE)
    tail <- substr(digits, nchar(digits) - decimal_places + 1, nchar(digits))
    if (grepl("[1-9]", tail)) return(FALSE)
    digits <- substr(digits, 1, nchar(digits) - decimal_places)
  } else {
    if (nchar(digits) - decimal_places > 10L) return(FALSE)
    digits <- paste0(digits, strrep("0", -decimal_places))
  }
  nchar(digits) < 10L || (nchar(digits) == 10L && digits <= "2147483647")
}

publication_identity <- function(filename) {
  identity <- suppressWarnings(system2("/usr/bin/stat", c("-c", shQuote("%d:%i"), "--", shQuote(filename)), stdout = TRUE, stderr = FALSE))
  status <- attr(identity, "status")
  if ((!is.null(status) && status != 0L) || length(identity) != 1L || !grepl("^[0-9]+:[0-9]+$", identity)) return(NA_character_)
  unname(identity)
}

publication_file_identity <- function(filename) {
  link <- Sys.readlink(filename)
  if (!is.na(link) && nzchar(link)) return(NA_character_)
  metadata <- function() {
    result <- suppressWarnings(system2("/usr/bin/stat", c("-c", shQuote("%d:%i:%f:%u:%g:%s:%y"), "--", shQuote(filename)), stdout = TRUE, stderr = FALSE))
    status <- attr(result, "status")
    if ((!is.null(status) && status != 0L) || length(result) != 1L) return(NA_character_)
    fields <- strsplit(result, ":", fixed = TRUE)[[1]]
    if (length(fields) < 7L || is.na(strtoi(fields[[3]], base = 16L)) ||
        bitwAnd(strtoi(fields[[3]], base = 16L), 61440L) != 32768L) return(NA_character_)
    unname(result)
  }
  before <- metadata()
  if (is.na(before)) return(NA_character_)
  checksum <- tryCatch(suppressWarnings(system2("/usr/bin/sha256sum", stdin = filename, stdout = TRUE, stderr = FALSE)), error = function(condition) character())
  status <- attr(checksum, "status")
  after <- metadata()
  link <- Sys.readlink(filename)
  if ((!is.null(status) && status != 0L) || length(checksum) != 1L ||
      !grepl("^[0-9a-f]{64}  -$", checksum) || is.na(after) || !identical(before, after) ||
      (!is.na(link) && nzchar(link))) return(NA_character_)
  paste0(before, ":", substr(checksum, 1L, 64L))
}

publication_remove_owned_file <- function(filename, expected) {
  if (is.na(expected)) return(invisible(FALSE))
  current <- publication_file_identity(filename)
  if (is.na(current) || !identical(current, expected)) return(invisible(FALSE))
  invisible(unlink(filename) == 0L)
}


main <- function() {
 count_path <- required_env("AUTONOMICS_INPUT0")
 metadata_path <- required_env("AUTONOMICS_INPUT1")
 outputs <- vapply(0:6,function(i)required_env(paste0("AUTONOMICS_OUTPUT",i)),character(1))
 links <- Sys.readlink(outputs)
 if (any(file.exists(outputs)) || any(!is.na(links)&nzchar(links))) stop("existing outputs must not be overwritten")
 identities <- vapply(outputs,function(p)file.path(normalizePath(dirname(p),mustWork=TRUE),basename(p)),character(1))
 if (anyDuplicated(identities)) stop("output paths must be distinct")
counts_frame <- read_literal_tsv(count_path)
metadata_frame <- read_literal_tsv(metadata_path)

if (ncol(counts_frame) < 2 || !identical(colnames(counts_frame)[[1]], "gene_id")) {
  stop("count matrix must start with gene_id followed by sample columns", call. = FALSE)
}
if (anyDuplicated(colnames(counts_frame))) {
  stop("count matrix column names must be unique", call. = FALSE)
}
gene_ids <- counts_frame[[1]]
if (anyNA(gene_ids) || !all(nzchar(gene_ids))) {
  stop("gene_id cannot be empty", call. = FALSE)
}
if (anyDuplicated(gene_ids)) {
  stop("gene_id values must be unique", call. = FALSE)
}

count_samples <- colnames(counts_frame)[-1]
counts <- suppressWarnings(matrix(as.numeric(as.matrix(counts_frame[, -1])), nrow = nrow(counts_frame)))
rownames(counts) <- gene_ids
colnames(counts) <- count_samples
if (anyNA(counts) || any(!is.finite(counts)) || any(counts < 0) || any(counts != floor(counts)) || any(counts > .Machine$integer.max)) {
  stop("all count values must be finite nonnegative integers within R integer range", call. = FALSE)
}
count_tokens <- as.vector(as.matrix(counts_frame[, -1]))
nonliteral_integers <- !grepl("^[+]?[0-9]+$", trimws(count_tokens))
if (any(!vapply(count_tokens[nonliteral_integers], exact_integer_token, logical(1)))) {
  stop("all count values must be finite nonnegative integers within R integer range", call. = FALSE)
}
if (any(colSums(counts) <= 0)) {
  stop("every sample library must have positive total counts", call. = FALSE)
}

if (ncol(metadata_frame) < 1 || !identical(colnames(metadata_frame)[[1]], "sample_id")) {
  stop("sample metadata must start with sample_id", call. = FALSE)
}
if (anyDuplicated(colnames(metadata_frame))) {
  stop("sample metadata column names must be unique", call. = FALSE)
}
metadata_samples <- metadata_frame[[1]]
if (anyNA(metadata_samples) || !all(nzchar(metadata_samples))) {
  stop("sample_id cannot be empty", call. = FALSE)
}
if (anyDuplicated(metadata_samples)) {
  stop("sample_id values must be unique", call. = FALSE)
}
if (!setequal(metadata_samples, count_samples)) {
  stop("count matrix and metadata sample sets must match exactly", call. = FALSE)
}

metadata_frame <- metadata_frame[match(count_samples, metadata_samples), , drop = FALSE]
rownames(metadata_frame) <- metadata_frame$sample_id


 if (ncol(counts)<2) stop("at least two samples are required for sample QC")
 storage.mode(counts) <- "integer"
 # Condition/phenotype columns are deliberately not used in the QC design.
 blind_metadata <- data.frame(row.names=count_samples, sample_id=count_samples)
 dds <- DESeq2::DESeqDataSetFromMatrix(countData=counts,colData=blind_metadata,design=~1)
 dds <- DESeq2::estimateSizeFactors(dds,type="ratio")
 sf <- DESeq2::sizeFactors(dds)
 if (any(!is.finite(sf)) || any(sf<=0)) stop("invalid size factors; no automatic normalization alternative")
 normalized <- DESeq2::counts(dds,normalized=TRUE)
 transformed <- log2(normalized+1)
 if (!identical(dimnames(transformed),dimnames(counts))) stop("normalization changed axes")
 centered <- sweep(t(transformed),2L,colMeans(t(transformed)),"-")
 total_variance <- sum(centered^2)/(ncol(counts)-1)
 components <- min(ncol(counts)-1L,nrow(counts))
 if (total_variance>0) {
  pca <- stats::prcomp(t(transformed),center=TRUE,scale.=FALSE,rank.=components)
  scores <- pca$x
  variance <- pca$sdev[seq_len(ncol(scores))]^2
  pca_table <- data.frame(component=colnames(scores),variance=variance,proportion=variance/total_variance,cumulative=cumsum(variance)/total_variance)
  pca_status <- "AVAILABLE"
 } else {
  scores <- matrix(numeric(),nrow=ncol(counts),ncol=0,dimnames=list(count_samples,character()))
  pca_table <- data.frame(component=character(),variance=numeric(),proportion=numeric(),cumulative=numeric())
  pca_status <- "NO_SAMPLE_VARIATION"
 }
 distance <- as.matrix(stats::dist(t(transformed),method="euclidean"))
 library <- data.frame(sample_id=count_samples,library_counts=colSums(counts),detected_genes=colSums(counts>0),zero_genes=colSums(counts==0),size_factor=sf,normalized_library_sum=colSums(normalized))
 if (length(DESeq2::resultsNames(dds)) || any(c("dispGeneEst","dispFit","betaConv") %in% names(S4Vectors::mcols(dds)))) stop("unexpected fitted differential model")
 sha <- function(p) {
  value <- system2("/usr/bin/sha256sum",stdin=p,stdout=TRUE,stderr=FALSE)
  status <- attr(value,"status")
  if ((!is.null(status)&&status!=0L)||length(value)!=1L||!grepl("^[0-9a-f]{64}  -$",value)) stop("cannot hash input")
  substr(value,1L,64L)
 }
 report <- list(schema_version=1L,operation="RNA_SEQ_PRESTART_QC_NO_DIFFERENTIAL_FIT",genes=nrow(counts),samples=ncol(counts),gene_ids=as.list(gene_ids),sample_ids=as.list(count_samples),
  normalization="official DESeq2 estimateSizeFactors(type=ratio) only; no automatic fallback",transform="log2(normalized counts + 1)",
  PCA="all submitted genes; sample x feature; centered; not scaled; no variable-feature selection",pca_status=pca_status,
  distance="Euclidean on all log2(normalized+1) features",design="~1; metadata phenotype columns unused",feature_or_sample_removal=FALSE,
  differential_fit_performed=FALSE,dispersion_fit_performed=FALSE,differential_tests_performed=FALSE,scientific_qc_pass_granted=FALSE,
  inputs=list(counts_sha256=sha(count_path),metadata_sha256=sha(metadata_path)),engine=list(R=as.character(getRversion()),DESeq2=as.character(utils::packageVersion("DESeq2"))),session=utils::capture.output(sessionInfo()))
 stages <- character();stage_ids <- character();staged <- character();owned <- rep(NA_character_,length(outputs));published <- integer();complete <- FALSE
 on.exit({
  if (!complete) for(i in published)publication_remove_owned_file(outputs[[i]],owned[[i]])
  for(i in seq_along(stages))if(identical(publication_identity(stages[[i]]),stage_ids[[i]])){
   if(length(staged)>=i)publication_remove_owned_file(staged[[i]],owned[[i]])
   suppressWarnings(system2("/usr/bin/rmdir",c("--",shQuote(stages[[i]])),stdout=FALSE,stderr=FALSE))
  }
 },add=TRUE)
 for(parent in dirname(outputs)){
  directory <- tempfile(".rnaseq-qc-",tmpdir=normalizePath(parent,mustWork=TRUE))
  if(!dir.create(directory,mode="0700"))stop("cannot create private staging")
  stages <- c(stages,directory);stage_ids <- c(stage_ids,publication_identity(directory))
  if(is.na(tail(stage_ids,1)))stop("cannot bind staging")
 }
 staged <- file.path(stages,paste0("port",0:6))
 matrix_table <- function(m)data.frame(gene_id=rownames(m),as.data.frame(m,check.names=FALSE),check.names=FALSE)
 tables <- list(matrix_table(normalized),matrix_table(transformed),data.frame(sample_id=rownames(scores),as.data.frame(scores,check.names=FALSE),check.names=FALSE),pca_table,data.frame(sample_id=rownames(distance),as.data.frame(distance,check.names=FALSE),check.names=FALSE),library)
 options(digits=17)
 for(i in seq_along(tables))write.table(tables[[i]],staged[[i]],sep="\t",quote=TRUE,row.names=FALSE,na="NA")
 jsonlite::write_json(report,staged[[7]],auto_unbox=TRUE,pretty=TRUE,null="null",na="null",digits=NA)
 for(i in seq_along(outputs)){
  owned[[i]] <- publication_file_identity(staged[[i]])
  if(is.na(owned[[i]]))stop("cannot bind output")
 }
 for(i in seq_along(outputs)){
  if(!identical(publication_identity(stages[[i]]),stage_ids[[i]])||!identical(publication_file_identity(staged[[i]]),owned[[i]]))stop("staging changed")
  if(!file.link(staged[[i]],outputs[[i]]))stop("publication refused")
  published <- c(published,i)
 }
 for(i in seq_along(outputs))if(!identical(publication_file_identity(outputs[[i]]),owned[[i]]))stop("published output changed")
 complete <- TRUE
}
main()
