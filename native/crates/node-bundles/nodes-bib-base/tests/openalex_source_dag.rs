use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};

use bib_base::LiteratureGateway;
use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_search::{LiteratureSearchNode, LiteratureSearchSpec};
use bib_base::query::OpenAlexSource;
use bib_types::{EvidenceSet, StructuredSearch};
use dag_core::dag::DAG;
use dag_core::dag::runtime::{InputHashing, SchedulerConfig};
use dag_core::registry::NodeCtx;
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};

struct Fixture {
    client: Arc<openalex::OpenAlexClient>,
    calls: Arc<Mutex<Vec<String>>>,
    stop: Arc<AtomicBool>,
    thread: Option<std::thread::JoinHandle<()>>,
    replies: Vec<Value>,
}

impl Fixture {
    fn new(replies: Vec<Value>) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let calls = Arc::new(Mutex::new(Vec::new()));
        let observed = calls.clone();
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = stop.clone();
        let responses = replies.clone();
        let thread = std::thread::spawn(move || {
            for reply in responses {
                let mut stream = loop {
                    if stopping.load(Ordering::SeqCst) {
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
                observed
                    .lock()
                    .unwrap()
                    .push(String::from_utf8(request).unwrap());
                let body = serde_json::to_vec(&reply).unwrap();
                let header = format!(
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    body.len()
                );
                stream.write_all(header.as_bytes()).unwrap();
                stream.write_all(&body).unwrap();
            }
        });
        Self {
            client: Arc::new(openalex::OpenAlexClient::new(None).with_base_url(base)),
            calls,
            stop,
            thread: Some(thread),
            replies,
        }
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        if let Some(thread) = self.thread.take() {
            thread.join().unwrap();
        }
    }
}

fn source(identifier: &str, name: &str) -> Value {
    json!({"id":format!("https://openalex.org/{identifier}"),"display_name":name,
        "type":"journal","alternate_titles":[],"abbreviated_title":null})
}

fn page(rows: Vec<Value>, count: usize, cursor: Option<&str>) -> Value {
    json!({"meta":{"count":count,"next_cursor":cursor},"results":rows})
}

async fn run(
    tag: &str,
    query: StructuredSearch,
    limit: u32,
    fixture: &Fixture,
    expected_ok: bool,
) -> Option<EvidenceSet> {
    let root = std::env::var_os("OPENALEX_DAG_EVIDENCE_ROOT")
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
    let spec = LiteratureSearchSpec {
        query,
        limit: Some(limit),
        sources: Some(vec!["openalex".into()]),
        path: "/evidence.json".into(),
        note: None,
    };
    let mut dag = DAG::default();
    dag.add_node_with_spec(
        "source".into(),
        Box::new(LiteratureSearchNode::with_gateway(spec, Arc::new(gateway))),
        "source_literature".into(),
        json!({"fixture":tag}),
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
    if let Some(root) = &root {
        for (name, value) in [
            ("run-report.json", serde_json::to_value(&report).unwrap()),
            (
                "dag.json",
                serde_json::to_value(dag.tui_snapshot()).unwrap(),
            ),
            ("fixture-replies.json", json!(fixture.replies)),
            (
                "fixture-requests.json",
                json!(*fixture.calls.lock().unwrap()),
            ),
        ] {
            std::fs::write(root.join(name), serde_json::to_vec_pretty(&value).unwrap()).unwrap();
        }
    }
    assert_eq!(report.ok, expected_ok);
    let storage = context.opendal.as_ref().unwrap();
    let read = |path: &str| (storage.resolve(path), storage.resolve_path(path));
    let (operator, path) = read("/merged.json");
    if !expected_ok {
        assert!(!operator.exists(&path).await.unwrap());
        let (operator, path) = read("/evidence.json");
        assert!(!operator.exists(&path).await.unwrap());
        return None;
    }
    let bytes = operator.read(&path).await.unwrap();
    Some(EvidenceSet::parse(&bytes.to_vec()).unwrap())
}

fn query(names: &[&str]) -> StructuredSearch {
    StructuredSearch {
        journal: Some(names.iter().map(|name| name.to_string()).collect()),
        ..Default::default()
    }
}

#[tokio::test]
async fn lower_ranked_exact_source_and_101_works_survive_actual_dag() {
    let works: Vec<Value> = (1..=101).map(|index| json!({"id":format!("https://openalex.org/W{index}"),
        "title":format!("Fixture {index}"),"authorships":[{"author":{"display_name":"Author Last"},"is_corresponding":true}]})).collect();
    let fixture = Fixture::new(vec![
        page(vec![source("S2", "Wrong"), source("S1", "Known")], 2, None),
        page(works[..100].to_vec(), 101, Some("next +/&=")),
        page(works[100..].to_vec(), 101, None),
    ]);
    let result = run("lower-exact-101", query(&["Known"]), 101, &fixture, true)
        .await
        .unwrap();
    assert_eq!(result.records.len(), 101);
    for (index, record) in result.records.iter().enumerate() {
        assert_eq!(record.citation.title, format!("Fixture {}", index + 1));
        assert!(record.citation.authors[0].corresponding);
    }
    assert_eq!(fixture.calls.lock().unwrap().len(), 3);
}

#[tokio::test]
async fn all_journals_resolved_without_dropping_or_component() {
    let fixture = Fixture::new(vec![
        page(vec![source("S1", "Known")], 1, None),
        page(vec![source("S2", "Other")], 1, None),
        page(
            vec![json!({"id":"https://openalex.org/W1","title":"Fixture"})],
            1,
            None,
        ),
    ]);
    assert_eq!(
        run(
            "all-journals",
            query(&["Known", "Other"]),
            5,
            &fixture,
            true
        )
        .await
        .unwrap()
        .records
        .len(),
        1
    );
    let request = fixture.calls.lock().unwrap()[2].clone();
    let target = request
        .lines()
        .next()
        .unwrap()
        .split_whitespace()
        .nth(1)
        .unwrap();
    let url = reqwest::Url::parse(&("http://fixture".to_owned() + target)).unwrap();
    assert_eq!(
        url.query_pairs()
            .find(|(name, _)| name == "filter")
            .unwrap()
            .1,
        "primary_location.source.id:S1|S2"
    );
}

#[tokio::test]
async fn ambiguous_exact_source_fails_and_blocks_merge() {
    let fixture = Fixture::new(vec![page(
        vec![source("S1", "Known"), source("S2", "Known")],
        2,
        None,
    )]);
    run("ambiguous", query(&["Known"]), 5, &fixture, false).await;
    assert_eq!(fixture.calls.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn unmatched_source_fails_and_blocks_merge() {
    let fixture = Fixture::new(vec![page(vec![source("S1", "Wrong")], 1, None)]);
    run("unmatched", query(&["Known"]), 5, &fixture, false).await;
    assert_eq!(fixture.calls.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn mesh_rejection_makes_no_provider_call_or_output() {
    let fixture = Fixture::new(vec![]);
    let mut query = query(&["Known"]);
    query.mesh = Some(vec!["Humans".into()]);
    run("mesh", query, 5, &fixture, false).await;
    assert!(fixture.calls.lock().unwrap().is_empty());
}

#[tokio::test]
async fn healthy_zero_results_produce_readable_empty_artifact() {
    let fixture = Fixture::new(vec![
        page(vec![source("S1", "Known")], 1, None),
        page(vec![], 0, None),
    ]);
    assert!(
        run("zero", query(&["Known"]), 5, &fixture, true)
            .await
            .unwrap()
            .records
            .is_empty()
    );
    assert_eq!(fixture.calls.lock().unwrap().len(), 2);
}
