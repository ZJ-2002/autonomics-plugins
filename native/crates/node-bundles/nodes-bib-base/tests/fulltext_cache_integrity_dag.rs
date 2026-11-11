use std::sync::{
    Arc,
    atomic::{AtomicUsize, Ordering},
};

use async_trait::async_trait;
use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_fulltext::{LiteratureFulltextNode, LiteratureFulltextSpec};
use nodes_bib_base::nodes::literature_search::{LiteratureSearchNode, LiteratureSearchSpec};
use bib_base::shared::BibShared;
use bib_base::stored_files::{stored_fulltext, vfs_virtual_path};
use bib_base::{LiteratureGateway, LiteratureSource, SourceBatch};
use bib_types::{Article, FileFormat, FullText, FullTextSource, Identifier, StructuredSearch};
use dag_core::dag::graph::PortOutputs;
use dag_core::dag::node_event::NodeReporter;
use dag_core::dag::runtime::{InputHashing, RunReport, SchedulerConfig};
use dag_core::dag::{DAG, DagError, DagNode};
use dag_core::node::{NodeInput, NodePorts};
use dag_core::registry::NodeCtx;
use dag_core::value::PortType;
use serde_json::json;
use sha2::{Digest, Sha256};

struct Root {
    path: std::path::PathBuf,
    persistent: bool,
}

impl Root {
    fn new(tag: &str) -> Self {
        let persistent = std::env::var_os("FULLTEXT_INTEGRITY_EVIDENCE_ROOT");
        let path = persistent
            .as_ref()
            .map(std::path::PathBuf::from)
            .map(|root| root.join(tag))
            .unwrap_or_else(|| {
                std::env::temp_dir().join(format!("fulltext-dag-{}", uuid::Uuid::new_v4()))
            });
        assert!(!path.exists(), "fresh proof path required");
        std::fs::create_dir_all(&path).unwrap();
        Self {
            path,
            persistent: persistent.is_some(),
        }
    }
}

impl Drop for Root {
    fn drop(&mut self) {
        if !self.persistent {
            std::fs::remove_dir_all(&self.path).unwrap();
        }
    }
}

struct Source {
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl LiteratureSource for Source {
    fn name(&self) -> &'static str {
        "fixture"
    }

    async fn search(&self, _: &StructuredSearch, _: usize) -> bib_base::Result<SourceBatch> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        Ok(SourceBatch {
            source: "fixture".into(),
            total: 1,
            articles: vec![article()],
            error: None,
        })
    }

    async fn fetch(&self, _: &Identifier) -> bib_base::Result<Option<Article>> {
        Err(bib_base::Error::Unknown("fixture fetch forbidden".into()))
    }
}

fn article() -> Article {
    Article::new("fulltext-fixture", "Engineering fixture").with_doi("10.1000/fulltext-fixture")
}

fn add_source(dag: &mut DAG, path: String, calls: Arc<AtomicUsize>) {
    let mut gateway = LiteratureGateway::new();
    gateway.add_source(Arc::new(Source { calls }));
    let spec = LiteratureSearchSpec {
        query: StructuredSearch::default(),
        limit: Some(1),
        sources: None,
        path,
        note: None,
    };
    dag.add_node_with_spec(
        "source".into(),
        Box::new(LiteratureSearchNode::with_gateway(
            spec.clone(),
            Arc::new(gateway),
        )),
        "source_literature".into(),
        json!({"query":{},"limit":1,"path":spec.path}),
    )
    .unwrap();
}

struct FileSetReadback {
    ports: NodePorts,
}

impl FileSetReadback {
    fn new() -> Self {
        Self {
            ports: NodePorts::new()
                .add_input_port_of_type(None, PortType::FileSet)
                .add_output_port_of_type(None, PortType::FileSet),
        }
    }
}

#[async_trait]
impl DagNode for FileSetReadback {
    fn ports(&self) -> &NodePorts {
        &self.ports
    }
    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(Self::new())
    }
    fn kind(&self) -> &'static str {
        "fixture_fileset_readback"
    }
    fn as_any(&self) -> &dyn std::any::Any {
        self
    }

    async fn execute(
        &mut self,
        context: &NodeCtx,
        inputs: &[NodeInput],
        _: &NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        let files = inputs.first().unwrap().data.as_file_set()?.to_vec();
        for file in &files {
            let actual = dag_core::fingerprint::file_sha256(&file.path, context.opendal.as_deref())
                .await
                .ok_or_else(|| {
                    DagError::Schedule("fixture cannot read actual FileSet object".into())
                })?;
            let fingerprint = file.fingerprint.as_ref().unwrap();
            assert!(!fingerprint.immutable_remote);
            assert_eq!(fingerprint.size, actual.0);
            assert_eq!(
                fingerprint.content_hash.as_deref(),
                Some(format!("sha256:{}", actual.1).as_str())
            );
        }
        let mut outputs = PortOutputs::new();
        outputs.insert(0, files);
        Ok(outputs)
    }
}

async fn run(
    dag: &mut DAG,
    context: &NodeCtx,
    root: &Root,
    index: usize,
    expected_ok: bool,
) -> RunReport {
    let report = dag
        .run(
            &SchedulerConfig {
                max_concurrency: 1,
                incremental: true,
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
    let directory = root.path.join(format!("run-{index}"));
    std::fs::create_dir_all(&directory).unwrap();
    std::fs::write(
        directory.join("run-report.json"),
        serde_json::to_vec_pretty(&report).unwrap(),
    )
    .unwrap();
    std::fs::write(
        directory.join("dag.json"),
        serde_json::to_vec_pretty(&dag.tui_snapshot()).unwrap(),
    )
    .unwrap();
    let mut receipts = Vec::new();
    for node in &report.nodes {
        for (index, file) in node.output_files.iter().enumerate() {
            let bytes = if let Some(virtual_path) = file.path.strip_prefix("vfs://") {
                let storage = context.opendal.as_ref().unwrap();
                storage
                    .resolve(virtual_path)
                    .read(&storage.resolve_path(virtual_path))
                    .await
                    .unwrap()
                    .to_vec()
            } else {
                std::fs::read(&file.path).unwrap()
            };
            let digest = format!("{:x}", Sha256::digest(&bytes));
            let identity = file.fingerprint.as_ref().unwrap();
            assert_eq!(identity.size, bytes.len() as u64);
            assert_eq!(
                identity.content_hash.as_deref(),
                Some(format!("sha256:{digest}").as_str())
            );
            assert!(!identity.immutable_remote);
            let relative = format!("actual-output-readback/{}/{index}.bin", node.id);
            let snapshot = directory.join(&relative);
            std::fs::create_dir_all(snapshot.parent().unwrap()).unwrap();
            std::fs::write(snapshot, &bytes).unwrap();
            receipts.push(json!({"node":node.id,"output_index":index,"file_ref":file,
                "readback":relative,"sha256":digest,"bytes":bytes.len()}));
        }
    }
    std::fs::write(
        directory.join("actual-output-readbacks.json"),
        serde_json::to_vec_pretty(&receipts).unwrap(),
    )
    .unwrap();
    assert_eq!(report.ok, expected_ok);
    if !expected_ok {
        assert!(report.errors.contains_key("fulltext"));
        let sink = report.nodes.iter().find(|node| node.id == "sink").unwrap();
        assert_eq!(serde_json::to_value(sink).unwrap()["status"], "skipped");
        assert!(sink.output_files.is_empty());
    }
    report
}

struct FulltextHarness {
    root: Root,
    context: NodeCtx,
    storage: Arc<vfs::OpendalFileStorage>,
    shared: Arc<BibShared>,
    row: FullText,
    calls: Arc<AtomicUsize>,
    dag: DAG,
}

impl FulltextHarness {
    async fn new(tag: &str, mismatch: bool) -> Self {
        let root = Root::new(tag);
        let storage = Arc::new(vfs::OpendalFileStorage::new(root.path.join("vfs")));
        let shared = Arc::new(
            BibShared::open_in_memory()
                .await
                .unwrap()
                .with_file_storage(storage.clone()),
        );
        let stored = stored_fulltext(&article().id, "paper.txt", b"original");
        storage
            .write_bytes(
                &vfs_virtual_path(&stored.path).unwrap(),
                b"original".to_vec(),
            )
            .await
            .unwrap();
        shared.bib.upsert_article(&article()).await.unwrap();
        let row = FullText {
            attachment_key: None,
            article_id: article().id,
            file_path: stored.path,
            file_format: FileFormat::Txt,
            text_content: None,
            source: FullTextSource::UserUpload,
            file_hash: Some(stored.file_hash),
            file_size: Some(8),
            uploaded_at: None,
            extract_status: None,
            text_format: None,
            extracted_by: None,
            extract_error: None,
        };
        shared.bib.upsert_fulltext(&row).await.unwrap();
        let runtime = if mismatch {
            let runtime = Arc::new(vfs::OpendalFileStorage::new(root.path.join("runtime")));
            runtime
                .write_bytes(
                    &vfs_virtual_path(&row.file_path).unwrap(),
                    b"tampered".to_vec(),
                )
                .await
                .unwrap();
            runtime
        } else {
            storage.clone()
        };
        let context = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            Some(runtime),
        );
        let calls = Arc::new(AtomicUsize::new(0));
        let mut dag = DAG::default();
        add_source(&mut dag, "/evidence.json".into(), calls.clone());
        dag.add_node_with_spec(
            "fulltext".into(),
            Box::new(LiteratureFulltextNode::with_shared(
                LiteratureFulltextSpec {
                    fetch_missing: Some(false),
                },
                shared.clone(),
            )),
            "literature_fulltext".into(),
            json!({"fetch_missing":false}),
        )
        .unwrap();
        dag.add_node_with_spec(
            "sink".into(),
            Box::new(FileSetReadback::new()),
            "fixture_fileset_readback".into(),
            json!({}),
        )
        .unwrap();
        dag.add_edge("source", "fulltext", 0, 0).unwrap();
        dag.add_edge("fulltext", "sink", 0, 0).unwrap();
        Self {
            root,
            context,
            storage,
            shared,
            row,
            calls,
            dag,
        }
    }

    async fn run(&mut self, index: usize, expected_ok: bool) -> RunReport {
        std::fs::write(
            self.root
                .path
                .join(format!("database-row-before-{index}.json")),
            serde_json::to_vec_pretty(&self.shared.bib.get_fulltext(&article().id).await.unwrap())
                .unwrap(),
        )
        .unwrap();
        run(&mut self.dag, &self.context, &self.root, index, expected_ok).await
    }
}

#[tokio::test]
async fn valid_native_fulltext_fileset_reaches_actual_readback_sink() {
    let mut harness = FulltextHarness::new("valid", false).await;
    harness.run(0, true).await;
}

#[tokio::test]
async fn missing_native_backing_file_blocks_sink_and_records_failure() {
    let mut harness = FulltextHarness::new("missing", false).await;
    harness
        .storage
        .delete_object(&vfs_virtual_path(&harness.row.file_path).unwrap())
        .await
        .unwrap();
    harness.run(0, false).await;
}

#[tokio::test]
async fn tampered_native_backing_file_blocks_sink_and_records_failure() {
    let mut harness = FulltextHarness::new("tampered", false).await;
    harness
        .storage
        .write_bytes(
            &vfs_virtual_path(&harness.row.file_path).unwrap(),
            b"tampered".to_vec(),
        )
        .await
        .unwrap();
    harness.run(0, false).await;
}

#[tokio::test]
async fn two_present_but_different_storage_views_are_not_equivalent() {
    let mut harness = FulltextHarness::new("different-views", true).await;
    harness.run(0, false).await;
}

#[tokio::test]
async fn synthetic_europepmc_pointer_materializes_and_passes_verified_fileset() {
    let mut harness = FulltextHarness::new("synthetic", false).await;
    harness.row.file_path = "europepmc:PMC42".into();
    harness.row.file_hash = None;
    harness.row.file_size = None;
    harness.row.text_content = Some("synthetic inline fixture".into());
    harness
        .shared
        .bib
        .upsert_fulltext(&harness.row)
        .await
        .unwrap();
    harness.run(0, true).await;
    let row = harness
        .shared
        .bib
        .get_fulltext(&article().id)
        .await
        .unwrap()
        .unwrap();
    assert!(row.file_path.starts_with("vfs:///"));
    assert_eq!(row.file_size, Some(24));
}

#[tokio::test]
async fn unchanged_fulltext_reuses_but_tampering_invalidates_and_blocks_old_sink() {
    let mut harness = FulltextHarness::new("incremental", false).await;
    harness.run(0, true).await;
    harness.run(1, true).await;
    assert_eq!(harness.calls.load(Ordering::SeqCst), 1);
    harness
        .storage
        .write_bytes(
            &vfs_virtual_path(&harness.row.file_path).unwrap(),
            b"tampered".to_vec(),
        )
        .await
        .unwrap();
    harness.run(2, false).await;
    assert_eq!(harness.calls.load(Ordering::SeqCst), 1);
}

#[tokio::test]
async fn native_host_output_with_preserved_metadata_is_recomputed_in_actual_dag() {
    let root = Root::new("host-cache");
    let context = NodeCtx::new(
        datafusion::prelude::SessionContext::new().runtime_env(),
        None,
    );
    let source = root.path.join("evidence.json");
    let merged = root.path.join("merged.json");
    let calls = Arc::new(AtomicUsize::new(0));
    let mut dag = DAG::default();
    add_source(
        &mut dag,
        source.to_string_lossy().into_owned(),
        calls.clone(),
    );
    let spec = EvidenceMergeSpec {
        path: merged.to_string_lossy().into_owned(),
    };
    dag.add_node_with_spec(
        "merge".into(),
        Box::new(EvidenceMergeNode::new(spec.clone())),
        "evidence_merge".into(),
        json!({"path":spec.path}),
    )
    .unwrap();
    dag.add_edge("source", "merge", 0, 0).unwrap();
    run(&mut dag, &context, &root, 0, true).await;
    run(&mut dag, &context, &root, 1, true).await;
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    let original = std::fs::read(&source).unwrap();
    let metadata = std::fs::metadata(&source).unwrap();
    let mut tampered = original.clone();
    tampered[0] ^= 1;
    std::fs::write(&source, &tampered).unwrap();
    std::fs::File::open(&source)
        .unwrap()
        .set_times(std::fs::FileTimes::new().set_modified(metadata.modified().unwrap()))
        .unwrap();
    let modified = std::fs::metadata(&source).unwrap();
    assert_eq!(modified.len(), metadata.len());
    assert_eq!(modified.modified().unwrap(), metadata.modified().unwrap());
    std::fs::write(root.path.join("counterexample-bytes.bin"), tampered).unwrap();
    run(&mut dag, &context, &root, 2, true).await;
    assert_eq!(calls.load(Ordering::SeqCst), 2);
    assert_eq!(std::fs::read(&source).unwrap(), original);
    assert_eq!(
        std::fs::read(&source).unwrap(),
        std::fs::read(&merged).unwrap()
    );
}

#[tokio::test]
async fn database_pointer_change_selects_new_file_while_old_file_stays_valid() {
    let mut harness = FulltextHarness::new("database-pointer", false).await;
    harness.run(0, true).await;
    let old_path = harness.row.file_path.clone();
    let replacement = stored_fulltext(&article().id, "replacement.txt", b"replacement");
    harness
        .storage
        .write_bytes(
            &vfs_virtual_path(&replacement.path).unwrap(),
            b"replacement".to_vec(),
        )
        .await
        .unwrap();
    harness.row.file_path = replacement.path;
    harness.row.file_hash = Some(replacement.file_hash);
    harness.row.file_size = Some(11);
    harness
        .shared
        .bib
        .upsert_fulltext(&harness.row)
        .await
        .unwrap();
    let old_virtual_path = vfs_virtual_path(&old_path).unwrap();
    let old_size = harness
        .storage
        .content_length(&old_virtual_path)
        .await
        .unwrap();
    assert_eq!(
        harness
            .storage
            .read_range(&old_virtual_path, 0..old_size)
            .await
            .unwrap()
            .to_vec(),
        b"original"
    );
    println!("OLD_FILE_STILL_VALID_AFTER_DATABASE_POINTER_CHANGE");
    harness.run(1, true).await;
    let outputs = harness.dag.output("fulltext").unwrap();
    let files = outputs.get(&0).unwrap().as_file_set().unwrap();
    assert_eq!(files[0].path, harness.row.file_path);
}

#[tokio::test]
async fn database_hash_change_is_not_hidden_by_valid_cached_old_bytes() {
    let mut harness = FulltextHarness::new("database-hash", false).await;
    harness.run(0, true).await;
    harness.row.file_hash = Some("0".repeat(64));
    harness
        .shared
        .bib
        .upsert_fulltext(&harness.row)
        .await
        .unwrap();
    harness.run(1, false).await;
}

#[tokio::test]
async fn unrelated_library_changes_do_not_invalidate_relevant_fulltext_state() {
    let mut harness = FulltextHarness::new("database-unrelated", false).await;
    harness.run(0, true).await;
    harness
        .shared
        .bib
        .upsert_article(
            &Article::new("unrelated", "Unrelated fixture").with_doi("10.1000/unrelated"),
        )
        .await
        .unwrap();
    let report = harness.run(1, true).await;
    assert!(
        report
            .nodes
            .iter()
            .find(|node| node.id == "fulltext")
            .unwrap()
            .execution
            .is_none()
    );
}
