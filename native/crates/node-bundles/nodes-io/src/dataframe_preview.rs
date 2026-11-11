//! Bounded table preview executed by the configured typed worker, not by the
//! coordinator's remote-only Arrow provider. The result is a small Channel.
use std::io::{self, Write};

use async_trait::async_trait;
use dag_core::{
    dag::{DagError, graph::PortOutputs, node_event::NodeReporter},
    node::{DagNode, NodeInput, NodePorts},
    registry::{NodeCtx, NodeFactory},
    value::{ChannelValue, NodeValue, PortType},
};
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;
use serde_json::{Value, json};

const MAX_ROWS: usize = 50;
const MAX_BYTES: usize = 256 * 1024;
const MAX_COLUMNS: usize = 256;

#[derive(Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DataFramePreviewSpec {
    #[serde(default)]
    pub offset: usize,
    pub limit: usize,
}

#[derive(Clone)]
pub struct DataFramePreviewNode {
    ports: NodePorts,
    spec: DataFramePreviewSpec,
}

fn ports() -> NodePorts {
    NodePorts::new()
        .add_input_port_of_type_with_label(None, PortType::DataFrame, "table")
        .add_output_port_of_type(None, PortType::Channel)
}

struct BoundedJson(Vec<u8>);
impl Write for BoundedJson {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if self.0.len().saturating_add(bytes.len()) > MAX_BYTES {
            return Err(io::Error::other(
                "preview exceeds 256 KiB; select fewer columns or rows",
            ));
        }
        self.0.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[async_trait]
impl DagNode for DataFramePreviewNode {
    fn ports(&self) -> &NodePorts {
        &self.ports
    }
    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(self.clone())
    }
    fn kind(&self) -> &'static str {
        "dataframe_preview"
    }
    fn as_any(&self) -> &dyn std::any::Any {
        self
    }

    async fn execute(
        &mut self,
        _ctx: &NodeCtx,
        inputs: &[NodeInput],
        _reporter: &NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        if inputs.len() != 1 || inputs[0].port != 0 || !(1..=MAX_ROWS).contains(&self.spec.limit) {
            return Err(DagError::Schedule(
                "preview requires one table and 1..=50 rows".into(),
            ));
        }
        let df = inputs[0].data.as_dataframe()?;
        let columns: Vec<String> = df
            .schema()
            .fields()
            .iter()
            .map(|f| f.name().clone())
            .collect();
        if columns.len() > MAX_COLUMNS
            || columns
                .iter()
                .collect::<std::collections::BTreeSet<_>>()
                .len()
                != columns.len()
        {
            return Err(DagError::Schedule("preview requires at most 256 uniquely named columns; project or rename columns first".into()));
        }
        let total = df.clone().count().await?;
        let batches = df
            .clone()
            .limit(self.spec.offset, Some(self.spec.limit))?
            .collect()
            .await?;
        let returned: usize = batches.iter().map(|b| b.num_rows()).sum();
        let mut writer = arrow::json::ArrayWriter::new(BoundedJson(Vec::new()));
        for batch in &batches {
            writer
                .write(batch)
                .map_err(|e| DagError::Schedule(e.to_string()))?;
        }
        writer
            .finish()
            .map_err(|e| DagError::Schedule(e.to_string()))?;
        let body = writer.into_inner().0;
        let objects: Vec<Value> = if returned == 0 {
            Vec::new()
        } else {
            serde_json::from_slice(&body).map_err(|e| DagError::Schedule(e.to_string()))?
        };
        let rows: Vec<Vec<Value>> = objects
            .iter()
            .map(|obj| {
                columns
                    .iter()
                    .map(|key| obj.get(key).cloned().unwrap_or(Value::Null))
                    .collect()
            })
            .collect();
        let fields: Vec<Value> = df
            .schema()
            .fields()
            .iter()
            .map(|f| json!({"name": f.name(), "type": f.data_type().to_string()}))
            .collect();
        let page = json!({"type": "dataframe", "total_rows": total, "returned_rows": returned,
            "offset": self.spec.offset, "fields": fields, "columns": columns.len(),
            "data": {"columns": columns, "rows": rows}, "max_bytes": MAX_BYTES});
        let encoded = serde_json::to_vec(&page).map_err(|e| DagError::Schedule(e.to_string()))?;
        if encoded.len() > MAX_BYTES {
            return Err(DagError::Schedule(
                "preview metadata exceeds 256 KiB; project fewer columns".into(),
            ));
        }
        let mut outputs = PortOutputs::new();
        outputs.insert(0, NodeValue::Channel(ChannelValue { items: vec![page] }));
        Ok(outputs)
    }
}

pub struct DataFramePreviewNodeFactory;
impl NodeFactory for DataFramePreviewNodeFactory {
    fn kind(&self) -> &'static str {
        "dataframe_preview"
    }
    fn desc(&self) -> &'static str {
        "Bounded table preview on the configured execution backend."
    }
    fn doc(&self) -> &'static str {
        "Returns a Channel with full row count and a page of at most 50 rows / 256 KiB. Does not modify the input table. Duplicate or over 256 columns require explicit projection first."
    }
    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(DataFramePreviewSpec)
    }
    fn ports(&self) -> NodePorts {
        ports()
    }
    fn build(
        &self,
        spec: Value,
        _ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec: DataFramePreviewSpec = serde_json::from_value(spec)?;
        if !(1..=MAX_ROWS).contains(&spec.limit) || spec.offset.checked_add(spec.limit).is_none() {
            return Err("preview limit must be 1..=50 and offset must not overflow".into());
        }
        Ok(Box::new(DataFramePreviewNode {
            ports: ports(),
            spec,
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use arrow_array::{Int64Array, RecordBatch, StringArray};
    use datafusion::prelude::SessionContext;
    use std::sync::Arc;

    async fn preview(offset: usize, limit: usize) -> Value {
        let session = SessionContext::new();
        let frame = session
            .read_batch(
                RecordBatch::try_from_iter(vec![
                    (
                        "id",
                        Arc::new(Int64Array::from(vec![1, 2, 3])) as arrow_array::ArrayRef,
                    ),
                    (
                        "text",
                        Arc::new(StringArray::from(vec![Some("one"), None, Some("三")]))
                            as arrow_array::ArrayRef,
                    ),
                ])
                .unwrap(),
            )
            .unwrap();
        let ctx = NodeCtx::new(session.runtime_env(), None);
        let mut node = DataFramePreviewNodeFactory
            .build(json!({"offset":offset,"limit":limit}), ctx.clone())
            .unwrap();
        let output = node
            .execute(
                &ctx,
                &[NodeInput {
                    port: 0,
                    data: NodeValue::DataFrame(frame),
                }],
                &NodeReporter::noop(),
            )
            .await
            .unwrap();
        let NodeValue::Channel(channel) = output.get(&0).unwrap() else {
            panic!("expected channel")
        };
        channel.items[0].clone()
    }

    #[tokio::test]
    async fn page_count_null_and_utf8_are_preserved() {
        let value = preview(1, 2).await;
        assert_eq!(value["total_rows"], 3);
        assert_eq!(value["returned_rows"], 2);
        assert_eq!(value["data"]["rows"], json!([[2, null], [3, "三"]]));
    }

    #[tokio::test]
    async fn empty_page_retains_full_count_and_columns() {
        let value = preview(100, 2).await;
        assert_eq!(value["returned_rows"], 0);
        assert_eq!(value["total_rows"], 3);
        assert_eq!(value["data"]["columns"], json!(["id", "text"]));
    }

    #[test]
    fn factory_rejects_unbounded_or_overflowing_page() {
        let ctx = NodeCtx::new(SessionContext::new().runtime_env(), None);
        for spec in [
            json!({"limit":0}),
            json!({"limit":51}),
            json!({"offset":usize::MAX,"limit":1}),
        ] {
            assert!(
                DataFramePreviewNodeFactory
                    .build(spec, ctx.clone())
                    .is_err()
            );
        }
    }

    #[test]
    fn byte_budget_refuses_whole_write_without_partial_success() {
        let mut sink = BoundedJson(vec![0; MAX_BYTES - 2]);
        assert!(sink.write_all(b"abcd").is_err());
        assert_eq!(sink.0.len(), MAX_BYTES - 2);
    }
}
