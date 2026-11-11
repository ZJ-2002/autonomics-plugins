use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};

use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_fetch::{LiteratureFetchNode, LiteratureFetchSpec};
use bib_base::{LiteratureGateway, OpenAlexSource};
use bib_types::{EvidenceSet, IdKind};
use dag_core::dag::DAG;
use dag_core::dag::runtime::{InputHashing, SchedulerConfig};
use dag_core::registry::NodeCtx;
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};

struct Reply {
    status: u16,
    location: Option<String>,
    body: Value,
}

fn work(identifier: &str) -> Reply {
    Reply {
        status: 200,
        location: None,
        body: json!({"id":format!("https://openalex.org/{identifier}"),"title":"Synthetic redirect fixture"}),
    }
}

fn redirect(location: &str) -> Reply {
    Reply {
        status: 301,
        location: Some(location.to_string()),
        body: json!({}),
    }
}

fn absent() -> Reply {
    Reply {
        status: 404,
        location: None,
        body: json!({"error":"synthetic missing record"}),
    }
}

struct Fixture {
    client: Arc<openalex::OpenAlexClient>,
    requests: Arc<Mutex<Vec<String>>>,
    stopped: Arc<AtomicBool>,
    worker: Option<std::thread::JoinHandle<()>>,
    replies: Vec<Value>,
    base: String,
}

impl Fixture {
    fn new(replies: Vec<Reply>) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let requests = Arc::new(Mutex::new(Vec::new()));
        let stopped = Arc::new(AtomicBool::new(false));
        let observed = requests.clone();
        let cancellation = stopped.clone();
        let reply_values = replies
            .iter()
            .map(|reply| {
                json!({
                    "status":reply.status,"location":reply.location,"body":reply.body
                })
            })
            .collect();
        let worker = std::thread::spawn(move || {
            for reply in replies {
                let mut stream = loop {
                    if cancellation.load(Ordering::SeqCst) {
                        return;
                    }
                    match listener.accept() {
                        Ok((stream, _)) => break stream,
                        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                            std::thread::sleep(std::time::Duration::from_millis(1));
                        }
                        Err(error) => panic!("fixture accept: {error}"),
                    }
                };
                stream
                    .set_read_timeout(Some(std::time::Duration::from_secs(5)))
                    .unwrap();
                let mut request = Vec::new();
                let mut buffer = [0u8; 1024];
                while !request.windows(4).any(|window| window == b"\r\n\r\n") {
                    let received = stream.read(&mut buffer).unwrap();
                    assert_ne!(received, 0);
                    request.extend_from_slice(&buffer[..received]);
                }
                let request = String::from_utf8(request).unwrap();
                assert!(!request.to_ascii_lowercase().contains("authorization:"));
                observed.lock().unwrap().push(request);
                let body = serde_json::to_vec(&reply.body).unwrap();
                let location = reply
                    .location
                    .map(|value| format!("Location: {value}\r\n"))
                    .unwrap_or_default();
                write!(stream,
                    "HTTP/1.1 {} fixture\r\nContent-Type: application/json\r\n{}Content-Length: {}\r\nConnection: close\r\n\r\n",
                    reply.status, location, body.len()).unwrap();
                stream.write_all(&body).unwrap();
            }
        });
        Self {
            client: Arc::new(openalex::OpenAlexClient::new(None).with_base_url(base.clone())),
            requests,
            stopped,
            worker: Some(worker),
            replies: reply_values,
            base,
        }
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        self.stopped.store(true, Ordering::SeqCst);
        if let Some(worker) = self.worker.take() {
            worker.join().unwrap();
        }
    }
}

async fn run(tag: &str, request: &str, fixture: &Fixture, canonical: Option<&str>, repaired: bool) {
    let phase = std::env::var("OPENALEX_MERGE_PROOF_PHASE").unwrap_or_else(|_| "after".into());
    assert!(phase == "before" || phase == "after");
    let expected_ok = canonical.is_some() && (!repaired || phase == "after");
    let root = std::env::var_os("OPENALEX_MERGE_DAG_EVIDENCE_ROOT")
        .map(std::path::PathBuf::from)
        .map(|root| root.join(tag));
    let storage = if let Some(root) = &root {
        assert!(!root.exists(), "fresh evidence directory required");
        std::fs::create_dir_all(root).unwrap();
        vfs::OpendalFileStorage::new(root.join("vfs"))
    } else {
        vfs::OpendalFileStorage::new_temp()
    };
    let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(Arc::new(storage)));
    let mut gateway = LiteratureGateway::new();
    gateway.add_source(Arc::new(OpenAlexSource::new(fixture.client.clone())));
    let configuration = json!({
        "id_kind":"openalex","id_value":request,"sources":["openalex"],
        "path":"/evidence.json","note":"Synthetic HTTP redirect contract; not a real study result"
    });
    let spec: LiteratureFetchSpec = serde_json::from_value(configuration.clone()).unwrap();
    let mut dag = DAG::default();
    dag.add_node_with_spec(
        "source".into(),
        Box::new(LiteratureFetchNode::with_gateway(spec, Arc::new(gateway))),
        "source_literature_fetch".into(),
        configuration.clone(),
    )
    .unwrap();
    dag.add_node_with_spec(
        "merge".into(),
        Box::new(EvidenceMergeNode::new(EvidenceMergeSpec {
            path: "/merged.json".into(),
        })),
        "evidence_merge".into(),
        json!({"path":"/merged.json"}),
    )
    .unwrap();
    dag.add_edge("source", "merge", 0, 0).unwrap();
    let report = dag
        .run(
            &SchedulerConfig {
                max_concurrency: 1,
                incremental: false,
                input_hashing: InputHashing::Content,
                compute_row_counts: false,
                memory_guard: None,
                ..SchedulerConfig::default()
            },
            &context,
            None,
        )
        .await
        .unwrap();
    let storage = context.opendal.as_ref().unwrap();
    let (source_operator, source_path) = (
        storage.resolve("/evidence.json"),
        storage.resolve_path("/evidence.json"),
    );
    let (merge_operator, merge_path) = (
        storage.resolve("/merged.json"),
        storage.resolve_path("/merged.json"),
    );
    let diagnostics = source_operator
        .read(&storage.resolve_path("/evidence.json.fetch-attempts.json"))
        .await
        .unwrap();
    let diagnostic_json: Value = serde_json::from_slice(&diagnostics.to_vec()).unwrap();
    let mut materialized = None;
    if report.ok {
        let source_bytes = source_operator.read(&source_path).await.unwrap().to_vec();
        let merged_bytes = merge_operator.read(&merge_path).await.unwrap().to_vec();
        let source = EvidenceSet::parse(&source_bytes).unwrap();
        let merged = EvidenceSet::parse(&merged_bytes).unwrap();
        assert_eq!(source.records.len(), 1);
        assert_eq!(merged.records.len(), 1);
        assert_eq!(source.records[0].citation, merged.records[0].citation);
        let article = &source.records[0].citation;
        assert_eq!(article.title, "Synthetic redirect fixture");
        let canonical = canonical.unwrap();
        assert!(
            article
                .identifiers
                .iter()
                .any(|identifier| identifier.kind == IdKind::OpenAlex
                    && identifier.value == canonical)
        );
        if repaired {
            assert!(article.identifiers.iter().any(|identifier| identifier.kind
                == IdKind::OpenAlex
                && identifier.value == "W111"));
        }
        materialized = Some(json!({"source":source,"merged":merged}));
    } else {
        assert!(!source_operator.exists(&source_path).await.unwrap());
        assert!(!merge_operator.exists(&merge_path).await.unwrap());
    }
    if let Some(root) = &root {
        for (name, value) in [
            ("run-report.json", serde_json::to_value(&report).unwrap()),
            (
                "dag.json",
                serde_json::to_value(dag.tui_snapshot()).unwrap(),
            ),
            ("input-spec.json", configuration),
            ("fixture-replies.json", json!(fixture.replies)),
            (
                "fixture-requests.json",
                json!(*fixture.requests.lock().unwrap()),
            ),
            ("fetch-attempts.json", diagnostic_json),
            ("materialized.json", json!(materialized)),
            (
                "expectation.json",
                json!({"phase":phase,"expected_ok":expected_ok,"canonical":canonical,"repair_case":repaired,"synthetic_HTTP":true}),
            ),
        ] {
            std::fs::write(root.join(name), serde_json::to_vec_pretty(&value).unwrap()).unwrap();
        }
    }
    assert_eq!(report.ok, expected_ok, "{tag}");
}

#[tokio::test]
async fn direct_canonical_work_succeeds() {
    let fixture = Fixture::new(vec![work("W111")]);
    run("direct", "W111", &fixture, Some("W111"), false).await;
}

#[tokio::test]
async fn lowercase_work_key_succeeds() {
    let fixture = Fixture::new(vec![work("W111")]);
    run("lowercase", "w111", &fixture, Some("W111"), false).await;
}

#[tokio::test]
async fn full_work_url_succeeds() {
    let fixture = Fixture::new(vec![work("W111")]);
    run(
        "full-url",
        "https://openalex.org/w111",
        &fixture,
        Some("W111"),
        false,
    )
    .await;
}

#[tokio::test]
async fn merged_work_301_preserves_requested_alias() {
    let fixture = Fixture::new(vec![redirect("/works/W222"), work("W222")]);
    run("merged-301", "W111", &fixture, Some("W222"), true).await;
}

#[tokio::test]
async fn merged_work_chain_preserves_requested_alias() {
    let fixture = Fixture::new(vec![
        redirect("/works/W222"),
        redirect("/works/W333"),
        work("W333"),
    ]);
    run("merged-chain", "W111", &fixture, Some("W333"), true).await;
}

#[tokio::test]
async fn mismatch_without_redirect_is_rejected() {
    let fixture = Fixture::new(vec![work("W222")]);
    run("wrong-body", "W111", &fixture, None, false).await;
}

#[tokio::test]
async fn redirect_to_wrong_entity_is_rejected() {
    let fixture = Fixture::new(vec![redirect("/authors/A222"), work("W222")]);
    run("wrong-entity", "W111", &fixture, None, false).await;
}

#[tokio::test]
async fn redirect_target_body_disagreement_is_rejected() {
    let fixture = Fixture::new(vec![redirect("/works/W222"), work("W333")]);
    run("wrong-target-body", "W111", &fixture, None, false).await;
}

#[tokio::test]
async fn cross_origin_redirect_is_rejected() {
    let destination = Fixture::new(vec![work("W222")]);
    let source = Fixture::new(vec![redirect(&format!("{}/works/W222", destination.base))]);
    run("cross-origin", "W111", &source, None, false).await;
}

#[tokio::test]
async fn missing_record_is_failed_not_empty_evidence() {
    let fixture = Fixture::new(vec![absent()]);
    run("missing", "W111", &fixture, None, false).await;
}

#[tokio::test]
async fn merged_missing_record_is_failed_not_empty_evidence() {
    let fixture = Fixture::new(vec![redirect("/works/W222"), absent()]);
    run("merged-missing", "W111", &fixture, None, false).await;
}
