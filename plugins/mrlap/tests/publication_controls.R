arguments <- commandArgs(trailingOnly = TRUE)
stopifnot(length(arguments) == 2L)
old_source <- parse(arguments[[2L]], keep.source = FALSE)
namespace <- new.env(parent = globalenv())
sys.source(arguments[[1L]], envir = namespace)
new_body <- as.list(body(namespace$run_mrlap))[-1L]
stopifnot(identical(new_body[[length(new_body)]], 0L))
new_body <- new_body[-c(1L, 2L, length(new_body))]
port_names <- c(summary_path = "AUTONOMICS_OUTPUT0", rds_path = "AUTONOMICS_OUTPUT1",
                txt_path = "AUTONOMICS_OUTPUT2", log_path = "AUTONOMICS_OUTPUT3")
for (index in seq_along(new_body)) {
  expression <- new_body[[index]]
  if (is.call(expression) && identical(expression[[1L]], as.name("<-"))) {
    name <- as.character(expression[[2L]])
    if (length(name) == 1L && name %in% names(port_names))
      new_body[[index]] <- call("<-", as.name(name), call("Sys.getenv", unname(port_names[[name]])))
  }
}
stopifnot(identical(old_source[[length(old_source)]], quote(q(status = 0))))
stopifnot(identical(as.list(old_source)[-length(old_source)], new_body))
results <- list(data.frame(case = "whole_original_method_AST_preserved_except_ports_sink_cleanup_exit", pass = TRUE))

run_case <- function(name, action) {
  root <- tempfile("mrlap-publish-control-", tmpdir = Sys.getenv("TMPDIR"))
  stopifnot(dir.create(root, mode = "0700"))
  ports <- file.path(root, paste0("port-", 0:3))
  variables <- paste0("AUTONOMICS_OUTPUT", 0:3)
  previous <- Sys.getenv(variables, unset = NA_character_)
  on.exit({
    for (index in seq_along(variables)) {
      if (is.na(previous[[index]])) Sys.unsetenv(variables[[index]])
      else do.call(Sys.setenv, setNames(list(previous[[index]]), variables[[index]]))
    }
    unlink(root, recursive = TRUE)
  }, add = TRUE)
  do.call(Sys.setenv, as.list(setNames(ports, variables)))
  writer <- function(outputs) {
    for (index in seq_along(outputs)) writeLines(paste0("payload-", index), outputs[[index]])
    0L
  }
  refused <- function(action) inherits(tryCatch({action(); NULL}, error = identity), "error")
  action(root, ports, writer, refused)
  stopifnot(length(list.files(root, pattern = "^\\.mrlap-owned-", all.files = TRUE)) == 0L)
  results[[length(results) + 1L]] <<- data.frame(case = name, pass = TRUE)
}

run_case("all_four_complete_outputs", function(root, ports, writer, refused) {
  stopifnot(namespace$publish_mrlap_outputs(writer) == 0L)
  for (index in seq_along(ports)) stopifnot(identical(readLines(ports[[index]]), paste0("payload-", index)))
})
for (position in 1:4) local({
  selected <- position
  run_case(paste0("dangling_declared_port_", selected), function(root, ports, writer, refused) {
    stopifnot(file.symlink(file.path(root, "absent"), ports[[selected]]))
    stopifnot(refused(function() namespace$publish_mrlap_outputs(function(outputs) stop("writer must not execute"))))
    stopifnot(nzchar(Sys.readlink(ports[[selected]])), !file.exists(file.path(root, "absent")))
  })
})
run_case("existing_regular_output_preserved", function(root, ports, writer, refused) {
  writeLines("foreign", ports[[2L]])
  stopifnot(refused(function() namespace$publish_mrlap_outputs(writer)), identical(readLines(ports[[2L]]), "foreign"))
})
run_case("duplicate_destinations_refused", function(root, ports, writer, refused) {
  Sys.setenv(AUTONOMICS_OUTPUT1 = ports[[1L]])
  stopifnot(refused(function() namespace$publish_mrlap_outputs(writer)), !any(file.exists(ports)))
})
run_case("late_foreign_second_port_preserved_first_link_rolled_back", function(root, ports, writer, refused) {
  competing <- function(outputs) {writer(outputs); writeLines("foreign", ports[[2L]]); 0L}
  stopifnot(refused(function() suppressWarnings(namespace$publish_mrlap_outputs(competing))))
  stopifnot(identical(readLines(ports[[2L]]), "foreign"), !any(file.exists(ports[-2L])))
})
run_case("writer_failure_publishes_only_failure_log", function(root, ports, writer, refused) {
  failing <- function(outputs) {writeLines("partial", outputs[[1L]]); stop("explicit synthetic writer failure")}
  stopifnot(namespace$publish_mrlap_outputs(failing) == 1L, !any(file.exists(ports[1:3])))
  stopifnot(grepl("explicit synthetic writer failure", paste(readLines(ports[[4L]]), collapse = " ")))
})
run_case("missing_last_staged_port_rolls_back_all_prior_links", function(root, ports, writer, refused) {
  incomplete <- function(outputs) {writer(outputs); unlink(outputs[[4L]]); 0L}
  stopifnot(refused(function() namespace$publish_mrlap_outputs(incomplete)), !any(file.exists(ports)))
})
run_case("staged_symlink_refused_without_touching_target", function(root, ports, writer, refused) {
  foreign <- file.path(root, "foreign-data")
  writeLines("foreign", foreign)
  linked <- function(outputs) {writer(outputs); unlink(outputs[[2L]]); stopifnot(file.symlink(foreign, outputs[[2L]])); 0L}
  stopifnot(refused(function() namespace$publish_mrlap_outputs(linked)), !any(file.exists(ports)), identical(readLines(foreign), "foreign"))
})
run_case("existing_directory_refused", function(root, ports, writer, refused) {
  stopifnot(dir.create(ports[[1L]]), refused(function() namespace$publish_mrlap_outputs(writer)), dir.exists(ports[[1L]]))
})
run_case("same_basenames_in_distinct_directories_supported", function(root, ports, writer, refused) {
  directories <- file.path(root, paste0("destination-", 1:4))
  stopifnot(all(vapply(directories, dir.create, logical(1))))
  targets <- file.path(directories, "same-name")
  do.call(Sys.setenv, as.list(setNames(targets, paste0("AUTONOMICS_OUTPUT", 0:3))))
  stopifnot(namespace$publish_mrlap_outputs(writer) == 0L, all(file.exists(targets)))
})
run_case("invalid_writer_status_refused", function(root, ports, writer, refused) {
  stopifnot(refused(function() namespace$publish_mrlap_outputs(function(outputs) {writer(outputs); 2L})), !any(file.exists(ports)))
})
run_case("missing_declared_output_refused", function(root, ports, writer, refused) {
  Sys.unsetenv("AUTONOMICS_OUTPUT3")
  stopifnot(refused(function() namespace$publish_mrlap_outputs(writer)), !any(file.exists(ports)))
})
run_case("late_foreign_failure_log_is_not_overwritten", function(root, ports, writer, refused) {
  failing <- function(outputs) {writeLines("foreign", ports[[4L]]); stop("synthetic failure")}
  stopifnot(refused(function() suppressWarnings(namespace$publish_mrlap_outputs(failing))), identical(readLines(ports[[4L]]), "foreign"), !any(file.exists(ports[1:3])))
})
run_case("string_writer_status_is_not_coerced", function(root, ports, writer, refused) {
  stopifnot(refused(function() namespace$publish_mrlap_outputs(function(outputs) {writer(outputs); "0"})), !any(file.exists(ports)))
})
run_case("staged_failure_log_symlink_cannot_modify_foreign_target", function(root, ports, writer, refused) {
  foreign <- file.path(root, "foreign-log")
  writeLines("foreign", foreign)
  failing <- function(outputs) {stopifnot(file.symlink(foreign, outputs[[4L]])); stop("synthetic failure")}
  stopifnot(refused(function() namespace$publish_mrlap_outputs(failing)), identical(readLines(foreign), "foreign"), !any(file.exists(ports)))
})
table <- do.call(rbind, results)
stopifnot(all(table$pass))
write.table(table, file = stdout(), sep = "\t", row.names = FALSE, quote = FALSE)
