use std::sync::Arc;

use async_trait::async_trait;
use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_search::{LiteratureSearchNode, LiteratureSearchSpec};
use bib_base::{LiteratureGateway, LiteratureSource, SourceBatch};
use bib_types::{Article, EvidenceSet, Identifier, StructuredSearch};
use dag_core::NodeCtx;
use dag_core::dag::DAG;
use dag_core::dag::runtime::{InputHashing, RunReport, SchedulerConfig};
use datafusion::prelude::SessionContext;
use serde_json::json;

struct FixtureSource {
    name: &'static str,
    articles: Vec<Article>,
    failure: bool,
}

#[async_trait]
impl LiteratureSource for FixtureSource {
    fn name(&self) -> &'static str {
        self.name
    }

    async fn search(
        &self,
        _query: &StructuredSearch,
        _limit: usize,
    ) -> bib_base::Result<SourceBatch> {
        if self.failure {
            return Err(bib_base::Error::Unknown(
                "fixture failure, not a live API response".into(),
            ));
        }
        Ok(SourceBatch {
            source: self.name.into(),
            total: self.articles.len(),
            articles: self.articles.clone(),
            error: None,
        })
    }

    async fn fetch(&self, _identifier: &Identifier) -> bib_base::Result<Option<Article>> {
        Err(bib_base::Error::Unknown(
            "fixture fetch must not run".into(),
        ))
    }
}

fn context(tag: &str) -> NodeCtx {
    let storage = match std::env::var_os("LITERATURE_CORE_EVIDENCE_ROOT") {
        Some(root) => {
            let path = std::path::PathBuf::from(root).join(tag).join("vfs");
            assert!(
                !path.exists(),
                "proof artifacts must not overwrite an earlier run"
            );
            std::fs::create_dir_all(&path).unwrap();
            vfs::OpendalFileStorage::new(path)
        }
        None => vfs::OpendalFileStorage::new_temp(),
    };
    NodeCtx::new(SessionContext::new().runtime_env(), Some(Arc::new(storage)))
}

fn source(dag: &mut DAG, identifier: &str, fixtures: Vec<FixtureSource>) {
    let mut gateway = LiteratureGateway::new();
    for fixture in fixtures {
        gateway.add_source(Arc::new(fixture));
    }
    let spec = LiteratureSearchSpec {
        query: StructuredSearch::default(),
        limit: Some(25),
        sources: None,
        path: format!("/{identifier}.json"),
        note: None,
    };
    dag.add_node_with_spec(
        identifier.into(),
        Box::new(LiteratureSearchNode::with_gateway(
            spec.clone(),
            Arc::new(gateway),
        )),
        "source_literature".into(),
        json!({"query": {}, "limit": 25, "path": spec.path}),
    )
    .unwrap();
}

fn merge(dag: &mut DAG, identifier: &str) {
    let spec = EvidenceMergeSpec {
        path: format!("/{identifier}.json"),
    };
    dag.add_node_with_spec(
        identifier.into(),
        Box::new(EvidenceMergeNode::new(spec.clone())),
        "evidence_merge".into(),
        json!({"path": spec.path}),
    )
    .unwrap();
}

async fn run(dag: &mut DAG, context: &NodeCtx, tag: &str) -> RunReport {
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
            context,
            None,
        )
        .await
        .unwrap();
    if let Some(root) = std::env::var_os("LITERATURE_CORE_EVIDENCE_ROOT") {
        let path = std::path::PathBuf::from(root).join(tag);
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
    report
}

async fn read(context: &NodeCtx, path: &str) -> EvidenceSet {
    let storage = context.opendal.as_ref().unwrap();
    let bytes = storage
        .resolve(path)
        .read(&storage.resolve_path(path))
        .await
        .unwrap();
    EvidenceSet::parse(&bytes.to_vec()).unwrap()
}

fn bridge_articles() -> Vec<Article> {
    vec![
        Article::new("doi", "DOI view").with_doi("10.1000/bridge"),
        Article::new("pmid", "PMID view").with_pmid("12345"),
        Article::new("bridge", "Combined view")
            .with_doi("10.1000/bridge")
            .with_pmid("12345"),
    ]
}

#[tokio::test]
async fn bridge_orders_flow_through_actual_source_and_merge_dag() {
    let articles = bridge_articles();
    for order in [
        [0, 1, 2],
        [0, 2, 1],
        [1, 0, 2],
        [1, 2, 0],
        [2, 0, 1],
        [2, 1, 0],
    ] {
        let tag = format!("bridge-{}{}{}", order[0], order[1], order[2]);
        let context = context(&tag);
        let mut dag = DAG::default();
        source(
            &mut dag,
            "source",
            vec![FixtureSource {
                name: "fixture",
                articles: order.iter().map(|&index| articles[index].clone()).collect(),
                failure: false,
            }],
        );
        merge(&mut dag, "merge");
        dag.add_edge("source", "merge", 0, 0).unwrap();
        let report = run(&mut dag, &context, &tag).await;
        assert!(report.ok);
        assert_eq!(report.nodes.len(), 2);
        let set = read(&context, "/merge.json").await;
        assert_eq!(set.records.len(), 1);
        assert_eq!(set.records[0].citation.id, articles[order[0]].id);
        assert!(set.records[0].citation.doi().is_some());
        assert!(set.records[0].citation.pmid().is_some());
    }
}

#[tokio::test]
async fn alias_identity_survives_two_actual_merge_stages() {
    let tag = "staged-identity";
    let context = context(tag);
    let articles = bridge_articles();
    let mut dag = DAG::default();
    source(
        &mut dag,
        "first",
        vec![FixtureSource {
            name: "fixture",
            articles: vec![articles[0].clone(), articles[2].clone()],
            failure: false,
        }],
    );
    source(
        &mut dag,
        "later",
        vec![FixtureSource {
            name: "fixture",
            articles: vec![articles[1].clone()],
            failure: false,
        }],
    );
    merge(&mut dag, "intermediate");
    merge(&mut dag, "final");
    dag.add_edge("first", "intermediate", 0, 0).unwrap();
    dag.add_edge("later", "final", 0, 1).unwrap();
    dag.add_edge("intermediate", "final", 0, 0).unwrap();
    let report = run(&mut dag, &context, tag).await;
    assert!(report.ok);
    assert_eq!(report.nodes.len(), 4);
    let set = read(&context, "/final.json").await;
    assert_eq!(set.records.len(), 1);
    assert_eq!(set.records[0].citation.id, "doi");
    assert!(set.records[0].citation.pmid().is_some());
}

#[tokio::test]
async fn successful_empty_plus_failure_is_valid_empty_in_actual_dag() {
    let tag = "empty-and-failed";
    let context = context(tag);
    let mut dag = DAG::default();
    source(
        &mut dag,
        "source",
        vec![
            FixtureSource {
                name: "empty",
                articles: vec![],
                failure: false,
            },
            FixtureSource {
                name: "down",
                articles: vec![],
                failure: true,
            },
        ],
    );
    merge(&mut dag, "merge");
    dag.add_edge("source", "merge", 0, 0).unwrap();
    let report = run(&mut dag, &context, tag).await;
    assert!(report.ok);
    assert!(read(&context, "/merge.json").await.records.is_empty());
}

#[tokio::test]
async fn every_source_failed_blocks_actual_downstream_merge() {
    let tag = "all-failed";
    let context = context(tag);
    let mut dag = DAG::default();
    source(
        &mut dag,
        "source",
        vec![FixtureSource {
            name: "down",
            articles: vec![],
            failure: true,
        }],
    );
    merge(&mut dag, "merge");
    dag.add_edge("source", "merge", 0, 0).unwrap();
    let report = run(&mut dag, &context, tag).await;
    assert!(!report.ok);
    assert!(report.errors.values().any(|error| {
        error
            .to_string()
            .contains("all requested literature sources failed")
    }));
    let storage = context.opendal.as_ref().unwrap();
    assert!(
        !storage
            .resolve("/merge.json")
            .exists(&storage.resolve_path("/merge.json"))
            .await
            .unwrap()
    );
}
