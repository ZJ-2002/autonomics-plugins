use super::*;
use dag_core::dag::node_event::NodeReporter;
use semantic_scholar::client::{CitationResponseTransport, ReceivedCitationResponse};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::sync::atomic::{AtomicUsize, Ordering};

#[derive(Debug)]
struct Replay {
    body: Vec<u8>,
    status: u16,
    mime: String,
    calls: AtomicUsize,
}

#[async_trait]
impl CitationResponseTransport for Replay {
    async fn response(
        &self,
        url: &str,
    ) -> semantic_scholar::error::Result<ReceivedCitationResponse> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        Ok(ReceivedCitationResponse {
            requested_url: url.into(),
            final_url: url.into(),
            status: self.status,
            content_type: Some(self.mime.clone()),
            retry_after_ms: None,
            body: self.body.clone(),
        })
    }
}

fn fixture(
    body: Vec<u8>,
    status: u16,
    mime: &str,
    direction: CitationDirection,
) -> (NodeCtx, LiteratureCitationsNode, Arc<Replay>) {
    let storage = Arc::new(vfs::OpendalFileStorage::new_temp());
    let context = NodeCtx::new(
        datafusion::prelude::SessionContext::new().runtime_env(),
        Some(storage),
    );
    let replay = Arc::new(Replay {
        body,
        status,
        mime: mime.into(),
        calls: AtomicUsize::new(0),
    });
    let client = Arc::new(
        semantic_scholar::S2Client::new()
            .with_api_key("synthetic-not-an-operator-key")
            .with_citation_transport(replay.clone()),
    );
    let node = LiteratureCitationsNode::with_client(
        LiteratureCitationsSpec {
            paper_id: "PMID:1".into(),
            direction,
            limit: Some(2),
            offset: Some(0),
            path: "vfs:///citation-result.json".into(),
            note: Some("synthetic provenance".into()),
        },
        client,
    );
    (context, node, replay)
}

async fn bytes(context: &NodeCtx, path: &str) -> Vec<u8> {
    crate::nodes::read_file_bytes(context, path).await.unwrap()
}

async fn audit(context: &NodeCtx) -> Value {
    serde_json::from_slice(&bytes(context, "vfs:///citation-result.json.citation-query.json").await)
        .unwrap()
}

async fn check_body(context: &NodeCtx, audit: &Value, expected: &[u8], format: &str) {
    let rows = audit["responses"].as_array().unwrap();
    assert_eq!(rows.len(), 1);
    let file = &rows[0]["body"];
    assert_eq!(file["format"], format);
    assert_eq!(
        bytes(context, file["path"].as_str().unwrap()).await,
        expected
    );
    let file: dag_core::value::FileRef = serde_json::from_value(file.clone()).unwrap();
    let fingerprint = file.fingerprint.unwrap();
    assert_eq!(fingerprint.size, expected.len() as u64);
    assert_eq!(
        fingerprint.content_hash.unwrap(),
        format!("sha256:{:x}", Sha256::digest(expected))
    );
    assert!(!fingerprint.immutable_remote);
    assert_eq!(
        audit["audit_kind"],
        "LOOKUP_RECEIPT_NOT_EVIDENCE_PUBLICATION"
    );
    assert_eq!(audit["g0_granted"], false);
}

#[tokio::test]
async fn both_directions_publish_evidence_and_exact_response_snapshots() {
    for (direction, nested, expected_origin) in [
        (CitationDirection::Citing, "citingPaper", "s2-citations"),
        (CitationDirection::Cited, "citedPaper", "s2-references"),
    ] {
        let raw = serde_json::to_vec(&json!({"offset":0,"next":2,"data":[{
            nested:{"paperId":"a","title":"Synthetic title","year":2020,"abstract":"full abstract"},
            "contexts":["one","two","three","four retained in raw body"],
            "intents":["methodology"],"isInfluential":true
        }]}))
        .unwrap();
        let (context, mut node, replay) = fixture(raw.clone(), 200, "application/json", direction);
        let outputs = node
            .execute(&context, &[], &NodeReporter::noop())
            .await
            .unwrap();
        assert_eq!(outputs.len(), 1);
        let file = outputs.get(&0).unwrap().as_file().unwrap();
        let saved = bytes(&context, &file.path).await;
        let evidence = EvidenceSet::parse(&saved).unwrap();
        assert_eq!(evidence.records.len(), 1);
        assert_eq!(evidence.records[0].citation.title, "Synthetic title");
        assert_eq!(evidence.records[0].citation.year, Some(2020));
        assert_eq!(evidence.records[0].origin.as_deref(), Some(expected_origin));
        assert!(
            evidence.records[0]
                .note
                .as_ref()
                .unwrap()
                .contains("synthetic provenance")
        );
        assert_eq!(
            file.fingerprint.as_ref().unwrap().content_hash.as_deref(),
            Some(format!("sha256:{:x}", Sha256::digest(saved)).as_str())
        );
        let receipt = audit(&context).await;
        assert_eq!(receipt["outcome"], "RECORDS");
        assert_eq!(receipt["records_received"], 1);
        assert_eq!(receipt["responses"][0]["status"], 200);
        check_body(&context, &receipt, &raw, "json").await;
        assert_eq!(replay.calls.load(Ordering::SeqCst), 1);
    }
}

#[tokio::test]
async fn errors_keep_exact_json_text_and_non_utf8_bodies_without_success_artifacts() {
    for (body, status, mime, format) in [
        (
            b"<html>synthetic failure</html>".to_vec(),
            500,
            "text/html",
            "txt",
        ),
        (
            br#"{"offset":0,"data":[],"error":"synthetic failure"}"#.to_vec(),
            200,
            "application/json",
            "json",
        ),
        (vec![255, 0, 254], 200, "application/json", "binary"),
    ] {
        let (context, mut node, _) = fixture(body.clone(), status, mime, CitationDirection::Citing);
        assert!(
            node.execute(&context, &[], &NodeReporter::noop())
                .await
                .is_err()
        );
        let receipt = audit(&context).await;
        assert_eq!(receipt["outcome"], "LOOKUP_ERROR");
        assert!(receipt["records_received"].is_null());
        assert_eq!(receipt["responses"][0]["status"], status);
        assert_eq!(receipt["responses"][0]["content_type"], mime);
        check_body(&context, &receipt, &body, format).await;
        assert!(
            crate::nodes::read_file_bytes(&context, "vfs:///citation-result.json")
                .await
                .is_err()
        );
    }
}

#[tokio::test]
async fn valid_empty_page_is_recorded_without_claiming_an_invalid_identifier() {
    let raw = br#"{"offset":0,"data":[]}"#.to_vec();
    let (context, mut node, _) = fixture(
        raw.clone(),
        200,
        "application/json",
        CitationDirection::Citing,
    );
    let error = node
        .execute(&context, &[], &NodeReporter::noop())
        .await
        .unwrap_err();
    assert!(
        error
            .to_string()
            .contains("does not establish an invalid paper id")
    );
    let receipt = audit(&context).await;
    assert_eq!(receipt["outcome"], "VALID_EMPTY_PAGE");
    assert_eq!(receipt["records_received"], 0);
    check_body(&context, &receipt, &raw, "json").await;
}

#[tokio::test]
async fn existing_evidence_or_query_receipt_blocks_before_lookup_without_overwriting() {
    for path in [
        "/citation-result.json",
        "/citation-result.json.citation-query.json",
    ] {
        let (context, mut node, replay) = fixture(
            b"{}".to_vec(),
            200,
            "application/json",
            CitationDirection::Citing,
        );
        context
            .opendal
            .as_ref()
            .unwrap()
            .write_bytes(path, b"protected original".to_vec())
            .await
            .unwrap();
        let error = node
            .execute(&context, &[], &NodeReporter::noop())
            .await
            .unwrap_err();
        assert!(
            error
                .to_string()
                .contains("existing output not overwritten")
        );
        assert_eq!(replay.calls.load(Ordering::SeqCst), 0);
        assert_eq!(bytes(&context, path).await, b"protected original");
    }
}

#[tokio::test]
async fn recorded_authentication_failure_is_preserved_without_anonymous_retry() {
    let (context, mut node, replay) = fixture(
        b"synthetic authentication rejection".to_vec(),
        403,
        "text/plain",
        CitationDirection::Citing,
    );
    assert!(
        node.execute(&context, &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(replay.calls.load(Ordering::SeqCst), 1);
    let receipt = audit(&context).await;
    assert_eq!(receipt["responses"][0]["status"], 403);
    assert!(
        !serde_json::to_string(&receipt)
            .unwrap()
            .contains("synthetic-not-an-operator-key")
    );
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn fresh_publication_does_not_clobber_when_writers_race() {
    let (context, _, _) = fixture(
        b"{}".to_vec(),
        200,
        "application/json",
        CitationDirection::Citing,
    );
    let barrier = Arc::new(tokio::sync::Barrier::new(2));
    let mut workers = Vec::new();
    for body in [b"first".to_vec(), b"second".to_vec()] {
        let context = context.clone();
        let barrier = barrier.clone();
        workers.push(tokio::spawn(async move {
            barrier.wait().await;
            write_artifact(&context, "vfs:///raced.json", body, "txt").await
        }));
    }
    let first = workers.remove(0).await.unwrap();
    let second = workers.remove(0).await.unwrap();
    assert_ne!(first.is_ok(), second.is_ok());
    let expected = if first.is_ok() {
        b"first".to_vec()
    } else {
        b"second".to_vec()
    };
    assert_eq!(bytes(&context, "vfs:///raced.json").await, expected);
}

#[cfg(unix)]
#[tokio::test]
async fn symlink_destinations_are_rejected_without_touching_the_target() {
    let root = tempfile::tempdir().unwrap();
    let target = root.path().join("protected.txt");
    std::fs::write(&target, b"original").unwrap();
    let alias = root.path().join("alias.txt");
    std::os::unix::fs::symlink(&target, &alias).unwrap();
    let context = NodeCtx::new(
        datafusion::prelude::SessionContext::new().runtime_env(),
        None,
    );
    assert!(
        write_artifact(
            &context,
            alias.to_str().unwrap(),
            b"replacement".to_vec(),
            "txt"
        )
        .await
        .is_err()
    );
    assert_eq!(std::fs::read(target).unwrap(), b"original");
}
