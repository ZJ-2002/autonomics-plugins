use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};

use bib_base::LiteratureGateway;
use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_fetch::{LiteratureFetchNode, LiteratureFetchSpec};
use nodes_bib_base::nodes::literature_search::{LiteratureSearchNode, LiteratureSearchSpec};
use bib_base::query::PubmedSource;
use bib_types::StructuredSearch;
use dag_core::dag::runtime::{InputHashing, SchedulerConfig};
use dag_core::dag::{DAG, DagNode};
use dag_core::registry::NodeCtx;
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};

const KEY: &str = "synthetic-ncbi-secret";

struct Fixture {
    client: Arc<eutils::EutilsClient>,
    requests: Arc<Mutex<Vec<String>>>,
    stopped: Arc<AtomicBool>,
    worker: Option<std::thread::JoinHandle<()>>,
}

impl Fixture {
    fn new() -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let stopped = Arc::new(AtomicBool::new(false));
        let requests = Arc::new(Mutex::new(Vec::new()));
        let worker_stopped = stopped.clone();
        let worker_requests = requests.clone();
        let worker = std::thread::spawn(move || {
            while !worker_stopped.load(Ordering::SeqCst) {
                let Ok((mut socket, _)) = listener.accept() else {
                    std::thread::sleep(std::time::Duration::from_millis(2));
                    continue;
                };
                socket
                    .set_read_timeout(Some(std::time::Duration::from_secs(2)))
                    .unwrap();
                let mut request = Vec::new();
                let mut buffer = [0u8; 4096];
                while !request.windows(4).any(|window| window == b"\r\n\r\n") {
                    let size = socket.read(&mut buffer).unwrap();
                    assert!(size > 0);
                    request.extend_from_slice(&buffer[..size]);
                }
                worker_requests
                    .lock()
                    .unwrap()
                    .push(String::from_utf8(request).unwrap());
                let body = format!("invalid credential {KEY}");
                let response = format!(
                    "HTTP/1.1 403 Forbidden\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                );
                socket.write_all(response.as_bytes()).unwrap();
            }
        });
        Self {
            client: Arc::new(
                eutils::EutilsClient::new("fixture", "fixture@localhost", Some(KEY))
                    .with_base_url(&endpoint),
            ),
            requests,
            stopped,
            worker: Some(worker),
        }
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        self.stopped.store(true, Ordering::SeqCst);
        self.worker.take().unwrap().join().unwrap();
    }
}

async fn run(tag: &str, fetch: bool) {
    let fixture = Fixture::new();
    let root = std::env::var_os("PUBMED_CREDENTIAL_DAG_EVIDENCE_ROOT")
        .map(std::path::PathBuf::from)
        .map(|path| path.join(tag));
    let storage = if let Some(root) = &root {
        assert!(!root.exists());
        std::fs::create_dir_all(root).unwrap();
        vfs::OpendalFileStorage::new(root.join("vfs"))
    } else {
        vfs::OpendalFileStorage::new_temp()
    };
    let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(Arc::new(storage)));
    let mut gateway = LiteratureGateway::new();
    gateway.add_source(Arc::new(PubmedSource::new(fixture.client.clone())));
    let gateway = Arc::new(gateway);
    let (kind, spec, node): (&str, Value, Box<dyn DagNode>) = if fetch {
        let spec = json!({"id_kind":"pmid","id_value":"30400809","sources":["pubmed"],"path":"/evidence.json"});
        let parsed: LiteratureFetchSpec = serde_json::from_value(spec.clone()).unwrap();
        (
            "source_literature_fetch",
            spec,
            Box::new(LiteratureFetchNode::with_gateway(parsed, gateway)),
        )
    } else {
        let spec = LiteratureSearchSpec {
            query: StructuredSearch {
                keywords: Some(vec!["fixture".into()]),
                ..Default::default()
            },
            limit: Some(1),
            sources: Some(vec!["pubmed".into()]),
            path: "/evidence.json".into(),
            note: None,
        };
        (
            "source_literature",
            json!({"query":{"keywords":["fixture"]},"limit":1,"sources":["pubmed"],"path":"/evidence.json"}),
            Box::new(LiteratureSearchNode::with_gateway(spec, gateway)),
        )
    };
    let mut dag = DAG::default();
    dag.add_node_with_spec("source".into(), node, kind.into(), spec)
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
    let report = serde_json::to_value(report).unwrap();
    let snapshot = serde_json::to_value(dag.tui_snapshot()).unwrap();
    if let Some(root) = &root {
        std::fs::write(
            root.join("run-report.json"),
            serde_json::to_vec_pretty(&report).unwrap(),
        )
        .unwrap();
        std::fs::write(
            root.join("dag.json"),
            serde_json::to_vec_pretty(&snapshot).unwrap(),
        )
        .unwrap();
    }
    assert_eq!(report["ok"], false);
    let statuses = report["nodes"]
        .as_array()
        .unwrap()
        .iter()
        .map(|node| {
            (
                node["id"].as_str().unwrap(),
                node["status"].as_str().unwrap(),
            )
        })
        .collect::<std::collections::BTreeMap<_, _>>();
    assert_eq!(
        statuses,
        std::collections::BTreeMap::from([("source", "failed"), ("merge", "skipped")])
    );
    assert!(!serde_json::to_string(&report).unwrap().contains(KEY));
    assert!(!serde_json::to_string(&snapshot).unwrap().contains(KEY));
    assert!(
        report["nodes"]
            .as_array()
            .unwrap()
            .iter()
            .all(|node| node["output_files"].as_array().unwrap().is_empty())
    );
    let storage = context.opendal.as_ref().unwrap();
    for path in ["/evidence.json", "/merged.json"] {
        assert!(
            !storage
                .resolve(path)
                .exists(&storage.resolve_path(path))
                .await
                .unwrap()
        );
    }
    if fetch {
        let path = "/evidence.json.fetch-attempts.json";
        let bytes = storage
            .resolve(path)
            .read(&storage.resolve_path(path))
            .await
            .unwrap()
            .to_vec();
        assert!(!String::from_utf8_lossy(&bytes).contains(KEY));
        let attempts: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(attempts["attempts"][0]["status"], "BACKEND_ERROR");
    }
    let requests = fixture.requests.lock().unwrap();
    assert_eq!(requests.len(), 1);
    assert!(requests[0].contains(&format!("api_key={KEY}")));
}

#[tokio::test]
async fn fetch_authentication_error_does_not_leak_into_report_or_publish() {
    run("fetch", true).await;
}

#[tokio::test]
async fn search_authentication_error_does_not_leak_into_report_or_publish() {
    run("search", false).await;
}
