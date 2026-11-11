use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_search::{LiteratureSearchNode, LiteratureSearchSpec};
use bib_base::{LiteratureGateway, LiteratureSource, SourceBatch};
use bib_types::{Article, EvidenceSet, Identifier, StructuredSearch};
use dag_core::NodeCtx;
use dag_core::dag::DAG;
use dag_core::dag::runtime::{InputHashing, SchedulerConfig};
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};

struct FixtureSource {
    name: &'static str,
    batch_name: &'static str,
    calls: Arc<Mutex<Vec<Value>>>,
}

#[async_trait]
impl LiteratureSource for FixtureSource {
    fn name(&self) -> &'static str {
        self.name
    }

    async fn search(
        &self,
        query: &StructuredSearch,
        limit: usize,
    ) -> bib_base::Result<SourceBatch> {
        self.calls.lock().unwrap().push(json!({
            "source": self.name,
            "query": query,
            "limit": limit,
        }));
        Ok(SourceBatch {
            source: self.batch_name.into(),
            total: 1,
            articles: vec![
                Article::new("guard-fixture", "Synthetic guard control").with_doi("10.1000/guard"),
            ],
            error: None,
        })
    }

    async fn fetch(&self, _: &Identifier) -> bib_base::Result<Option<Article>> {
        panic!("search DAG must not invoke typed fetch")
    }
}

fn spec() -> LiteratureSearchSpec {
    serde_json::from_value(json!({
        "query": {
            "keywords": ["synthetic_alpha", "synthetic phrase"],
            "keywords_op": "AND",
            "authors": ["Fixture Author"],
            "year_range": {"from": 2020, "to": 2024}
        },
        "limit": 25,
        "sources": ["fixture"],
        "path": "/source.json",
        "note": "Synthetic DAG evidence, not official HTTP"
    }))
    .unwrap()
}

async fn prove(
    tag: &str,
    spec: LiteratureSearchSpec,
    sources: Vec<(&'static str, &'static str)>,
    expected_error: Option<&str>,
    expected_calls: usize,
    expected_origin: &str,
) {
    let evidence_path = std::env::var_os("LITERATURE_GUARD_EVIDENCE_ROOT")
        .map(|root| std::path::PathBuf::from(root).join(tag));
    let storage = match &evidence_path {
        Some(path) => {
            assert!(
                !path.exists(),
                "must not overwrite existing proof artifacts"
            );
            std::fs::create_dir_all(path.join("vfs")).unwrap();
            vfs::OpendalFileStorage::new(path.join("vfs"))
        }
        None => vfs::OpendalFileStorage::new_temp(),
    };
    let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(Arc::new(storage)));
    let calls = Arc::new(Mutex::new(Vec::new()));
    let mut gateway = LiteratureGateway::new();
    for (name, batch_name) in sources {
        gateway.add_source(Arc::new(FixtureSource {
            name,
            batch_name,
            calls: calls.clone(),
        }));
    }
    let mut dag = DAG::default();
    dag.add_node_with_spec(
        "source".into(),
        Box::new(LiteratureSearchNode::with_gateway(
            spec.clone(),
            Arc::new(gateway),
        )),
        "source_literature".into(),
        json!({
            "query": spec.query,
            "limit": spec.limit,
            "sources": spec.sources,
            "path": spec.path,
            "note": spec.note,
        }),
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
    let actual_calls = calls.lock().unwrap().clone();
    if let Some(path) = &evidence_path {
        for (name, value) in [
            ("run-report.json", serde_json::to_value(&report).unwrap()),
            (
                "dag.json",
                serde_json::to_value(dag.tui_snapshot()).unwrap(),
            ),
            ("calls.json", json!(actual_calls)),
        ] {
            std::fs::write(path.join(name), serde_json::to_vec_pretty(&value).unwrap()).unwrap();
        }
    }
    assert_eq!(actual_calls.len(), expected_calls);
    assert_eq!(report.nodes.len(), 2);
    let source = report
        .nodes
        .iter()
        .find(|node| node.id == "source")
        .unwrap();
    let merge = report.nodes.iter().find(|node| node.id == "merge").unwrap();
    let source = serde_json::to_value(source).unwrap();
    let merge = serde_json::to_value(merge).unwrap();
    let storage = context.opendal.as_ref().unwrap();
    if let Some(message) = expected_error {
        assert!(!report.ok);
        assert_eq!(source["status"], "failed");
        assert_eq!(source["execution"]["exit_code"], 1);
        assert!(
            source["error"]["message"]
                .as_str()
                .unwrap()
                .contains(message)
        );
        assert_eq!(merge["status"], "skipped");
        assert_eq!(merge["skipped_because"], "source");
        for path in ["/source.json", "/merge.json"] {
            assert!(
                !storage
                    .resolve(path)
                    .exists(&storage.resolve_path(path))
                    .await
                    .unwrap()
            );
        }
        assert!(source["output_files"].as_array().unwrap().is_empty());
        assert!(merge["output_files"].as_array().unwrap().is_empty());
    } else {
        assert!(report.ok);
        assert_eq!(source["status"], "success");
        assert_eq!(merge["status"], "success");
        for call in &actual_calls {
            assert_eq!(call["query"], serde_json::to_value(&spec.query).unwrap());
            assert_eq!(call["limit"], 25);
        }
        for path in ["/source.json", "/merge.json"] {
            let bytes = storage
                .resolve(path)
                .read(&storage.resolve_path(path))
                .await
                .unwrap();
            let evidence = EvidenceSet::parse(&bytes.to_vec()).unwrap();
            assert_eq!(evidence.records.len(), 1);
            assert_eq!(evidence.records[0].origin.as_deref(), Some(expected_origin));
            assert_eq!(evidence.records[0].citation.id, "guard-fixture");
            assert_eq!(evidence.records[0].note, spec.note);
        }
    }
}

#[tokio::test]
async fn inverted_year_blocks_actual_downstream() {
    let mut spec = spec();
    spec.query.year_range.as_mut().unwrap().from = 2025;
    prove(
        "inverted-year",
        spec,
        vec![("fixture", "fixture")],
        Some("year range"),
        0,
        "",
    )
    .await;
}

#[tokio::test]
async fn duplicate_selection_blocks_actual_downstream() {
    let mut spec = spec();
    spec.sources = Some(vec!["fixture".into(), "fixture".into()]);
    prove(
        "duplicate-selection",
        spec,
        vec![("fixture", "fixture")],
        Some("duplicate names"),
        0,
        "",
    )
    .await;
}

#[tokio::test]
async fn duplicate_registration_blocks_actual_downstream() {
    prove(
        "duplicate-registration",
        spec(),
        vec![("fixture", "fixture"), ("fixture", "fixture")],
        Some("duplicate registered"),
        0,
        "",
    )
    .await;
}

#[tokio::test]
async fn relative_path_blocks_actual_downstream() {
    let mut spec = spec();
    spec.path = "relative/source.json".into();
    prove(
        "relative-path",
        spec,
        vec![("fixture", "fixture")],
        Some("path"),
        0,
        "",
    )
    .await;
}

#[tokio::test]
async fn false_origin_blocks_actual_downstream() {
    prove(
        "false-origin",
        spec(),
        vec![("fixture", "false-origin")],
        Some("inconsistent provenance"),
        1,
        "",
    )
    .await;
}

#[tokio::test]
async fn valid_query_identity_survives_actual_dag() {
    prove(
        "valid-query",
        spec(),
        vec![("fixture", "fixture")],
        None,
        1,
        "fixture",
    )
    .await;
}

#[tokio::test]
async fn faulty_origin_does_not_contaminate_healthy_source() {
    let mut spec = spec();
    spec.sources = Some(vec!["fixture".into(), "healthy".into()]);
    prove(
        "partial-provenance-failure",
        spec,
        vec![("fixture", "false-origin"), ("healthy", "healthy")],
        None,
        2,
        "healthy",
    )
    .await;
}
