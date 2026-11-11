//! `literature_fulltext`: resolve the full-text files behind evidence
//! records into a `FileSet` of real VFS `FileRef`s.
//!
//! The bibliography library keeps uploaded full texts as content-addressed
//! VFS objects (`vfs:///literature/{article_id}/{sha256}-{filename}`) with
//! `fulltexts` DB rows as pointers. This node turns evidence records into
//! those pointers' [`FileRef`]s after verifying the actual library and
//! runtime bytes against any recorded `file_hash` and `file_size`.
//!
//! One repair on the way through: full texts fetched from Europe PMC are
//! stored as synthetic pointers (`europepmc:PMC…`) with the text inline and
//! no VFS object behind them. The node materializes those into real
//! content-addressed objects and rewrites the row, so every resolved output
//! is an actual file — get_output shows a FileRef, not a URI scheme.

use std::sync::Arc;

use async_trait::async_trait;
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;
use sha2::{Digest, Sha256};

use bib_types::evidence::{EvidenceSet, FORMAT};
use bib_types::types::{FileFormat, FullText, IdKind};
use dag_core::dag::graph::PortOutputs;
use dag_core::dag::{DagError, DagNode};
use dag_core::node::{NodeInput, NodePorts};
use dag_core::registry::{NodeCtx, NodeFactory};
use dag_core::value::{FileFingerprint, FileRef, PortType};

use crate::nodes::{read_file_bytes, shared_bib, to_vfs_uri, validate_output_path};
use crate::library_service::LibraryAccess;
use crate::shared::BibShared;
use crate::stored_files::vfs_virtual_path;

/// Spec for [`LiteratureFulltextNode`].
#[derive(Debug, Clone, JsonSchema, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct LiteratureFulltextSpec {
    /// When `true` (default), records whose article is missing from the
    /// library — or present without a full text — are saved and fetched
    /// from Europe PMC open access, mirroring `bib_save`. When `false` the
    /// node is a pure resolver over the existing library.
    #[serde(default)]
    pub fetch_missing: Option<bool>,
}

fn port_layout() -> NodePorts {
    NodePorts::new()
        .add_input_port_of_type_with_label_and_format(None, PortType::File, "evidence", FORMAT)
        .add_output_port_of_type(None, PortType::FileSet)
}

/// Verify both VFS views and any recorded database identity before
/// publishing a mutable snapshot of the actual bytes. Missing legacy
/// hash/size fields are filled in the output, not silently written to the DB.
async fn verified_file_ref(
    context: &NodeCtx,
    shared: &LibraryAccess,
    fulltext: &FullText,
) -> Result<FileRef, DagError> {
    validate_output_path(&fulltext.file_path)?;
    let path = to_vfs_uri(&fulltext.file_path);
    let virtual_path = vfs_virtual_path(&path)
        .ok_or_else(|| DagError::Schedule("invalid stored full-text VFS path".into()))?;
    let storage = shared.file_storage.as_ref().ok_or_else(|| {
        DagError::Schedule("full-text verification requires library VFS storage".into())
    })?;
    let bytes = storage
        .resolve(&virtual_path)
        .read(&storage.resolve_path(&virtual_path))
        .await
        .map_err(|error| {
            DagError::Schedule(format!("cannot read stored full text `{path}`: {error}"))
        })?
        .to_vec();
    let size = bytes.len() as u64;
    let digest = format!("{:x}", Sha256::digest(&bytes));
    if fulltext
        .file_size
        .is_some_and(|declared| declared < 0 || declared as u64 != size)
    {
        return Err(DagError::Schedule(format!(
            "stored full-text size does not match actual bytes: `{path}`"
        )));
    }
    if let Some(declared) = &fulltext.file_hash
        && (declared.len() != 64
            || !declared.bytes().all(|byte| byte.is_ascii_hexdigit())
            || !declared.eq_ignore_ascii_case(&digest))
    {
        return Err(DagError::Schedule(format!(
            "stored full-text SHA256 does not match actual bytes: `{path}`"
        )));
    }
    if read_file_bytes(context, &path).await? != bytes {
        return Err(DagError::Schedule(format!(
            "library and runtime full-text VFS bytes differ: `{path}`"
        )));
    }
    Ok(FileRef {
        path,
        format: Some(fulltext.file_format.as_str().to_string()),
        fingerprint: Some(FileFingerprint {
            size,
            mtime_ns: 0,
            content_hash: Some(format!("sha256:{digest}")),
            immutable_remote: false,
        }),
    })
}

pub struct LiteratureFulltextNode {
    meta: NodePorts,
    spec: LiteratureFulltextSpec,
    /// Test seam: injected shared bibliography.
    shared: Option<Arc<LibraryAccess>>,
}

impl LiteratureFulltextNode {
    pub fn new(spec: LiteratureFulltextSpec) -> Self {
        Self {
            meta: port_layout(),
            spec,
            shared: None,
        }
    }

    /// Build a node bound to a caller-supplied bibliography (tests).
    pub fn with_shared(spec: LiteratureFulltextSpec, shared: Arc<BibShared>) -> Self {
        Self {
            meta: port_layout(),
            spec,
            shared: Some(Arc::new(LibraryAccess::local(shared))),
        }
    }
}

/// Identifier kinds tried, in order, when matching an evidence record
/// against the library — same priority the dedup layer uses.
const ID_KINDS: [IdKind; 4] = [IdKind::Doi, IdKind::Pmid, IdKind::Pmc, IdKind::Arxiv];

impl LiteratureFulltextNode {
    fn shared(&self) -> Result<Arc<LibraryAccess>, DagError> {
        self.shared.clone().map(Ok).unwrap_or_else(shared_bib)
    }

    async fn lookup_article_id(
        bib: &LibraryAccess,
        citation: &bib_types::Article,
    ) -> Result<Option<String>, String> {
        let mut matched_article_id: Option<String> = None;
        for kind in ID_KINDS {
            for identifier in citation.identifiers.iter().filter(|identifier| identifier.kind == kind) {
                let normalized = if kind == IdKind::Doi {
                    bib_types::convert::normalize_doi(&identifier.value)
                } else {
                    identifier.value.trim().to_string()
                };
                let mut candidates = vec![normalized.clone()];
                if kind == IdKind::Doi {
                    let lower = normalized.to_lowercase();
                    if lower != normalized {
                        candidates.push(lower);
                    }
                }
                for candidate in &candidates {
                    if let Some(article) = bib
                        .find_by_identifier(kind, candidate)
                        .await
                        .map_err(|error| format!("reading identifiers for `{candidate}`: {error}"))?
                    {
                        if matched_article_id.as_ref().is_some_and(|previous| previous != &article.id) {
                            return Err("conflicting citation identifiers resolve to different library articles".into());
                        }
                        matched_article_id = Some(article.id);
                    }
                }
            }
        }
        Ok(matched_article_id)
    }

    /// Resolve one evidence record to a stored [`FullText`], optionally
    /// saving + OA-fetching when missing. `None` with a reason on miss.
    async fn resolve_record(
        &self,
        bib: &Arc<LibraryAccess>,
        shared: &Arc<LibraryAccess>,
        record: &bib_types::evidence::EvidenceRecord,
        fetch_missing: bool,
    ) -> Result<Option<FullText>, String> {
        let citation = &record.citation;
        let describe = || {
            citation
                .doi()
                .map(|doi| format!("doi:{doi}"))
                .or_else(|| citation.pmid().map(|pmid| format!("pmid:{pmid}")))
                .unwrap_or_else(|| citation.title.clone())
        };

        let mut article_id = Self::lookup_article_id(bib, citation).await?;

        // 2. Missing article: save the evidence citation itself, then fetch.
        if article_id.is_none() && fetch_missing {
            bib.upsert_article(citation)
                .await
                .map_err(|error| format!("saving `{}`: {error}", describe()))?;
            article_id = Some(citation.id.clone());
        }
        let Some(article_id) = article_id else {
            return Ok(None);
        };

        // 3. Existing full text.
        if let Some(fulltext) = bib
            .get_fulltext(&article_id)
            .await
            .map_err(|error| format!("reading fulltexts for `{article_id}`: {error}"))?
        {
            return Ok(Some(fulltext));
        }
        if !fetch_missing {
            return Ok(None);
        }

        // 4. OA fetch — the canonical file-writing path (same chain as
        // bib_save): text lands in the VFS, the row points at the file.
        let Some(article) = bib
            .get_article(&article_id)
            .await
            .map_err(|error| format!("reloading `{}`: {error}", describe()))?
        else {
            return Ok(None);
        };
        let fetched = match shared.file_storage.as_ref() {
            Some(_) => shared.fetch_fulltext(&article).await.map_err(|error| format!("bibliography service: {error}"))?,
            // No storage handle: fetching would produce a synthetic
            // pointer, which this node exists to eliminate.
            None => return Ok(None),
        };
        match fetched {
            Some(fulltext) => Ok(Some(fulltext)),
            None => Ok(None),
        }
    }

    /// Synthetic `europepmc:` pointers carry their text inline with no VFS
    /// object. Materialize the text into a content-addressed object,
    /// rewrite the row, and return the real path.
    async fn materialize(&self, fulltext: FullText) -> Result<FullText, DagError> {
        self.shared()?.materialize_legacy(fulltext).await
            .map_err(|error| DagError::Schedule(error.to_string()))
    }

}

#[async_trait]
impl DagNode for LiteratureFulltextNode {
    fn remote_execution_blocker(&self) -> Option<&'static str> {
        Some("literature_fulltext requires the coordinator's shared bibliography; independent workers do not own that library. Fetch an explicitly approved full-text URL with http_fetch on a worker with an operator-configured network policy. This is not evidence that the article is unavailable and does not authorize local execution.")
    }

    fn ports(&self) -> &NodePorts {
        &self.meta
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(Self {
            meta: self.meta.clone(),
            spec: self.spec.clone(),
            shared: self.shared.clone(),
        })
    }

    fn kind(&self) -> &'static str {
        "literature_fulltext"
    }

    fn as_any(&self) -> &dyn std::any::Any {
        self
    }

    async fn cache_dependency_state(
        &self,
        context: &NodeCtx,
        inputs: &[NodeInput],
    ) -> Result<Option<serde_json::Value>, DagError> {
        if inputs.len() != 1 || inputs[0].port != 0 {
            return Err(DagError::Schedule(
                "literature_fulltext requires exactly one evidence input on port 0".into(),
            ));
        }
        let file = inputs[0].file_value()?;
        if file
            .format
            .as_deref()
            .is_some_and(|format| format != FORMAT)
        {
            return Err(DagError::Schedule(
                "literature_fulltext cache dependency requires evidence input".into(),
            ));
        }
        let shared = self.shared()?;
        let bytes = read_file_bytes(context, &file.path).await?;
        let evidence = EvidenceSet::parse(&bytes).map_err(|error| {
            DagError::Schedule(format!(
                "cannot read full-text dependency evidence: {error}"
            ))
        })?;
        let fetch_missing = self.spec.fetch_missing.unwrap_or(true);
        let mut records = Vec::with_capacity(evidence.records.len());
        for record in &evidence.records {
            let matched = Self::lookup_article_id(&shared, &record.citation)
                .await
                .map_err(DagError::Schedule)?;
            let effective = matched
                .clone()
                .or_else(|| fetch_missing.then(|| record.citation.id.clone()));
            let fulltext = match effective.as_deref() {
                Some(article_id) => shared.get_fulltext(article_id).await.map_err(|error| {
                    DagError::Schedule(format!(
                        "reading fulltexts dependency for `{article_id}`: {error}"
                    ))
                })?,
                None => None,
            };
            let declaration = fulltext.as_ref().map(|fulltext| {
                let inline_hash = if fulltext.file_path.starts_with("europepmc:") {
                    fulltext
                        .text_content
                        .as_ref()
                        .map(|text| format!("sha256:{:x}", Sha256::digest(text.as_bytes())))
                } else {
                    None
                };
                serde_json::json!({"article_id":fulltext.article_id,"path":fulltext.file_path,
                    "format":fulltext.file_format.as_str(),"hash":fulltext.file_hash,
                    "size":fulltext.file_size,"synthetic_text_hash":inline_hash})
            });
            let mut oa_identifiers = Vec::new();
            if fetch_missing && fulltext.is_none() {
                let article = match effective.as_deref() {
                    Some(article_id) => {
                        shared.get_article(article_id).await.map_err(|error| {
                            DagError::Schedule(format!(
                                "reading OA dependency for `{article_id}`: {error}"
                            ))
                        })?
                    }
                    None => None,
                };
                let article = article.as_ref().unwrap_or(&record.citation);
                for kind in [IdKind::Pmc, IdKind::Pmid, IdKind::Doi] {
                    oa_identifiers
                        .push(serde_json::json!({"kind":kind,"value":article.identifier(kind)}));
                }
            }
            records.push(
                serde_json::json!({"matched_article_id":matched,"effective_article_id":effective,
                "fulltext":declaration,"oa_identifiers":oa_identifiers}),
            );
        }
        Ok(Some(
            serde_json::json!({"schema":"bib-fulltext-cache-dependency-v1",
            "fetch_missing":fetch_missing,"records":records}),
        ))
    }

    async fn execute(
        &mut self,
        node_ctx: &NodeCtx,
        inputs: &[NodeInput],
        reporter: &dag_core::dag::node_event::NodeReporter,
    ) -> std::result::Result<PortOutputs, DagError> {
        if inputs.len() != 1 || inputs[0].port != 0 {
            return Err(DagError::Schedule(
                "literature_fulltext requires exactly one evidence input on port 0".into(),
            ));
        }
        let input = inputs.first().ok_or_else(|| {
            DagError::Schedule(
                "literature_fulltext requires exactly one evidence input on port 0".into(),
            )
        })?;
        let file = input.file_value()?;
        if let Some(format) = file.format.as_deref()
            && format != FORMAT
        {
            return Err(DagError::Schedule(format!(
                "literature_fulltext input carries format `{format}`, expected `{FORMAT}`"
            )));
        }

        let shared = self.shared()?;
        let bib = shared.clone();
        let bytes = read_file_bytes(node_ctx, &file.path).await?;
        let set = EvidenceSet::parse(&bytes).map_err(|error| {
            DagError::Schedule(format!(
                "literature_fulltext input `{}`: {error}",
                file.path
            ))
        })?;
        let fetch_missing = self.spec.fetch_missing.unwrap_or(true);

        let mut files: Vec<FileRef> = Vec::with_capacity(set.records.len());
        let mut misses: Vec<String> = Vec::new();
        for record in &set.records {
            match self
                .resolve_record(&bib, &shared, record, fetch_missing)
                .await
            {
                Ok(Some(fulltext)) => {
                    let fulltext = if fulltext.file_path.starts_with("vfs://") {
                        fulltext
                    } else if fulltext.file_path.starts_with("europepmc:") {
                        let _storage = shared.file_storage.as_ref().ok_or_else(|| {
                            DagError::Schedule(
                                "synthetic full text requires library VFS storage".into(),
                            )
                        })?;
                        self.materialize(fulltext).await?
                    } else {
                        return Err(DagError::Schedule(format!(
                            "unsupported stored full-text path `{}`",
                            fulltext.file_path
                        )));
                    };
                    files.push(verified_file_ref(node_ctx, &shared, &fulltext).await?);
                }
                Ok(None) => misses.push(miss_label(record)),
                Err(reason) => {
                    return Err(DagError::Schedule(format!(
                        "literature_fulltext failed on {reason}"
                    )));
                }
            }
        }

        if files.is_empty() {
            // Even on the failure path, surface the miss list through the
            // NodeReporter so the TUI / scheduler log see it; the JSON
            // `report.warnings` field stays engine-level and will not
            // carry per-node reporter emissions, so callers should judge
            // coverage from the (zero-length) FileSet / runtime
            // telemetry, not from an empty warnings array.
            let message = format!(
                "no full text resolved for any of the {} evidence record(s): {}",
                set.records.len(),
                misses.join(", ")
            );
            reporter.warn(message.clone());
            return Err(DagError::Schedule(message));
        }
        if !misses.is_empty() {
            reporter.warn(format!(
                "{} of {} evidence record(s) have no full text available: {}",
                misses.len(),
                set.records.len(),
                misses.join(", ")
            ));
        }

        let mut outputs = PortOutputs::new();
        outputs.insert(0, files);
        Ok(outputs)
    }
}

fn miss_label(record: &bib_types::evidence::EvidenceRecord) -> String {
    let citation = &record.citation;
    citation
        .doi()
        .map(|doi| format!("doi:{}", bib_types::convert::normalize_doi(doi)))
        .or_else(|| citation.pmid().map(|pmid| format!("pmid:{pmid}")))
        .unwrap_or_else(|| citation.short_cite())
}

pub struct LiteratureFulltextNodeFactory {}

#[async_trait]
impl NodeFactory for LiteratureFulltextNodeFactory {
    fn kind(&self) -> &'static str {
        "literature_fulltext"
    }

    fn desc(&self) -> &'static str {
        "Resolve evidence records to their full-text files as a FileSet of FileRefs"
    }

    fn doc(&self) -> &'static str {
        "Takes one `evidence` artifact and resolves every record to the full-text \
         file stored in the bibliography library, emitting a FileSet of real \
         VFS FileRefs — get_output on this node lists the actual files \
         (path, format pdf/txt/html, sha256 fingerprint). Records are matched \
         to the library by DOI, then PMID, PMCID, arXiv id. With \
         `fetch_missing: true` (default), unmatched records are saved from \
         the evidence citation and their full text fetched from Europe PMC \
         open access **as a stored VFS file** (the same file-writing chain \
         as bib_save); `false` makes the node a pure resolver over the \
         existing library.\n\
         \n\
         Open-access texts that were stored as synthetic pointers without a \
         backing file are materialized into content-addressed VFS objects on \
         first resolution. Library and runtime bytes must agree, and any \
         recorded hash/size must match before a mutable FileRef is emitted. \
         Missing objects, identity mismatches and unsupported stored paths \
         fail the node rather than publishing unchecked pointers. Records \
         with no full text available are skipped with a warning naming the \
         identifier; when nothing resolves at all the node fails and the same \
         warning is emitted first so the TUI / scheduler log can see the \
         miss list. (Note: NodeReporter warnings do **not** flow into the \
         run-level JSON `warnings` array — judge coverage from the FileSet \
         length and timing, not from an empty warnings array.)\n\
         \n\
         Requires the runtime host's shared bibliography (the same storage \
         the engine and the library mount). Independent remote workers cannot \
         use this library service. For remote retrieval, use `http_fetch` with \
         an approved full-text URL and an operator-configured worker network policy; \
         do not switch to local execution when remote placement is required."
    }

    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(LiteratureFulltextSpec)
    }

    fn ports(&self) -> NodePorts {
        port_layout()
    }

    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec: LiteratureFulltextSpec = serde_json::from_value(spec)?;
        Ok(Box::new(LiteratureFulltextNode::new(spec)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::stored_fulltext;
    use bib_types::evidence::EvidenceRecord;
    use bib_types::types::{Article, Identifier};
    use dag_core::dag::node_event::NodeReporter;
    use dag_core::node::NodeInput;

    #[test]
    fn fetch_controls_reject_unknown_spellings_before_library_or_network() {
        for field in ["fetch_misssing", "fetchMissing", "allow_fetch"] {
            let mut specification = serde_json::json!({});
            specification[field] = serde_json::json!(false);
            let parsed = serde_json::from_value::<LiteratureFulltextSpec>(specification.clone());
            assert!(parsed.is_err(), "silently discarded {field}");
            let context = NodeCtx::new(
                datafusion::prelude::SessionContext::new().runtime_env(),
                None,
            );
            assert!(
                LiteratureFulltextNodeFactory {}
                    .build(specification, context)
                    .is_err()
            );
        }
    }

    #[test]
    fn fetch_controls_preserve_explicit_boolean_and_existing_default() {
        for requested in [false, true] {
            let specification: LiteratureFulltextSpec =
                serde_json::from_value(serde_json::json!({"fetch_missing":requested})).unwrap();
            assert_eq!(specification.fetch_missing, Some(requested));
        }
        let default: LiteratureFulltextSpec =
            serde_json::from_value(serde_json::json!({})).unwrap();
        assert_eq!(default.fetch_missing, None);
        assert!(default.fetch_missing.unwrap_or(true));
        for invalid in [serde_json::json!("false"), serde_json::json!(0)] {
            assert!(
                serde_json::from_value::<LiteratureFulltextSpec>(
                    serde_json::json!({"fetch_missing":invalid})
                )
                .is_err()
            );
        }
    }

    #[tokio::test]
    async fn fetch_controls_reject_misrouted_evidence_before_library_lookup() {
        let mut node = LiteratureFulltextNode::new(LiteratureFulltextSpec {
            fetch_missing: Some(false),
        });
        let context = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        let inputs = [NodeInput::file(
            3,
            FileRef::new("vfs:///not-read.json", Some(FORMAT.into())),
        )];
        let execution = node.execute(&context, &inputs, &NodeReporter::noop()).await;
        let cache = node.cache_dependency_state(&context, &inputs).await;
        assert!(execution.unwrap_err().to_string().contains("port 0"));
        assert!(cache.unwrap_err().to_string().contains("port 0"));
    }

    async fn citation_identity_fixture(
        mode: &str,
    ) -> (NodeCtx, LiteratureFulltextNode, Vec<NodeInput>, String) {
        let shared = shared_with_storage().await;
        let (context, storage) = node_ctx_with_evidence_storage(&shared);
        let mut first = Article::new("cached-first", "Synthetic first article")
            .with_doi("10.9999/identity-a");
        first.identifiers.push(Identifier::pmid("910001"));
        let mut second = Article::new("cached-second", "Synthetic second article")
            .with_doi("10.9999/identity-b");
        second.identifiers.push(Identifier::pmid("910002"));
        shared.bib.upsert_article(&first).await.unwrap();
        shared.bib.upsert_article(&second).await.unwrap();
        let stored = upload_fulltext(&shared, &first.id, b"synthetic first article bytes").await;
        assert_eq!(shared.bib.find_by_identifier(IdKind::Doi, "10.9999/identity-a")
            .await.unwrap().unwrap().id, first.id);
        assert_eq!(shared.bib.find_by_identifier(IdKind::Pmid, "910002")
            .await.unwrap().unwrap().id, second.id);
        let mut citation = Article::new("cached-evidence", "Synthetic citation")
            .with_doi("10.9999/identity-a");
        match mode {
            "conflicting-kinds" => citation.identifiers.push(Identifier::pmid("910002")),
            "conflicting-dois" => citation.identifiers.push(Identifier::doi("10.9999/identity-b")),
            "consistent" => {
                citation.identifiers[0] = Identifier::doi("https://doi.org/10.9999/IDENTITY-A");
                citation.identifiers.push(Identifier::pmid("910001"));
            }
            _ => panic!("Unknown synthetic citation fixture"),
        }
        let path = write_evidence(&storage, mode, vec![EvidenceRecord {
            citation, note: None, origin: Some("synthetic-identity-contract".into()),
        }]).await;
        let inputs = vec![NodeInput::file(0, FileRef::new(path, Some(FORMAT.into())))];
        let node = LiteratureFulltextNode::with_shared(
            LiteratureFulltextSpec { fetch_missing: Some(false) }, shared,
        );
        (context, node, inputs, stored.file_path)
    }

    #[tokio::test]
    async fn cached_identity_execution_rejects_conflicting_known_identifiers() {
        let (context, mut node, inputs, _expected_path) = citation_identity_fixture("conflicting-kinds").await;
        let error = node.execute(&context, &inputs, &NodeReporter::noop()).await
            .expect_err("Conflicting locally resolved DOI/PMID must not select the first article");
        assert!(error.to_string().contains("conflicting citation identifiers"), "{error}");
    }

    #[tokio::test]
    async fn cached_identity_cache_state_rejects_conflicting_known_identifiers() {
        let (context, node, inputs, _expected_path) = citation_identity_fixture("conflicting-kinds").await;
        let error = node.cache_dependency_state(&context, &inputs).await
            .expect_err("An ambiguous citation cannot acquire a reusable cached identity");
        assert!(error.to_string().contains("conflicting citation identifiers"), "{error}");
    }

    #[tokio::test]
    async fn cached_identity_execution_checks_every_same_kind_identifier() {
        let (context, mut node, inputs, _expected_path) = citation_identity_fixture("conflicting-dois").await;
        let error = node.execute(&context, &inputs, &NodeReporter::noop()).await
            .expect_err("The second DOI must not be silently ignored");
        assert!(error.to_string().contains("conflicting citation identifiers"), "{error}");
    }

    #[tokio::test]
    async fn cached_identity_consistent_normalized_identifiers_keep_existing_result() {
        let (context, mut node, inputs, expected_path) = citation_identity_fixture("consistent").await;
        let outputs = node.execute(&context, &inputs, &NodeReporter::noop()).await.unwrap();
        let files = outputs.get(&0).unwrap().as_file_set().unwrap();
        assert_eq!(files.len(), 1);
        assert_eq!(files[0].path, expected_path);
        assert!(node.cache_dependency_state(&context, &inputs).await.unwrap().is_some());
    }

    async fn shared_with_storage() -> Arc<BibShared> {
        let shared = BibShared::open_in_memory()
            .await
            .unwrap()
            .with_file_storage(Arc::new(vfs::OpendalFileStorage::new_temp()));
        Arc::new(shared)
    }

    /// A NodeCtx whose mounted VFS mirrors the test's evidence file.
    /// The node reads the evidence bytes via `read_file_bytes`, which
    /// routes through the mounted opendal storage.
    fn node_ctx_with_evidence_storage(
        shared: &BibShared,
    ) -> (NodeCtx, Arc<vfs::OpendalFileStorage>) {
        let storage = shared.file_storage.as_ref().unwrap().clone();
        let ctx = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            Some(storage.clone()),
        );
        (ctx, storage)
    }

    /// Write the evidence JSON into the VFS storage at a fresh
    /// `/tmp/fulltext-node-...json` virtual path and return that path.
    /// The node reads it via `read_file_bytes`, which resolves the bare
    /// absolute path through the mounted opendal storage.
    async fn write_evidence(
        storage: &vfs::OpendalFileStorage,
        tag: &str,
        records: Vec<EvidenceRecord>,
    ) -> String {
        let path = format!("/tmp/fulltext-node-{tag}-{}.json", uuid::Uuid::new_v4());
        let set = EvidenceSet {
            records,
            ..Default::default()
        };
        storage
            .write_bytes(&path, set.to_bytes().unwrap())
            .await
            .unwrap();
        path
    }

    async fn upload_fulltext(shared: &BibShared, article_id: &str, content: &[u8]) -> FullText {
        let stored = stored_fulltext(article_id, "paper.pdf", content);
        let virtual_path = vfs_virtual_path(&stored.path).unwrap();
        shared
            .file_storage
            .as_ref()
            .unwrap()
            .write_bytes(&virtual_path, content.to_vec())
            .await
            .unwrap();
        let fulltext = FullText {
            article_id: article_id.to_owned(),
            attachment_key: None,
            file_path: stored.path,
            file_format: FileFormat::Pdf,
            text_content: None,
            source: bib_types::types::FullTextSource::UserUpload,
            file_hash: Some(stored.file_hash.clone()),
            file_size: Some(content.len() as i64),
            uploaded_at: None,
            extract_status: None,
            text_format: None,
            extracted_by: None,
            extract_error: None,
        };
        shared.bib.upsert_fulltext(&fulltext).await.unwrap();
        fulltext
    }

    #[tokio::test]
    async fn resolves_uploaded_fulltext_to_fileset() {
        let shared = shared_with_storage().await;
        let (ctx, storage) = node_ctx_with_evidence_storage(&shared);
        let mut article = Article::new("art-1", "Uploaded study");
        article.identifiers.push(Identifier::doi("10.1/up"));
        shared.bib.upsert_article(&article).await.unwrap();
        let stored = upload_fulltext(&shared, "art-1", b"%PDF-1.4 fake").await;

        let mut record_citation = Article::new("ev-1", "Uploaded study");
        record_citation
            .identifiers
            .push(Identifier::doi("https://doi.org/10.1/UP"));
        let path = write_evidence(
            &storage,
            "uploaded",
            vec![EvidenceRecord {
                citation: record_citation,
                note: None,
                origin: None,
            }],
        )
        .await;

        let mut node = LiteratureFulltextNode::with_shared(
            LiteratureFulltextSpec {
                fetch_missing: Some(false),
            },
            shared.clone(),
        );
        let inputs = vec![NodeInput::file(0, FileRef::new(&path, Some(FORMAT.into())))];
        let outputs = node
            .execute(&ctx, &inputs, &NodeReporter::noop())
            .await
            .unwrap();

        let files = outputs
            .get(&0)
            .and_then(|value| value.as_file_set().ok())
            .expect("FileSet output");
        assert_eq!(files.len(), 1);
        assert_eq!(files[0].path, stored.file_path);
        assert_eq!(files[0].format.as_deref(), Some("pdf"));
        let fingerprint = files[0].fingerprint.as_ref().unwrap();
        assert_eq!(fingerprint.size, b"%PDF-1.4 fake".len() as u64);
        assert_eq!(
            fingerprint.content_hash.as_deref(),
            stored
                .file_hash
                .map(|hash| format!("sha256:{hash}"))
                .as_deref()
        );
        assert!(!fingerprint.immutable_remote);
    }

    #[tokio::test]
    async fn materializes_synthetic_pointer_into_vfs_object() {
        let shared = shared_with_storage().await;
        let (ctx, storage) = node_ctx_with_evidence_storage(&shared);
        let mut article = Article::new("art-2", "OA study");
        article.identifiers.push(Identifier::pmid("42"));
        shared.bib.upsert_article(&article).await.unwrap();
        // Synthetic Europe PMC pointer: inline text, no VFS object.
        shared
            .bib
            .upsert_fulltext(&FullText {
                article_id: "art-2".into(),
                attachment_key: None,
                file_path: "europepmc:PMC42".into(),
                file_format: FileFormat::Txt,
                text_content: Some("full text words".into()),
                source: bib_types::types::FullTextSource::OpenAccess,
                file_hash: None,
                file_size: Some(15),
                uploaded_at: None,
                extract_status: None,
                text_format: None,
                extracted_by: None,
                extract_error: None,
            })
            .await
            .unwrap();

        let path = write_evidence(
            &storage,
            "synthetic",
            vec![EvidenceRecord {
                citation: article.clone(),
                note: None,
                origin: None,
            }],
        )
        .await;

        let mut node = LiteratureFulltextNode::with_shared(
            LiteratureFulltextSpec {
                fetch_missing: Some(false),
            },
            shared.clone(),
        );
        let inputs = vec![NodeInput::file(0, FileRef::new(&path, Some(FORMAT.into())))];
        let outputs = node
            .execute(&ctx, &inputs, &NodeReporter::noop())
            .await
            .unwrap();

        let files = outputs
            .get(&0)
            .and_then(|value| value.as_file_set().ok())
            .unwrap();
        assert_eq!(files.len(), 1);
        assert!(
            files[0].path.starts_with("vfs:///literature/art-2/"),
            "{}",
            files[0].path
        );
        assert!(
            files[0]
                .fingerprint
                .as_ref()
                .and_then(|fp| fp.content_hash.as_deref())
                .is_some_and(|hash| hash.starts_with("sha256:"))
        );

        // The DB row now points at the materialized object.
        let row = shared.bib.get_fulltext("art-2").await.unwrap().unwrap();
        assert_eq!(row.file_path, files[0].path);
        // And the object is readable through the library storage.
        let virtual_path = vfs_virtual_path(&row.file_path).unwrap();
        let storage = shared.file_storage.as_ref().unwrap();
        let size = storage.content_length(&virtual_path).await.unwrap();
        let bytes = storage.read_range(&virtual_path, 0..size).await.unwrap();
        assert_eq!(bytes.to_vec(), b"full text words");
    }

    #[tokio::test]
    async fn nothing_resolved_fails_with_identifier_list() {
        let shared = shared_with_storage().await;
        let (ctx, storage) = node_ctx_with_evidence_storage(&shared);
        let mut citation = Article::new("evidence-x", "Unknown study");
        citation.identifiers.push(Identifier::doi("10.1/nowhere"));
        let path = write_evidence(
            &storage,
            "miss",
            vec![EvidenceRecord {
                citation,
                note: None,
                origin: None,
            }],
        )
        .await;
        let mut node = LiteratureFulltextNode::with_shared(
            LiteratureFulltextSpec {
                fetch_missing: Some(false),
            },
            shared,
        );
        let inputs = vec![NodeInput::file(0, FileRef::new(&path, Some(FORMAT.into())))];
        let err = node
            .execute(&ctx, &inputs, &NodeReporter::noop())
            .await
            .unwrap_err()
            .to_string();
        assert!(err.contains("no full text resolved"), "{err}");
        assert!(err.contains("doi:10.1/nowhere"), "{err}");
    }

    #[tokio::test]
    async fn without_shared_bibliography_fails_closed() {
        let ctx_no_storage = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        let mut node = LiteratureFulltextNode::new(LiteratureFulltextSpec {
            fetch_missing: None,
        });
        let blocker = node.remote_execution_blocker().unwrap();
        assert!(blocker.contains("shared bibliography"));
        assert!(blocker.contains("http_fetch"));
        let err = node
            .execute(&ctx_no_storage, &[], &NodeReporter::noop())
            .await
            .unwrap_err()
            .to_string();
        // Empty input trips first; call the accessor directly for the
        // no-shared case.
        drop(err);
        let err = shared_bib().unwrap_err().to_string();
        assert!(err.contains("shared bibliography"), "{err}");
    }
}
