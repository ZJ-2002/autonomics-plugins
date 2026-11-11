use std::io::{Read, Write};
use std::net::TcpListener;
use std::sync::{Arc, Mutex};

use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_search::{LiteratureSearchNode, LiteratureSearchSpec};
use bib_base::{ArxivSource, LiteratureGateway};
use bib_types::{BoolOp, EvidenceSet, StructuredSearch};
use dag_core::NodeCtx;
use dag_core::dag::DAG;
use dag_core::dag::runtime::{InputHashing, SchedulerConfig};
use datafusion::prelude::SessionContext;
use serde_json::json;

static ENDPOINT_LOCK: tokio::sync::Mutex<()> = tokio::sync::Mutex::const_new(());

struct Fixture {
    previous: Option<std::ffi::OsString>,
    request: Arc<Mutex<Option<String>>>,
    worker: Option<std::thread::JoinHandle<()>>,
}

impl Fixture {
    fn new() -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let previous = std::env::var_os("ENDPOINT_ARXIV_URL");
        unsafe {
            std::env::set_var(
                "ENDPOINT_ARXIV_URL",
                format!("http://{}/api/query", listener.local_addr().unwrap()),
            );
        }
        let request = Arc::new(Mutex::new(None));
        let captured = request.clone();
        let worker = std::thread::spawn(move || {
            let deadline = std::time::Instant::now() + std::time::Duration::from_secs(8);
            while std::time::Instant::now() < deadline {
                match listener.accept() {
                    Ok((mut stream, _)) => {
                        stream
                            .set_read_timeout(Some(std::time::Duration::from_secs(3)))
                            .unwrap();
                        let mut bytes = Vec::new();
                        let mut buffer = [0u8; 1024];
                        while !bytes.windows(4).any(|window| window == b"\r\n\r\n") {
                            let count = stream.read(&mut buffer).unwrap();
                            assert!(count > 0 && bytes.len() < 16384);
                            bytes.extend_from_slice(&buffer[..count]);
                        }
                        let text = String::from_utf8(bytes).unwrap();
                        assert!(!text.to_ascii_lowercase().contains("authorization:"));
                        *captured.lock().unwrap() = Some(text.lines().next().unwrap().to_owned());
                        let body = r#"<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
<id>urn:synthetic:field-contract</id><title>Synthetic empty protocol control</title><updated>2026-01-01T00:00:00Z</updated>
<opensearch:totalResults>0</opensearch:totalResults><opensearch:startIndex>0</opensearch:startIndex><opensearch:itemsPerPage>0</opensearch:itemsPerPage></feed>"#;
                        write!(stream, "HTTP/1.1 200 OK\r\nContent-Type: application/atom+xml\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).unwrap();
                        return;
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                        std::thread::sleep(std::time::Duration::from_millis(1))
                    }
                    Err(error) => panic!("fixture accept: {error}"),
                }
            }
        });
        Self {
            previous,
            request,
            worker: Some(worker),
        }
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        if let Some(worker) = self.worker.take() {
            worker.join().unwrap();
        }
        unsafe {
            match self.previous.take() {
                Some(value) => std::env::set_var("ENDPOINT_ARXIV_URL", value),
                None => std::env::remove_var("ENDPOINT_ARXIV_URL"),
            }
        }
    }
}

async fn prove(tag: &str, query: StructuredSearch, expected: &str) {
    let _guard = ENDPOINT_LOCK.lock().await;
    let fixture = Fixture::new();
    let root = std::env::var_os("ARXIV_FIELDS_DAG_EVIDENCE_ROOT")
        .map(std::path::PathBuf::from)
        .map(|root| root.join(tag));
    let storage = match &root {
        Some(root) => {
            assert!(!root.exists());
            std::fs::create_dir_all(root.join("vfs")).unwrap();
            vfs::OpendalFileStorage::new(root.join("vfs"))
        }
        None => vfs::OpendalFileStorage::new_temp(),
    };
    let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(Arc::new(storage)));
    let mut gateway = LiteratureGateway::new();
    gateway.add_source(Arc::new(ArxivSource::new(Arc::new(
        arxiv::ArxivClient::new(),
    ))));
    let configuration =
        json!({"query": query, "limit": 25, "sources": ["arxiv"], "path": "/source.json"});
    let source = LiteratureSearchNode::with_gateway(
        serde_json::from_value::<LiteratureSearchSpec>(configuration.clone()).unwrap(),
        Arc::new(gateway),
    );
    let mut dag = DAG::default();
    dag.add_node_with_spec(
        "source".into(),
        Box::new(source),
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
    assert!(report.ok);
    let request = fixture.request.lock().unwrap().clone().unwrap();
    let path = request.split_whitespace().nth(1).unwrap();
    let url = reqwest::Url::parse(&format!("http://fixture{path}")).unwrap();
    let pairs: Vec<_> = url.query_pairs().collect();
    assert_eq!(
        pairs
            .iter()
            .filter(|(name, _)| name == "search_query")
            .count(),
        1
    );
    assert_eq!(
        pairs
            .iter()
            .find(|(name, _)| name == "search_query")
            .unwrap()
            .1,
        expected
    );
    let storage = context.opendal.as_ref().unwrap();
    for path in ["/source.json", "/merge.json"] {
        let bytes = storage
            .resolve(path)
            .read(&storage.resolve_path(path))
            .await
            .unwrap();
        assert!(
            EvidenceSet::parse(&bytes.to_vec())
                .unwrap()
                .records
                .is_empty()
        );
    }
    let report = serde_json::to_value(report).unwrap();
    assert_eq!(report["nodes"].as_array().unwrap().len(), 2);
    assert!(
        report["nodes"]
            .as_array()
            .unwrap()
            .iter()
            .all(|node| node["status"] == "success")
    );
    if let Some(root) = root {
        for (name, value) in [
            ("input-spec.json", configuration),
            ("run-report.json", report),
            (
                "dag.json",
                serde_json::to_value(dag.tui_snapshot()).unwrap(),
            ),
            (
                "request.json",
                json!({"request_line":request,"expected_search_query":expected,"mock_http_not_official_live_query":true,"g0_granted":false}),
            ),
        ] {
            std::fs::write(root.join(name), serde_json::to_vec_pretty(&value).unwrap()).unwrap();
        }
    }
}

#[tokio::test]
async fn compound_exclusion_reaches_the_actual_sdk_and_dag() {
    prove(
        "exclude",
        StructuredSearch {
            keywords: Some(vec!["electron".into(), "proton".into()]),
            keywords_op: Some(BoolOp::Not),
            ..Default::default()
        },
        "((ti:electron OR abs:electron) ANDNOT (ti:proton OR abs:proton))",
    )
    .await;
}

#[tokio::test]
async fn conjunction_keeps_per_term_title_abstract_alternatives() {
    prove(
        "and",
        StructuredSearch {
            keywords: Some(vec!["electron".into(), "proton".into()]),
            keywords_op: Some(BoolOp::And),
            ..Default::default()
        },
        "((ti:electron OR abs:electron) AND (ti:proton OR abs:proton))",
    )
    .await;
}

#[tokio::test]
async fn disjunction_keeps_per_term_title_abstract_alternatives() {
    prove(
        "or",
        StructuredSearch {
            keywords: Some(vec!["electron".into(), "proton".into()]),
            ..Default::default()
        },
        "((ti:electron OR abs:electron) OR (ti:proton OR abs:proton))",
    )
    .await;
}

#[tokio::test]
async fn phrase_and_author_constraint_survive_real_sdk_transport() {
    prove(
        "phrase-author",
        StructuredSearch {
            keywords: Some(vec!["synthetic phrase".into()]),
            authors: Some(vec!["Smith".into()]),
            ..Default::default()
        },
        "(ti:\"synthetic phrase\" OR abs:\"synthetic phrase\") AND au:Smith",
    )
    .await;
}
