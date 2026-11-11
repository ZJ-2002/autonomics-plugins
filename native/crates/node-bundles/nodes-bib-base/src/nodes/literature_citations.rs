//! `source_literature_citations`: citation-graph retrieval from Semantic
//! Scholar — papers that cite a given paper, or papers it cites — emitted
//! as an `evidence` artifact (the node counterpart of the retired
//! `s2_citations` / `s2_references` tools).

use std::sync::{Arc, OnceLock};

use async_trait::async_trait;
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;

use bib_types::evidence::{EvidenceRecord, EvidenceSet, FORMAT};
use bib_types::types::Article;
use dag_core::dag::graph::PortOutputs;
use dag_core::dag::{DagError, DagNode};
use dag_core::node::{NodeInput, NodePorts};
use dag_core::registry::{NodeCtx, NodeFactory};
use dag_core::value::PortType;

use super::citation_publication::{ensure_fresh, write_artifact};

#[cfg(test)]
#[path = "citation_audit_tests.rs"]
mod audit_tests;

/// Which direction of the citation graph to walk.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Deserialize, JsonSchema)]
#[serde(rename_all = "lowercase")]
pub enum CitationDirection {
    /// Papers that cite the given paper (impact / follow-up work).
    #[default]
    Citing,
    /// Papers the given paper cites (its reference list).
    Cited,
}

/// Spec for [`LiteratureCitationsNode`].
#[derive(Debug, Clone, JsonSchema, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LiteratureCitationsSpec {
    /// Paper identifier in any Semantic Scholar form: S2 SHA,
    /// `CorpusId:<id>`, `DOI:<doi>`, `ARXIV:<id>`, `PMID:<id>`,
    /// `PMCID:<id>`, or `URL:<url>`.
    pub paper_id: String,
    /// Graph direction. Default `citing` (papers citing this one).
    #[serde(default)]
    pub direction: CitationDirection,
    /// Maximum records per page (default 20); values outside 1..=1000 are rejected.
    #[serde(default)]
    #[schemars(range(min = 1, max = 1000))]
    pub limit: Option<u32>,
    /// Pagination offset (default 0).
    #[serde(default)]
    pub offset: Option<u32>,
    /// Destination for the evidence JSON artifact. `vfs://` URI or absolute
    /// local path; existing evidence or query receipts are never overwritten.
    pub path: String,
    /// Optional provenance note stamped on every record.
    #[serde(default)]
    pub note: Option<String>,
}

/// Process-wide S2 client: one connection pool for every citations node.
static S2_CLIENT: OnceLock<Arc<semantic_scholar::S2Client>> = OnceLock::new();

pub(crate) fn shared_s2_client() -> Arc<semantic_scholar::S2Client> {
    S2_CLIENT
        .get_or_init(|| Arc::new(semantic_scholar::S2Client::from_env()))
        .clone()
}

const DEFAULT_LIMIT: u32 = 20;
const MAX_LIMIT: u32 = 1000;

impl LiteratureCitationsSpec {
    fn validated_page(&self) -> Result<(u32, u32), DagError> {
        if self.paper_id.trim().is_empty()
            || self.paper_id.trim() != self.paper_id
            || self.paper_id.chars().any(char::is_control)
        {
            return Err(DagError::Schedule(
                "paper_id must be non-empty without surrounding whitespace or control characters"
                    .into(),
            ));
        }
        let limit = self.limit.unwrap_or(DEFAULT_LIMIT);
        if !(1..=MAX_LIMIT).contains(&limit) {
            return Err(DagError::Schedule(format!(
                "citation limit must be within 1..={MAX_LIMIT}; values are not silently clipped"
            )));
        }
        crate::nodes::validate_output_path(&self.path)?;
        Ok((limit, self.offset.unwrap_or(0)))
    }
}

fn port_layout() -> NodePorts {
    NodePorts::new().add_output_port_of_type_with_label_and_format(
        None,
        PortType::File,
        "evidence",
        FORMAT,
    )
}

/// Compose the citation-graph metadata (contexts, intents, influence) that
/// has no home in `Article` into a compact `note` prefix, so the evidence
/// record keeps it without widening the payload schema. Shared by the
/// citing and cited directions, which carry identical metadata fields.
pub(crate) fn citation_note(
    contexts: Option<&Vec<String>>,
    intents: Option<&Vec<String>>,
    is_influential: Option<bool>,
    fallback: Option<&str>,
) -> Option<String> {
    let mut parts: Vec<String> = Vec::new();
    if is_influential == Some(true) {
        parts.push("influential citation".into());
    }
    if let Some(intents) = intents.filter(|list| !list.is_empty()) {
        parts.push(format!("intents: [{}]", intents.join(", ")));
    }
    if let Some(contexts) = contexts.filter(|list| !list.is_empty()) {
        // Trim each context snippet to keep the note compact.
        let trimmed: Vec<String> = contexts
            .iter()
            .take(3)
            .map(|context| {
                let snippet: String = context.chars().take(120).collect();
                format!("“{snippet}”")
            })
            .collect();
        parts.push(format!("context: {}", trimmed.join(" ")));
    }
    if let Some(fallback) = fallback {
        parts.push(fallback.to_string());
    }
    (!parts.is_empty()).then(|| parts.join("; "))
}

pub struct LiteratureCitationsNode {
    meta: NodePorts,
    spec: LiteratureCitationsSpec,
    /// Test seam: injected client.
    client: Option<Arc<semantic_scholar::S2Client>>,
}

impl LiteratureCitationsNode {
    pub fn new(spec: LiteratureCitationsSpec) -> Self {
        Self {
            meta: port_layout(),
            spec,
            client: None,
        }
    }

    /// Build a node bound to a caller-supplied client (tests).
    pub fn with_client(
        spec: LiteratureCitationsSpec,
        client: Arc<semantic_scholar::S2Client>,
    ) -> Self {
        Self {
            meta: port_layout(),
            spec,
            client: Some(client),
        }
    }
}

#[async_trait]
impl DagNode for LiteratureCitationsNode {
    fn ports(&self) -> &NodePorts {
        &self.meta
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(Self {
            meta: self.meta.clone(),
            spec: self.spec.clone(),
            client: self.client.clone(),
        })
    }

    fn kind(&self) -> &'static str {
        "source_literature_citations"
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
                "source_literature_citations declares no input ports".into(),
            ));
        }
        let (limit, offset) = self.spec.validated_page()?;
        ensure_fresh(node_ctx, &self.spec.path).await?;
        let audit_path = format!("{}.citation-query.json", self.spec.path);
        ensure_fresh(node_ctx, &audit_path).await?;
        let client = self
            .client
            .clone()
            .unwrap_or_else(shared_s2_client)
            .for_run();

        let direction_word = match self.spec.direction {
            CitationDirection::Citing => "citing",
            CitationDirection::Cited => "cited",
        };

        let lookup: Result<Vec<EvidenceRecord>, DagError> = async {
            Ok(match self.spec.direction {
                CitationDirection::Citing => {
                    let resp = client
                        .get_citations(&self.spec.paper_id, limit, offset, None)
                        .await
                        .map_err(|error| {
                            DagError::Schedule(format!(
                                "citation lookup for `{}` failed: {error}",
                                self.spec.paper_id
                            ))
                        })?;
                    resp.data
                        .iter()
                        .map(|entry| EvidenceRecord {
                            citation: semantic_scholar::convert::paper_to_article(
                                &entry.citing_paper,
                            ),
                            note: citation_note(
                                entry.contexts.as_ref(),
                                entry.intents.as_ref(),
                                entry.is_influential,
                                self.spec.note.as_deref(),
                            ),
                            origin: Some("s2-citations".into()),
                        })
                        .collect()
                }
                CitationDirection::Cited => {
                    let resp = client
                        .get_references(&self.spec.paper_id, limit, offset, None)
                        .await
                        .map_err(|error| {
                            DagError::Schedule(format!(
                                "reference lookup for `{}` failed: {error}",
                                self.spec.paper_id
                            ))
                        })?;
                    resp.data
                        .iter()
                        .map(|entry| EvidenceRecord {
                            citation: semantic_scholar::convert::paper_to_article(
                                &entry.cited_paper,
                            ),
                            note: citation_note(
                                entry.contexts.as_ref(),
                                entry.intents.as_ref(),
                                entry.is_influential,
                                self.spec.note.as_deref(),
                            ),
                            origin: Some("s2-references".into()),
                        })
                        .collect()
                }
            })
        }
        .await;

        let run_id = uuid::Uuid::new_v4().to_string();
        let mut responses = Vec::new();
        for (index, response) in client
            .captured_citation_responses()
            .await
            .into_iter()
            .enumerate()
        {
            let (extension, format) =
                if serde_json::from_slice::<serde_json::Value>(&response.body).is_ok() {
                    ("json", "json")
                } else if std::str::from_utf8(&response.body).is_ok() {
                    ("txt", "txt")
                } else {
                    ("bin", "binary")
                };
            let file = write_artifact(
                node_ctx,
                &format!(
                    "{}.citation-run-{run_id}/response-{index}.{extension}",
                    self.spec.path
                ),
                response.body,
                format,
            )
            .await?;
            responses.push(serde_json::json!({
                "requested_url":response.requested_url,"final_url":response.final_url,
                "status":response.status,"content_type":response.content_type,
                "retry_after_ms":response.retry_after_ms,"body":file
            }));
        }
        let audit = serde_json::json!({
            "schema_version":2,"run_id":run_id,"paper_id":self.spec.paper_id,
            "direction":direction_word,"effective_limit":limit,"offset":offset,
            "responses":responses,"records_received":lookup.as_ref().ok().map(Vec::len),
            "outcome":match &lookup {Err(_)=>"LOOKUP_ERROR",Ok(records) if records.is_empty()=>"VALID_EMPTY_PAGE",Ok(_)=>"RECORDS"},
            "error":lookup.as_ref().err().map(ToString::to_string),
            "scope":"SDK_RECEIVED_ENTITY_BODY_BYTES_NOT_HTTP_WIRE_OR_COMPLETE_GRAPH",
            "audit_kind":"LOOKUP_RECEIPT_NOT_EVIDENCE_PUBLICATION",
            "g0_granted":false
        });
        write_artifact(
            node_ctx,
            &audit_path,
            serde_json::to_vec_pretty(&audit)
                .map_err(|error| DagError::Schedule(error.to_string()))?,
            "json",
        )
        .await?;
        let records = lookup?;

        if records.is_empty() {
            return Err(DagError::Schedule(format!(
                "valid empty {direction_word} page for `{}`; this does not establish an invalid paper id",
                self.spec.paper_id
            )));
        }

        let set = EvidenceSet {
            records,
            ..Default::default()
        };
        let bytes = set.to_bytes().map_err(DagError::Schedule)?;
        let file = write_artifact(node_ctx, &self.spec.path, bytes, FORMAT).await?;
        let mut outputs = PortOutputs::new();
        outputs.insert_file(0, file);
        Ok(outputs)
    }
}

pub struct LiteratureCitationsNodeFactory {}

#[async_trait]
impl NodeFactory for LiteratureCitationsNodeFactory {
    fn kind(&self) -> &'static str {
        "source_literature_citations"
    }

    fn desc(&self) -> &'static str {
        "Get papers citing a given paper (or its reference list) as an evidence file"
    }

    fn doc(&self) -> &'static str {
        "Walks the Semantic Scholar citation graph from one paper and writes the \
         result as an `evidence` artifact (File, format `evidence`). \
         `direction: citing` (default) returns papers that cite it — impact and \
         follow-up work; `direction: cited` returns its reference list. Each \
         record's note carries the citation-graph metadata: influence flag, \
         intents (methodology / background / result), and up to three context \
         snippets. `paper_id` accepts any S2 form (SHA, `CorpusId:<id>`, \
         `DOI:<doi>`, `ARXIV:<id>`, `PMID:<id>`, `URL:<url>`). Fails when the \
         response is an explicitly valid empty page; this does not establish an invalid id. Chain into evidence_merge \
         with search results, or evidence_export for a bibliography. \
         This retrieves one page, not the complete graph. Unknown controls, \
         input ports and limits outside 1..=1000 are rejected, not ignored or clipped. \
         Received body bytes and a lookup-only query receipt are retained on failure. \
         Existing evidence or receipts are not overwritten; use a new path for a new run."
    }

    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(LiteratureCitationsSpec)
    }

    fn ports(&self) -> NodePorts {
        port_layout()
    }

    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec: LiteratureCitationsSpec = serde_json::from_value(spec)?;
        spec.validated_page()
            .map_err(|error| dag_core::registry::error::Error::Unknown(error.to_string()))?;
        Ok(Box::new(LiteratureCitationsNode::new(spec)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_citation_controls_are_rejected() {
        let spec = serde_json::json!({
            "paper_id": "DOI:10.1000/fixture",
            "path": "vfs:///citations.json",
            "limti": 100
        });
        assert!(serde_json::from_value::<LiteratureCitationsSpec>(spec).is_err());
        let schema = serde_json::to_value(schema_for!(LiteratureCitationsSpec)).unwrap();
        assert_eq!(schema["additionalProperties"], false);
        assert_eq!(schema["properties"]["limit"]["minimum"], 1);
        assert_eq!(schema["properties"]["limit"]["maximum"], 1000);
    }

    fn input_contract_spec() -> LiteratureCitationsSpec {
        serde_json::from_value(serde_json::json!({
            "paper_id": "DOI:10.1000/fixture",
            "path": "vfs:///citations.json"
        }))
        .unwrap()
    }

    #[test]
    fn valid_page_defaults_and_boundaries_are_preserved() {
        let mut spec = input_contract_spec();
        assert_eq!(spec.validated_page().unwrap(), (20, 0));
        for limit in [1, 20, 1000] {
            spec.limit = Some(limit);
            spec.offset = Some(1234);
            assert_eq!(spec.validated_page().unwrap(), (limit, 1234));
        }
    }

    #[test]
    fn invalid_page_limits_are_rejected_without_clipping() {
        for limit in [0, 1001, u32::MAX] {
            let mut spec = input_contract_spec();
            spec.limit = Some(limit);
            assert!(
                spec.validated_page()
                    .unwrap_err()
                    .to_string()
                    .contains("not silently clipped")
            );
        }
    }

    #[test]
    fn invalid_identifiers_and_destinations_are_rejected() {
        for paper_id in [
            "",
            "   ",
            " DOI:10.1000/fixture",
            "DOI:10.1000/fixture\n",
            "PMID:\u{0000}1",
        ] {
            let mut spec = input_contract_spec();
            spec.paper_id = paper_id.into();
            assert!(spec.validated_page().is_err());
        }
        for path in ["", "/", "vfs:///", "relative.json", "vfs:///bad\n.json"] {
            let mut spec = input_contract_spec();
            spec.path = path.into();
            assert!(spec.validated_page().is_err());
        }
    }

    #[tokio::test]
    async fn direct_execution_rejects_invalid_controls_and_undeclared_inputs_before_lookup() {
        let context = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        let mut spec = input_contract_spec();
        spec.limit = Some(1001);
        let mut node = LiteratureCitationsNode::new(spec);
        let error = node
            .execute(
                &context,
                &[],
                &dag_core::dag::node_event::NodeReporter::noop(),
            )
            .await
            .unwrap_err();
        assert!(error.to_string().contains("not silently clipped"));
        let mut node = LiteratureCitationsNode::new(input_contract_spec());
        let error = node
            .execute(
                &context,
                &[NodeInput::file(
                    0,
                    dag_core::value::FileRef::new("vfs:///unused.json", None),
                )],
                &dag_core::dag::node_event::NodeReporter::noop(),
            )
            .await
            .unwrap_err();
        assert!(error.to_string().contains("declares no input ports"));
    }

    #[test]
    fn factory_build_rejects_invalid_request_contracts() {
        let context = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        for patch in [
            serde_json::json!({"limit": 0}),
            serde_json::json!({"limit": 1001}),
            serde_json::json!({"paper_id": ""}),
            serde_json::json!({"path": "relative.json"}),
            serde_json::json!({"limti": 20}),
        ] {
            let mut value =
                serde_json::json!({"paper_id": "PMID:1", "path": "vfs:///citations.json"});
            value
                .as_object_mut()
                .unwrap()
                .extend(patch.as_object().unwrap().clone());
            assert!(
                LiteratureCitationsNodeFactory {}
                    .build(value, context.clone())
                    .is_err()
            );
        }
        assert!(
            LiteratureCitationsNodeFactory {}
                .build(
                    serde_json::json!({"paper_id": "PMID:1", "path": "vfs:///citations.json"}),
                    context,
                )
                .is_ok()
        );
    }

    fn strs(items: &[&str]) -> Option<Vec<String>> {
        Some(items.iter().map(|s| s.to_string()).collect())
    }

    #[test]
    fn citation_note_composes_metadata_compactly() {
        let contexts = strs(&["We follow the design of X"]);
        let intents = strs(&["methodology"]);
        let note = citation_note(
            contexts.as_ref(),
            intents.as_ref(),
            Some(true),
            Some("user note"),
        )
        .unwrap();
        assert!(
            note.starts_with("influential citation; intents: [methodology]"),
            "{note}"
        );
        assert!(note.contains("context: "), "{note}");
        assert!(note.ends_with("user note"), "{note}");
    }

    #[test]
    fn citation_note_none_when_entry_carries_no_metadata() {
        assert!(citation_note(None, None, None, None).is_none());
        // No metadata but a user note still yields the note.
        assert_eq!(citation_note(None, None, None, Some("n")), Some("n".into()));
    }

    #[test]
    fn article_conversion_preserves_title() {
        let paper = semantic_scholar::types::Paper {
            paper_id: "x".into(),
            title: Some("Follow-up work".into()),
            ..Default::default()
        };
        let article: Article = semantic_scholar::convert::paper_to_article(&paper);
        assert_eq!(article.title, "Follow-up work");
    }
}
