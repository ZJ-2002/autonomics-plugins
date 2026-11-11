use super::*;
use chembl::client::{CapturedResponse, ResponseTransport};
use dag_core::dag::node_event::NodeReporter;
use serde_json::{Value, json};

#[derive(Debug)]
struct Body(Value);

#[async_trait]
impl ResponseTransport for Body {
    async fn response(&self, url: &str) -> chembl::error::Result<CapturedResponse> {
        Ok(CapturedResponse {
            url: url.to_string(),
            status: 200,
            body: self.0.to_string(),
        })
    }
}

fn fixed() -> bool {
    true
}

fn save(name: &str, value: Value) {
    let Some(root) = std::env::var_os("CHEMBL_COUNTER_DIR") else {
        return;
    };
    let root = std::path::PathBuf::from(root);
    std::fs::write(
        root.join(format!("{name}.json")),
        serde_json::to_vec_pretty(&value).unwrap(),
    )
    .unwrap();
}

fn activity() -> Value {
    json!({"activity_id":1,"molecule_chembl_id":"CHEMBL25","target_chembl_id":"CHEMBL2","assay_chembl_id":"CHEMBL1","pchembl_value":"7.0","standard_value":"10.0"})
}

fn molecule() -> Value {
    json!({"molecule_chembl_id":"CHEMBL25","pref_name":"Synthetic compound","withdrawn_flag":false})
}

fn page(kind: &str, records: Vec<Value>) -> Value {
    json!({if kind=="activity" {"activities"} else {"molecules"}:records,
        "page_meta":{"limit":if kind=="activity" {1000} else {100},"offset":0,"total_count":records.len(),"next":null,"previous":null}})
}

fn context() -> NodeCtx {
    NodeCtx::new(
        datafusion::prelude::SessionContext::new().runtime_env(),
        Some(Arc::new(vfs::OpendalFileStorage::new_temp())),
    )
}

async fn run(
    kind: &str,
    spec: Value,
    body: Value,
    extra: bool,
) -> std::result::Result<PortOutputs, DagError> {
    let client = ChEMBLClient::new().with_transport(Arc::new(Body(body)));
    let mut node: Box<dyn DagNode> = if kind == "activity" {
        Box::new(ChemblActivitiesNode::with_client(
            serde_json::from_value(spec).unwrap(),
            client,
        ))
    } else {
        Box::new(ChemblMoleculesNode::with_client(
            serde_json::from_value(spec).unwrap(),
            client,
        ))
    };
    let inputs = if extra {
        vec![dag_core::dag::NodeInput::file(
            0,
            dag_core::value::FileRef::new("vfs:///unused.tsv", Some("tsv".into())),
        )]
    } else {
        Vec::new()
    };
    node.execute(&context(), &inputs, &NodeReporter::noop())
        .await
}

fn spec(kind: &str) -> Value {
    if kind == "activity" {
        json!({"molecule_chembl_id":"CHEMBL25","fetch_all":false})
    } else {
        json!({"query":"synthetic compound","fetch_all":false})
    }
}

async fn rejection(name: &str, kind: &str, spec: Value, body: Value, extra: bool) {
    let result = run(kind, spec.clone(), body.clone(), extra).await;
    assert_eq!(result.is_ok(), !fixed(), "{name}: {result:?}");
    save(
        name,
        json!({"fixed":fixed(),"accepted":result.is_ok(),"spec":spec,"body":body,"error":result.err().map(|error|error.to_string())}),
    );
}

#[test]
fn both_selected_specs_reject_unknown_controls() {
    for kind in ["activity", "molecule"] {
        let mut config = spec(kind);
        config["official"] = json!(true);
        let accepted = if kind == "activity" {
            serde_json::from_value::<ChemblActivitiesSpec>(config).is_ok()
        } else {
            serde_json::from_value::<ChemblMoleculesSpec>(config).is_ok()
        };
        assert_eq!(accepted, !fixed());
    }
    save(
        "unknown-controls",
        json!({"fixed":fixed(),"accepted":!fixed()}),
    );
}

#[tokio::test]
async fn activity_rejects_extra_input() {
    rejection(
        "activity-extra-input",
        "activity",
        spec("activity"),
        page("activity", vec![activity()]),
        true,
    )
    .await;
}

#[tokio::test]
async fn molecule_rejects_extra_input() {
    rejection(
        "molecule-extra-input",
        "molecule",
        spec("molecule"),
        page("molecule", vec![molecule()]),
        true,
    )
    .await;
}

#[tokio::test]
async fn activity_whitespace_filter_is_not_treated_as_a_valid_id() {
    let mut config = spec("activity");
    config["molecule_chembl_id"] = json!(" ");
    rejection(
        "blank-filter",
        "activity",
        config,
        page("activity", vec![activity()]),
        false,
    )
    .await;
}

#[tokio::test]
async fn molecule_blank_search_is_rejected() {
    let mut config = spec("molecule");
    config["query"] = json!("");
    rejection(
        "blank-query",
        "molecule",
        config,
        page("molecule", vec![molecule()]),
        false,
    )
    .await;
}

#[tokio::test]
async fn nonfinite_api_values_are_not_successful_numeric_measurements() {
    let mut record = activity();
    record["pchembl_value"] = json!("NaN");
    rejection(
        "nonfinite-measurement",
        "activity",
        spec("activity"),
        page("activity", vec![record]),
        false,
    )
    .await;
}

#[tokio::test]
async fn absent_activity_identity_is_not_zero() {
    let mut record = activity();
    record.as_object_mut().unwrap().remove("activity_id");
    rejection(
        "missing-activity-id",
        "activity",
        spec("activity"),
        page("activity", vec![record]),
        false,
    )
    .await;
}

#[tokio::test]
async fn unsigned_activity_identity_does_not_wrap_into_negative() {
    let mut record = activity();
    record["activity_id"] = json!(u64::MAX);
    rejection(
        "activity-id-overflow",
        "activity",
        spec("activity"),
        page("activity", vec![record]),
        false,
    )
    .await;
}

#[tokio::test]
async fn absent_molecule_identity_is_not_a_successful_empty_string() {
    let mut record = molecule();
    record.as_object_mut().unwrap().remove("molecule_chembl_id");
    rejection(
        "missing-molecule-id",
        "molecule",
        spec("molecule"),
        page("molecule", vec![record]),
        false,
    )
    .await;
}

#[tokio::test]
async fn absent_withdrawn_flag_remains_unknown_not_false() {
    let mut record = molecule();
    record.as_object_mut().unwrap().remove("withdrawn_flag");
    let output = run(
        "molecule",
        spec("molecule"),
        page("molecule", vec![record]),
        false,
    )
    .await
    .unwrap();
    let batches = output
        .dataframe(0)
        .unwrap()
        .clone()
        .collect()
        .await
        .unwrap();
    let flags = batches[0]
        .column(9)
        .as_any()
        .downcast_ref::<BooleanArray>()
        .unwrap();
    assert_eq!(flags.is_null(0), fixed());
    save(
        "missing-withdrawn",
        json!({"fixed":fixed(),"is_null":flags.is_null(0)}),
    );
}

#[tokio::test]
async fn named_activity_resource_does_not_accept_unrelated_array() {
    rejection(
        "wrong-resource-array",
        "activity",
        spec("activity"),
        page("molecule", vec![molecule()]),
        false,
    )
    .await;
}

#[tokio::test]
async fn page_offset_must_anchor_frozen_request() {
    let mut body = page("activity", vec![activity()]);
    body["page_meta"]["offset"] = json!(7);
    rejection("offset-mismatch", "activity", spec("activity"), body, false).await;
}

#[tokio::test]
async fn missing_pagination_is_not_defaulted_to_complete_first_page() {
    let mut body = page("activity", vec![activity()]);
    body.as_object_mut().unwrap().remove("page_meta");
    rejection(
        "missing-page-meta",
        "activity",
        spec("activity"),
        body,
        false,
    )
    .await;
}

#[tokio::test]
async fn single_activity_page_is_not_truncated_by_all_pages_only_cap() {
    let mut config = spec("activity");
    config["max_records"] = json!(1);
    let mut second = activity();
    second["activity_id"] = json!(2);
    let output = run(
        "activity",
        config,
        page("activity", vec![activity(), second]),
        false,
    )
    .await
    .unwrap();
    let batches = output
        .dataframe(0)
        .unwrap()
        .clone()
        .collect()
        .await
        .unwrap();
    let rows: usize = batches.iter().map(RecordBatch::num_rows).sum();
    assert_eq!(rows, if fixed() { 2 } else { 1 });
    save(
        "activity-single-page-cap",
        json!({"fixed":fixed(),"rows":rows}),
    );
}

#[tokio::test]
async fn single_molecule_page_is_not_truncated_by_all_pages_only_cap() {
    let mut config = spec("molecule");
    config["max_records"] = json!(1);
    let mut second = molecule();
    second["molecule_chembl_id"] = json!("CHEMBL26");
    let output = run(
        "molecule",
        config,
        page("molecule", vec![molecule(), second]),
        false,
    )
    .await
    .unwrap();
    let batches = output
        .dataframe(0)
        .unwrap()
        .clone()
        .collect()
        .await
        .unwrap();
    let rows: usize = batches.iter().map(RecordBatch::num_rows).sum();
    assert_eq!(rows, if fixed() { 2 } else { 1 });
    save(
        "molecule-single-page-cap",
        json!({"fixed":fixed(),"rows":rows}),
    );
}
