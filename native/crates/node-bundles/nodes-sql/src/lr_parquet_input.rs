//! Typed Parquet input for audited LR scoring, without statistics-based value substitution.

use async_trait::async_trait;
use dag_core::dag::{DagError, graph::PortOutputs};
use dag_core::node::{DagNode, NodeInput, NodePorts};
use dag_core::registry::{NodeCtx, NodeFactory};
use dag_core::value::PortType;
use datafusion::prelude::{ParquetReadOptions, SessionConfig, SessionContext};
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;

pub const LR_PARQUET_INPUT_KIND: &str = "lr_parquet_input";

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
struct LrParquetInputSpec {
    format: String,
}

#[derive(Clone)]
struct LrParquetInputNode {
    ports: NodePorts,
}

fn ports() -> NodePorts {
    NodePorts::new()
        .add_input_port_of_type(None, PortType::File)
        .add_output_port(None)
}

fn session(context: &NodeCtx) -> SessionContext {
    SessionContext::new_with_config_rt(
        SessionConfig::new().with_collect_statistics(false),
        context.runtime_env.clone(),
    )
}

#[async_trait]
impl DagNode for LrParquetInputNode {
    fn ports(&self) -> &NodePorts {
        &self.ports
    }

    fn kind(&self) -> &'static str {
        LR_PARQUET_INPUT_KIND
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(self.clone())
    }

    fn as_any(&self) -> &dyn std::any::Any {
        self
    }

    async fn execute(
        &mut self,
        context: &NodeCtx,
        inputs: &[NodeInput],
        _reporter: &dag_core::dag::node_event::NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        if inputs.len() != 1 || inputs[0].port != 0 {
            return Err(DagError::NodeError {
                node_type: LR_PARQUET_INPUT_KIND.into(),
                msg: "one immutable Parquet file on port 0 is required".into(),
            });
        }
        let file = inputs[0].file_value()?;
        let frame = session(context)
            .read_parquet(&file.path, ParquetReadOptions::default())
            .await?;
        let mut outputs = PortOutputs::new();
        outputs.insert(0, frame);
        Ok(outputs)
    }
}

pub struct LrParquetInputNodeFactory;

impl NodeFactory for LrParquetInputNodeFactory {
    fn kind(&self) -> &'static str {
        LR_PARQUET_INPUT_KIND
    }

    fn desc(&self) -> &'static str {
        "Audited LR Parquet input without file-statistics constant-column substitution."
    }

    fn doc(&self) -> &'static str {
        "Parquet-only typed File-to-DataFrame adapter. Uses a fresh isolated session sharing \
        the runtime object stores and hard-disables listing file statistics: min=max and \
        null_count=0 cannot prove float columns are constant when Parquet excludes NaN from \
        min/max. Preserves source types, NULL and NaN; downstream LR rejects nonfinite \
        scientific inputs. No Float32 promotion, CSV inference, format conversion, global \
        memory limits, catalog authenticity, scientific eligibility or production certification."
    }

    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(LrParquetInputSpec)
    }

    fn ports(&self) -> NodePorts {
        ports()
    }

    fn build(
        &self,
        value: serde_json::Value,
        _context: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec: LrParquetInputSpec = serde_json::from_value(value)?;
        if spec.format != "parquet" {
            return Err("lr_parquet_input accepts only the frozen parquet format".into());
        }
        Ok(Box::new(LrParquetInputNode { ports: ports() }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn isolated_reader_disables_file_statistics() {
        let context = NodeCtx::new(SessionContext::new().runtime_env(), None);
        assert!(!session(&context).state().config().collect_statistics());
    }

    #[test]
    fn reader_rejects_unknown_controls() {
        assert!(
            serde_json::from_value::<LrParquetInputSpec>(
                serde_json::json!({"format":"parquet", "collect_statistics":true})
            )
            .is_err()
        );
    }

    #[test]
    fn reader_rejects_non_parquet_formats() {
        let context = NodeCtx::new(SessionContext::new().runtime_env(), None);
        assert!(
            LrParquetInputNodeFactory
                .build(serde_json::json!({"format":"csv"}), context)
                .is_err()
        );
    }
}
