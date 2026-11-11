use super::*;
use dag_core::dag::node_event::NodeReporter;
use opentargets::client::{CapturedResponse, ResponseTransport};
use serde_json::{Value, json};

#[derive(Debug)]
struct Reply(u16, String);

#[async_trait]
impl ResponseTransport for Reply {
    async fn response(&self, url: &str, request: &Value) -> opentargets::Result<CapturedResponse> {
        assert_eq!(request["variables"]["q"], "BRCA1");
        Ok(CapturedResponse {
            url: url.into(),
            request: request.clone(),
            status: self.0,
            body: self.1.clone(),
        })
    }
}

fn client(status: u16, body: String) -> OpenTargetsClient {
    OpenTargetsClient::with_endpoint("http://fixture.invalid")
        .with_transport(Arc::new(Reply(status, body)))
}

fn context() -> NodeCtx {
    NodeCtx::new(
        SessionContext::new().runtime_env(),
        Some(Arc::new(vfs::OpendalFileStorage::new_temp())),
    )
}

fn response() -> Value {
    json!({"data":{"search":{"total":1,"hits":[{"id":"ENSG00000012048","entity":"target","name":"BRCA1","score":17.4,"description":null}]}}})
}

#[test]
fn selected_search_controls_are_validated_without_silent_clipping() {
    for patch in [
        json!({"endpoint":"not a URL"}),
        json!({"endpoint":"http://user:private@fixture.invalid"}),
        json!({"endpoint":"file:///tmp/invalid"}),
        json!({"endpoint":"http://fixture.invalid/#fragment"}),
        json!({"query":""}),
        json!({"query":"BRCA1\n"}),
        json!({"size":3001}),
        json!({"index":2147483648u64}),
        json!({"entity":["invented"]}),
    ] {
        let mut config = json!({"query":"BRCA1"});
        config
            .as_object_mut()
            .unwrap()
            .extend(patch.as_object().unwrap().clone());
        let spec: OpentargetsSearchSpec = serde_json::from_value(config).unwrap();
        assert!(validate_search_spec(&spec).is_err());
    }
    assert!(
        serde_json::from_value::<OpentargetsSearchSpec>(json!({"query":"BRCA1","unknown":true}))
            .is_err()
    );
    let spec: OpentargetsSearchSpec = serde_json::from_value(
        json!({"query":"BRCA1","size":3000,"index":2147483647u64,"entity":["target"]}),
    )
    .unwrap();
    validate_search_spec(&spec).unwrap();
}

#[tokio::test]
async fn selected_search_preserves_all_five_fields_and_raw_request_audit() {
    let ctx = context();
    let mut node = OpentargetsSearchNode::with_client(
        serde_json::from_value(
            json!({"query":"BRCA1","entity":["target"],"audit_path":"vfs:///search.json"}),
        )
        .unwrap(),
        client(200, response().to_string()),
    );
    let output = node
        .execute(&ctx, &[], &NodeReporter::noop())
        .await
        .unwrap();
    let batches = output
        .dataframe(0)
        .unwrap()
        .clone()
        .collect()
        .await
        .unwrap();
    assert_eq!(batches.len(), 1);
    let batch = &batches[0];
    assert_eq!((batch.num_rows(), batch.num_columns()), (1, 5));
    assert_eq!(
        batch
            .schema()
            .fields()
            .iter()
            .map(|field| field.name().as_str())
            .collect::<Vec<_>>(),
        vec!["entity", "id", "name", "score", "description"]
    );
    for (index, expected) in [(0, "target"), (1, "ENSG00000012048"), (2, "BRCA1")] {
        assert_eq!(
            batch
                .column(index)
                .as_any()
                .downcast_ref::<StringArray>()
                .unwrap()
                .value(0),
            expected
        );
    }
    assert_eq!(
        batch
            .column(3)
            .as_any()
            .downcast_ref::<Float64Array>()
            .unwrap()
            .value(0)
            .to_bits(),
        17.4_f64.to_bits()
    );
    assert!(batch.column(4).is_null(0));
    let audit: Value = serde_json::from_slice(
        &search_publication::read_file_bytes(&ctx, "vfs:///search.json")
            .await
            .unwrap(),
    )
    .unwrap();
    assert_eq!(audit["stage"], "RAW_LOOKUP_NOT_NODE_COMPLETION");
    assert_eq!(audit["responses"][0]["request"]["variables"]["q"], "BRCA1");
    assert_eq!(audit["g0_granted"], false);
}

#[tokio::test]
async fn selected_search_rejects_extra_inputs_and_invalid_result_before_output() {
    let ctx = context();
    let spec = || serde_json::from_value(json!({"query":"BRCA1"})).unwrap();
    let mut node = OpentargetsSearchNode::with_client(spec(), client(200, response().to_string()));
    let input = dag_core::dag::NodeInput::file(
        0,
        dag_core::value::FileRef::new("vfs:///unused.tsv", Some("tsv".into())),
    );
    assert!(
        node.execute(&ctx, &[input], &NodeReporter::noop())
            .await
            .is_err()
    );
    let mut invalid = response();
    invalid["data"]["search"]["hits"][0]
        .as_object_mut()
        .unwrap()
        .remove("score");
    let mut node = OpentargetsSearchNode::with_client(spec(), client(200, invalid.to_string()));
    assert!(
        node.execute(&ctx, &[], &NodeReporter::noop())
            .await
            .is_err()
    );
}

#[tokio::test]
async fn failed_search_preserves_text_error_audit_without_success_claim() {
    let ctx = context();
    let body = "<html>unavailable</html>\n";
    let mut node = OpentargetsSearchNode::with_client(
        serde_json::from_value(json!({"query":"BRCA1","audit_path":"vfs:///failure.json"}))
            .unwrap(),
        client(503, body.into()),
    );
    assert!(
        node.execute(&ctx, &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    let audit: Value = serde_json::from_slice(
        &search_publication::read_file_bytes(&ctx, "vfs:///failure.json")
            .await
            .unwrap(),
    )
    .unwrap();
    let file: dag_core::value::FileRef =
        serde_json::from_value(audit["responses"][0]["response"].clone()).unwrap();
    assert_eq!(file.format.as_deref(), Some("txt"));
    assert_eq!(
        search_publication::read_file_bytes(&ctx, &file.path)
            .await
            .unwrap(),
        body.as_bytes()
    );
    assert_eq!(audit["responses"][0]["status"], 503);
    assert_eq!(audit["stage"], "RAW_LOOKUP_NOT_NODE_COMPLETION");
    assert!(!audit["details"]["qualification_error"].is_null());
}
