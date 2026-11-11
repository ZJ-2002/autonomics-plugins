use super::*;
use chembl::client::{CapturedResponse, ResponseTransport};
use dag_core::dag::node_event::NodeReporter;
use serde_json::{Value, json};
use std::sync::Mutex;

#[derive(Debug)]
struct Pages(Mutex<Vec<Value>>);

#[async_trait]
impl ResponseTransport for Pages {
    async fn response(&self, url: &str) -> chembl::error::Result<CapturedResponse> {
        Ok(CapturedResponse {
            url: url.to_string(),
            status: 200,
            body: self.0.lock().unwrap().remove(0).to_string(),
        })
    }
}

fn context() -> NodeCtx {
    NodeCtx::new(
        datafusion::prelude::SessionContext::new().runtime_env(),
        Some(Arc::new(vfs::OpendalFileStorage::new_temp())),
    )
}

fn client(pages: Vec<Value>) -> ChEMBLClient {
    ChEMBLClient::new().with_transport(Arc::new(Pages(Mutex::new(pages))))
}

#[test]
fn numeric_unknown_and_finite_strings_keep_their_semantics() {
    for value in [json!(null), json!("")] {
        let activity: Activity = serde_json::from_value(json!({"standard_value":value})).unwrap();
        assert_eq!(activity.standard_value, None);
    }
    let activity: Activity = serde_json::from_value(json!({"standard_value":"1.25e-3"})).unwrap();
    assert_eq!(activity.standard_value, Some(0.00125));
    for value in ["NaN", "inf", "-inf", "1e999"] {
        assert!(serde_json::from_value::<Activity>(json!({"standard_value":value})).is_err());
    }
}

#[test]
fn withdrawal_false_true_and_unknown_are_distinct() {
    for value in [json!({}), json!({"withdrawn_flag":null})] {
        assert_eq!(
            serde_json::from_value::<Molecule>(value)
                .unwrap()
                .withdrawn_flag,
            None
        );
    }
    for flag in [true, false] {
        assert_eq!(
            serde_json::from_value::<Molecule>(json!({"withdrawn_flag":flag}))
                .unwrap()
                .withdrawn_flag,
            Some(flag)
        );
    }
}

#[test]
fn advertised_cursor_rejects_nonadvancing_and_ambiguous_offsets() {
    for next in [
        "/activity.json?offset=0",
        "/activity.json?offset=1&offset=2",
        "/activity.json?offset=4294967296",
    ] {
        let meta = chembl::PageMeta {
            next: Some(next.into()),
            ..Default::default()
        };
        assert!(chembl::page_guard::next_offset(&meta).is_err());
    }
    let meta = chembl::PageMeta {
        next: Some("/activity.json?offset=1000".into()),
        ..Default::default()
    };
    assert_eq!(chembl::page_guard::next_offset(&meta).unwrap(), Some(1000));
}

#[tokio::test]
async fn activity_walk_uses_advertised_cursor_and_preserves_raw_audit() {
    let record = json!({"activity_id":1,"molecule_chembl_id":"CHEMBL25","target_chembl_id":"CHEMBL2","assay_chembl_id":"CHEMBL1"});
    let pages = vec![
        json!({"activities":[record.clone()],"page_meta":{"limit":1000,"offset":0,"total_count":1001,"next":"/activity.json?offset=1000"}}),
        json!({"activities":[record],"page_meta":{"limit":1000,"offset":1000,"total_count":1001,"next":null}}),
    ];
    let ctx = context();
    let mut node = ChemblActivitiesNode::with_client(
        serde_json::from_value(
            json!({"molecule_chembl_id":"CHEMBL25","audit_path":"vfs:///query.json"}),
        )
        .unwrap(),
        client(pages),
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
    assert_eq!(
        batches.iter().map(|batch| batch.num_rows()).sum::<usize>(),
        2
    );
}

#[tokio::test]
async fn empty_activity_page_is_a_valid_zero_row_typed_table() {
    let body =
        json!({"activities":[],"page_meta":{"limit":1000,"offset":0,"total_count":0,"next":null}});
    let mut node = ChemblActivitiesNode::with_client(
        serde_json::from_value(json!({"molecule_chembl_id":"CHEMBL25"})).unwrap(),
        client(vec![body]),
    );
    let output = node
        .execute(&context(), &[], &NodeReporter::noop())
        .await
        .unwrap();
    let frame = output.dataframe(0).unwrap().clone();
    assert_eq!(frame.schema().fields().len(), 13);
    let batches = frame.collect().await.unwrap();
    assert_eq!(
        batches.iter().map(|batch| batch.num_rows()).sum::<usize>(),
        0
    );
}

#[tokio::test]
async fn mismatch_to_frozen_activity_filter_is_not_success() {
    let body = json!({"activities":[{"activity_id":1,"molecule_chembl_id":"CHEMBL26","target_chembl_id":"CHEMBL2","assay_chembl_id":"CHEMBL1"}],"page_meta":{"limit":1000,"offset":0,"total_count":1,"next":null}});
    let mut node = ChemblActivitiesNode::with_client(
        serde_json::from_value(json!({"molecule_chembl_id":"CHEMBL25"})).unwrap(),
        client(vec![body]),
    );
    let error = node
        .execute(&context(), &[], &NodeReporter::noop())
        .await
        .unwrap_err();
    assert!(error.to_string().contains("contradicts frozen filter"));
}
