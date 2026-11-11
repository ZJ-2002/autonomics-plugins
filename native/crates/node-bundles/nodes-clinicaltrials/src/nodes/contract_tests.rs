// Synthetic fixture identifiers; no provider records were downloaded.
use super::*;
use crate::client::{CapturedResponse, ResponseTransport};
use dag_core::dag::node_event::NodeReporter;
use serde_json::{Value, json};

#[derive(Debug)]
struct Body(Value);

#[async_trait]
impl ResponseTransport for Body {
    async fn response(&self, url: &str) -> crate::error::Result<CapturedResponse> {
        Ok(CapturedResponse {
            url: url.into(),
            response_url: url.into(),
            headers: std::collections::BTreeMap::from([(
                "content-type".into(),
                "application/json".into(),
            )]),
            status: 200,
            body: self.0.to_string(),
        })
    }
}

fn fixed() -> bool {
    true
}

fn save(name: &str, value: Value) {
    let Some(root) = std::env::var_os("CT_COUNTER_DIR") else {
        return;
    };
    let root = std::path::PathBuf::from(root);
    std::fs::write(
        root.join(format!("{name}.json")),
        serde_json::to_vec_pretty(&value).unwrap(),
    )
    .unwrap();
}

fn body() -> Value {
    json!({"protocolSection":{"identificationModule":{"nctId":"NCT00000000","briefTitle":"Synthetic technical study"}}})
}

fn context() -> NodeCtx {
    NodeCtx::new(
        datafusion::prelude::SessionContext::new().runtime_env(),
        None,
    )
}

async fn run(body: Value, extra: bool) -> Result<PortOutputs, DagError> {
    let client = ClinicalTrialsClient::new().with_transport(Arc::new(Body(body)));
    let mut node = ClinicalTrialsStudyNode::with_client(
        serde_json::from_value(json!({"nct_id":"NCT00000000"})).unwrap(),
        client,
    );
    let inputs = if extra {
        vec![dag_core::dag::NodeInput::file(
            0,
            dag_core::value::FileRef::new("vfs:///extra.tsv", Some("tsv".into())),
        )]
    } else {
        vec![]
    };
    node.execute(&context(), &inputs, &NodeReporter::noop())
        .await
}

async fn rejected(name: &str, body: Value, extra: bool) {
    let result = run(body.clone(), extra).await;
    assert_eq!(result.is_ok(), !fixed(), "{name}: {result:?}");
    save(
        name,
        json!({"fixed":fixed(),"accepted":result.is_ok(),"body":body,"error":result.err().map(|error|error.to_string())}),
    );
}

#[test]
fn unknown_spec_controls_do_not_disappear() {
    let accepted = serde_json::from_value::<ClinicalTrialsStudySpec>(
        json!({"nct_id":"NCT00000000","official":true}),
    )
    .is_ok();
    assert_eq!(accepted, !fixed());
    save(
        "unknown-controls",
        json!({"fixed":fixed(),"accepted":accepted}),
    );
}

#[tokio::test]
async fn zero_input_source_rejects_extra_input() {
    rejected("extra-input", body(), true).await;
}

#[test]
fn unicode_invalid_nct_does_not_panic() {
    let result = std::panic::catch_unwind(|| crate::client::normalize_nct_id("éé1234567"));
    assert_eq!(result.is_err(), !fixed());
    if fixed() {
        assert!(result.as_ref().unwrap().is_err());
    }
    save(
        "unicode-nct",
        json!({"fixed":fixed(),"panicked":result.is_err()}),
    );
}

#[tokio::test]
async fn error_payload_is_not_all_null_success() {
    rejected(
        "error-payload",
        json!({"message":"SYNTHETIC_PROVIDER_ERROR"}),
        false,
    )
    .await;
}

#[tokio::test]
async fn empty_payload_is_not_all_null_success() {
    rejected("empty-payload", json!({}), false).await;
}

#[tokio::test]
async fn wrong_root_does_not_disappear() {
    rejected("missing-protocol", json!({"resultsSection":{}}), false).await;
}

#[tokio::test]
async fn missing_id_is_not_qualified_source() {
    let mut value = body();
    value["protocolSection"]["identificationModule"]
        .as_object_mut()
        .unwrap()
        .remove("nctId");
    rejected("missing-id", value, false).await;
}

#[tokio::test]
async fn wrong_id_is_not_the_requested_source() {
    let mut value = body();
    value["protocolSection"]["identificationModule"]["nctId"] = json!("NCT00000001");
    rejected("wrong-id", value, false).await;
}

#[tokio::test]
async fn returned_noncanonical_id_is_not_silently_qualified() {
    let mut value = body();
    value["protocolSection"]["identificationModule"]["nctId"] = json!("nct00000000");
    rejected("returned-lowercase", value, false).await;
}

#[test]
fn official_intervention_type_is_preserved() {
    let value = json!({"type":"DRUG","name":"Synthetic agent"});
    let parsed: crate::types::Intervention = serde_json::from_value(value.clone()).unwrap();
    assert_eq!(
        parsed.intervention_type.as_deref(),
        if fixed() { Some("DRUG") } else { None }
    );
    save(
        "official-intervention-type",
        json!({"fixed":fixed(),"type":parsed.intervention_type,"body":value}),
    );
}

#[test]
fn official_date_type_is_preserved() {
    let value = json!({"date":"2026-10","type":"ESTIMATED"});
    let parsed: crate::types::DateValue = serde_json::from_value(value.clone()).unwrap();
    assert_eq!(
        parsed.value_type.as_deref(),
        if fixed() { Some("ESTIMATED") } else { None }
    );
    save(
        "official-date-type",
        json!({"fixed":fixed(),"type":parsed.value_type,"body":value}),
    );
}

#[test]
fn official_enrollment_type_is_preserved() {
    let value = json!({"count":7,"type":"ACTUAL"});
    let parsed: crate::types::EnrollmentInfo = serde_json::from_value(value.clone()).unwrap();
    assert_eq!(
        parsed.value_type.as_deref(),
        if fixed() { Some("ACTUAL") } else { None }
    );
    save(
        "official-enrollment-type",
        json!({"fixed":fixed(),"type":parsed.value_type,"body":value}),
    );
}

async fn projected_intervention(
    name: &str,
    intervention: Value,
    expected: Option<&str>,
    before: &str,
) {
    let mut value = body();
    value["protocolSection"]["armsInterventionsModule"] = json!({"interventions":[intervention]});
    let output = run(value, false).await.unwrap();
    let batches = output
        .dataframe(0)
        .unwrap()
        .clone()
        .collect()
        .await
        .unwrap();
    let array = batches[0]
        .column(13)
        .as_any()
        .downcast_ref::<StringArray>()
        .unwrap();
    let actual = if array.is_null(0) {
        None
    } else {
        Some(array.value(0))
    };
    assert_eq!(actual, if fixed() { expected } else { Some(before) });
    save(name, json!({"fixed":fixed(),"actual":actual}));
}

#[tokio::test]
async fn absent_intervention_type_is_not_invented() {
    projected_intervention(
        "missing-intervention-type",
        json!({"name":"Synthetic agent"}),
        Some("Synthetic agent"),
        "INTERVENTION:Synthetic agent",
    )
    .await;
}

#[tokio::test]
async fn absent_intervention_name_is_not_invented() {
    projected_intervention(
        "missing-intervention-name",
        json!({"interventionType":"DRUG"}),
        Some("DRUG"),
        "DRUG:unknown",
    )
    .await;
}

#[tokio::test]
async fn empty_intervention_is_not_invented() {
    projected_intervention(
        "empty-intervention",
        json!({}),
        None,
        "INTERVENTION:unknown",
    )
    .await;
}

#[tokio::test]
async fn accepted_lowercase_request_uses_canonical_official_id() {
    let client = ClinicalTrialsClient::new().with_transport(Arc::new(Body(body())));
    client.study(" nct00000000 ").await.unwrap();
    let actual = client.captured_responses()[0].url.clone();
    assert!(actual.ends_with(if fixed() {
        "/NCT00000000"
    } else {
        "/nct00000000"
    }));
    save("canonical-request", json!({"fixed":fixed(),"url":actual}));
}

#[tokio::test]
async fn audit_sidecar_records_success_and_preserves_existing_outputs() {
    let directory = tempfile::tempdir().unwrap();
    let audit = directory.path().join("lookup.json");
    let response = directory.path().join("lookup.json.response-0.json");
    let client = ClinicalTrialsClient::new().with_transport(Arc::new(Body(body())));
    let mut node = ClinicalTrialsStudyNode::with_client(
        serde_json::from_value(json!({"nct_id":"NCT00000000","audit_path":audit})).unwrap(),
        client,
    );
    let output = node
        .execute(&context(), &[], &NodeReporter::noop())
        .await
        .unwrap();
    let batches = output
        .dataframe(0)
        .unwrap()
        .clone()
        .collect()
        .await
        .unwrap();
    assert_eq!(batches[0].num_rows(), 1);
    assert_eq!(batches[0].num_columns(), 16);
    let audit_before = std::fs::read(&audit).unwrap();
    let response_before = std::fs::read(&response).unwrap();
    let record: Value = serde_json::from_slice(&audit_before).unwrap();
    assert_eq!(record["stage"], "RAW_LOOKUP_NOT_NODE_COMPLETION");
    assert!(record["details"]["lookup_error"].is_null());
    assert_eq!(
        serde_json::from_slice::<Value>(&response_before).unwrap(),
        body()
    );
    assert!(
        node.execute(&context(), &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(std::fs::read(audit).unwrap(), audit_before);
    assert_eq!(std::fs::read(response).unwrap(), response_before);
}

#[tokio::test]
async fn audit_sidecar_preserves_rejected_response_without_publishing_a_table() {
    let directory = tempfile::tempdir().unwrap();
    let audit = directory.path().join("rejected.json");
    let payload = json!({"message":"SYNTHETIC_PROVIDER_FAILURE"});
    let client = ClinicalTrialsClient::new().with_transport(Arc::new(Body(payload.clone())));
    let mut node = ClinicalTrialsStudyNode::with_client(
        serde_json::from_value(json!({"nct_id":"NCT00000000","audit_path":audit})).unwrap(),
        client,
    );
    assert!(
        node.execute(&context(), &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    let record: Value = serde_json::from_slice(&std::fs::read(audit).unwrap()).unwrap();
    assert_eq!(record["responses"].as_array().unwrap().len(), 1);
    assert!(record["details"]["lookup_error"].as_str().is_some());
    let received: Value = serde_json::from_slice(
        &std::fs::read(directory.path().join("rejected.json.response-0.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(received, payload);
}
