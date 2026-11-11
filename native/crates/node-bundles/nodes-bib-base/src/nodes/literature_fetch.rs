//! `source_literature_fetch`: retrieve one article by typed identifier and
//! emit it as a single-record `evidence` artifact (the node counterpart of
//! the retired `lit_fetch` tool).

use std::collections::BTreeSet;
use std::sync::Arc;

use async_trait::async_trait;
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;

use bib_types::evidence::{EvidenceRecord, EvidenceSet, FORMAT};
use bib_types::types::{Article, IdKind, Identifier};
use dag_core::dag::graph::PortOutputs;
use dag_core::dag::{DagError, DagNode};
use dag_core::node::{NodeInput, NodePorts};
use dag_core::registry::{NodeCtx, NodeFactory};
use dag_core::value::PortType;

use crate::nodes::literature_search::shared_gateway;
use crate::library_service::GatewayAccess;
use crate::nodes::{validate_output_path, write_artifact};
use crate::query::LiteratureGateway;

/// Spec for [`LiteratureFetchNode`].
#[derive(Debug, Clone, JsonSchema, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LiteratureFetchSpec {
    /// Identifier kind: `doi`, `pmid`, `pmc`, `embase`, `arxiv`, `biorxiv`,
    /// `s2`, `openalex`, or `other`.
    pub id_kind: String,
    /// The identifier value (DOIs are normalized automatically).
    pub id_value: String,
    /// Sources to try, in order (e.g. `["pubmed", "crossref"]`). Default:
    /// every source that supports the identifier kind, in registration
    /// order, first hit wins. An unknown name fails the node.
    #[serde(default)]
    pub sources: Option<Vec<String>>,
    /// Destination for the evidence JSON artifact. Prefers a `vfs://`
    /// URI for cross-process artifacts; a bare absolute path is
    /// auto-rewritten to `vfs:///...` so the engine and the agent share
    /// one mounted object-store namespace. Overwritten on re-run.
    pub path: String,
    /// Optional provenance note stamped on the record.
    #[serde(default)]
    pub note: Option<String>,
}

fn parse_id_kind(raw: &str) -> Result<IdKind, DagError> {
    let normalized = raw.trim().to_lowercase();
    let kind = match normalized.as_str() {
        "doi" => IdKind::Doi,
        "pmid" => IdKind::Pmid,
        "pmc" => IdKind::Pmc,
        "embase" => IdKind::Embase,
        "arxiv" => IdKind::Arxiv,
        "biorxiv" => IdKind::Biorxiv,
        "s2" => IdKind::S2,
        "openalex" => IdKind::OpenAlex,
        "other" => IdKind::Other,
        other => {
            return Err(DagError::Schedule(format!(
                "unknown id_kind `{other}`; valid kinds: doi, pmid, pmc, embase, arxiv, \
                 biorxiv, s2, openalex, other"
            )));
        }
    };
    Ok(kind)
}

fn identity_key(kind: IdKind, value: &str) -> String {
    let value = value.trim();
    match kind {
        IdKind::Doi | IdKind::Biorxiv => {
            bib_types::convert::normalize_doi(value).to_ascii_lowercase()
        }
        IdKind::Pmid => value.trim_start_matches('0').to_string(),
        IdKind::Pmc => {
            let number = if value
                .get(..3)
                .is_some_and(|prefix| prefix.eq_ignore_ascii_case("PMC"))
            {
                &value[3..]
            } else {
                value
            };
            format!("PMC{}", number.trim_start_matches('0'))
        }
        IdKind::OpenAlex => value
            .strip_prefix("https://openalex.org/")
            .or_else(|| value.strip_prefix("http://openalex.org/"))
            .unwrap_or(value)
            .to_ascii_uppercase(),
        IdKind::Arxiv => value
            .strip_prefix("https://arxiv.org/abs/")
            .or_else(|| value.strip_prefix("http://arxiv.org/abs/"))
            .unwrap_or(value)
            .to_string(),
        IdKind::S2 if value.len() == 40 && value.bytes().all(|byte| byte.is_ascii_hexdigit()) => {
            value.to_ascii_lowercase()
        }
        _ => value.to_string(),
    }
}

fn without_arxiv_version(value: &str) -> &str {
    value
        .rsplit_once('v')
        .filter(|(_, version)| {
            !version.is_empty() && version.bytes().all(|byte| byte.is_ascii_digit())
        })
        .map(|(base, _)| base)
        .unwrap_or(value)
}

fn verify_returned_identity(identifier: &Identifier, article: &Article) -> Result<(), DagError> {
    if article.id.trim().is_empty() {
        return Err(DagError::Schedule(
            "returned article has empty internal identity".into(),
        ));
    }
    let anchor = if identifier.kind == IdKind::S2 {
        [
            ("DOI:", IdKind::Doi),
            ("PMID:", IdKind::Pmid),
            ("PMCID:", IdKind::Pmc),
            ("ARXIV:", IdKind::Arxiv),
        ]
        .iter()
        .find_map(|(prefix, kind)| {
            identifier
                .value
                .strip_prefix(prefix)
                .map(|value| Identifier::new(*kind, value))
        })
        .unwrap_or_else(|| identifier.clone())
    } else {
        identifier.clone()
    };
    let requested = identity_key(anchor.kind, &anchor.value);
    let matched = article.identifiers.iter().any(|candidate| {
        let relevant = candidate.kind == anchor.kind
            || (matches!(candidate.kind, IdKind::Doi | IdKind::Biorxiv)
                && matches!(anchor.kind, IdKind::Doi | IdKind::Biorxiv));
        if !relevant {
            return false;
        }
        let returned = identity_key(candidate.kind, &candidate.value);
        !returned.is_empty()
            && if anchor.kind == IdKind::Arxiv && without_arxiv_version(&requested) == requested {
                without_arxiv_version(&returned) == requested
            } else {
                returned == requested
            }
    });
    if !matched {
        return Err(DagError::Schedule(
            "returned article does not anchor requested identity".into(),
        ));
    }
    Ok(())
}

fn port_layout() -> NodePorts {
    NodePorts::new().add_output_port_of_type_with_label_and_format(
        None,
        PortType::File,
        "evidence",
        FORMAT,
    )
}

pub struct LiteratureFetchNode {
    meta: NodePorts,
    spec: LiteratureFetchSpec,
    /// Test seam: run against an injected gateway instead of the shared one.
    gateway: Option<Arc<GatewayAccess>>,
}

impl LiteratureFetchNode {
    pub fn new(spec: LiteratureFetchSpec) -> Self {
        Self {
            meta: port_layout(),
            spec,
            gateway: None,
        }
    }

    /// Build a node bound to a caller-supplied gateway (tests).
    pub fn with_gateway(spec: LiteratureFetchSpec, gateway: Arc<LiteratureGateway>) -> Self {
        Self {
            meta: port_layout(),
            spec,
            gateway: Some(Arc::new(GatewayAccess::Local(gateway))),
        }
    }
}

#[async_trait]
impl DagNode for LiteratureFetchNode {
    fn ports(&self) -> &NodePorts {
        &self.meta
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(Self {
            meta: self.meta.clone(),
            spec: self.spec.clone(),
            gateway: self.gateway.clone(),
        })
    }

    fn kind(&self) -> &'static str {
        "source_literature_fetch"
    }

    fn as_any(&self) -> &dyn std::any::Any {
        self
    }

    fn sink_path(&self) -> Option<&str> {
        Some(&self.spec.path)
    }

    async fn execute(
        &mut self,
        node_ctx: &NodeCtx,
        inputs: &[NodeInput],
        _reporter: &dag_core::dag::node_event::NodeReporter,
    ) -> std::result::Result<PortOutputs, DagError> {
        if !inputs.is_empty() {
            return Err(DagError::Schedule(
                "typed literature source has no input ports".into(),
            ));
        }
        validate_output_path(&self.spec.path)?;
        let kind = parse_id_kind(&self.spec.id_kind)?;
        let value = identity_key(kind, &self.spec.id_value);
        if value.is_empty() || value.chars().any(char::is_control) {
            return Err(DagError::Schedule(
                "typed literature identifier must be nonempty and contain no control characters"
                    .into(),
            ));
        }
        let decimal = match kind {
            IdKind::Pmid => Some(value.as_str()),
            IdKind::Pmc => value.strip_prefix("PMC"),
            _ => None,
        };
        if decimal.is_some_and(|number| {
            number.is_empty() || !number.bytes().all(|byte| byte.is_ascii_digit())
        }) {
            return Err(DagError::Schedule(
                "PMID/PMCID must contain a positive decimal identifier".into(),
            ));
        }
        let identifier = Identifier::new(kind, value.clone());
        let gateway = self.gateway.clone().unwrap_or_else(shared_gateway);
        let registered = gateway.source_names().await.map_err(|error| DagError::Schedule(error.to_string()))?;
        if registered.iter().collect::<BTreeSet<_>>().len() != registered.len() {
            return Err(DagError::Schedule(
                "duplicate registered literature source name".into(),
            ));
        }
        let sources = self
            .spec
            .sources
            .clone()
            .unwrap_or_else(|| registered.iter().map(|name| name.to_string()).collect());
        if sources.is_empty() || sources.iter().collect::<BTreeSet<_>>().len() != sources.len() {
            return Err(DagError::Schedule(
                "literature sources must be nonempty and contain no duplicate names".into(),
            ));
        }
        let unknown: Vec<_> = sources
            .iter()
            .map(String::as_str)
            .filter(|name| !registered.iter().any(|registered| registered == *name))
            .collect();
        if !unknown.is_empty() {
            return Err(DagError::Schedule(format!(
                "unknown literature source(s) {}; valid names: {}",
                unknown.join(", "),
                registered.join(", ")
            )));
        }
        let mut fetched = None;
        let mut attempts = Vec::new();
        let mut backend_errors = Vec::new();
        let mut identity_error = None;
        for source in &sources {
            if !gateway
                .supports_named(source, kind)
                .await
                .map_err(|error| DagError::Schedule(error.to_string()))?
            {
                attempts.push(
                    serde_json::json!({"source":source,"status":"UNSUPPORTED_IDENTIFIER_KIND"}),
                );
                continue;
            }
            match gateway.fetch_from(source, &identifier).await {
                Ok(Some(article)) => {
                    if let Err(error) = verify_returned_identity(&identifier, &article) {
                        attempts.push(serde_json::json!({"source":source,"status":"IDENTITY_MISMATCH","returned_article":article,"error":error.to_string()}));
                        identity_error = Some(error);
                        break;
                    }
                    attempts.push(serde_json::json!({"source":source,"status":"VERIFIED_TYPED_HIT","returned_article":article}));
                    fetched = Some((source.clone(), article));
                    break;
                }
                Ok(None) => attempts.push(
                    serde_json::json!({"source":source,"status":"NO_RECORD_REPORTED_BY_ADAPTER"}),
                ),
                Err(error) => {
                    attempts.push(serde_json::json!({"source":source,"status":"BACKEND_ERROR","error":error.to_string()}));
                    backend_errors.push(format!("{source}: {error}"));
                }
            }
        }
        let diagnostics = serde_json::to_vec_pretty(&serde_json::json!({"schema_version":1,
            "identifier":identifier,"attempts":attempts,"scope":"TYPED_GATEWAY_ATTEMPTS_NOT_RAW_HTTP_OR_OFFICIAL_SOURCE_CERTIFICATION"}))
            .map_err(|error| DagError::Schedule(error.to_string()))?;
        write_artifact(
            node_ctx,
            &format!("{}.fetch-attempts.json", self.spec.path),
            diagnostics,
            "json",
        )
        .await?;
        if let Some(error) = identity_error {
            return Err(error);
        }

        let Some((source_name, citation)) = fetched else {
            if !backend_errors.is_empty() {
                return Err(DagError::Schedule(format!(
                    "literature fetch backend failures (not a true absence): {}",
                    backend_errors.join("; ")
                )));
            }
            return Err(DagError::Schedule(format!(
                "no literature source returned an article for {} `{value}`",
                kind.as_str()
            )));
        };

        let set = EvidenceSet {
            records: vec![EvidenceRecord {
                citation,
                note: self.spec.note.clone(),
                origin: Some(source_name),
            }],
            ..Default::default()
        };
        let bytes = set.to_bytes().map_err(DagError::Schedule)?;
        let file = write_artifact(node_ctx, &self.spec.path, bytes, FORMAT).await?;
        let mut outputs = PortOutputs::new();
        outputs.insert_file(0, file);
        Ok(outputs)
    }
}

pub struct LiteratureFetchNodeFactory {}

#[async_trait]
impl NodeFactory for LiteratureFetchNodeFactory {
    fn kind(&self) -> &'static str {
        "source_literature_fetch"
    }

    fn desc(&self) -> &'static str {
        "Retrieve one article by DOI / PMID / arXiv / S2 / OpenAlex id as an evidence file"
    }

    fn doc(&self) -> &'static str {
        "Fetches a single bibliographic record by typed identifier through the \
         literature gateway and writes it as a one-record `evidence` artifact \
         (File, format `evidence`). Sources that support the identifier kind \
         are tried in registration order, first hit wins; pass `sources` to \
         pin an order. Unsupported adapters are skipped. Requires the returned \
         record to contain the requested identifier; matching aliases are \
         preserved. Attempts and backend errors are recorded in \
         `<path>.fetch-attempts.json` (not an output port). Fails when no \
         source knows the identifier or the returned identity cannot be \
         verified. Chain into \
         evidence_merge to combine with search results, or evidence_export \
         for a bibliography. DOI values are normalized (URL prefixes \
         stripped) automatically."
    }

    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(LiteratureFetchSpec)
    }

    fn ports(&self) -> NodePorts {
        port_layout()
    }

    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec: LiteratureFetchSpec = serde_json::from_value(spec)?;
        Ok(Box::new(LiteratureFetchNode::new(spec)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::nodes::read_file_bytes;
    use crate::query::{LiteratureGateway, LiteratureSource, SourceBatch};
    use bib_types::query::StructuredSearch;
    use dag_core::dag::node_event::NodeReporter;

    struct FetchableSource {
        article: Option<Article>,
    }

    #[async_trait]
    impl LiteratureSource for FetchableSource {
        fn name(&self) -> &'static str {
            "fake"
        }

        async fn search(
            &self,
            _query: &StructuredSearch,
            _limit: usize,
        ) -> crate::Result<SourceBatch> {
            Ok(SourceBatch {
                source: "fake".into(),
                total: 0,
                articles: Vec::new(),
                error: None,
            })
        }

        async fn fetch(&self, id: &Identifier) -> crate::Result<Option<Article>> {
            // DOIs are case-insensitive at real APIs; compare lowercased.
            Ok(match id.kind {
                IdKind::Doi if id.value.to_lowercase() == "10.1/known" => self.article.clone(),
                _ => None,
            })
        }
    }

    fn spec(id_kind: &str, id_value: &str, path: &str) -> LiteratureFetchSpec {
        LiteratureFetchSpec {
            id_kind: id_kind.into(),
            id_value: id_value.into(),
            sources: None,
            path: path.into(),
            note: Some("ctx".into()),
        }
    }

    fn node_ctx() -> (NodeCtx, Arc<vfs::OpendalFileStorage>) {
        let storage = Arc::new(vfs::OpendalFileStorage::new_temp());
        let ctx = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            Some(storage.clone()),
        );
        (ctx, storage)
    }

    fn tmp_path(tag: &str) -> String {
        // Absolute; `write_artifact` rewrites it to `vfs:///tmp/...` which
        // resolves inside the test's VFS temp root.
        format!("/tmp/fetch-node-{tag}-{}.json", uuid::Uuid::new_v4())
    }

    #[tokio::test]
    async fn fetches_known_doi_into_single_record_evidence() {
        let (ctx, _storage) = node_ctx();
        let mut article = Article::new("1", "Known paper");
        article.identifiers.push(Identifier::doi("10.1/known"));
        let mut gateway = LiteratureGateway::new();
        gateway.add_source(Arc::new(FetchableSource {
            article: Some(article),
        }));
        let gateway = Arc::new(gateway);
        let path = tmp_path("known");
        let mut node = LiteratureFetchNode::with_gateway(
            spec("DOI", "https://doi.org/10.1/KNOWN", &path),
            gateway,
        );
        let outputs = node
            .execute(&ctx, &[], &NodeReporter::noop())
            .await
            .unwrap();
        let file = outputs
            .get(&0)
            .and_then(|value| value.as_file().ok())
            .expect("file output");
        assert_eq!(file.format.as_deref(), Some("evidence"));
        assert!(file.path.starts_with("vfs://"), "{}", file.path);
        assert!(
            file.fingerprint
                .as_ref()
                .is_some_and(|fp| !fp.immutable_remote)
        );

        let set = EvidenceSet::parse(&read_file_bytes(&ctx, &path).await.unwrap()).unwrap();
        assert_eq!(set.records.len(), 1);
        assert_eq!(set.records[0].citation.title, "Known paper");
        assert_eq!(set.records[0].origin.as_deref(), Some("fake"));
        assert_eq!(set.records[0].note.as_deref(), Some("ctx"));
    }

    #[tokio::test]
    async fn unknown_identifier_fails_closed() {
        let (ctx, _storage) = node_ctx();
        let mut gateway = LiteratureGateway::new();
        gateway.add_source(Arc::new(FetchableSource { article: None }));
        let gateway = Arc::new(gateway);
        let mut node = LiteratureFetchNode::with_gateway(
            spec("doi", "10.1/missing", &tmp_path("missing")),
            gateway,
        );
        let err = node
            .execute(&ctx, &[], &NodeReporter::noop())
            .await
            .unwrap_err()
            .to_string();
        assert!(err.contains("no literature source returned"), "{err}");
    }

    #[tokio::test]
    async fn unknown_id_kind_lists_valid_kinds() {
        let (ctx, _storage) = node_ctx();
        let mut node = LiteratureFetchNode::new(spec("isbn", "x", &tmp_path("kind")));
        let err = node
            .execute(&ctx, &[], &NodeReporter::noop())
            .await
            .unwrap_err()
            .to_string();
        assert!(err.contains("unknown id_kind `isbn`"), "{err}");
        assert!(err.contains("openalex"), "{err}");
    }
}
