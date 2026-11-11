//! `table_from_df` node — converts an upstream DataFrame into a LaTeX tabular string.
//!
//! This node reads the schema and data rows from the input DataFrame and
//! produces a single-row DataFrame with a `latex` column containing the
//! rendered LaTeX `tabular` environment (with booktabs rules).

use std::sync::Arc;

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
pub struct TableFromDfSpec {
    /// Table format: `booktabs` (default) or `plain`.
    #[serde(default = "default_format")]
    pub format: String,

    /// Optional plain-text caption for the table; LaTeX commands are escaped.
    pub caption: Option<String>,

    /// Optional `\label{...}` for cross-referencing.
    pub label: Option<String>,

    /// Maximum number of data rows to include (0 or omitted = all).
    pub max_rows: Option<usize>,
}

fn default_format() -> String {
    "booktabs".into()
}

// ---------------------------------------------------------------------------
// Node
// ---------------------------------------------------------------------------

#[derive(Clone)]
pub struct TableFromDfNode {
    meta: NodePorts,
    format: String,
    caption: Option<String>,
    label: Option<String>,
    max_rows: Option<usize>,
}

fn port_layout() -> NodePorts {
    NodePorts::new()
        .add_input_port(None) // DataFrame input
        .add_output_port(None) // String output (latex column)
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

pub struct TableFromDfFactory {}

impl NodeFactory for TableFromDfFactory {
    fn kind(&self) -> &'static str {
        "table_from_df"
    }

    fn desc(&self) -> &'static str {
        "Convert a DataFrame to a LaTeX tabular environment string."
    }

    fn doc(&self) -> &'static str {
        "Takes a DataFrame as input and produces a single-row DataFrame with a 'latex' column \
         containing the rendered LaTeX tabular environment. Uses booktabs by default \
         (\\toprule, \\midrule, \\bottomrule). The header row comes from the DataFrame column \
         names. Renders Utf8/LargeUtf8/Utf8View, Boolean, Int8-64, UInt8-64, Float32/64, \
         Date32/64, Time32/64 and Timestamp columns; Date64 must represent exact days, \
         time values must lie within one day, and timezone metadata must be valid. \
         Nulls become empty cells and any other \
         column type is rejected with an error instead of rendering blank."
    }

    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(TableFromDfSpec)
    }

    fn ports(&self) -> NodePorts {
        port_layout()
    }

    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: dag_core::registry::NodeCtx,
    ) -> Result<Box<dyn DagNode>, dag_core::registry::error::Error> {
        let s: TableFromDfSpec = serde_json::from_value(spec)?;
        if !matches!(s.format.as_str(), "plain" | "booktabs") {
            return Err(dag_core::registry::error::Error::Unknown(
                "table format must be plain or booktabs".into(),
            ));
        }
        if s.label
            .as_deref()
            .is_some_and(|label| !valid_latex_label(label))
        {
            return Err(dag_core::registry::error::Error::Unknown(
                "table label must be a non-empty ASCII alphanumeric identifier with :._-".into(),
            ));
        }
        Ok(Box::new(TableFromDfNode {
            meta: port_layout(),
            format: s.format,
            caption: s.caption,
            label: s.label,
            max_rows: s.max_rows.filter(|maximum| *maximum > 0),
        }))
    }
}

// ---------------------------------------------------------------------------
// DagNode impl
// ---------------------------------------------------------------------------

#[async_trait]
impl DagNode for TableFromDfNode {
    fn ports(&self) -> &NodePorts {
        &self.meta
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(self.clone())
    }

    fn kind(&self) -> &'static str {
        "table_from_df"
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
        if inputs.len() != 1 {
            return Err(DagError::NodeError {
                node_type: "table_from_df".into(),
                msg: "exactly one input DataFrame is required".into(),
            });
        }

        let df = inputs[0].dataframe()?;
        for field in df.schema().fields() {
            if !supported_cell_type(field.data_type()) {
                return Err(DagError::NodeError {
                    node_type: "table_from_df".into(),
                    msg: format!(
                        "column `{}` has unsupported type {} for LaTeX table rendering",
                        field.name(),
                        field.data_type()
                    ),
                });
            }
            let empty = arrow_array::new_empty_array(field.data_type());
            arrow_cast::display::ArrayFormatter::try_new(empty.as_ref(), &cell_format_options())
                .map_err(|error| DagError::NodeError {
                    node_type: "table_from_df".into(),
                    msg: format!(
                        "column `{}`: official Arrow formatting failed: {error}",
                        field.name()
                    ),
                })?;
        }

        // Collect rows from the DataFrame.
        let batches = df
            .clone()
            .collect()
            .await
            .map_err(|e| DagError::NodeError {
                node_type: "table_from_df".into(),
                msg: format!("failed to collect batches: {e}"),
            })?;

        // Extract schema (column names).
        let schema = df.schema();
        let col_names: Vec<String> = schema.fields().iter().map(|f| f.name().clone()).collect();
        let n_cols = col_names.len();

        if n_cols == 0 {
            return Err(DagError::NodeError {
                node_type: "table_from_df".into(),
                msg: "input DataFrame has no columns".into(),
            });
        }

        // Build column alignment spec.
        let col_spec: String = "l".repeat(n_cols);

        // Collect data rows.
        let mut rows: Vec<Vec<String>> = Vec::new();
        let mut row_count = 0usize;

        for batch in &batches {
            let n = batch.num_rows();
            for i in 0..n {
                if let Some(max) = self.max_rows {
                    if row_count >= max {
                        break;
                    }
                }
                let mut row = Vec::with_capacity(n_cols);
                for j in 0..n_cols {
                    let col = batch.column(j);
                    let cell =
                        arrow_cell_to_string(col.as_ref(), i, &col_names[j]).map_err(|msg| {
                            DagError::NodeError {
                                node_type: "table_from_df".into(),
                                msg,
                            }
                        })?;
                    row.push(cell);
                }
                rows.push(row);
                row_count += 1;
            }
        }

        // Render LaTeX tabular.
        let latex = render_tabular(
            &col_names,
            &rows,
            &col_spec,
            &self.format,
            self.caption.as_deref(),
            self.label.as_deref(),
        );

        // Build output DataFrame.
        let out_schema: SchemaRef = Arc::new(Schema::new(vec![Field::new(
            "latex",
            DataType::Utf8,
            false,
        )]));
        let cols: Vec<ArrayRef> = vec![Arc::new(StringArray::from(vec![latex.as_str()]))];
        let batch = RecordBatch::try_new(out_schema, cols).map_err(|e| DagError::NodeError {
            node_type: "table_from_df".into(),
            msg: format!("failed to build output batch: {e}"),
        })?;

        let session = node_ctx.session();
        let out_df = session.read_batch(batch).map_err(|e| DagError::NodeError {
            node_type: "table_from_df".into(),
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

/// Extract a cell value as a string from an Arrow array at a given row index.
///
/// Nulls render as empty cells. Unsupported column types are an explicit
/// error — previously they fell through to a silent empty string, producing
/// blank table columns (e.g. every unsigned integer type).
fn supported_cell_type(data_type: &DataType) -> bool {
    use arrow_schema::TimeUnit;
    matches!(
        data_type,
        DataType::Utf8
            | DataType::LargeUtf8
            | DataType::Utf8View
            | DataType::Boolean
            | DataType::Int8
            | DataType::Int16
            | DataType::Int32
            | DataType::Int64
            | DataType::UInt8
            | DataType::UInt16
            | DataType::UInt32
            | DataType::UInt64
            | DataType::Float32
            | DataType::Float64
            | DataType::Date32
            | DataType::Date64
            | DataType::Time32(TimeUnit::Second | TimeUnit::Millisecond)
            | DataType::Time64(TimeUnit::Microsecond | TimeUnit::Nanosecond)
            | DataType::Timestamp(_, _)
    )
}

fn cell_format_options() -> arrow_cast::display::FormatOptions<'static> {
    arrow_cast::display::FormatOptions::new()
        .with_datetime_format(Some("%Y-%m-%d"))
        .with_timestamp_format(Some("%Y-%m-%d %H:%M:%S%.f"))
        .with_timestamp_tz_format(Some("%Y-%m-%d %H:%M:%S%.f%:z"))
}

fn arrow_cell_to_string(
    array: &dyn arrow_array::Array,
    row: usize,
    column: &str,
) -> Result<String, String> {
    use arrow_cast::display::ArrayFormatter;
    use arrow_schema::TimeUnit;

    if row >= array.len() {
        return Err(format!(
            "column `{column}`: row index {row} is out of bounds ({} rows)",
            array.len()
        ));
    }
    if !supported_cell_type(array.data_type()) {
        return Err(format!(
            "column `{column}` has unsupported type {} for LaTeX table rendering",
            array.data_type()
        ));
    }
    if array.is_null(row) {
        return Ok(String::new());
    }
    if matches!(array.data_type(), DataType::Date64)
        && array
            .as_any()
            .downcast_ref::<arrow_array::Date64Array>()
            .unwrap()
            .value(row)
            % 86_400_000
            != 0
    {
        return Err(format!(
            "column `{column}` has a Date64 value that does not represent an exact day"
        ));
    }
    let time = match array.data_type() {
        DataType::Time32(TimeUnit::Second) => Some((
            i64::from(
                array
                    .as_any()
                    .downcast_ref::<arrow_array::Time32SecondArray>()
                    .unwrap()
                    .value(row),
            ),
            86_400,
        )),
        DataType::Time32(TimeUnit::Millisecond) => Some((
            i64::from(
                array
                    .as_any()
                    .downcast_ref::<arrow_array::Time32MillisecondArray>()
                    .unwrap()
                    .value(row),
            ),
            86_400_000,
        )),
        DataType::Time64(TimeUnit::Microsecond) => Some((
            array
                .as_any()
                .downcast_ref::<arrow_array::Time64MicrosecondArray>()
                .unwrap()
                .value(row),
            86_400_000_000,
        )),
        DataType::Time64(TimeUnit::Nanosecond) => Some((
            array
                .as_any()
                .downcast_ref::<arrow_array::Time64NanosecondArray>()
                .unwrap()
                .value(row),
            86_400_000_000_000,
        )),
        _ => None,
    };
    if time.is_some_and(|(value, limit)| value < 0 || value >= limit) {
        return Err(format!(
            "column `{column}` has a time outside the valid day range"
        ));
    }
    let options = cell_format_options();
    ArrayFormatter::try_new(array, &options)
        .and_then(|formatter| formatter.value(row).try_to_string())
        .map_err(|error| format!("column `{column}`: official Arrow formatting failed: {error}"))
}

/// Render a complete LaTeX table float.
fn render_tabular(
    header: &[String],
    rows: &[Vec<String>],
    col_spec: &str,
    format: &str,
    caption: Option<&str>,
    label: Option<&str>,
) -> String {
    let mut out = String::with_capacity(1024);
    let use_booktabs = format != "plain";

    // Table float wrapper.
    out.push_str("\\begin{table}[htbp]\n");
    out.push_str("  \\centering\n");

    if let Some(cap) = caption {
        out.push_str(&format!("  \\caption{{{}}}\n", escape_latex_text(cap)));
    }

    // Tabular environment.
    out.push_str(&format!("  \\begin{{tabular}}{{{col_spec}}}\n"));

    if use_booktabs {
        out.push_str("    \\toprule\n");
    } else {
        out.push_str("    \\hline\n");
    }

    // Header row.
    let header_escaped: Vec<String> = header.iter().map(|h| escape_latex_text(h)).collect();
    out.push_str(&format!("    {} \\\\\n", header_escaped.join(" & ")));

    if use_booktabs {
        out.push_str("    \\midrule\n");
    } else {
        out.push_str("    \\hline\n");
    }

    // Data rows.
    for row in rows {
        let cells: Vec<String> = row.iter().map(|c| escape_latex_text(c)).collect();
        out.push_str(&format!("    {} \\\\\n", cells.join(" & ")));
    }

    if use_booktabs {
        out.push_str("    \\bottomrule\n");
    } else {
        out.push_str("    \\hline\n");
    }

    out.push_str("  \\end{tabular}\n");

    if let Some(lbl) = label {
        out.push_str(&format!("  \\label{{{lbl}}}\n"));
    }

    out.push_str("\\end{table}");
    out
}

/// Escape special LaTeX characters in plain text.
pub(crate) fn escape_latex_text(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '&' => out.push_str("\\&"),
            '%' => out.push_str("\\%"),
            '$' => out.push_str("\\$"),
            '#' => out.push_str("\\#"),
            '_' => out.push_str("\\_"),
            '{' => out.push_str("\\{"),
            '}' => out.push_str("\\}"),
            '\\' => out.push_str("\\textbackslash{}"),
            '^' => out.push_str("\\textasciicircum{}"),
            '~' => out.push_str("\\textasciitilde{}"),
            c => out.push(c),
        }
    }
    out
}

pub(crate) fn valid_latex_label(label: &str) -> bool {
    !label.is_empty()
        && label
            .bytes()
            .all(|character| character.is_ascii_alphanumeric() || b":._-".contains(&character))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn render_booktabs_table() {
        let latex = render_tabular(
            &["Method".into(), "Beta".into(), "P".into()],
            &[
                vec!["IVW".into(), "0.42".into(), "0.001".into()],
                vec!["Egger".into(), "0.38".into(), "0.005".into()],
            ],
            "lll",
            "booktabs",
            Some("MR results"),
            Some("tab:mr"),
        );
        assert!(latex.contains("\\begin{table}"));
        assert!(latex.contains("\\begin{tabular}{lll}"));
        assert!(latex.contains("\\toprule"));
        assert!(latex.contains("Method & Beta & P"));
        assert!(latex.contains("IVW & 0.42 & 0.001"));
        assert!(latex.contains("\\midrule"));
        assert!(latex.contains("\\bottomrule"));
        assert!(latex.contains("\\caption{MR results}"));
        assert!(latex.contains("\\label{tab:mr}"));
    }

    #[test]
    fn render_plain_table() {
        let latex = render_tabular(
            &["A".into(), "B".into()],
            &[vec!["1".into(), "2".into()]],
            "cc",
            "plain",
            None,
            None,
        );
        assert!(latex.contains("\\hline"));
        assert!(!latex.contains("\\toprule"));
        assert!(latex.contains("A & B"));
        assert!(latex.contains("1 & 2"));
    }

    #[test]
    fn escape_special_chars() {
        assert_eq!(escape_latex_text("100%"), "100\\%");
        assert_eq!(escape_latex_text("a_b"), "a\\_b");
        assert_eq!(escape_latex_text("x & y"), "x \\& y");
    }

    // ---- cell rendering type coverage ----

    use arrow_array::{
        ArrayRef, BinaryArray, Date32Array, Date64Array, Float64Array, Int64Array,
        Time32SecondArray, Time64NanosecondArray, TimestampMicrosecondArray, UInt8Array,
        UInt16Array, UInt32Array, UInt64Array,
    };

    fn cell_of(array: &ArrayRef, row: usize, column: &str) -> String {
        arrow_cell_to_string(array.as_ref(), row, column).unwrap()
    }

    #[test]
    fn unsigned_int_columns_render_values_and_nulls() {
        let u8_col: ArrayRef = Arc::new(UInt8Array::from(vec![Some(7), None]));
        let u16_col: ArrayRef = Arc::new(UInt16Array::from(vec![Some(300), Some(65535)]));
        let u32_col: ArrayRef = Arc::new(UInt32Array::from(vec![Some(4_000_000_000), None]));
        let u64_col: ArrayRef = Arc::new(UInt64Array::from(vec![
            Some(18_446_744_073_709_551_615),
            Some(0),
        ]));
        // Regression: every unsigned width used to fall through to "".
        assert_eq!(cell_of(&u8_col, 0, "u8"), "7");
        assert_eq!(cell_of(&u8_col, 1, "u8"), "");
        assert_eq!(cell_of(&u16_col, 1, "u16"), "65535");
        assert_eq!(cell_of(&u32_col, 0, "u32"), "4000000000");
        assert_eq!(cell_of(&u32_col, 1, "u32"), "");
        assert_eq!(cell_of(&u64_col, 0, "u64"), "18446744073709551615");
        // Previously-covered types keep rendering.
        let i64_col: ArrayRef = Arc::new(Int64Array::from(vec![Some(-5)]));
        let f64_col: ArrayRef = Arc::new(Float64Array::from(vec![Some(1.25)]));
        assert_eq!(cell_of(&i64_col, 0, "i64"), "-5");
        assert_eq!(cell_of(&f64_col, 0, "f64"), "1.25");
    }

    #[test]
    fn date_and_time_columns_render_iso_values() {
        // Day counts verified against the proleptic Gregorian calendar:
        // 0 = 1970-01-01, 59 = 1970-03-01, 365 = 1971-01-01 (1970 has 365
        // days), 366 = 1971-01-02, 10957 = 2000-01-01 (30·365 + 7 leap
        // days), 11017 = 2000-03-01.
        for (days, expected) in [
            (0, "1970-01-01"),
            (59, "1970-03-01"),
            (365, "1971-01-01"),
            (366, "1971-01-02"),
            (10957, "2000-01-01"),
            (11017, "2000-03-01"),
            (-1, "1969-12-31"),
        ] {
            let d32: ArrayRef = Arc::new(Date32Array::from(vec![days as i32]));
            assert_eq!(cell_of(&d32, 0, "d"), expected);
            let d64: ArrayRef = Arc::new(Date64Array::from(vec![days * 86_400_000]));
            assert_eq!(cell_of(&d64, 0, "d"), expected);
        }
        let t32: ArrayRef = Arc::new(Time32SecondArray::from(vec![3661]));
        assert_eq!(cell_of(&t32, 0, "t"), "01:01:01");
        let t64: ArrayRef = Arc::new(Time64NanosecondArray::from(vec![12_345_678_901_234]));
        assert_eq!(cell_of(&t64, 0, "t"), "03:25:45.678901234");
        // 1_700_000_000 s since epoch = 2023-11-14 22:13:20 UTC.
        let ts: ArrayRef = Arc::new(TimestampMicrosecondArray::from(vec![1_700_000_000_000_000]));
        assert_eq!(cell_of(&ts, 0, "ts"), "2023-11-14 22:13:20");
    }

    #[test]
    fn unsupported_column_type_errors_instead_of_rendering_blank() {
        let binary: ArrayRef = Arc::new(BinaryArray::from_vec(vec![b"\x01\x02"]));
        let error = arrow_cell_to_string(binary.as_ref(), 0, "blob").unwrap_err();
        assert!(
            error.contains("column `blob` has unsupported type Binary"),
            "{error}"
        );
        // Out-of-bounds rows are caught explicitly too.
        let col: ArrayRef = Arc::new(Int64Array::from(vec![Some(1)]));
        let error = arrow_cell_to_string(col.as_ref(), 5, "x").unwrap_err();
        assert!(error.contains("out of bounds"), "{error}");
    }

    #[tokio::test]
    async fn execute_renders_unsigned_and_date_columns_end_to_end() {
        use dag_core::registry::NodeCtx;

        let schema = Arc::new(Schema::new(vec![
            Field::new("gene", arrow_schema::DataType::Utf8, false),
            Field::new("n_snps", arrow_schema::DataType::UInt32, true),
            Field::new("reads", arrow_schema::DataType::UInt64, true),
            Field::new("peak", arrow_schema::DataType::Date32, false),
        ]));
        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(StringArray::from(vec!["GENE1", "GENE2"])),
                Arc::new(UInt32Array::from(vec![Some(12), None])),
                Arc::new(UInt64Array::from(vec![Some(9_000_000_000_000), Some(3)])),
                Arc::new(Date32Array::from(vec![10957, 11017])),
            ],
        )
        .unwrap();
        let session = datafusion::prelude::SessionContext::new();
        let df = session.read_batch(batch).unwrap();

        let mut node = TableFromDfFactory {}
            .build(
                serde_json::json!({}),
                NodeCtx::new(session.runtime_env(), None),
            )
            .unwrap();
        let out = node
            .execute(
                &NodeCtx::new(session.runtime_env(), None),
                &[NodeInput::new_dataframe(0, df)],
                &dag_core::dag::node_event::NodeReporter::noop(),
            )
            .await
            .unwrap();

        let batches = out.dataframe(0).unwrap().clone().collect().await.unwrap();
        let latex = batches[0]
            .column(0)
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap()
            .value(0)
            .to_string();
        // Unsigned values render; the null UInt32 cell stays empty.
        assert!(
            latex.contains("GENE1 & 12 & 9000000000000 & 2000-01-01"),
            "{latex}"
        );
        assert!(latex.contains("GENE2 &  & 3 & 2000-03-01"), "{latex}");
    }
}
