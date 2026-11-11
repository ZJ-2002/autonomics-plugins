use std::sync::Arc;

use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_fetch::{LiteratureFetchNode, LiteratureFetchSpec};
use nodes_bib_base::nodes::literature_search::{LiteratureSearchNode, LiteratureSearchSpec};
use bib_base::{ArxivSource, LiteratureGateway};
use bib_types::EvidenceSet;
use dag_core::NodeCtx;
use dag_core::dag::runtime::{InputHashing, SchedulerConfig};
use dag_core::dag::{DAG, DagNode};
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};

#[path = "../../../arxiv/tests/common/feed_integrity_fixture.rs"]
mod fixture_data;
#[path = "../../../arxiv/tests/common/atom_http_fixture.rs"]
mod transport;

const NOTE: &str = "Synthetic arXiv feed integrity fixture, not live research evidence";
static ENDPOINT_LOCK: tokio::sync::Mutex<()> = tokio::sync::Mutex::const_new(());

async fn run(tag: &str) {
    let _guard = ENDPOINT_LOCK.lock().await;
    let fetch = tag.starts_with("fetch");
    let expected_ok = !tag.ends_with("_rejected");
    let body = fixture_data::body(tag);
    let mut fixture = transport::Fixture::new(body.clone());
    let root = std::env::var_os("ARXIV_DAG_FEED_EVIDENCE_ROOT")
        .map(|root| std::path::PathBuf::from(root).join(tag));
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
    let gateway = Arc::new(gateway);
    let (kind, spec, node): (&str, Value, Box<dyn DagNode>) = if fetch {
        let spec = json!({"id_kind":"arxiv","id_value":fixture_data::identifier(tag),"sources":["arxiv"],"path":"/source.json","note":NOTE});
        (
            "source_literature_fetch",
            spec.clone(),
            Box::new(LiteratureFetchNode::with_gateway(
                serde_json::from_value::<LiteratureFetchSpec>(spec).unwrap(),
                gateway,
            )),
        )
    } else {
        let spec = json!({"query":{"keywords":["fixture"]},"limit":2,"sources":["arxiv"],"path":"/source.json","note":NOTE});
        (
            "source_literature",
            spec.clone(),
            Box::new(LiteratureSearchNode::with_gateway(
                serde_json::from_value::<LiteratureSearchSpec>(spec).unwrap(),
                gateway,
            )),
        )
    };
    let mut dag = DAG::default();
    dag.add_node_with_spec("source".into(), node, kind.into(), spec.clone())
        .unwrap();
    dag.add_node_with_spec(
        "merge".into(),
        Box::new(EvidenceMergeNode::new(EvidenceMergeSpec {
            path: "/merge.json".into(),
        })),
        "evidence_merge".into(),
        json!({"path":"/merge.json"}),
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
    let request = fixture.finish();
    if let Some(root) = &root {
        std::fs::write(root.join("response.atom"), body).unwrap();
        std::fs::write(root.join("request.txt"), request).unwrap();
        for (name, value) in [
            ("run-report.json", report.clone()),
            ("input-spec.json", spec),
            (
                "dag.json",
                serde_json::to_value(dag.tui_snapshot()).unwrap(),
            ),
        ] {
            std::fs::write(root.join(name), serde_json::to_vec_pretty(&value).unwrap()).unwrap();
        }
        for node in report["nodes"].as_array().unwrap() {
            if node["id"] == "source" {
                std::fs::copy(
                    node["execution"]["task_manifest"]["path"].as_str().unwrap(),
                    root.join("actual-source-task.json"),
                )
                .unwrap();
            }
            for stream in ["stdout", "stderr"] {
                if let Some(path) = node["execution"][format!("{stream}_log")]["path"].as_str() {
                    std::fs::copy(
                        path,
                        root.join(format!("{}-{stream}.txt", node["id"].as_str().unwrap())),
                    )
                    .unwrap();
                }
            }
        }
    }
    assert_eq!(report["ok"], expected_ok);
    for node in report["nodes"].as_array().unwrap() {
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
    let storage = context.opendal.as_ref().unwrap();
    if expected_ok {
        for path in ["/source.json", "/merge.json"] {
            let bytes = storage
                .resolve(path)
                .read(&storage.resolve_path(path))
                .await
                .unwrap();
            let set = EvidenceSet::parse(&bytes.to_vec()).unwrap();
            assert_eq!(
                set.records.len(),
                if tag.contains("empty_feed") { 0 } else { 1 }
            );
            for record in &set.records {
                assert_eq!(record.origin.as_deref(), Some("arxiv"));
                assert_eq!(record.note.as_deref(), Some(NOTE));
                assert_eq!(record.citation.id, fixture_data::identifier(tag));
                assert!(record.citation.identifiers.iter().any(|identifier| {
                    identifier.kind == bib_types::IdKind::Arxiv
                        && identifier.value == fixture_data::identifier(tag)
                }));
                assert_eq!(record.citation.title, "Error");
            }
        }
    } else if fetch {
        let path = "/source.json.fetch-attempts.json";
        let bytes = storage
            .resolve(path)
            .read(&storage.resolve_path(path))
            .await
            .unwrap();
        let diagnostics: Value = serde_json::from_slice(&bytes.to_vec()).unwrap();
        assert_eq!(diagnostics["attempts"][0]["status"], "BACKEND_ERROR");
        assert!(
            diagnostics["attempts"][0]["error"]
                .as_str()
                .unwrap()
                .contains("failed to parse XML response")
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

case!(search_html_body_rejected);
case!(search_wrong_namespace_rejected);
case!(search_truncated_feed_rejected);
case!(search_missing_total_rejected);
case!(search_duplicate_total_rejected);
case!(search_missing_id_rejected);
case!(fetch_late_missing_id_rejected);
case!(fetch_html_body_rejected);
case!(fetch_missing_id_rejected);
case!(search_atom_prefix_control);
case!(fetch_old_identifier_control);
case!(search_empty_feed_control);
