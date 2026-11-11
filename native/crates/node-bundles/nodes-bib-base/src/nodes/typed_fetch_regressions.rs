use std::sync::{
    Arc,
    atomic::{AtomicUsize, Ordering},
};

use async_trait::async_trait;
use bib_types::query::StructuredSearch;
use bib_types::{Article, IdKind, Identifier};
use dag_core::dag::{DagNode, node_event::NodeReporter};
use dag_core::node::NodeInput;
use dag_core::registry::NodeCtx;
use dag_core::value::FileRef;
use datafusion::prelude::SessionContext;

use super::literature_fetch::{LiteratureFetchNode, LiteratureFetchSpec};
use super::read_file_bytes;
use crate::query::{LiteratureGateway, LiteratureSource, SourceBatch};

struct FixtureSource {
    name: &'static str,
    article: Option<Article>,
    error: bool,
    supported: bool,
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl LiteratureSource for FixtureSource {
    fn name(&self) -> &'static str {
        self.name
    }
    fn supports(&self, _: IdKind) -> bool {
        self.supported
    }
    async fn search(&self, _: &StructuredSearch, _: usize) -> crate::Result<SourceBatch> {
        panic!("typed fetch must not invoke keyword search")
    }
    async fn fetch(&self, _: &Identifier) -> crate::Result<Option<Article>> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        if self.error {
            Err(crate::error::Error::Unknown("fixture_backend_503".into()))
        } else {
            Ok(self.article.clone())
        }
    }
}

fn context() -> NodeCtx {
    NodeCtx::new(
        SessionContext::new().runtime_env(),
        Some(Arc::new(vfs::OpendalFileStorage::new_temp())),
    )
}

fn spec(kind: &str, value: &str, sources: Option<Vec<String>>) -> LiteratureFetchSpec {
    LiteratureFetchSpec {
        id_kind: kind.into(),
        id_value: value.into(),
        sources,
        path: "/typed.json".into(),
        note: Some("fixture, not author HTTP".into()),
    }
}

fn article() -> Article {
    Article::new("fixture-paper", "Typed fixture").with_doi("10.1000/known")
}

fn source(
    name: &'static str,
    article: Option<Article>,
    error: bool,
    supported: bool,
) -> (Arc<FixtureSource>, Arc<AtomicUsize>) {
    let calls = Arc::new(AtomicUsize::new(0));
    (
        Arc::new(FixtureSource {
            name,
            article,
            error,
            supported,
            calls: calls.clone(),
        }),
        calls,
    )
}

fn node(spec: LiteratureFetchSpec, sources: Vec<Arc<FixtureSource>>) -> LiteratureFetchNode {
    let mut gateway = LiteratureGateway::new();
    for source in sources {
        gateway.add_source(source);
    }
    LiteratureFetchNode::with_gateway(spec, Arc::new(gateway))
}

#[test]
fn unknown_control_is_not_silently_discarded() {
    let parsed = serde_json::from_value::<LiteratureFetchSpec>(serde_json::json!({
        "id_kind":"doi","id_value":"10.1000/known","path":"/typed.json","select_best":true}));
    assert!(parsed.is_err());
}

#[tokio::test]
async fn extra_input_is_rejected_before_backend_call() {
    let (source, calls) = source("fixture", Some(article()), false, true);
    let mut node = node(spec("doi", "10.1000/known", None), vec![source]);
    let input = NodeInput::file(0, FileRef::new("/extra.json", Some("evidence".into())));
    assert!(
        node.execute(&context(), &[input], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}

#[tokio::test]
async fn empty_identifier_is_rejected_before_backend_call() {
    let (source, calls) = source("fixture", Some(article()), false, true);
    let mut node = node(spec("doi", " ", None), vec![source]);
    assert!(
        node.execute(&context(), &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}

#[tokio::test]
async fn invalid_decimal_identifiers_are_not_sent_to_backend() {
    for (kind, value) in [
        ("pmid", "abc"),
        ("pmid", "000"),
        ("pmc", "PMCabc"),
        ("pmc", "PMC000"),
    ] {
        let (source, calls) = source("fixture", Some(article()), false, true);
        let mut node = node(spec(kind, value, None), vec![source]);
        assert!(
            node.execute(&context(), &[], &NodeReporter::noop())
                .await
                .is_err(),
            "{kind} {value}"
        );
        assert_eq!(calls.load(Ordering::SeqCst), 0);
    }
}

#[tokio::test]
async fn unrelated_returned_article_is_not_published() {
    let (source, _) = source("fixture", Some(article()), false, true);
    let mut node = node(spec("doi", "10.1000/other", None), vec![source]);
    let context = context();
    assert!(
        node.execute(&context, &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert!(read_file_bytes(&context, "/typed.json").await.is_err());
}

#[tokio::test]
async fn returned_article_without_requested_identifier_is_not_published() {
    let (source, _) = source(
        "fixture",
        Some(Article::new("unanchored", "No IDs")),
        false,
        true,
    );
    let mut node = node(spec("doi", "10.1000/known", None), vec![source]);
    assert!(
        node.execute(&context(), &[], &NodeReporter::noop())
            .await
            .is_err()
    );
}

#[tokio::test]
async fn returned_article_with_empty_internal_id_is_rejected() {
    let (source, _) = source(
        "fixture",
        Some(Article::new("", "Empty ID").with_doi("10.1000/known")),
        false,
        true,
    );
    let mut node = node(spec("doi", "10.1000/known", None), vec![source]);
    assert!(
        node.execute(&context(), &[], &NodeReporter::noop())
            .await
            .is_err()
    );
}

#[tokio::test]
async fn backend_failure_is_not_indistinguishable_from_true_absence() {
    let (source, _) = source("fixture", None, true, true);
    let mut node = node(spec("doi", "10.1000/known", None), vec![source]);
    let error = node
        .execute(&context(), &[], &NodeReporter::noop())
        .await
        .unwrap_err()
        .to_string();
    assert!(error.contains("fixture_backend_503"), "{error}");
}

#[tokio::test]
async fn explicitly_selected_unsupported_source_is_not_called() {
    let (source, calls) = source("fixture", Some(article()), false, false);
    let mut node = node(
        spec("doi", "10.1000/known", Some(vec!["fixture".into()])),
        vec![source],
    );
    assert!(
        node.execute(&context(), &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}

#[tokio::test]
async fn duplicate_selected_source_names_are_rejected() {
    let (source, calls) = source("fixture", Some(article()), false, true);
    let mut node = node(
        spec(
            "doi",
            "10.1000/known",
            Some(vec!["fixture".into(), "fixture".into()]),
        ),
        vec![source],
    );
    assert!(
        node.execute(&context(), &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}

#[tokio::test]
async fn duplicate_registered_source_names_are_not_ambiguous() {
    let (first, calls) = source("fixture", Some(article()), false, true);
    let (second, _) = source("fixture", Some(article()), false, true);
    let mut node = node(spec("doi", "10.1000/known", None), vec![first, second]);
    assert!(
        node.execute(&context(), &[], &NodeReporter::noop())
            .await
            .is_err()
    );
    assert_eq!(calls.load(Ordering::SeqCst), 0);
}

#[tokio::test]
async fn explicit_arxiv_version_is_not_replaced_by_another_version() {
    let mut returned = Article::new("arxiv-fixture", "Different version");
    returned
        .identifiers
        .push(Identifier::new(IdKind::Arxiv, "2401.00001v3"));
    let (source, _) = source("fixture", Some(returned), false, true);
    let mut node = node(spec("arxiv", "2401.00001v2", None), vec![source]);
    assert!(
        node.execute(&context(), &[], &NodeReporter::noop())
            .await
            .is_err()
    );
}

#[tokio::test]
async fn doi_non_ascii_characters_are_not_case_folded() {
    let returned = Article::new("unicode-fixture", "Unicode DOI").with_doi("10.1000/Α");
    let (source, _) = source("fixture", Some(returned), false, true);
    let mut node = node(spec("doi", "10.1000/α", None), vec![source]);
    assert!(
        node.execute(&context(), &[], &NodeReporter::noop())
            .await
            .is_err()
    );
}

#[tokio::test]
async fn matched_doi_is_not_rejected_because_a_legitimate_alias_is_also_present() {
    let mut returned = article();
    returned.identifiers.push(Identifier::doi("10.1000/alias"));
    let (source, _) = source("fixture", Some(returned.clone()), false, true);
    let mut node = node(
        spec("doi", "https://doi.org/10.1000/KNOWN", None),
        vec![source],
    );
    let context = context();
    node.execute(&context, &[], &NodeReporter::noop())
        .await
        .unwrap();
    let evidence = bib_types::evidence::EvidenceSet::parse(
        &read_file_bytes(&context, "/typed.json").await.unwrap(),
    )
    .unwrap();
    assert_eq!(
        serde_json::to_value(&evidence.records[0].citation).unwrap(),
        serde_json::to_value(&returned).unwrap()
    );
}

#[tokio::test]
async fn backend_failure_can_fall_back_in_frozen_order_to_valid_hit() {
    let (first, first_calls) = source("first", None, true, true);
    let (second, second_calls) = source("second", Some(article()), false, true);
    let mut node = node(
        spec(
            "doi",
            "10.1000/known",
            Some(vec!["first".into(), "second".into()]),
        ),
        vec![first, second],
    );
    let context = context();
    node.execute(&context, &[], &NodeReporter::noop())
        .await
        .unwrap();
    assert_eq!(first_calls.load(Ordering::SeqCst), 1);
    assert_eq!(second_calls.load(Ordering::SeqCst), 1);
    let evidence = bib_types::evidence::EvidenceSet::parse(
        &read_file_bytes(&context, "/typed.json").await.unwrap(),
    )
    .unwrap();
    assert_eq!(evidence.records[0].origin.as_deref(), Some("second"));
}

#[tokio::test]
async fn explicit_source_order_is_preserved() {
    let (first, first_calls) = source("first", Some(article()), false, true);
    let (second, second_calls) = source("second", Some(article()), false, true);
    let mut node = node(
        spec(
            "doi",
            "10.1000/known",
            Some(vec!["second".into(), "first".into()]),
        ),
        vec![first, second],
    );
    let context = context();
    node.execute(&context, &[], &NodeReporter::noop())
        .await
        .unwrap();
    assert_eq!(first_calls.load(Ordering::SeqCst), 0);
    assert_eq!(second_calls.load(Ordering::SeqCst), 1);
}

#[tokio::test]
async fn unsupported_default_source_is_skipped_in_original_order() {
    let (first, first_calls) = source("first", Some(article()), false, false);
    let (second, second_calls) = source("second", Some(article()), false, true);
    let mut node = node(spec("doi", "10.1000/known", None), vec![first, second]);
    node.execute(&context(), &[], &NodeReporter::noop())
        .await
        .unwrap();
    assert_eq!(first_calls.load(Ordering::SeqCst), 0);
    assert_eq!(second_calls.load(Ordering::SeqCst), 1);
}

#[tokio::test]
async fn all_nine_identifier_kinds_preserve_typed_fetch_contract() {
    for (name, kind, value) in [
        ("doi", IdKind::Doi, "10.1000/known"),
        ("pmid", IdKind::Pmid, "123"),
        ("pmc", IdKind::Pmc, "PMC123"),
        ("arxiv", IdKind::Arxiv, "2401.00001v2"),
        ("biorxiv", IdKind::Biorxiv, "10.1101/known"),
        ("s2", IdKind::S2, "abcdef"),
        ("openalex", IdKind::OpenAlex, "W123"),
        ("embase", IdKind::Embase, "opaque123"),
        ("other", IdKind::Other, "opaque123"),
    ] {
        let mut returned = Article::new("fixture", "Typed identifier");
        returned.identifiers.push(Identifier::new(kind, value));
        let (source, _) = source("fixture", Some(returned.clone()), false, true);
        let mut node = node(spec(name, value, None), vec![source]);
        let context = context();
        node.execute(&context, &[], &NodeReporter::noop())
            .await
            .unwrap();
        let evidence = bib_types::evidence::EvidenceSet::parse(
            &read_file_bytes(&context, "/typed.json").await.unwrap(),
        )
        .unwrap();
        assert_eq!(
            serde_json::to_value(&evidence.records[0].citation).unwrap(),
            serde_json::to_value(&returned).unwrap()
        );
    }
}
