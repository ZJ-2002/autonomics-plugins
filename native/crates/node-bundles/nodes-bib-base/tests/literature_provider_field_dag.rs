use std::sync::Arc;

use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_search::{LiteratureSearchNode, LiteratureSearchSpec};
use bib_base::{ArxivSource, CrossrefSource, LiteratureGateway, LiteratureSource, S2Source};
use bib_types::StructuredSearch;
use dag_core::NodeCtx;
use dag_core::dag::DAG;
use dag_core::dag::runtime::{InputHashing, SchedulerConfig};
use datafusion::prelude::SessionContext;
use serde_json::json;

async fn prove(provider: &str, field: &str) {
    let mut query = json!({"keywords": ["synthetic_alpha"]});
    query[field] = json!(["Fixture constraint"]);
    prove_rejection(provider, field, query, &["unsupported", field]).await;
}

async fn prove_rejection(provider: &str, label: &str, query: serde_json::Value, errors: &[&str]) {
    let tag = format!("{provider}-{label}");
    let evidence_path = std::env::var_os("LITERATURE_PROVIDER_FIELD_EVIDENCE_ROOT")
        .map(|root| std::path::PathBuf::from(root).join(tag));
    let storage = match &evidence_path {
        Some(path) => {
            assert!(!path.exists(), "must not overwrite prior evidence");
            std::fs::create_dir_all(path.join("vfs")).unwrap();
            vfs::OpendalFileStorage::new(path.join("vfs"))
        }
        None => vfs::OpendalFileStorage::new_temp(),
    };
    let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(Arc::new(storage)));
    let query: StructuredSearch = serde_json::from_value(query).unwrap();
    let spec = LiteratureSearchSpec {
        query: query.clone(),
        limit: Some(25),
        sources: Some(vec![provider.into()]),
        path: "/source.json".into(),
        note: Some("Actual SDK rejection, not official HTTP or scientific approval".into()),
    };
    let source: Arc<dyn LiteratureSource> = match provider {
        "arxiv" => Arc::new(ArxivSource::new(Arc::new(arxiv::ArxivClient::new()))),
        "crossref" => Arc::new(CrossrefSource::new(Arc::new(
            crossref::CrossrefClient::new(),
        ))),
        "semantic_scholar" => Arc::new(S2Source::new(Arc::new(semantic_scholar::S2Client::new()))),
        _ => panic!("unknown proof provider"),
    };
    let mut gateway = LiteratureGateway::new();
    gateway.add_source(source);
    let configuration = json!({
        "query": spec.query,
        "limit": spec.limit,
        "sources": spec.sources,
        "path": spec.path,
        "note": spec.note,
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
    if let Some(path) = &evidence_path {
        std::fs::write(
            path.join("input-spec.json"),
            serde_json::to_vec_pretty(&configuration).unwrap(),
        )
        .unwrap();
        std::fs::write(
            path.join("run-report.json"),
            serde_json::to_vec_pretty(&report).unwrap(),
        )
        .unwrap();
        std::fs::write(
            path.join("dag.json"),
            serde_json::to_vec_pretty(&dag.tui_snapshot()).unwrap(),
        )
        .unwrap();
    }
    assert_eq!(report["ok"], false);
    let nodes = report["nodes"].as_array().unwrap();
    assert_eq!(nodes.len(), 2);
    let source = nodes.iter().find(|node| node["id"] == "source").unwrap();
    let merge = nodes.iter().find(|node| node["id"] == "merge").unwrap();
    assert_eq!(source["status"], "failed");
    assert_eq!(source["execution"]["exit_code"], 1);
    let message = source["error"]["message"].as_str().unwrap();
    let translation = if provider == "semantic_scholar" {
        "s2 query translation"
    } else {
        provider
    };
    assert!(message.contains(translation));
    for expected in errors {
        assert!(message.contains(expected), "{message}");
    }
    assert_eq!(merge["status"], "skipped");
    assert_eq!(merge["skipped_because"], "source");
    for node in nodes {
        assert!(node["output_files"].as_array().unwrap().is_empty());
    }
    let storage = context.opendal.as_ref().unwrap();
    for path in ["/source.json", "/merge.json"] {
        assert!(
            !storage
                .resolve(path)
                .exists(&storage.resolve_path(path))
                .await
                .unwrap()
        );
    }
}

#[tokio::test]
async fn arxiv_mesh_blocks_actual_native_dag() {
    prove("arxiv", "mesh").await;
}

#[tokio::test]
async fn arxiv_publication_type_blocks_actual_native_dag() {
    prove("arxiv", "publication_types").await;
}

#[tokio::test]
async fn arxiv_affiliation_blocks_actual_native_dag() {
    prove("arxiv", "affiliation").await;
}

#[tokio::test]
async fn crossref_mesh_blocks_actual_native_dag() {
    prove("crossref", "mesh").await;
}

#[tokio::test]
async fn s2_title_blocks_actual_native_dag() {
    prove("semantic_scholar", "title").await;
}

#[tokio::test]
async fn s2_authors_blocks_actual_native_dag() {
    prove("semantic_scholar", "authors").await;
}

#[tokio::test]
async fn s2_mesh_blocks_actual_native_dag() {
    prove("semantic_scholar", "mesh").await;
}

#[tokio::test]
async fn s2_affiliation_blocks_actual_native_dag() {
    prove("semantic_scholar", "affiliation").await;
}

#[tokio::test]
async fn crossref_blank_fields_block_actual_native_dag() {
    for field in [
        "keywords",
        "title",
        "authors",
        "journal",
        "affiliation",
        "publication_types",
        "mesh",
    ] {
        let mut query = json!({});
        query[field] = json!(["", " \t\n "]);
        prove_rejection(
            "crossref",
            &format!("blank-{field}"),
            query,
            &["structured search is empty"],
        )
        .await;
    }
}
