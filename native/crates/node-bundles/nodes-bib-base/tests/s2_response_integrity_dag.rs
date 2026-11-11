use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};

use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_fetch::{LiteratureFetchNode, LiteratureFetchSpec};
use nodes_bib_base::nodes::literature_search::{LiteratureSearchNode, LiteratureSearchSpec};
use bib_base::{LiteratureGateway, LiteratureSource, S2Source};
use bib_types::{EvidenceSet, StructuredSearch};
use dag_core::NodeCtx;
use dag_core::dag::runtime::{InputHashing, SchedulerConfig};
use dag_core::dag::{DAG, DagNode};
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};

const DOI: &str = "10.1234/s2-response-fixture";
const NOTE: &str = "Synthetic response integrity fixture, not official research results";
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

fn response(tag: &str) -> (Value, bool, bool, u32, usize) {
    let mut paper: Value = serde_json::from_str(include_str!(
        "fixtures/paper_abstract.json"
    ))
    .unwrap();
    paper["externalIds"] = json!({"DOI": DOI});
    let fetch = tag.contains("fetch");
    let rejected = tag.ends_with("_rejected");
    if tag.starts_with("missing_id") {
        paper.as_object_mut().unwrap().remove("paperId");
    } else if tag.starts_with("empty_id") {
        paper["paperId"] = json!("");
    } else if tag.starts_with("blank_id") {
        paper["paperId"] = json!(" \t ");
    } else if tag.starts_with("control_id") {
        paper["paperId"] = json!("fixture\nidentifier");
    }
    if fetch {
        return (paper, true, !rejected, 1, 1);
    }
    let mut body = json!({"total": 1, "token": null, "data": [paper.clone()]});
    let mut limit = 1;
    let mut records = 1;
    match tag {
        "string_total_search_valid" => body["total"] = json!("1"),
        "negative_total_search_rejected" => body["total"] = json!(-1),
        "missing_total_search_rejected" => {
            body.as_object_mut().unwrap().remove("total");
        }
        "missing_data_search_rejected" => {
            body.as_object_mut().unwrap().remove("data");
        }
        "tail_invalid_id_search_rejected" => {
            let mut tail = paper.clone();
            tail["paperId"] = json!("");
            body["total"] = json!(2);
            body["data"] = json!([paper, tail]);
        }
        "empty_search_valid" => {
            body["total"] = json!(0);
            body["data"] = json!([]);
            records = 0;
        }
        "approximate_total_search_valid" | "limited_page_search_valid" => {
            let mut second = paper.clone();
            second["paperId"] = json!("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
            second["externalIds"] = json!({"DOI": "10.1234/s2-response-second-fixture"});
            body["data"] = json!([paper, second]);
            if tag == "approximate_total_search_valid" {
                limit = 2;
                records = 2;
            } else {
                body["total"] = json!(999);
            }
        }
        "duplicate_page_search_valid" => {
            body["total"] = json!(2);
            body["data"] = json!([paper.clone(), paper]);
            limit = 2;
        }
        _ => {}
    }
    (body, false, !rejected, limit, records)
}

async fn run(tag: &str) {
    let _endpoint_guard = ENDPOINT_LOCK.lock().await;
    let (body, fetch, expected_ok, limit, records) = response(tag);
    let fixture = Fixture::new(body.to_string());
    let root = std::env::var_os("S2_RESPONSE_DAG_EVIDENCE_ROOT")
        .map(std::path::PathBuf::from)
        .map(|root| root.join(tag));
    let storage = match &root {
        Some(root) => {
            assert!(!root.exists(), "must not overwrite earlier proof artifacts");
            std::fs::create_dir_all(root.join("vfs")).unwrap();
            vfs::OpendalFileStorage::new(root.join("vfs"))
        }
        None => vfs::OpendalFileStorage::new_temp(),
    };
    let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(Arc::new(storage)));
    let source = Arc::new(S2Source::new(fixture.client.clone()));
    let mut gateway = LiteratureGateway::new();
    gateway.add_source(source.clone());
    let gateway = Arc::new(gateway);
    let (kind, configuration, node): (&str, Value, Box<dyn DagNode>) = if fetch {
        let configuration = json!({"id_kind": "doi", "id_value": DOI, "sources": ["semantic_scholar"], "path": "/source.json", "note": NOTE});
        let spec: LiteratureFetchSpec = serde_json::from_value(configuration.clone()).unwrap();
        (
            "source_literature_fetch",
            configuration,
            Box::new(LiteratureFetchNode::with_gateway(spec, gateway)),
        )
    } else {
        let configuration = json!({"query": {"keywords": ["fixture"]}, "limit": limit, "sources": ["semantic_scholar"], "path": "/source.json", "note": NOTE});
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
    let probe = if tag == "approximate_total_search_valid" {
        let result = source
            .search(
                &StructuredSearch {
                    keywords: Some(vec!["fixture".into()]),
                    ..Default::default()
                },
                2,
            )
            .await
            .unwrap();
        Some(
            json!({"total": result.total, "articles": result.articles.len(), "source": result.source}),
        )
    } else {
        None
    };
    let requests = fixture.requests.lock().unwrap().clone();
    assert_eq!(requests.len(), if probe.is_some() { 2 } else { 1 });
    if let Some(root) = &root {
        for (name, value) in [
            ("run-report.json", report.clone()),
            ("input-spec.json", configuration),
            ("response-body.json", body),
            ("requests.json", json!(requests)),
            (
                "dag.json",
                serde_json::to_value(dag.tui_snapshot()).unwrap(),
            ),
            (
                "expected-contract.json",
                json!({"ok": expected_ok, "records": records, "fetch": fetch}),
            ),
        ] {
            std::fs::write(root.join(name), serde_json::to_vec_pretty(&value).unwrap()).unwrap();
        }
        if let Some(probe) = &probe {
            std::fs::write(
                root.join("approximate-total-probe.json"),
                serde_json::to_vec_pretty(probe).unwrap(),
            )
            .unwrap();
        }
        let task = report["nodes"]
            .as_array()
            .unwrap()
            .iter()
            .find(|node| node["id"] == "source")
            .unwrap();
        std::fs::copy(
            task["execution"]["task_manifest"]["path"].as_str().unwrap(),
            root.join("actual-source-task.json"),
        )
        .unwrap();
        for node in report["nodes"].as_array().unwrap() {
            if let Some(execution) = node["execution"].as_object() {
                for stream in ["stdout", "stderr"] {
                    if let Some(path) = execution
                        .get(&format!("{stream}_log"))
                        .and_then(|reference| reference.get("path"))
                        .and_then(Value::as_str)
                    {
                        std::fs::copy(
                            path,
                            root.join(format!("{}-{stream}.txt", node["id"].as_str().unwrap())),
                        )
                        .unwrap();
                    }
                }
            }
        }
    }
    assert_eq!(report["ok"], expected_ok);
    let nodes = report["nodes"].as_array().unwrap();
    for node in nodes {
        assert_eq!(
            node["status"],
            if expected_ok {
                "success"
            } else if node["id"] == "source" {
                "failed"
            } else {
                "skipped"
            }
        );
        if !expected_ok {
            assert!(node["output_files"].as_array().is_none_or(Vec::is_empty));
        }
    }
    if expected_ok {
        let storage = context.opendal.as_ref().unwrap();
        for path in ["/source.json", "/merge.json"] {
            let bytes = storage
                .resolve(path)
                .read(&storage.resolve_path(path))
                .await
                .unwrap();
            let evidence = EvidenceSet::parse(&bytes.to_vec()).unwrap();
            assert_eq!(evidence.records.len(), records);
            for record in &evidence.records {
                assert_eq!(record.origin.as_deref(), Some("semantic_scholar"));
                assert_eq!(record.note.as_deref(), Some(NOTE));
                assert!(record.citation.id.starts_with("doi:10.1234/s2-response-"));
                assert!(
                    record
                        .citation
                        .abstract_text
                        .as_deref()
                        .unwrap()
                        .starts_with("Synthetic résumé")
                );
            }
        }
    }
    if let Some(probe) = probe {
        assert_eq!(
            probe,
            json!({"total": 1, "articles": 2, "source": "semantic_scholar"})
        );
    }
}

macro_rules! case {
    ($name:ident) => {
        #[tokio::test]
        async fn $name() {
            run(stringify!($name)).await;
        }
    };
}

case!(string_total_search_valid);
case!(negative_total_search_rejected);
case!(missing_total_search_rejected);
case!(missing_data_search_rejected);
case!(missing_id_search_rejected);
case!(empty_id_search_rejected);
case!(blank_id_search_rejected);
case!(control_id_search_rejected);
case!(tail_invalid_id_search_rejected);
case!(missing_id_fetch_rejected);
case!(empty_id_fetch_rejected);
case!(blank_id_fetch_rejected);
case!(numeric_search_valid);
case!(empty_search_valid);
case!(approximate_total_search_valid);
case!(limited_page_search_valid);
case!(duplicate_page_search_valid);
case!(numeric_fetch_valid);
