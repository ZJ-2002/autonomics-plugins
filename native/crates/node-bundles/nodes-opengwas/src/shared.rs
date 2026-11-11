//! Shared JSON → Arrow helpers used by all OpenGWAS source nodes.

use std::sync::Arc;

use arrow_array::{
    Array, BooleanArray, Float64Array, Int64Array, RecordBatch, StringArray, UInt64Array,
};
use arrow_schema::{DataType, Field, Schema};
use serde_json::Value;

use dag_core::dag::{DagError, graph::PortOutputs};
use dag_core::node::NodePorts;
use dag_core::registry::NodeCtx;

use opengwas::types::GwasInfo;

/// GWAS field ordering priority — common columns appear first in the output.
pub(crate) const FIELD_PRIORITY: &[&str] = &[
    "rsid",
    "variant",
    "chr",
    "chromosome",
    "position",
    "pos",
    "ea",
    "nea",
    "eaf",
    "beta",
    "se",
    "pval",
    "p",
    "nsnp",
    "trait",
    "study_id",
    "id",
    "samplesize",
    "sample_size",
    "ncase",
    "ncontrol",
    "unit",
    "population",
];

/// Extract a flat row array from an API response that may be a bare JSON
/// array, or an object keyed by study ID whose values are arrays.
pub(crate) fn extract_rows(value: &Value) -> Vec<Value> {
    match value {
        Value::Array(arr) => arr.clone(),
        Value::Object(map) => {
            let all_arrays = !map.is_empty() && map.values().all(|v| v.is_array());
            if all_arrays {
                map.values()
                    .flat_map(|v| v.as_array().into_iter().flatten().cloned())
                    .collect()
            } else {
                vec![value.clone()]
            }
        }
        _ => vec![value.clone()],
    }
}

/// Infer the column set from the union of keys across all rows, ordered by
/// [`FIELD_PRIORITY`] then alphabetical for remaining keys.
pub(crate) fn infer_columns(rows: &[Value]) -> Vec<String> {
    let mut seen: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut columns: Vec<String> = Vec::new();
    for row in rows {
        if let Some(obj) = row.as_object() {
            for key in obj.keys() {
                if seen.insert(key.clone()) {
                    columns.push(key.clone());
                }
            }
        }
    }
    columns.sort_by(|a, b| {
        let ai = FIELD_PRIORITY.iter().position(|&p| p == a).unwrap_or(999);
        let bi = FIELD_PRIORITY.iter().position(|&p| p == b).unwrap_or(999);
        ai.cmp(&bi).then_with(|| a.cmp(b))
    });
    columns
}

/// Infer the Arrow [`DataType`] for a column by scanning all non-null values.
pub(crate) fn infer_type(rows: &[Value], key: &str) -> DataType {
    let mut all_int = true;
    let mut all_num = true;
    let mut any_non_null = false;
    let mut has_negative = false;
    let mut exceeds_i64 = false;
    let mut exceeds_exact_float = false;
    let mut all_bool = true;
    for row in rows {
        match row.get(key) {
            Some(Value::Number(n)) => {
                any_non_null = true;
                all_bool = false;
                if n.is_i64() || n.is_u64() {
                    has_negative |= n.as_i64().is_some_and(|value| value < 0);
                    exceeds_i64 |= n.as_u64().is_some_and(|value| value > i64::MAX as u64);
                    exceeds_exact_float |= n.as_u64().is_some_and(|value| value > (1_u64 << 53))
                        || n.as_i64().is_some_and(|value| value < -(1_i64 << 53));
                } else {
                    all_int = false;
                }
            }
            Some(Value::String(_)) => {
                any_non_null = true;
                all_bool = false;
                all_int = false;
                all_num = false;
            }
            Some(Value::Bool(_)) => {
                any_non_null = true;
                all_int = false;
                all_num = false;
            }
            Some(Value::Null) | None => {}
            Some(_) => {
                any_non_null = true;
                all_bool = false;
                all_int = false;
                all_num = false;
            }
        }
    }
    if !any_non_null {
        DataType::Utf8
    } else if all_bool {
        DataType::Boolean
    } else if all_int {
        if exceeds_i64 && has_negative {
            DataType::Utf8
        } else if exceeds_i64 {
            DataType::UInt64
        } else {
            DataType::Int64
        }
    } else if all_num {
        if exceeds_exact_float {
            DataType::Utf8
        } else {
            DataType::Float64
        }
    } else {
        DataType::Utf8
    }
}

/// Build a single column array from JSON values.
pub(crate) fn build_column(rows: &[Value], key: &str, dtype: &DataType) -> Arc<dyn Array> {
    match dtype {
        DataType::Boolean => {
            let values: Vec<Option<bool>> = rows
                .iter()
                .map(|row| row.get(key).and_then(Value::as_bool))
                .collect();
            Arc::new(BooleanArray::from(values))
        }
        DataType::Int64 => {
            let vals: Vec<Option<i64>> = rows
                .iter()
                .map(|r| r.get(key).and_then(Value::as_i64))
                .collect();
            Arc::new(Int64Array::from(vals))
        }
        DataType::UInt64 => {
            let vals: Vec<Option<u64>> = rows
                .iter()
                .map(|row| row.get(key).and_then(Value::as_u64))
                .collect();
            Arc::new(UInt64Array::from(vals))
        }
        DataType::Float64 => {
            let vals: Vec<Option<f64>> = rows
                .iter()
                .map(|r| r.get(key).and_then(|v| v.as_f64()))
                .collect();
            Arc::new(Float64Array::from(vals))
        }
        _ => {
            let vals: Vec<Option<String>> = rows
                .iter()
                .map(|r| match r.get(key) {
                    Some(Value::Null) | None => None,
                    Some(Value::String(s)) => Some(s.clone()),
                    Some(Value::Number(n)) => Some(n.to_string()),
                    Some(Value::Bool(b)) => Some(b.to_string()),
                    Some(other) => Some(other.to_string()),
                })
                .collect();
            let refs: Vec<Option<&str>> = vals.iter().map(|o| o.as_deref()).collect();
            Arc::new(StringArray::from(refs))
        }
    }
}

/// Build an Arrow [`RecordBatch`] from a JSON row array, inferring the schema
/// dynamically. Used by all JSON-returning OpenGWAS endpoints.
pub(crate) fn build_json_batch(rows: &[Value]) -> Result<RecordBatch, DagError> {
    if rows.is_empty() {
        return Ok(RecordBatch::new_empty(Arc::new(Schema::empty())));
    }

    if rows
        .iter()
        .any(|row| row.as_object().is_none_or(|object| object.is_empty()))
    {
        return Err(DagError::Schedule(
            "OpenGWAS tabular rows must be non-empty JSON objects".into(),
        ));
    }

    let columns = infer_columns(rows);
    let fields: Vec<Field> = columns
        .iter()
        .map(|name| Field::new(name, infer_type(rows, name), true))
        .collect();
    let schema = Arc::new(Schema::new(fields));

    let mut arrays: Vec<Arc<dyn Array>> = Vec::with_capacity(columns.len());
    for col in &columns {
        let dtype = schema.field_with_name(col).unwrap().data_type().clone();
        let arr = build_column(rows, col, &dtype);
        arrays.push(arr);
    }

    RecordBatch::try_new(schema, arrays)
        .map_err(|e| DagError::Schedule(format!("failed to build OpenGWAS batch: {e}")))
}

pub(crate) fn build_ld_clump_batch(
    value: &Value,
    request: &opengwas::types::LdClumpRequest,
) -> Result<RecordBatch, DagError> {
    request.validate().map_err(DagError::Schedule)?;
    let retained = value.as_array().ok_or_else(|| {
        DagError::Schedule("OpenGWAS /ld/clump must return an array of rs IDs".into())
    })?;
    let requested: std::collections::HashSet<&str> =
        request.rsid.iter().map(String::as_str).collect();
    let mut selected = std::collections::HashSet::new();
    for value in retained {
        let rsid = value.as_str().ok_or_else(|| {
            DagError::Schedule("OpenGWAS /ld/clump returned a non-string rs ID".into())
        })?;
        if !requested.contains(rsid) || !selected.insert(rsid) {
            return Err(DagError::Schedule(
                "OpenGWAS /ld/clump returned an unrequested or duplicate rs ID".into(),
            ));
        }
    }
    let mut rsids = Vec::with_capacity(selected.len());
    let mut pvalues = Vec::with_capacity(selected.len());
    for (rsid, pvalue) in request.rsid.iter().zip(&request.pval) {
        if selected.contains(rsid.as_str()) {
            rsids.push(rsid.as_str());
            pvalues.push(*pvalue);
        }
    }
    let schema = Arc::new(Schema::new(vec![
        Field::new("rsid", DataType::Utf8, false),
        Field::new("pval", DataType::Float64, false),
    ]));
    RecordBatch::try_new(
        schema,
        vec![
            Arc::new(StringArray::from(rsids)),
            Arc::new(Float64Array::from(pvalues)),
        ],
    )
    .map_err(|error| DagError::Schedule(format!("failed to build OpenGWAS LD batch: {error}")))
}

pub(crate) async fn ld_clump_to_output(
    ctx: &NodeCtx,
    value: &Value,
    request: &opengwas::types::LdClumpRequest,
) -> Result<PortOutputs, DagError> {
    let batch = build_ld_clump_batch(value, request)?;
    let df = ctx.session().read_batch(batch).map_err(|error| {
        DagError::Schedule(format!("failed to read OpenGWAS LD batch: {error}"))
    })?;
    let mut outputs = PortOutputs::new();
    outputs.insert(0, df);
    Ok(outputs)
}

/// Build an Arrow batch from a list of [`GwasInfo`] records.
///
/// Known metadata fields have a fixed nullable schema. Additional API fields
/// are appended with inferred types; nested values are encoded as JSON text.
pub(crate) fn build_gwasinfo_batch(rows: &[GwasInfo]) -> Result<RecordBatch, DagError> {
    macro_rules! opt_str_col {
        ($field:ident) => {{
            let vals: Vec<Option<String>> = rows.iter().map(|r| r.$field.clone()).collect();
            let refs: Vec<Option<&str>> = vals.iter().map(|o| o.as_deref()).collect();
            Arc::new(StringArray::from(refs)) as Arc<dyn Array>
        }};
    }
    macro_rules! opt_i64_col {
        ($field:ident) => {{
            Arc::new(Int64Array::from(
                rows.iter().map(|r| r.$field).collect::<Vec<_>>(),
            )) as Arc<dyn Array>
        }};
    }

    let mut fields = vec![
        Field::new("id", DataType::Utf8, true),
        Field::new("trait", DataType::Utf8, true),
        Field::new("group_name", DataType::Utf8, true),
        Field::new("category", DataType::Utf8, true),
        Field::new("subcategory", DataType::Utf8, true),
        Field::new("population", DataType::Utf8, true),
        Field::new("sex", DataType::Utf8, true),
        Field::new("author", DataType::Utf8, true),
        Field::new("year", DataType::Int64, true),
        Field::new("pmid", DataType::Int64, true),
        Field::new("nsnp", DataType::Int64, true),
        Field::new("sample_size", DataType::Int64, true),
        Field::new("ncase", DataType::Int64, true),
        Field::new("ncontrol", DataType::Int64, true),
        Field::new("mr", DataType::Int64, true),
        Field::new("priority", DataType::Int64, true),
        Field::new("is_nc", DataType::Int64, true),
        Field::new("sd", DataType::Float64, true),
        Field::new("unit", DataType::Utf8, true),
        Field::new("build", DataType::Utf8, true),
        Field::new("ontology", DataType::Utf8, true),
        Field::new("consortium", DataType::Utf8, true),
        Field::new("doi", DataType::Utf8, true),
        Field::new("study_design", DataType::Utf8, true),
        Field::new("covariates", DataType::Utf8, true),
        Field::new("coverage", DataType::Utf8, true),
        Field::new("qc_prior_to_upload", DataType::Utf8, true),
        Field::new("imputation_panel", DataType::Utf8, true),
        Field::new("beta_transformation", DataType::Utf8, true),
        Field::new("note", DataType::Utf8, true),
    ];

    let mut arrays: Vec<Arc<dyn Array>> = vec![
        opt_str_col!(id),
        opt_str_col!(trait_),
        opt_str_col!(group_name),
        opt_str_col!(category),
        opt_str_col!(subcategory),
        opt_str_col!(population),
        opt_str_col!(sex),
        opt_str_col!(author),
        opt_i64_col!(year),
        opt_i64_col!(pmid),
        opt_i64_col!(nsnp),
        opt_i64_col!(sample_size),
        opt_i64_col!(ncase),
        opt_i64_col!(ncontrol),
        opt_i64_col!(mr),
        opt_i64_col!(priority),
        opt_i64_col!(is_nc),
        Arc::new(Float64Array::from(
            rows.iter().map(|r| r.sd).collect::<Vec<_>>(),
        )) as Arc<dyn Array>,
        opt_str_col!(unit),
        opt_str_col!(build),
        opt_str_col!(ontology),
        opt_str_col!(consortium),
        opt_str_col!(doi),
        opt_str_col!(study_design),
        opt_str_col!(covariates),
        opt_str_col!(coverage),
        opt_str_col!(qc_prior_to_upload),
        opt_str_col!(imputation_panel),
        opt_str_col!(beta_transformation),
        opt_str_col!(note),
    ];
    let extras: Vec<Value> = rows
        .iter()
        .map(|row| Value::Object(row.extra_fields.clone()))
        .collect();
    for name in infer_columns(&extras) {
        if fields.iter().any(|field| field.name() == &name) {
            return Err(DagError::Schedule(
                "additional metadata shadows a known output field".into(),
            ));
        }
        let dtype = infer_type(&extras, &name);
        arrays.push(build_column(&extras, &name, &dtype));
        fields.push(Field::new(name, dtype, true));
    }
    RecordBatch::try_new(Arc::new(Schema::new(fields)), arrays)
        .map_err(|e| DagError::Schedule(format!("failed to build gwasinfo batch: {e}")))
}

/// Create an OpenGWAS client from the environment.
pub(crate) fn make_client() -> Result<opengwas::OpengwasClient, DagError> {
    opengwas::OpengwasClient::new(None).map_err(|e| {
        DagError::Schedule(format!(
            "failed to create OpenGWAS client (is OPENGWAS_TOKEN or OPENGWAS_JWT set?): {e}"
        ))
    })
}

/// A [`NodePorts`] with a single output port.
pub(crate) fn single_output_port() -> NodePorts {
    NodePorts::new().add_output_port(None)
}

/// Convert a JSON response into a single-output [`PortOutputs`] via dynamic
/// schema inference. Shared by all JSON-returning source nodes.
pub(crate) async fn json_to_output(
    ctx: &NodeCtx,
    value: &Value,
    endpoint: &str,
) -> Result<PortOutputs, DagError> {
    let rows = extract_rows(value);
    tracing::info!("OpenGWAS {}: {} rows returned", endpoint, rows.len());
    let batch = build_json_batch(&rows)?;
    let session = ctx.session();
    let df = session
        .read_batch(batch)
        .map_err(|e| DagError::Schedule(format!("failed to read OpenGWAS batch: {e}")))?;
    let mut res: PortOutputs = PortOutputs::new();
    res.insert(0, df);
    Ok(res)
}

/// Convert `Vec<GwasInfo>` into a single-output [`PortOutputs`].
pub(crate) async fn gwasinfo_to_output(
    ctx: &NodeCtx,
    rows: Vec<GwasInfo>,
    endpoint: &str,
) -> Result<PortOutputs, DagError> {
    tracing::info!("OpenGWAS {}: {} records returned", endpoint, rows.len());
    let batch = build_gwasinfo_batch(&rows)?;
    let session = ctx.session();
    let df = session
        .read_batch(batch)
        .map_err(|e| DagError::Schedule(format!("failed to read gwasinfo batch: {e}")))?;
    let mut res: PortOutputs = PortOutputs::new();
    res.insert(0, df);
    Ok(res)
}

#[cfg(test)]
mod conversion_tests {
    use super::{build_json_batch, build_ld_clump_batch};
    use arrow_array::{StringArray, UInt64Array};
    use arrow_schema::DataType;
    use opengwas::types::LdClumpRequest;
    use serde_json::json;

    #[test]
    fn json_large_unsigned_integer_is_not_wrapped() {
        let batch = build_json_batch(&[json!({"n": u64::MAX})]).unwrap();
        let array = batch
            .column(0)
            .as_any()
            .downcast_ref::<UInt64Array>()
            .unwrap();
        assert_eq!(array.value(0), u64::MAX);
    }

    #[test]
    fn json_mixed_numeric_range_is_preserved_as_text() {
        let batch = build_json_batch(&[json!({"n": -1}), json!({"n": u64::MAX})]).unwrap();
        assert_eq!(batch.schema().field(0).data_type(), &DataType::Utf8);
        let array = batch
            .column(0)
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap();
        assert_eq!(array.value(1), "18446744073709551615");
    }

    #[test]
    fn ld_empty_array_retains_schema_but_error_object_is_rejected() {
        let request = LdClumpRequest {
            rsid: vec!["rs1205".into()],
            pval: vec![1e-9],
            pthresh: None,
            r2: None,
            kb: None,
            pop: None,
        };
        let empty = build_ld_clump_batch(&json!([]), &request).unwrap();
        assert_eq!((empty.num_rows(), empty.num_columns()), (0, 2));
        assert!(build_ld_clump_batch(&json!({"error": "request failed"}), &request).is_err());
    }

    #[test]
    fn empty_metadata_is_a_typed_table_not_an_execution_error() {
        let empty = super::build_gwasinfo_batch(&[]).unwrap();
        assert_eq!(empty.num_rows(), 0);
        assert_eq!(empty.num_columns(), 30);
        assert_eq!(empty.schema().field(0).name(), "id");
    }

    #[test]
    fn metadata_preserves_additional_scalar_and_nested_fields() {
        let info: opengwas::types::GwasInfo = serde_json::from_value(json!({
            "id":"study-extra", "trait":"Trait", "extension_flag":true,
            "extension_count":u64::MAX, "extension_structure":{"labels":["A","B"]}
        }))
        .unwrap();
        let batch = super::build_gwasinfo_batch(&[info]).unwrap();
        let flags = batch
            .column_by_name("extension_flag")
            .unwrap()
            .as_any()
            .downcast_ref::<arrow_array::BooleanArray>()
            .unwrap();
        assert!(flags.value(0));
        let counts = batch
            .column_by_name("extension_count")
            .unwrap()
            .as_any()
            .downcast_ref::<UInt64Array>()
            .unwrap();
        assert_eq!(counts.value(0), u64::MAX);
        let structure = batch
            .column_by_name("extension_structure")
            .unwrap()
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap();
        assert_eq!(
            serde_json::from_str::<serde_json::Value>(structure.value(0)).unwrap(),
            json!({"labels":["A","B"]})
        );
    }
}
