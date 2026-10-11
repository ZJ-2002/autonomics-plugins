
# Plugin entry. Every output is a technical component artifact; neither the
# node nor a parameter may grant scientific acceptance or formal execution.
input_paths <- vapply(0:3, function(i) Sys.getenv(paste0("AUTONOMICS_INPUT", i)), character(1))
output_paths <- vapply(0:2, function(i) Sys.getenv(paste0("AUTONOMICS_OUTPUT", i)), character(1))
if (any(!nzchar(input_paths)) || any(!file.exists(input_paths)) ||
    any(!nzchar(output_paths)) || anyDuplicated(output_paths) || any(file.exists(output_paths)))
  stop("Four actual inputs and three fresh distinct outputs required", call. = FALSE)
answer <- cis_fit_declared(input_paths[[1]], input_paths[[2]], input_paths[[3]], input_paths[[4]])
answer$audit$artifact_scope <- "OFFICIAL_CIS_TECHNICAL_COMPONENT_NOT_FORMAL_AUTHORIZATION"
script <- sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE))
if (length(script) != 1L || !file.exists(script)) stop("Actual adapter script identity unavailable")
answer$audit$adapter_script_sha256 <- digest::digest(file = script, algo = "sha256")
for (path in output_paths) dir.create(dirname(path), recursive = TRUE, showWarnings = FALSE)
write.table(answer$estimate, output_paths[[1]], quote = FALSE, row.names = FALSE, sep = "\t", na = "NA")
jsonlite::write_json(answer$audit, output_paths[[2]], auto_unbox = TRUE, digits = 17, null = "null", na = "null")
saveRDS(answer, output_paths[[3]], version = 3)
