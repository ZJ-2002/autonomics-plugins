//! DataFrame transpose and unpivot transform nodes.

use arrow_array::{Array, ArrayRef, Float64Array, RecordBatch, StringArray, UInt64Array};
use arrow_cast::{CastOptions, cast_with_options};
use arrow_schema::{DataType, Field, Schema};
use arrow_select::{concat::concat, interleave::interleave, take::take};
use async_trait::async_trait;
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;
use std::collections::HashSet;
use std::sync::Arc;

use dag_core::dag::{DagError, graph::PortOutputs};
use dag_core::node::{DagNode, NodeInput, NodePorts};
use dag_core::registry::{NodeCtx, NodeFactory};

pub const TABLE_TRANSPOSE_KIND: &str = "table_transpose";
pub const MELT_UNPIVOT_KIND: &str = "melt_unpivot";

fn node_error(kind: &'static str, message: impl Into<String>) -> DagError {
    DagError::NodeError {
        node_type: kind.into(),
        msg: message.into(),
    }
}

fn strict_cast(
    array: &ArrayRef,
    datatype: &DataType,
) -> Result<ArrayRef, arrow_schema::ArrowError> {
    cast_with_options(
        array,
        datatype,
        &CastOptions {
            safe: false,
            ..Default::default()
        },
    )
}

pub(crate) fn utf8_values(array: &ArrayRef) -> Result<Vec<Option<String>>, DagError> {
    let array = strict_cast(array, &DataType::Utf8)
        .map_err(|error| DagError::Schedule(format!("cannot cast identifier to Utf8: {error}")))?;
    let array = array
        .as_any()
        .downcast_ref::<StringArray>()
        .ok_or_else(|| DagError::Schedule("identifier cast did not produce Utf8".into()))?;
    Ok((0..array.len())
        .map(|index| {
            if array.is_null(index) {
                None
            } else {
                Some(array.value(index).to_string())
            }
        })
        .collect())
}

pub(crate) fn float_values(array: &ArrayRef) -> Result<Vec<Option<f64>>, DagError> {
    let array = strict_cast(array, &DataType::Float64).map_err(|error| {
        DagError::Schedule(format!("cannot cast matrix value to Float64: {error}"))
    })?;
    let array = array
        .as_any()
        .downcast_ref::<Float64Array>()
        .ok_or_else(|| DagError::Schedule("value cast did not produce Float64".into()))?;
    Ok((0..array.len())
        .map(|index| {
            if array.is_null(index) {
                None
            } else {
                Some(array.value(index))
            }
        })
        .collect())
}

fn canonical_names(names: &[String]) -> bool {
    names
        .iter()
        .all(|name| !name.is_empty() && name.trim() == name)
        && names.iter().collect::<HashSet<_>>().len() == names.len()
}

fn compatible_values(kind: &'static str, arrays: Vec<ArrayRef>) -> Result<Vec<ArrayRef>, DagError> {
    let first = arrays
        .first()
        .ok_or_else(|| node_error(kind, "no value columns selected"))?;
    let target = if arrays
        .iter()
        .all(|array| array.data_type() == first.data_type())
    {
        first.data_type().clone()
    } else if arrays.iter().all(|array| array.data_type().is_numeric()) {
        DataType::Float64
    } else {
        DataType::Utf8
    };
    arrays
        .into_iter()
        .map(|array| {
            if array.data_type() == &target {
                return Ok(array);
            }
            let converted = strict_cast(&array, &target).map_err(|error| {
                node_error(kind, format!("cannot convert selected value: {error}"))
            })?;
            if target == DataType::Float64 {
                let restored = strict_cast(&converted, array.data_type()).map_err(|error| {
                    node_error(kind, format!("numeric promotion must be lossless: {error}"))
                })?;
                if restored.as_ref() != array.as_ref() {
                    return Err(node_error(kind, "numeric promotion must be lossless"));
                }
            }
            Ok(converted)
        })
        .collect()
}

fn input_frame<'input>(
    kind: &'static str,
    inputs: &'input [NodeInput],
) -> Result<&'input datafusion::prelude::DataFrame, DagError> {
    if inputs.len() != 1 {
        return Err(node_error(
            kind,
            "exactly one upstream DataFrame is required",
        ));
    }
    let frame = inputs[0].dataframe()?;
    let names = frame
        .schema()
        .fields()
        .iter()
        .map(|field| field.name().clone())
        .collect::<Vec<_>>();
    if names.iter().collect::<HashSet<_>>().len() != names.len() {
        return Err(node_error(
            kind,
            "duplicate input column names are forbidden",
        ));
    }
    Ok(frame)
}

fn port_layout() -> NodePorts {
    NodePorts::new()
        .add_input_port(None)
        .add_output_port(None)
        .add_output_port(None)
}

#[derive(Debug, Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct TableTransposeSpec {
    pub id_column: String,
    #[serde(default)]
    pub keep_columns: Vec<String>,
    #[serde(default)]
    pub row_order: Vec<String>,
    #[serde(default = "default_true")]
    pub streaming: bool,
    #[serde(default = "default_chunk_size")]
    pub chunk_size: usize,
}

fn default_true() -> bool {
    true
}
fn default_chunk_size() -> usize {
    1024
}

impl TableTransposeSpec {
    fn validate(&self) -> Result<(), DagError> {
        if !canonical_names(&[self.id_column.clone()])
            || !canonical_names(&self.keep_columns)
            || self.keep_columns.contains(&self.id_column)
        {
            return Err(node_error(
                TABLE_TRANSPOSE_KIND,
                "id_column and keep_columns must be canonical and distinct",
            ));
        }
        if self.chunk_size == 0 {
            return Err(node_error(
                TABLE_TRANSPOSE_KIND,
                "chunk_size must be greater than zero",
            ));
        }
        if self.row_order.iter().any(|value| value.is_empty()) {
            return Err(node_error(
                TABLE_TRANSPOSE_KIND,
                "row_order cannot contain an empty identity",
            ));
        }
        if self.row_order.iter().collect::<HashSet<_>>().len() != self.row_order.len() {
            return Err(node_error(
                TABLE_TRANSPOSE_KIND,
                "duplicate row_order identities are forbidden",
            ));
        }
        Ok(())
    }
}

#[derive(Clone)]
pub struct TableTransposeNode {
    ports: NodePorts,
    spec: TableTransposeSpec,
}

impl TableTransposeNode {
    pub fn new(id_column: String, keep_columns: Vec<String>) -> Self {
        Self::new_with_options(id_column, keep_columns, true, 1024)
    }

    pub fn new_with_options(
        id_column: String,
        keep_columns: Vec<String>,
        streaming: bool,
        chunk_size: usize,
    ) -> Self {
        Self {
            ports: port_layout(),
            spec: TableTransposeSpec {
                id_column,
                keep_columns,
                row_order: Vec::new(),
                streaming,
                chunk_size,
            },
        }
    }
}

#[async_trait]
impl DagNode for TableTransposeNode {
    fn ports(&self) -> &NodePorts {
        &self.ports
    }
    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(self.clone())
    }
    fn kind(&self) -> &'static str {
        TABLE_TRANSPOSE_KIND
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
        self.spec.validate()?;
        let frame = input_frame(TABLE_TRANSPOSE_KIND, inputs)?;
        let fields = frame.schema().fields();
        let (id_index, _) = fields.find(&self.spec.id_column).ok_or_else(|| {
            node_error(
                TABLE_TRANSPOSE_KIND,
                format!("id column `{}` is absent", self.spec.id_column),
            )
        })?;
        for name in &self.spec.keep_columns {
            if fields.find(name).is_none() {
                return Err(node_error(
                    TABLE_TRANSPOSE_KIND,
                    format!("keep column `{name}` is absent"),
                ));
            }
        }
        let value_indexes = (0..fields.len())
            .filter(|index| {
                *index != id_index && !self.spec.keep_columns.contains(fields[*index].name())
            })
            .collect::<Vec<_>>();
        if value_indexes.is_empty() {
            return Err(node_error(
                TABLE_TRANSPOSE_KIND,
                "input has no value columns to transpose",
            ));
        }
        let batches = frame.clone().collect().await?;
        let mut row_ids = Vec::new();
        for batch in &batches {
            row_ids.extend(utf8_values(batch.column(id_index))?);
        }
        if row_ids.is_empty() {
            return Err(node_error(TABLE_TRANSPOSE_KIND, "input has no rows"));
        }
        let mut seen = HashSet::new();
        let mut output_names = Vec::new();
        for identity in row_ids {
            let identity = identity.ok_or_else(|| {
                node_error(TABLE_TRANSPOSE_KIND, "missing transpose row identity")
            })?;
            if identity.is_empty() {
                return Err(node_error(
                    TABLE_TRANSPOSE_KIND,
                    "empty transpose row identity",
                ));
            }
            if identity == "column" {
                return Err(node_error(
                    TABLE_TRANSPOSE_KIND,
                    "transpose row identity collides with reserved column header",
                ));
            }
            if !seen.insert(identity.clone()) {
                return Err(node_error(
                    TABLE_TRANSPOSE_KIND,
                    "duplicate transpose row identity",
                ));
            }
            output_names.push(identity);
        }
        let row_indexes = if self.spec.row_order.is_empty() {
            (0..output_names.len()).collect::<Vec<_>>()
        } else {
            if self.spec.row_order.len() != output_names.len() {
                return Err(node_error(
                    TABLE_TRANSPOSE_KIND,
                    "row_order must cover the complete row identity set",
                ));
            }
            let positions = output_names
                .iter()
                .enumerate()
                .map(|(index, name)| (name, index))
                .collect::<std::collections::HashMap<_, _>>();
            let indexes = self
                .spec
                .row_order
                .iter()
                .map(|name| {
                    positions.get(name).copied().ok_or_else(|| {
                        node_error(
                            TABLE_TRANSPOSE_KIND,
                            "row_order contains an unknown row identity",
                        )
                    })
                })
                .collect::<Result<Vec<_>, _>>()?;
            output_names = self.spec.row_order.clone();
            indexes
        };
        let arrays = value_indexes
            .iter()
            .map(|index| {
                let pieces = batches
                    .iter()
                    .map(|batch| batch.column(*index).as_ref())
                    .collect::<Vec<_>>();
                concat(&pieces).map_err(|error| {
                    node_error(
                        TABLE_TRANSPOSE_KIND,
                        format!("cannot assemble input values: {error}"),
                    )
                })
            })
            .collect::<Result<Vec<_>, _>>()?;
        let arrays = compatible_values(TABLE_TRANSPOSE_KIND, arrays)?;
        let datatype = arrays[0].data_type().clone();
        let references = arrays
            .iter()
            .map(|array| array.as_ref())
            .collect::<Vec<_>>();
        let mut output_fields = vec![Field::new("column", DataType::Utf8, true)];
        output_fields.extend(
            output_names
                .iter()
                .map(|name| Field::new(name, datatype.clone(), true)),
        );
        let schema = Arc::new(Schema::new(output_fields));
        let chunk_size = if self.spec.streaming {
            self.spec.chunk_size
        } else {
            value_indexes.len()
        };
        let mut output: Option<datafusion::prelude::DataFrame> = None;
        for (chunk_index, chunk) in value_indexes.chunks(chunk_size).enumerate() {
            let start = chunk_index * chunk_size;
            let mut columns: Vec<ArrayRef> = vec![Arc::new(StringArray::from(
                chunk
                    .iter()
                    .map(|index| fields[*index].name().clone())
                    .collect::<Vec<_>>(),
            ))];
            for row in &row_indexes {
                let coordinates = (start..start + chunk.len())
                    .map(|index| (index, *row))
                    .collect::<Vec<_>>();
                columns.push(interleave(&references, &coordinates).map_err(|error| {
                    node_error(
                        TABLE_TRANSPOSE_KIND,
                        format!("cannot transpose values: {error}"),
                    )
                })?);
            }
            let batch = RecordBatch::try_new(schema.clone(), columns).map_err(|error| {
                node_error(
                    TABLE_TRANSPOSE_KIND,
                    format!("cannot transpose table: {error}"),
                )
            })?;
            let next = ctx.session().read_batch(batch)?;
            output = Some(match output {
                Some(previous) => previous.union(next)?,
                None => next,
            });
        }
        let mut outputs = PortOutputs::new();
        outputs.insert(
            0,
            output.ok_or_else(|| {
                node_error(
                    TABLE_TRANSPOSE_KIND,
                    "input has no value columns to transpose",
                )
            })?,
        );
        outputs.insert(1, frame.clone());
        Ok(outputs)
    }
}

pub struct TableTransposeNodeFactory;
impl NodeFactory for TableTransposeNodeFactory {
    fn kind(&self) -> &'static str {
        TABLE_TRANSPOSE_KIND
    }
    fn desc(&self) -> &'static str {
        "Transposes a DataFrame without renaming row identities or misassigning row metadata."
    }
    fn doc(&self) -> &'static str {
        "Port0 transposes non-id, non-keep columns into rows named by the column field. Exact nonmissing unique id values become headers; reserved column collisions fail. Explicit row_order freezes the complete header axis and reindexes values by identity; unknown, missing or duplicate entries fail. Without it header order follows the gathered input, which may be nondeterministic for parallel scans. Port1 retains the complete original typed DataFrame, including keep_columns metadata at its original row identity, rather than attaching it to unrelated transposed rows. Homogeneous Arrow value types are preserved; mixed numeric values require lossless Float64 promotion, other mixed values use strict Utf8 conversion. Input is fully collected; streaming only bounds output RecordBatch rows, not input memory. Output row order is not guaranteed after downstream materialization. Unknown parameters and invalid/duplicate configured names fail. This is an engineering reshape, not a statistical or scientific qualification."
    }
    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(TableTransposeSpec)
    }
    fn ports(&self) -> NodePorts {
        port_layout()
    }
    fn build(
        &self,
        spec: serde_json::Value,
        _ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec: TableTransposeSpec = serde_json::from_value(spec)?;
        spec.validate()
            .map_err(|error| dag_core::registry::error::Error::Unknown(error.to_string()))?;
        Ok(Box::new(TableTransposeNode {
            ports: port_layout(),
            spec,
        }))
    }
}

#[derive(Debug, Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct MeltUnpivotSpec {
    pub id_cols: Vec<String>,
    #[serde(default = "default_var_name")]
    pub var_name: String,
    #[serde(default = "default_value_name")]
    pub value_name: String,
    #[serde(default)]
    pub column_filter_regex: Option<String>,
}

fn default_var_name() -> String {
    "variable".into()
}
fn default_value_name() -> String {
    "value".into()
}

impl MeltUnpivotSpec {
    fn validate(&self) -> Result<(), DagError> {
        let mut names = self.id_cols.clone();
        names.push(self.var_name.clone());
        names.push(self.value_name.clone());
        if self.id_cols.is_empty() || !canonical_names(&names) {
            return Err(node_error(
                MELT_UNPIVOT_KIND,
                "id_cols, var_name and value_name must be canonical and distinct",
            ));
        }
        if let Some(pattern) = &self.column_filter_regex {
            regex::Regex::new(pattern).map_err(|error| {
                node_error(MELT_UNPIVOT_KIND, format!("invalid regex: {error}"))
            })?;
        }
        Ok(())
    }
}

#[derive(Clone)]
pub struct MeltUnpivotNode {
    ports: NodePorts,
    spec: MeltUnpivotSpec,
}
impl MeltUnpivotNode {
    pub fn new(spec: MeltUnpivotSpec) -> Self {
        Self {
            ports: port_layout(),
            spec,
        }
    }
}

#[async_trait]
impl DagNode for MeltUnpivotNode {
    fn ports(&self) -> &NodePorts {
        &self.ports
    }
    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(self.clone())
    }
    fn kind(&self) -> &'static str {
        MELT_UNPIVOT_KIND
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
        self.spec.validate()?;
        let frame = input_frame(MELT_UNPIVOT_KIND, inputs)?;
        let fields = frame.schema().fields();
        let id_indexes = self
            .spec
            .id_cols
            .iter()
            .map(|name| {
                fields.find(name).map(|(index, _)| index).ok_or_else(|| {
                    node_error(MELT_UNPIVOT_KIND, format!("id column `{name}` is absent"))
                })
            })
            .collect::<Result<Vec<_>, _>>()?;
        let filter = self
            .spec
            .column_filter_regex
            .as_deref()
            .map(regex::Regex::new)
            .transpose()
            .map_err(|error| node_error(MELT_UNPIVOT_KIND, format!("invalid regex: {error}")))?;
        let value_indexes = (0..fields.len())
            .filter(|index| {
                let name = fields[*index].name();
                !self.spec.id_cols.contains(name)
                    && filter.as_ref().is_none_or(|pattern| pattern.is_match(name))
            })
            .collect::<Vec<_>>();
        if value_indexes.is_empty() {
            return Err(node_error(MELT_UNPIVOT_KIND, "no value columns selected"));
        }
        let batches = frame.clone().collect().await?;
        let mut output: Option<datafusion::prelude::DataFrame> = None;
        let source_batches = if batches.is_empty() {
            vec![RecordBatch::new_empty(frame.schema().inner().clone())]
        } else {
            batches
        };
        for batch in source_batches {
            let values = compatible_values(
                MELT_UNPIVOT_KIND,
                value_indexes
                    .iter()
                    .map(|index| batch.column(*index).clone())
                    .collect(),
            )?;
            let rows = (0..batch.num_rows())
                .flat_map(|row| std::iter::repeat_n(row as u64, value_indexes.len()))
                .collect::<Vec<_>>();
            let indices = UInt64Array::from(rows);
            let mut output_fields = id_indexes
                .iter()
                .map(|index| fields[*index].as_ref().clone())
                .collect::<Vec<_>>();
            output_fields.push(Field::new(&self.spec.var_name, DataType::Utf8, true));
            output_fields.push(Field::new(
                &self.spec.value_name,
                values[0].data_type().clone(),
                true,
            ));
            let mut columns = id_indexes
                .iter()
                .map(|index| {
                    take(batch.column(*index).as_ref(), &indices, None).map_err(|error| {
                        node_error(
                            MELT_UNPIVOT_KIND,
                            format!("cannot preserve id values: {error}"),
                        )
                    })
                })
                .collect::<Result<Vec<_>, _>>()?;
            columns.push(Arc::new(StringArray::from(
                (0..batch.num_rows())
                    .flat_map(|_| {
                        value_indexes
                            .iter()
                            .map(|index| fields[*index].name().clone())
                    })
                    .collect::<Vec<_>>(),
            )));
            let references = values
                .iter()
                .map(|array| array.as_ref())
                .collect::<Vec<_>>();
            let coordinates = (0..batch.num_rows())
                .flat_map(|row| (0..values.len()).map(move |column| (column, row)))
                .collect::<Vec<_>>();
            columns.push(interleave(&references, &coordinates).map_err(|error| {
                node_error(MELT_UNPIVOT_KIND, format!("cannot unpivot values: {error}"))
            })?);
            let next = ctx.session().read_batch(
                RecordBatch::try_new(Arc::new(Schema::new(output_fields)), columns).map_err(
                    |error| node_error(MELT_UNPIVOT_KIND, format!("cannot unpivot table: {error}")),
                )?,
            )?;
            output = Some(match output {
                Some(previous) => previous.union(next)?,
                None => next,
            });
        }
        let mut outputs = PortOutputs::new();
        outputs.insert(
            0,
            output.ok_or_else(|| {
                node_error(MELT_UNPIVOT_KIND, "cannot construct empty unpivot output")
            })?,
        );
        outputs.insert(1, frame.clone());
        Ok(outputs)
    }
}

pub struct MeltUnpivotNodeFactory;
impl NodeFactory for MeltUnpivotNodeFactory {
    fn kind(&self) -> &'static str {
        MELT_UNPIVOT_KIND
    }
    fn desc(&self) -> &'static str {
        "Unpivots selected columns while preserving identifier types, values and complete source lineage."
    }
    fn doc(&self) -> &'static str {
        "Port0 melts non-id columns selected by an optional Rust regex into id/variable/value rows. Original id Arrow types and null masks are preserved, including numeric identifiers; homogeneous value types are retained. Mixed numeric values require exact roundtrip-safe Float64 promotion; mixed other values use strict Utf8 conversion, never failed-cast NULL. Port1 retains the original full typed DataFrame. Empty rows retain the selected schema, but missing id columns or duplicate/unknown configuration fail even on empty input. Values are converted once per batch/column rather than recast per cell. Physical output row order is not a contract; compare complete row/value multiplicities. This is engineering reshaping, not statistical or scientific qualification."
    }
    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(MeltUnpivotSpec)
    }
    fn ports(&self) -> NodePorts {
        port_layout()
    }
    fn build(
        &self,
        spec: serde_json::Value,
        _ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec: MeltUnpivotSpec = serde_json::from_value(spec)?;
        spec.validate()
            .map_err(|error| dag_core::registry::error::Error::Unknown(error.to_string()))?;
        Ok(Box::new(MeltUnpivotNode::new(spec)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use arrow_array::Int64Array;
    use datafusion::prelude::SessionContext;

    fn ctx() -> NodeCtx {
        NodeCtx::new(SessionContext::new().runtime_env(), None)
    }

    fn wide_frame() -> datafusion::prelude::DataFrame {
        let session = SessionContext::new();
        let schema = Arc::new(Schema::new(vec![
            Field::new("gene", DataType::Utf8, false),
            Field::new("pathway", DataType::Utf8, false),
            Field::new("cell_1", DataType::Int64, false),
            Field::new("cell_2", DataType::Int64, false),
        ]));
        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(StringArray::from(vec!["GENE1", "GENE2"])),
                Arc::new(StringArray::from(vec!["immune", "metabolic"])),
                Arc::new(Int64Array::from(vec![1, 3])),
                Arc::new(Int64Array::from(vec![2, 4])),
            ],
        )
        .unwrap();
        session.read_batch(batch).unwrap()
    }

    #[tokio::test]
    async fn transposes_matrix_and_preserves_source_metadata() {
        let mut node = TableTransposeNode::new("gene".into(), vec!["pathway".into()]);
        let outputs = node
            .execute(
                &ctx(),
                &[NodeInput::new_dataframe(0, wide_frame())],
                &dag_core::dag::node_event::NodeReporter::noop(),
            )
            .await
            .unwrap();
        let schema = outputs.dataframe(0).unwrap().schema();
        let names: Vec<_> = schema.fields().iter().map(|f| f.name().as_str()).collect();
        assert_eq!(names, ["column", "GENE1", "GENE2"]);
        assert_eq!(
            outputs.dataframe(0).unwrap().clone().count().await.unwrap(),
            2
        );
    }

    #[tokio::test]
    async fn transposes_in_chunked_output_mode() {
        let mut node =
            TableTransposeNode::new_with_options("gene".into(), vec!["pathway".into()], true, 1);
        let outputs = node
            .execute(
                &ctx(),
                &[NodeInput::new_dataframe(0, wide_frame())],
                &dag_core::dag::node_event::NodeReporter::noop(),
            )
            .await
            .unwrap();
        assert_eq!(
            outputs.dataframe(0).unwrap().clone().count().await.unwrap(),
            2
        );
    }

    #[tokio::test]
    async fn unpivots_with_regex_filter() {
        let mut node = MeltUnpivotNode::new(MeltUnpivotSpec {
            id_cols: vec!["gene".into()],
            var_name: "cell".into(),
            value_name: "count".into(),
            column_filter_regex: Some("^cell_".into()),
        });
        let outputs = node
            .execute(
                &ctx(),
                &[NodeInput::new_dataframe(0, wide_frame())],
                &dag_core::dag::node_event::NodeReporter::noop(),
            )
            .await
            .unwrap();
        assert_eq!(
            outputs.dataframe(0).unwrap().clone().count().await.unwrap(),
            4
        );
    }
}
