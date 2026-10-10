# Controlled visualization repair

This preserves the original `visualization` kind, two required File inputs
(plot-ready data, trusted frozen R script assigning `p`), and one PNG output.
It uses the installed immutable OCI image with R4.5.3, Arrow23.0.1.2 and
ggplot2 4.0.3; the inline runner replaces its broken `emptyenv()` enclosure
with `baseenv()`. The plotting method remains official `ggplot2::ggsave`.

The manifest declares `terminal = true`. This requires the repaired
container-plugin manifest/factory and ContainerCommandNode implementation;
old engines reject the new field rather than enforcing the terminal contract.
The default for other manifests remains false, including node clones.

Supported encodings are CSV, TSV, Parquet, Arrow IPC stream and Arrow IPC file.
Width and height are inches; DPI determines raster resolution. Defaults are
8×6 inches at150DPI. Missing plots, invalid scripts/data and invalid parameters
fail rather than publish a normal PNG. Diagnostic workspaces may retain partial
images and full failure logs; these are not successful output artifacts.

R code is trusted code, not an enforced syntax whitelist or a security sandbox.
`baseenv()` does not make arbitrary R safe. Freeze and review scripts independently
of container isolation. Do not infer statistical or scientific approval from a
rendered plot, and do not reclassify already-seen legacy results as new evidence.

The proof is an isolated runtime with freshly compiled current IO/plugin crates
and recorded cached DAG/runtime dependencies. It is not a full current engine
build, production plugin upgrade, resident-daemon acceptance or G0 approval.
Installed production checkouts, image, plugin config and study inputs are unchanged.

Reference recipes and encoder are under `study_plugins/tests/visualization_*`;
actual execution and independent replay use `scripts/prove_cachexia_visualization.py`
and `scripts/review_cachexia_visualization.py`. Use a fresh R process for each
reference configuration, matching the node's per-task process lifecycle.
