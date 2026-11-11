use std::collections::BTreeMap;
use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::{
    Arc, Mutex,
    atomic::{AtomicBool, Ordering},
};

use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_search::{LiteratureSearchNode, LiteratureSearchSpec};
use bib_base::{LiteratureGateway, S2Source};
use bib_types::query::{BoolOp, YearRange};
use bib_types::{EvidenceSet, StructuredSearch};
use dag_core::NodeCtx;
use dag_core::dag::DAG;
use dag_core::dag::runtime::{InputHashing, SchedulerConfig};
use datafusion::prelude::SessionContext;
use semantic_scholar::client::PaperSearchFilter;
use serde_json::json;

const NOTE: &str = "Synthetic HTTP protocol fixture, not official search results";
const PAPER_ID: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
static ENDPOINT_LOCK: tokio::sync::Mutex<()> = tokio::sync::Mutex::const_new(());

struct Fixture {
    client: Arc<semantic_scholar::S2Client>,
    targets: Arc<Mutex<Vec<String>>>,
    stopped: Arc<AtomicBool>,
    worker: Option<std::thread::JoinHandle<()>>,
    previous_endpoint: Option<std::ffi::OsString>,
}

impl Fixture {
    fn new() -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let previous_endpoint = std::env::var_os("ENDPOINT_S2_GRAPH_URL");
        unsafe { std::env::set_var("ENDPOINT_S2_GRAPH_URL", endpoint) };
        let targets = Arc::new(Mutex::new(Vec::new()));
        let stopped = Arc::new(AtomicBool::new(false));
        let worker_targets = targets.clone();
        let worker_stopped = stopped.clone();
        let worker = std::thread::spawn(move || {
            while !worker_stopped.load(Ordering::SeqCst) {
                let Ok((mut socket, _)) = listener.accept() else {
                    std::thread::sleep(std::time::Duration::from_millis(2));
                    continue;
                };
                socket
                    .set_read_timeout(Some(std::time::Duration::from_secs(2)))
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
                let target = request
                    .lines()
                    .next()
                    .unwrap()
                    .split_whitespace()
                    .nth(1)
                    .unwrap()
                    .to_owned();
                worker_targets.lock().unwrap().push(target);
                let body = json!({
                    "total": 1, "offset": 0, "next": null, "token": null,
                    "data": [{"paperId": PAPER_ID, "title": "Fixture paper", "year": 2022}]
                })
                .to_string();
                let response = format!(
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
                    body.len()
                );
                socket.write_all(response.as_bytes()).unwrap();
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
            targets,
            stopped,
            worker: Some(worker),
            previous_endpoint,
        }
    }

    fn request(&self) -> reqwest::Url {
        let targets = self.targets.lock().unwrap();
        assert_eq!(targets.len(), 1);
        reqwest::Url::parse(&format!("http://fixture{}", targets[0])).unwrap()
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        self.stopped.store(true, Ordering::SeqCst);
        self.worker.take().unwrap().join().unwrap();
        unsafe {
            match &self.previous_endpoint {
                Some(value) => std::env::set_var("ENDPOINT_S2_GRAPH_URL", value),
                None => std::env::remove_var("ENDPOINT_S2_GRAPH_URL"),
            }
        }
    }
}

fn query(operator: BoolOp, mask: u8, keywords: bool) -> StructuredSearch {
    StructuredSearch {
        keywords: keywords.then(|| vec!["synthetic_alpha".into(), "synthetic_beta".into()]),
        keywords_op: keywords.then_some(operator),
        year_range: (mask & 1 != 0).then_some(YearRange {
            from: 2020,
            to: 2024,
        }),
        journal: (mask & 2 != 0).then(|| vec!["Nature".into()]),
        publication_types: (mask & 4 != 0).then(|| vec!["Review".into()]),
        ..Default::default()
    }
}

async fn run(tag: &str, operator: BoolOp, mask: u8, keywords: bool) {
    let _endpoint_guard = ENDPOINT_LOCK.lock().await;
    let fixture = Fixture::new();
    let root = std::env::var_os("S2_BULK_FILTER_EVIDENCE_ROOT")
        .map(|root| std::path::PathBuf::from(root).join(tag));
    let storage = match &root {
        Some(root) => {
            assert!(!root.exists(), "must not overwrite earlier proof artifacts");
            std::fs::create_dir_all(root.join("vfs")).unwrap();
            vfs::OpendalFileStorage::new(root.join("vfs"))
        }
        None => vfs::OpendalFileStorage::new_temp(),
    };
    let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(Arc::new(storage)));
    let mut gateway = LiteratureGateway::new();
    gateway.add_source(Arc::new(S2Source::new(fixture.client.clone())));
    let spec = LiteratureSearchSpec {
        query: query(operator, mask, keywords),
        limit: Some(1),
        sources: Some(vec!["semantic_scholar".into()]),
        path: "/source.json".into(),
        note: Some(NOTE.into()),
    };
    let configuration = json!({
        "query": spec.query, "limit": spec.limit, "sources": spec.sources,
        "path": spec.path, "note": spec.note,
    });
    let mut dag = DAG::default();
    dag.add_node_with_spec(
        "source".into(),
        Box::new(LiteratureSearchNode::with_gateway(spec, Arc::new(gateway))),
        "source_literature".into(),
        configuration.clone(),
    )
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
    let request = fixture.request();
    let pairs = request.query_pairs().into_owned().collect::<Vec<_>>();
    let parameters = pairs.iter().cloned().collect::<BTreeMap<_, _>>();
    assert_eq!(pairs.len(), parameters.len());
    if let Some(root) = &root {
        for (filename, value) in [
            ("run-report.json", report.clone()),
            ("input-spec.json", configuration.clone()),
            (
                "request.json",
                json!({"path": request.path(), "parameters": parameters}),
            ),
            (
                "dag.json",
                serde_json::to_value(dag.tui_snapshot()).unwrap(),
            ),
        ] {
            std::fs::write(
                root.join(filename),
                serde_json::to_vec_pretty(&value).unwrap(),
            )
            .unwrap();
        }
        let source = report["nodes"]
            .as_array()
            .unwrap()
            .iter()
            .find(|node| node["id"] == "source")
            .unwrap();
        let path = source["execution"]["task_manifest"]["path"]
            .as_str()
            .unwrap();
        std::fs::copy(path, root.join("actual-source-task.json")).unwrap();
    }
    assert_eq!(report["ok"], true);
    for node in report["nodes"].as_array().unwrap() {
        assert_eq!(node["status"], "success");
    }
    assert_eq!(
        parameters.get("year").map(String::as_str),
        (mask & 1 != 0).then_some("2020-2024")
    );
    assert_eq!(
        parameters.get("venue").map(String::as_str),
        (mask & 2 != 0).then_some("Nature")
    );
    assert_eq!(
        parameters.get("publicationTypes").map(String::as_str),
        (mask & 4 != 0).then_some("Review")
    );
    let expected_query = if keywords {
        match operator {
            // Bulk search explicitly supports + for AND; retain the wire contract.
            // https://api.semanticscholar.org/graph/v1/swagger.json
            BoolOp::And => "synthetic_alpha + synthetic_beta",
            BoolOp::Or => "synthetic_alpha | synthetic_beta",
            BoolOp::Not => "synthetic_alpha -synthetic_beta",
        }
    } else {
        ""
    };
    assert_eq!(
        parameters.get("query").map(String::as_str),
        keywords.then_some(expected_query)
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
        assert_eq!(evidence.records[0].citation.id, format!("s2:{PAPER_ID}"));
        assert_eq!(evidence.records[0].note.as_deref(), Some(NOTE));
        assert_eq!(
            evidence.records[0].origin.as_deref(),
            Some("semantic_scholar")
        );
    }
    assert_eq!(
        request.path(),
        "/paper/search/bulk",
        "structured Boolean queries must not be sent to relevance search"
    );
    assert!(!parameters.contains_key("limit"));
    assert!(!parameters.contains_key("offset"));
}

macro_rules! case {
    ($name:ident, $operator:expr, $mask:expr) => {
        #[tokio::test]
        async fn $name() {
            run(stringify!($name), $operator, $mask, true).await;
        }
    };
}

case!(and_year, BoolOp::And, 1);
case!(and_venue, BoolOp::And, 2);
case!(and_type, BoolOp::And, 4);
case!(and_year_venue, BoolOp::And, 3);
case!(and_year_type, BoolOp::And, 5);
case!(and_venue_type, BoolOp::And, 6);
case!(and_all_filters, BoolOp::And, 7);
case!(or_year, BoolOp::Or, 1);
case!(or_venue, BoolOp::Or, 2);
case!(or_type, BoolOp::Or, 4);
case!(or_year_venue, BoolOp::Or, 3);
case!(or_year_type, BoolOp::Or, 5);
case!(or_venue_type, BoolOp::Or, 6);
case!(or_all_filters, BoolOp::Or, 7);
case!(not_year, BoolOp::Not, 1);
case!(not_venue, BoolOp::Not, 2);
case!(not_type, BoolOp::Not, 4);
case!(not_year_venue, BoolOp::Not, 3);
case!(not_year_type, BoolOp::Not, 5);
case!(not_venue_type, BoolOp::Not, 6);
case!(not_all_filters, BoolOp::Not, 7);
case!(and_no_filter_control, BoolOp::And, 0);
case!(or_no_filter_control, BoolOp::Or, 0);
case!(not_no_filter_control, BoolOp::Not, 0);

#[tokio::test]
async fn filters_only_routes_to_bulk() {
    run("filters_only_routes_to_bulk", BoolOp::Or, 7, false).await;
}

#[tokio::test]
async fn raw_relevance_all_filters_control() {
    let _endpoint_guard = ENDPOINT_LOCK.lock().await;
    let fixture = Fixture::new();
    let filter = PaperSearchFilter {
        year: Some("2020-2024".into()),
        publication_date_or_year: None,
        venue: Some("Nature".into()),
        publication_types: Some("Review".into()),
        fields_of_study: Some("Medicine".into()),
        open_access_pdf: true,
        min_citation_count: Some(12),
    };
    let result = fixture
        .client
        .search_paper_filtered("fixture search", 3, 0, &filter, None)
        .await
        .unwrap();
    assert_eq!(result.data.len(), 1);
    let request = fixture.request();
    let parameters = request
        .query_pairs()
        .into_owned()
        .collect::<BTreeMap<_, _>>();
    if let Some(root) = std::env::var_os("S2_BULK_FILTER_EVIDENCE_ROOT") {
        let path = std::path::PathBuf::from(root).join("raw_relevance_all_filters_control");
        assert!(!path.exists());
        std::fs::create_dir_all(&path).unwrap();
        std::fs::write(
            path.join("request.json"),
            serde_json::to_vec_pretty(&json!({"path":request.path(),"parameters":parameters}))
                .unwrap(),
        )
        .unwrap();
    }
    assert_eq!(request.path(), "/paper/search");
    for (key, value) in [
        ("query", "fixture search"),
        ("limit", "3"),
        ("offset", "0"),
        ("year", "2020-2024"),
        ("venue", "Nature"),
        ("publicationTypes", "Review"),
        ("fieldsOfStudy", "Medicine"),
        ("openAccessPdf", ""),
        ("minCitationCount", "12"),
    ] {
        assert_eq!(parameters.get(key).map(String::as_str), Some(value));
    }
}
