# Plugin-era render runner for the visualization node: adapted verbatim from
# the legacy image-baked /opt/autonomics/render.R (containers/visualization,
# now Dockerfile/render.R in this directory for image provenance). The
# runner is staged by ContainerCommandNode and executed as
# `Rscript /work/.autonomics/script`; every legacy wrapper spec param
# arrives as an AUTONOMICS_VISUALIZATION_* environment variable.
#
# The user R script is NOT baked here and NOT a manifest file: it enters as
# an ordinary File on input port 1, so ContainerCommandNode stages it and
# AUTONOMICS_INPUT1 points at it inside the container. The plot-ready data
# on port 0 is AUTONOMICS_INPUT0; `df` is preloaded into the script's
# environment before it is sourced.

data_path <- Sys.getenv("AUTONOMICS_INPUT0")
script_path <- Sys.getenv("AUTONOMICS_INPUT1")
output_path <- Sys.getenv("AUTONOMICS_OUTPUT0")
data_format <- Sys.getenv("AUTONOMICS_VISUALIZATION_DATA_FORMAT")
width <- as.numeric(Sys.getenv("AUTONOMICS_VISUALIZATION_WIDTH"))
height <- as.numeric(Sys.getenv("AUTONOMICS_VISUALIZATION_HEIGHT"))
dpi <- as.numeric(Sys.getenv("AUTONOMICS_VISUALIZATION_DPI"))

if (!nzchar(data_path) || !nzchar(script_path) || !nzchar(output_path)) {
  stop("visualization render requires input, script, and output bindings")
}

df <- switch(
  data_format,
  csv = arrow::read_csv_arrow(data_path, as_data_frame = TRUE),
  tsv = arrow::read_tsv_arrow(data_path, as_data_frame = TRUE),
  parquet = arrow::read_parquet(data_path, as_data_frame = TRUE),
  arrow_stream = arrow::read_ipc_stream(data_path, as_data_frame = TRUE),
  arrow_file = arrow::read_feather(data_path, as_data_frame = TRUE),
  stop("unsupported visualization data format: ", data_format)
)

script_env <- new.env(parent = emptyenv())
script_env$df <- df
source(script_path, local = script_env)
if (!exists("p", envir = script_env, inherits = FALSE) || is.null(script_env$p)) {
  stop("visualization script must assign a plot to a variable named `p`")
}

ggplot2::ggsave(
  filename = output_path,
  plot = script_env$p,
  device = "png",
  width = width,
  height = height,
  dpi = dpi,
  units = "in"
)
