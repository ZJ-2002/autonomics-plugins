//! `figure_embed` node — wraps an image path as a LaTeX figure string.
//!
//! This node produces a single-row DataFrame with a `latex` string, not JSON.
//! It prepares a figure block; it does not read or qualify the image asset.

use std::sync::Arc;

use crate::table_node::{escape_latex_text, valid_latex_label};
use arrow_array::{ArrayRef, RecordBatch, StringArray};
use arrow_schema::{DataType, Field, Schema, SchemaRef};
use async_trait::async_trait;
use datafusion::common::HashMap;
use schemars::{JsonSchema, schema_for};
use serde::{Deserialize, Serialize};

use dag_core::{
    dag::{DagError, graph::PortOutputs},
    node::{DagNode, NodeInput, NodePorts},
    registry::NodeFactory,
};

// ---------------------------------------------------------------------------
// Spec
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct FigureEmbedSpec {
    /// Path to the image file (relative to the LaTeX working directory).
    pub path: String,

    /// Optional plain-text caption; LaTeX commands are escaped.
    pub caption: Option<String>,

    /// Optional `\label{...}`.
    pub label: Option<String>,

    /// Width as a fraction of `\textwidth` (e.g. `0.8` for `0.8\textwidth`).
    /// If omitted, no width constraint is applied.
    pub width: Option<f64>,

    /// Float placement: `h`, `t`, `b`, `p`, `H`. Default: `htbp`.
    #[serde(default = "default_placement")]
    pub placement: String,
}

fn default_placement() -> String {
    "htbp".into()
}

// ---------------------------------------------------------------------------
// Node
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct FigureEmbedNode {
    meta: NodePorts,
    spec: FigureEmbedSpec,
}

fn port_layout() -> NodePorts {
    NodePorts::new().add_output_port(None) // 1 output, no inputs (source node)
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

pub struct FigureEmbedFactory {}

impl NodeFactory for FigureEmbedFactory {
    fn kind(&self) -> &'static str {
        "figure_embed"
    }

    fn desc(&self) -> &'static str {
        "Wrap a relative image path as a LaTeX figure string in a DataFrame."
    }

    fn doc(&self) -> &'static str {
        "Produces a one-row DataFrame with a latex string, not JSON. \
         Accepts a relative ASCII asset path, plain-text caption, safe label, \
         optional width in (0,1], and float placement. Does not read the image \
         or certify its content; H placement requires the LaTeX float package."
    }

    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(FigureEmbedSpec)
    }

    fn ports(&self) -> NodePorts {
        port_layout()
    }

    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: dag_core::registry::NodeCtx,
    ) -> Result<Box<dyn DagNode>, dag_core::registry::error::Error> {
        let s: FigureEmbedSpec = serde_json::from_value(spec)?;
        let safe_path = !s.path.is_empty()
            && !s.path.starts_with('/')
            && s.path
                .bytes()
                .all(|character| character.is_ascii_alphanumeric() || b"/._-".contains(&character))
            && s.path
                .split('/')
                .all(|component| !component.is_empty() && component != "." && component != "..");
        if !safe_path {
            return Err(dag_core::registry::error::Error::Unknown(
                "image path must be a relative ASCII asset path without empty or traversal components".into(),
            ));
        }
        if s.width
            .is_some_and(|width| !width.is_finite() || width <= 0.0 || width > 1.0)
        {
            return Err(dag_core::registry::error::Error::Unknown(
                "figure width must be finite and in (0,1]".into(),
            ));
        }
        let safe_placement = s.placement == "H"
            || (!s.placement.is_empty()
                && s.placement
                    .bytes()
                    .all(|character| b"htbp!".contains(&character))
                && s.placement
                    .bytes()
                    .any(|character| b"htbp".contains(&character)));
        if !safe_placement {
            return Err(dag_core::registry::error::Error::Unknown(
                "figure placement must use h,t,b,p,! or H alone".into(),
            ));
        }
        if s.label
            .as_deref()
            .is_some_and(|label| !valid_latex_label(label))
        {
            return Err(dag_core::registry::error::Error::Unknown(
                "figure label must be a non-empty ASCII alphanumeric identifier with :._-".into(),
            ));
        }
        Ok(Box::new(FigureEmbedNode {
            meta: port_layout(),
            spec: s,
        }))
    }
}

// ---------------------------------------------------------------------------
// DagNode impl
// ---------------------------------------------------------------------------

#[async_trait]
impl DagNode for FigureEmbedNode {
    fn ports(&self) -> &NodePorts {
        &self.meta
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(self.clone())
    }

    fn kind(&self) -> &'static str {
        "figure_embed"
    }

    fn as_any(&self) -> &dyn std::any::Any {
        self
    }

    async fn execute(
        &mut self,
        node_ctx: &dag_core::registry::NodeCtx,
        inputs: &[NodeInput],
        _reporter: &dag_core::dag::node_event::NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        if !inputs.is_empty() {
            return Err(DagError::NodeError {
                node_type: "figure_embed".into(),
                msg: "figure_embed accepts no input ports".into(),
            });
        }
        // Build the LaTeX figure block.
        let latex = render_figure_latex(&self.spec);

        // Output as a single-row DataFrame with a 'latex' column.
        let out_schema: SchemaRef = Arc::new(Schema::new(vec![Field::new(
            "latex",
            DataType::Utf8,
            false,
        )]));
        let cols: Vec<ArrayRef> = vec![Arc::new(StringArray::from(vec![latex.as_str()]))];
        let batch = RecordBatch::try_new(out_schema, cols).map_err(|e| DagError::NodeError {
            node_type: "figure_embed".into(),
            msg: format!("failed to build output batch: {e}"),
        })?;

        let session = node_ctx.session();
        let out_df = session.read_batch(batch).map_err(|e| DagError::NodeError {
            node_type: "figure_embed".into(),
            msg: format!("read_batch failed: {e}"),
        })?;

        let mut out: PortOutputs = PortOutputs::new();
        out.insert(0, out_df);
        Ok(out)
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn render_figure_latex(spec: &FigureEmbedSpec) -> String {
    let mut out = String::with_capacity(512);

    out.push_str(&format!("\\begin{{figure}}[{}]\n", spec.placement));
    out.push_str("  \\centering\n");

    let width_cmd = match spec.width {
        Some(w) => format!("[width={w}\\textwidth] "),
        None => String::new(),
    };
    out.push_str(&format!(
        "  \\includegraphics{width_cmd}{{{path}}}\n",
        path = spec.path
    ));

    if let Some(ref cap) = spec.caption {
        out.push_str(&format!("  \\caption{{{}}}\n", escape_latex_text(cap)));
    }
    if let Some(ref lbl) = spec.label {
        out.push_str(&format!("  \\label{{{lbl}}}\n"));
    }

    out.push_str("\\end{figure}");
    out
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn render_figure_basic() {
        let spec = FigureEmbedSpec {
            path: "figures/plot.pdf".into(),
            caption: Some("Main result.".into()),
            label: Some("fig:main".into()),
            width: Some(0.8),
            placement: "htbp".into(),
        };
        let latex = render_figure_latex(&spec);
        assert!(latex.contains("\\begin{figure}[htbp]"));
        assert!(latex.contains("\\includegraphics[width=0.8\\textwidth] {figures/plot.pdf}"));
        assert!(latex.contains("\\caption{Main result.}"));
        assert!(latex.contains("\\label{fig:main}"));
        assert!(latex.contains("\\end{figure}"));
    }

    #[test]
    fn render_figure_no_width() {
        let spec = FigureEmbedSpec {
            path: "img.png".into(),
            caption: None,
            label: None,
            width: None,
            placement: "h".into(),
        };
        let latex = render_figure_latex(&spec);
        assert!(latex.contains("\\begin{figure}[h]"));
        assert!(latex.contains("\\includegraphics{img.png}"));
        assert!(!latex.contains("\\caption"));
        assert!(!latex.contains("\\label"));
    }
}
