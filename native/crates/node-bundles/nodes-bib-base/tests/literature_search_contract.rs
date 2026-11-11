use std::sync::{
    Arc,
    atomic::{AtomicUsize, Ordering},
};

use async_trait::async_trait;
use nodes_bib_base::nodes::literature_search::{
    LiteratureSearchNode, LiteratureSearchNodeFactory, LiteratureSearchSpec,
};
use bib_base::{LiteratureGateway, LiteratureSource, SourceBatch};
use bib_types::{Article, EvidenceSet, Identifier, StructuredSearch};
use dag_core::dag::{DagNode, node_event::NodeReporter};
use dag_core::node::NodeInput;
use dag_core::registry::{NodeCtx, NodeFactory};
use dag_core::value::FileRef;
use datafusion::prelude::SessionContext;
use serde_json::json;

struct FixtureSource {
    name: &'static str,
    batch_name: &'static str,
    empty: bool,
    calls: Arc<AtomicUsize>,
    received_limit: Arc<AtomicUsize>,
}

#[async_trait]
impl LiteratureSource for FixtureSource {
    fn name(&self) -> &'static str {
        self.name
    }

    async fn search(&self, _: &StructuredSearch, limit: usize) -> bib_base::Result<SourceBatch> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        self.received_limit.store(limit, Ordering::SeqCst);
        let articles = if self.empty || limit == 0 {
            Vec::new()
        } else {
            vec![Article::new("fixture-id", "Contract fixture").with_doi("10.1000/contract")]
        };
        Ok(SourceBatch {
            source: self.batch_name.into(),
            total: articles.len(),
            articles,
            error: None,
        })
    }

    async fn fetch(&self, _: &Identifier) -> bib_base::Result<Option<Article>> {
        panic!("search must not invoke typed fetch")
    }
}

fn context() -> NodeCtx {
    NodeCtx::new(
        SessionContext::new().runtime_env(),
        Some(Arc::new(vfs::OpendalFileStorage::new_temp())),
    )
}

fn spec() -> LiteratureSearchSpec {
    LiteratureSearchSpec {
        query: StructuredSearch::default(),
        limit: Some(25),
        sources: Some(vec!["fixture".into()]),
        path: "/search.json".into(),
        note: Some("Synthetic contract control, not official HTTP".into()),
    }
}

fn fixture(
    name: &'static str,
    batch_name: &'static str,
    empty: bool,
) -> (FixtureSource, Arc<AtomicUsize>, Arc<AtomicUsize>) {
    let calls = Arc::new(AtomicUsize::new(0));
    let received_limit = Arc::new(AtomicUsize::new(usize::MAX));
    (
        FixtureSource {
            name,
            batch_name,
            empty,
            calls: calls.clone(),
            received_limit: received_limit.clone(),
        },
        calls,
        received_limit,
    )
}

fn node(spec: LiteratureSearchSpec, sources: Vec<FixtureSource>) -> LiteratureSearchNode {
    let mut gateway = LiteratureGateway::new();
    for source in sources {
        gateway.add_source(Arc::new(source));
    }
    LiteratureSearchNode::with_gateway(spec, Arc::new(gateway))
}

async fn published(context: &NodeCtx) -> bool {
    let storage = context.opendal.as_ref().unwrap();
    storage
        .resolve("/search.json")
        .read(&storage.resolve_path("/search.json"))
        .await
        .is_ok()
}

fn rejected(mut configuration: serde_json::Value) {
    configuration["path"] = json!("/search.json");
    let result = LiteratureSearchNodeFactory {}.build(configuration, context());
    assert!(
        result.is_err(),
        "unknown configured scientific control was discarded"
    );
}

#[test]
fn factory_unknown_control_is_rejected() {
    rejected(json!({"query":{},"select_best":true}));
}

#[test]
fn factory_unknown_query_field_is_rejected() {
    rejected(json!({"query":{"keywrods":["synthetic_alpha"]}}));
}

#[test]
fn factory_unknown_year_field_is_rejected() {
    rejected(json!({"query":{"year_range":{"from":2020,"to":2024,"exclude_seen":true}}}));
}

#[tokio::test]
async fn extra_input_is_rejected_before_source_call() {
    let (source, calls, _) = fixture("fixture", "fixture", false);
    let mut node = node(spec(), vec![source]);
    let context = context();
    let input = NodeInput::file(0, FileRef::new("/extra.json", Some("evidence".into())));
    assert!(
        node.execute(&context, &[input], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(calls.load(Ordering::SeqCst), 0);
    assert!(!published(&context).await);
}

#[tokio::test]
async fn unsupported_output_path_is_rejected_before_source_call() {
    let (source, calls, _) = fixture("fixture", "fixture", false);
    let mut configuration = spec();
    configuration.path = "relative/search.json".into();
    let mut node = node(configuration, vec![source]);
    assert!(
        node.execute(&context(), &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}

#[tokio::test]
async fn duplicate_selected_sources_are_rejected_before_source_call() {
    let (source, calls, _) = fixture("fixture", "fixture", false);
    let mut configuration = spec();
    configuration.sources = Some(vec!["fixture".into(), "fixture".into()]);
    let mut node = node(configuration, vec![source]);
    let context = context();
    assert!(
        node.execute(&context, &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(calls.load(Ordering::SeqCst), 0);
    assert!(!published(&context).await);
}

#[tokio::test]
async fn duplicate_registered_sources_are_rejected_before_source_call() {
    let (first, first_calls, _) = fixture("fixture", "fixture", false);
    let (second, second_calls, _) = fixture("fixture", "fixture", false);
    let mut node = node(spec(), vec![first, second]);
    let context = context();
    assert!(
        node.execute(&context, &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(first_calls.load(Ordering::SeqCst), 0);
    assert_eq!(second_calls.load(Ordering::SeqCst), 0);
    assert!(!published(&context).await);
}

#[tokio::test]
async fn inverted_year_range_is_rejected_before_source_call() {
    let (source, calls, _) = fixture("fixture", "fixture", false);
    let mut configuration = spec();
    configuration.query.year_range = Some(bib_types::query::YearRange {
        from: 2024,
        to: 2020,
    });
    let mut node = node(configuration, vec![source]);
    assert!(
        node.execute(&context(), &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}

#[tokio::test]
async fn source_batch_cannot_claim_another_registered_origin() {
    let (source, calls, _) = fixture("fixture", "unregistered-origin", false);
    let mut node = node(spec(), vec![source]);
    let context = context();
    assert!(
        node.execute(&context, &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    assert!(!published(&context).await);
}

async fn control(limit: u32, empty: bool, expected_limit: usize, expected_records: usize) {
    let (source, calls, received_limit) = fixture("fixture", "fixture", empty);
    let mut configuration = spec();
    configuration.limit = Some(limit);
    let mut node = node(configuration.clone(), vec![source]);
    let context = context();
    let outputs = node
        .execute(&context, &[], &NodeReporter::noop())
        .await
        .unwrap();
    assert_eq!(outputs.len(), 1);
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    assert_eq!(received_limit.load(Ordering::SeqCst), expected_limit);
    let storage = context.opendal.as_ref().unwrap();
    let bytes = storage
        .resolve("/search.json")
        .read(&storage.resolve_path("/search.json"))
        .await
        .unwrap();
    let evidence = EvidenceSet::parse(&bytes.to_vec()).unwrap();
    assert_eq!(evidence.records.len(), expected_records);
    for record in &evidence.records {
        assert_eq!(record.origin.as_deref(), Some("fixture"));
        assert_eq!(record.note, configuration.note);
        assert_eq!(record.citation.id, "fixture-id");
    }
}

#[tokio::test]
async fn documented_zero_limit_control() {
    control(0, false, 0, 0).await;
}

#[tokio::test]
async fn documented_hard_cap_control() {
    control(201, false, 200, 1).await;
}

#[tokio::test]
async fn healthy_empty_control() {
    control(25, true, 25, 0).await;
}

#[tokio::test]
async fn valid_search_identity_and_note_control() {
    control(25, false, 25, 1).await;
}
