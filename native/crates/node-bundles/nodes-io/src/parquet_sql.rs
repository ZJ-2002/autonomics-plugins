//! DataFusion SQL node with Parquet File inputs and outputs.

use async_trait::async_trait;
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::io::{Read, Write};
use std::path::Path;

use dag_core::dag::{DagError, graph::PortOutputs};
use dag_core::node::{DagNode, NodeInput, NodePorts};
use dag_core::registry::{NodeCtx, NodeFactory};
use dag_core::value::{FileFingerprint, FileRef, PortType};
use datafusion::dataframe::DataFrameWriteOptions;
use datafusion::prelude::ParquetReadOptions;

pub const DATAFUSION_SQL_KIND: &str = "datafusion_sql";

#[derive(Debug, Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DataFusionSqlSpec {
    /// SQL query. The input Parquet file is registered as `table_name`.
    pub sql: String,
    #[serde(default = "default_table_name")]
    pub table_name: String,
    /// Absolute local, `file://`, or `vfs://` output Parquet path.
    pub output_path: String,
}

fn default_table_name() -> String {
    "input".into()
}

pub struct DataFusionSqlNode {
    ports: NodePorts,
    sql: String,
    table_name: String,
    output_path: String,
}

impl DataFusionSqlNode {
    pub fn new(sql: String, table_name: String, output_path: String) -> Self {
        Self {
            ports: port_layout(),
            sql,
            table_name,
            output_path,
        }
    }
}

fn port_layout() -> NodePorts {
    NodePorts::new()
        .add_input_port_of_type_with_label(None, PortType::File, "parquet")
        .add_output_port_of_type(None, PortType::File)
}

pub fn validate(spec: &DataFusionSqlSpec) -> Result<(), String> {
    if spec.sql.trim().is_empty() {
        return Err("sql cannot be empty".into());
    }
    if spec.table_name.is_empty()
        || !spec
            .table_name
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || character == '_')
        || spec
            .table_name
            .chars()
            .next()
            .is_none_or(|c| c.is_ascii_digit())
    {
        return Err("table_name must be a nonempty SQL identifier".into());
    }
    let output_path = spec
        .output_path
        .strip_prefix("vfs://")
        .or_else(|| spec.output_path.strip_prefix("file://"))
        .unwrap_or(&spec.output_path);
    if !output_path.starts_with('/') || output_path.contains('\0') {
        return Err("output_path must be an absolute local, file://, or vfs:// path".into());
    }
    if !spec.output_path.to_ascii_lowercase().ends_with(".parquet") {
        return Err("output_path must end in .parquet".into());
    }
    Ok(())
}

#[async_trait]
impl DagNode for DataFusionSqlNode {
    fn ports(&self) -> &NodePorts {
        &self.ports
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(Self {
            ports: self.ports.clone(),
            sql: self.sql.clone(),
            table_name: self.table_name.clone(),
            output_path: self.output_path.clone(),
        })
    }

    fn kind(&self) -> &'static str {
        DATAFUSION_SQL_KIND
    }

    fn as_any(&self) -> &dyn std::any::Any {
        self
    }

    async fn execute(
        &mut self,
        ctx: &NodeCtx,
        inputs: &[NodeInput],
        _reporter: &dag_core::dag::node_event::NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        if inputs.len() != 1 || inputs[0].port != 0 {
            return Err(DagError::Schedule(format!(
                "{DATAFUSION_SQL_KIND} requires exactly one Parquet input on port 0"
            )));
        }
        let input = &inputs[0];
        let file = input.file_value()?;
        if let Some(format) = file.format.as_deref()
            && !format.eq_ignore_ascii_case("parquet")
        {
            return Err(DagError::Schedule(
                "datafusion_sql requires a Parquet File input".into(),
            ));
        }
        let input_path = crate::file_to_dataframe::file_port_path(&file.path);
        let output_path = crate::file_decompress::normalize_and_source(ctx, &self.output_path);
        let local_output = output_path.strip_prefix("file://").unwrap_or(&output_path);
        if output_path.starts_with("vfs://") {
            crate::file_decompress::ensure_vfs_target(ctx, &output_path).await?;
        } else {
            crate::file_decompress::ensure_local_target(Path::new(local_output))?;
        }
        let session = ctx.session();
        session
            .register_parquet(&self.table_name, &input_path, ParquetReadOptions::default())
            .await
            .map_err(|error| {
                DagError::Schedule(format!(
                    "cannot register Parquet input `{input_path}`: {error}"
                ))
            })?;
        let result = session.sql(&self.sql).await.map_err(DagError::DataFusion)?;
        let staging = tempfile::tempdir().map_err(|error| DagError::Schedule(error.to_string()))?;
        let staged = staging.path().join("result.parquet");
        result
            .write_parquet(
                staged
                    .to_str()
                    .ok_or_else(|| DagError::Schedule("invalid staging path".into()))?,
                DataFrameWriteOptions::new().with_single_file_output(true),
                None::<datafusion::config::TableParquetOptions>,
            )
            .await
            .map_err(|error| {
                DagError::Schedule(format!(
                    "cannot write Parquet output `{output_path}`: {error}"
                ))
            })?;
        let size = std::fs::metadata(&staged)
            .map_err(|error| DagError::Schedule(error.to_string()))?
            .len();
        let mut reader =
            std::fs::File::open(&staged).map_err(|error| DagError::Schedule(error.to_string()))?;
        let mut digest = Sha256::new();
        let mut chunk = vec![0_u8; 1024 * 1024];
        loop {
            let count = reader
                .read(&mut chunk)
                .map_err(|error| DagError::Schedule(error.to_string()))?;
            if count == 0 {
                break;
            }
            digest.update(&chunk[..count]);
        }
        drop(reader);
        if output_path.starts_with("vfs://") {
            crate::file_decompress::upload_local(ctx, &output_path, &staged).await?;
        } else {
            crate::file_decompress::ensure_local_target(Path::new(local_output))?;
            let parent = Path::new(local_output)
                .parent()
                .ok_or_else(|| DagError::Schedule("output parent missing".into()))?;
            std::fs::create_dir_all(parent)
                .map_err(|error| DagError::Schedule(error.to_string()))?;
            let mut pending = tempfile::NamedTempFile::new_in(parent)
                .map_err(|error| DagError::Schedule(error.to_string()))?;
            let mut input = std::fs::File::open(&staged)
                .map_err(|error| DagError::Schedule(error.to_string()))?;
            std::io::copy(&mut input, &mut pending)
                .and_then(|_| pending.flush())
                .map_err(|error| DagError::Schedule(error.to_string()))?;
            pending
                .persist_noclobber(local_output)
                .map_err(|error| DagError::Schedule(error.to_string()))?;
        }
        let output_file = FileRef {
            path: output_path.clone(),
            format: Some("parquet".into()),
            fingerprint: Some(FileFingerprint {
                size,
                mtime_ns: 0,
                content_hash: Some(format!("sha256:{:x}", digest.finalize())),
                immutable_remote: false,
            }),
        };
        let mut outputs = PortOutputs::new();
        outputs.insert_file(0, output_file);
        Ok(outputs)
    }
}

pub struct DataFusionSqlNodeFactory {}

impl NodeFactory for DataFusionSqlNodeFactory {
    fn kind(&self) -> &'static str {
        DATAFUSION_SQL_KIND
    }

    fn desc(&self) -> &'static str {
        "Runs DataFusion SQL over an upstream Parquet File and writes one Parquet File."
    }

    fn doc(&self) -> &'static str {
        "The input File port must refer to Parquet and is registered with the configured \
        table name (`input` by default). The SQL result is materialized as a single-file \
        Parquet output. This node is for Parquet inputs only; it does not read the opaque \
        H5AD main path. Exactly one File is required on port 0; unknown controls \
        and relative scheme paths are rejected. Outputs require fresh destinations, \
        obey runtime VFS write permissions, and carry content SHA256 fingerprints."
    }

    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(DataFusionSqlSpec)
    }

    fn ports(&self) -> NodePorts {
        port_layout()
    }

    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec: DataFusionSqlSpec = serde_json::from_value(spec)?;
        validate(&spec).map_err(dag_core::registry::error::Error::Unknown)?;
        Ok(Box::new(DataFusionSqlNode::new(
            spec.sql,
            spec.table_name,
            spec.output_path,
        )))
    }

    fn ports_for_spec(
        &self,
        spec: serde_json::Value,
    ) -> dag_core::registry::error::Result<NodePorts> {
        let spec: DataFusionSqlSpec = serde_json::from_value(spec)?;
        validate(&spec).map_err(dag_core::registry::error::Error::Unknown)?;
        Ok(port_layout())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_non_identifier_table_names() {
        let spec = DataFusionSqlSpec {
            sql: "SELECT 1".into(),
            table_name: "bad-name".into(),
            output_path: "/out.parquet".into(),
        };
        assert!(validate(&spec).is_err());
    }
}
