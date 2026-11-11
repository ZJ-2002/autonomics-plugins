use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};

use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_fetch::{LiteratureFetchNode, LiteratureFetchSpec};
use nodes_bib_base::nodes::literature_search::{LiteratureSearchNode, LiteratureSearchSpec};
use bib_base::{LiteratureGateway, S2Source};
use bib_types::EvidenceSet;
use dag_core::NodeCtx;
use dag_core::dag::runtime::{InputHashing, SchedulerConfig};
use dag_core::dag::{DAG, DagNode};
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};

const PAPER_ID: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const NOTE: &str = "Synthetic abstract contract fixture, not official live research evidence";
static ENDPOINT_LOCK: tokio::sync::Mutex<()> = tokio::sync::Mutex::const_new(());

struct Fixture {
    client: Arc<semantic_scholar::S2Client>,
    requests: Arc<Mutex<Vec<String>>>,
    stopped: Arc<AtomicBool>,
    worker: Option<std::thread::JoinHandle<()>>,
    previous_endpoint: Option<std::ffi::OsString>,
}

impl Fixture {
    fn new(body: String) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let previous_endpoint = std::env::var_os("ENDPOINT_S2_GRAPH_URL");
        unsafe {
            std::env::set_var(
                "ENDPOINT_S2_GRAPH_URL",
                format!("http://{}", listener.local_addr().unwrap()),
            );
        }
        let requests = Arc::new(Mutex::new(Vec::new()));
        let stopped = Arc::new(AtomicBool::new(false));
        let captured = requests.clone();
        let cancelled = stopped.clone();
        let worker = std::thread::spawn(move || {
            while !cancelled.load(Ordering::SeqCst) {
                match listener.accept() {
                    Ok((mut socket, _)) => {
                        socket
                            .set_read_timeout(Some(std::time::Duration::from_secs(3)))
                            .unwrap();
                        let mut bytes = Vec::new();
                        let mut buffer = [0u8; 4096];
                        while !bytes.windows(4).any(|window| window == b"\r\n\r\n") {
                            let size = socket.read(&mut buffer).unwrap();
                            assert!(size > 0);
                            bytes.extend_from_slice(&buffer[..size]);
                        }
                        let request = String::from_utf8(bytes).unwrap();
                        assert!(!request.to_ascii_lowercase().contains("x-api-key:"));
                        captured.lock().unwrap().push(request);
                        write!(socket, "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).unwrap();
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        std::thread::sleep(std::time::Duration::from_millis(2));
                    }
                    Err(error) => panic!("fixture accept failed: {error}"),
                }
            }
        });
        Self {
            client: Arc::new(semantic_scholar::S2Client::with_client(
                reqwest::Client::builder()
                    .no_proxy()
                    .timeout(std::time::Duration::from_secs(5))
                    .build()
                    .unwrap(),
            )),
            requests,
            stopped,
            worker: Some(worker),
            previous_endpoint,
        }
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        self.stopped.store(true, Ordering::SeqCst);
        self.worker.take().unwrap().join().unwrap();
        unsafe {
            match &self.previous_endpoint {
                Some(previous) => std::env::set_var("ENDPOINT_S2_GRAPH_URL", previous),
                None => std::env::remove_var("ENDPOINT_S2_GRAPH_URL"),
            }
        }
    }
}

async fn run(tag: &str, fetch: bool, missing: bool) {
    let _endpoint_guard = ENDPOINT_LOCK.lock().await;
    let mut paper: Value = serde_json::from_str(include_str!(
        "fixtures/paper_abstract.json"
    ))
    .unwrap();
    let expected = paper["abstract"].as_str().unwrap().to_owned();
    if missing {
        if fetch {
            paper.as_object_mut().unwrap().remove("abstract");
        } else {
            paper["abstract"] = Value::Null;
        }
    }
    let body = if fetch {
        paper.clone()
    } else {
        json!({"total": 1, "token": null, "data": [paper]})
    };
    let fixture = Fixture::new(body.to_string());
    let root = std::env::var_os("S2_ABSTRACT_DAG_EVIDENCE_ROOT")
        .map(std::path::PathBuf::from)
        .map(|root| root.join(tag));
    let storage = match &root {
        Some(root) => {
            assert!(!root.exists(), "must not overwrite previous evidence");
            std::fs::create_dir_all(root.join("vfs")).unwrap();
            vfs::OpendalFileStorage::new(root.join("vfs"))
        }
        None => vfs::OpendalFileStorage::new_temp(),
    };
    let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(Arc::new(storage)));
    let mut gateway = LiteratureGateway::new();
    gateway.add_source(Arc::new(S2Source::new(fixture.client.clone())));
    let gateway = Arc::new(gateway);
    let (kind, configuration, node): (&str, Value, Box<dyn DagNode>) = if fetch {
        let configuration = json!({
            "id_kind": "s2", "id_value": PAPER_ID, "sources": ["semantic_scholar"],
            "path": "/source.json", "note": NOTE,
        });
        let spec: LiteratureFetchSpec = serde_json::from_value(configuration.clone()).unwrap();
        (
            "source_literature_fetch",
            configuration,
            Box::new(LiteratureFetchNode::with_gateway(spec, gateway)),
        )
    } else {
        let configuration = json!({
            "query": {"keywords": ["fixture"]}, "limit": 1,
            "sources": ["semantic_scholar"], "path": "/source.json", "note": NOTE,
        });
        let spec: LiteratureSearchSpec = serde_json::from_value(configuration.clone()).unwrap();
        (
            "source_literature",
            configuration,
            Box::new(LiteratureSearchNode::with_gateway(spec, gateway)),
        )
    };
    let mut dag = DAG::default();
    dag.add_node_with_spec("source".into(), node, kind.into(), configuration.clone())
        .unwrap();
    dag.add_node_with_spec(
        "merge".into(),
        Box::new(EvidenceMergeNode::new(EvidenceMergeSpec {
            path: "/merge.json".into(),
        })),
        "evidence_merge".into(),
        json!({"path": "/merge.json"}),
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
    let requests = fixture.requests.lock().unwrap().clone();
    assert_eq!(requests.len(), 1);
    let target = requests[0]
        .lines()
        .next()
        .unwrap()
        .split_whitespace()
        .nth(1)
        .unwrap();
    let request = reqwest::Url::parse(&format!("http://fixture{target}")).unwrap();
    if let Some(root) = &root {
        for (name, value) in [
            ("run-report.json", report.clone()),
            ("input-spec.json", configuration),
            ("response-body.json", body),
            ("request.json", json!({"target": target})),
            (
                "dag.json",
                serde_json::to_value(dag.tui_snapshot()).unwrap(),
            ),
        ] {
            std::fs::write(root.join(name), serde_json::to_vec_pretty(&value).unwrap()).unwrap();
        }
        let source = report["nodes"]
            .as_array()
            .unwrap()
            .iter()
            .find(|node| node["id"] == "source")
            .unwrap();
        std::fs::copy(
            source["execution"]["task_manifest"]["path"]
                .as_str()
                .unwrap(),
            root.join("actual-source-task.json"),
        )
        .unwrap();
    }
    assert_eq!(report["ok"], true);
    assert!(
        report["nodes"]
            .as_array()
            .unwrap()
            .iter()
            .all(|node| node["status"] == "success")
    );
    let parameters = request
        .query_pairs()
        .into_owned()
        .collect::<std::collections::BTreeMap<_, _>>();
    assert!(
        parameters["fields"]
            .split(',')
            .any(|field| field == "abstract")
    );
    assert_eq!(
        request.path(),
        if fetch {
            format!("/paper/{PAPER_ID}")
        } else {
            "/paper/search/bulk".into()
        }
    );
    let storage = context.opendal.as_ref().unwrap();
    for path in ["/source.json", "/merge.json"] {
        let bytes = storage
            .resolve(path)
            .read(&storage.resolve_path(path))
            .await
            .unwrap();
        let evidence = EvidenceSet::parse(&bytes.to_vec()).unwrap();
        assert_eq!(evidence.records.len(), 1);
        let record = &evidence.records[0];
        assert_eq!(record.citation.id, format!("s2:{PAPER_ID}"));
        assert_eq!(record.note.as_deref(), Some(NOTE));
        assert_eq!(record.origin.as_deref(), Some("semantic_scholar"));
        assert_eq!(
            record.citation.abstract_text.as_deref(),
            (!missing).then_some(expected.as_str())
        );
    }
}

#[tokio::test]
async fn search_dag_preserves_official_abstract() {
    run("search_dag_preserves_official_abstract", false, false).await;
}

#[tokio::test]
async fn fetch_dag_preserves_official_abstract() {
    run("fetch_dag_preserves_official_abstract", true, false).await;
}

#[tokio::test]
async fn search_null_abstract_control_is_not_invented() {
    run("search_null_abstract_control_is_not_invented", false, true).await;
}

#[tokio::test]
async fn fetch_missing_abstract_control_is_not_invented() {
    run("fetch_missing_abstract_control_is_not_invented", true, true).await;
}
