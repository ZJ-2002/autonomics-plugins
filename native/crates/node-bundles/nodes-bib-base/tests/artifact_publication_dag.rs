use std::sync::{
    Arc,
    atomic::{AtomicUsize, Ordering},
};

use async_trait::async_trait;
use nodes_bib_base::nodes::evidence_export::{
    EvidenceExportFormat, EvidenceExportNode, EvidenceExportSpec,
};
use nodes_bib_base::nodes::evidence_merge::{EvidenceMergeNode, EvidenceMergeSpec};
use nodes_bib_base::nodes::literature_search::{LiteratureSearchNode, LiteratureSearchSpec};
use bib_base::{LiteratureGateway, LiteratureSource, SourceBatch};
use bib_types::{Article, EvidenceSet, Identifier, StructuredSearch};
use dag_core::dag::DAG;
use dag_core::dag::runtime::{InputHashing, RunReport, SchedulerConfig};
use dag_core::registry::NodeCtx;
use datafusion::prelude::SessionContext;
use serde_json::json;
use vfs::{
    BackendConfig, BackendDefinition, MountDefinition, MountedObjectStore, OpendalFileStorage,
    VfsManifest,
};

struct FixtureSource {
    calls: Arc<AtomicUsize>,
}

#[async_trait]
impl LiteratureSource for FixtureSource {
    fn name(&self) -> &'static str {
        "fixture"
    }

    async fn search(&self, _: &StructuredSearch, _: usize) -> bib_base::Result<SourceBatch> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        Ok(SourceBatch {
            source: "fixture".into(),
            total: 1,
            articles: vec![Article::new("fixture", "Fixture paper").with_doi("10.1000/fixture")],
            error: None,
        })
    }

    async fn fetch(&self, _: &Identifier) -> bib_base::Result<Option<Article>> {
        Err(bib_base::Error::Unknown("fixture fetch forbidden".into()))
    }
}

struct Harness {
    root: std::path::PathBuf,
    persistent: bool,
    memory: bool,
    storage: Arc<OpendalFileStorage>,
    context: NodeCtx,
    calls: Arc<AtomicUsize>,
    dag: DAG,
    reports: usize,
}

impl Harness {
    fn new(tag: &str, locked_node: Option<&str>, memory: bool) -> Self {
        let persistent = std::env::var_os("ARTIFACT_PUBLICATION_EVIDENCE_ROOT");
        let root = persistent
            .as_ref()
            .map(std::path::PathBuf::from)
            .map(|root| root.join(tag))
            .unwrap_or_else(|| {
                std::env::temp_dir().join(format!("artifact-dag-{}", uuid::Uuid::new_v4()))
            });
        assert!(!root.exists(), "fresh evidence directory required");
        std::fs::create_dir_all(root.join("vfs/locked")).unwrap();
        std::fs::write(root.join("vfs/locked/current.json"), b"original").unwrap();
        let storage = if memory {
            Arc::new(OpendalFileStorage::from_operator(
                opendal::Operator::new(opendal::services::Memory::default())
                    .unwrap()
                    .finish(),
            ))
        } else {
            let mounts = Arc::new(
                MountedObjectStore::from_manifest(&VfsManifest {
                    backend: vec![BackendDefinition {
                        id: "host".into(),
                        config: BackendConfig::local(root.join("vfs").to_string_lossy()),
                    }],
                    mount: vec![
                        MountDefinition {
                            path: "/".into(),
                            backend: "host".into(),
                            source: "/".into(),
                            read_only: false,
                            permissions: Default::default(),
                        },
                        MountDefinition {
                            path: "/locked".into(),
                            backend: "host".into(),
                            source: root.join("vfs/locked").to_string_lossy().into_owned(),
                            read_only: true,
                            permissions: Default::default(),
                        },
                    ],
                })
                .unwrap(),
            );
            Arc::new(OpendalFileStorage::with_mounts(&root.join("vfs"), mounts))
        };
        let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(storage.clone()));
        let calls = Arc::new(AtomicUsize::new(0));
        let mut gateway = LiteratureGateway::new();
        gateway.add_source(Arc::new(FixtureSource {
            calls: calls.clone(),
        }));
        let path = |name: &str, filename: &str| {
            if locked_node == Some(name) {
                "/open/../locked/current.json".to_owned()
            } else {
                format!("/{filename}")
            }
        };
        let mut dag = DAG::default();
        let source_spec = LiteratureSearchSpec {
            query: StructuredSearch::default(),
            limit: Some(5),
            sources: None,
            path: path("source", "source.json"),
            note: Some("Engineering fixture, no G0".into()),
        };
        dag.add_node_with_spec(
            "source".into(),
            Box::new(LiteratureSearchNode::with_gateway(
                source_spec.clone(),
                Arc::new(gateway),
            )),
            "source_literature".into(),
            json!({"query":{},"path":source_spec.path}),
        )
        .unwrap();
        let merge_spec = EvidenceMergeSpec {
            path: path("merge", "merged.json"),
        };
        dag.add_node_with_spec(
            "merge".into(),
            Box::new(EvidenceMergeNode::new(merge_spec.clone())),
            "evidence_merge".into(),
            json!({"path":merge_spec.path}),
        )
        .unwrap();
        let export_spec = EvidenceExportSpec {
            format: EvidenceExportFormat::Ris,
            path: path("export", "export.ris"),
        };
        dag.add_node_with_spec(
            "export".into(),
            Box::new(EvidenceExportNode::new(export_spec.clone())),
            "evidence_export".into(),
            json!({"format":"ris","path":export_spec.path}),
        )
        .unwrap();
        dag.add_edge("source", "merge", 0, 0).unwrap();
        dag.add_edge("merge", "export", 0, 0).unwrap();
        Self {
            root,
            persistent: persistent.is_some(),
            memory,
            storage,
            context,
            calls,
            dag,
            reports: 0,
        }
    }

    async fn run(&mut self, expected_ok: bool) -> RunReport {
        let report = self
            .dag
            .run(
                &SchedulerConfig {
                    max_concurrency: 1,
                    incremental: true,
                    input_hashing: InputHashing::Content,
                    compute_row_counts: false,
                    memory_guard: None,
                    ..SchedulerConfig::default()
                },
                &self.context,
                None,
            )
            .await
            .unwrap();
        let directory = self.root.join(format!("run-{}", self.reports));
        std::fs::create_dir_all(&directory).unwrap();
        std::fs::write(
            directory.join("run-report.json"),
            serde_json::to_vec_pretty(&report).unwrap(),
        )
        .unwrap();
        std::fs::write(
            directory.join("dag.json"),
            serde_json::to_vec_pretty(&self.dag.tui_snapshot()).unwrap(),
        )
        .unwrap();
        for node in &report.nodes {
            for file in &node.output_files {
                assert!(!file.fingerprint.as_ref().unwrap().immutable_remote);
                let virtual_path = file.path.strip_prefix("vfs://").unwrap();
                let bytes = self
                    .storage
                    .resolve(virtual_path)
                    .read(&self.storage.resolve_path(virtual_path))
                    .await
                    .unwrap()
                    .to_vec();
                if self.memory {
                    let relative = virtual_path.trim_start_matches('/');
                    let destination = directory.join("memory-output-readback").join(relative);
                    std::fs::create_dir_all(destination.parent().unwrap()).unwrap();
                    std::fs::write(destination, bytes).unwrap();
                }
            }
        }
        self.reports += 1;
        assert_eq!(report.ok, expected_ok);
        report
    }

    async fn read(&self, path: &str) -> Vec<u8> {
        self.storage
            .resolve(path)
            .read(&self.storage.resolve_path(path))
            .await
            .unwrap()
            .to_vec()
    }

    async fn assert_complete(&self) {
        let source = EvidenceSet::parse(&self.read("/source.json").await).unwrap();
        let merged = EvidenceSet::parse(&self.read("/merged.json").await).unwrap();
        assert_eq!(source, merged);
        assert_eq!(merged.records.len(), 1);
        assert_eq!(merged.records[0].citation.title, "Fixture paper");
        let export = String::from_utf8(self.read("/export.ris").await).unwrap();
        assert!(export.contains("TI  - Fixture paper"));
        assert!(export.contains("DO  - 10.1000/fixture"));
    }
}

impl Drop for Harness {
    fn drop(&mut self) {
        if !self.persistent {
            std::fs::remove_dir_all(&self.root).unwrap();
        }
    }
}

#[tokio::test]
async fn writable_filesystem_pipeline_publishes_readable_mutable_outputs() {
    let mut harness = Harness::new("writable", None, false);
    harness.run(true).await;
    harness.assert_complete().await;
}

#[tokio::test]
async fn readonly_source_blocks_all_downstream_outputs() {
    let mut harness = Harness::new("readonly-source", Some("source"), false);
    harness.run(false).await;
    assert_eq!(harness.read("/locked/current.json").await, b"original");
    assert!(!harness.root.join("vfs/merged.json").exists());
    assert!(!harness.root.join("vfs/export.ris").exists());
}

#[tokio::test]
async fn readonly_merge_preserves_old_file_and_blocks_export() {
    let mut harness = Harness::new("readonly-merge", Some("merge"), false);
    harness.run(false).await;
    assert_eq!(harness.read("/locked/current.json").await, b"original");
    assert!(!harness.root.join("vfs/export.ris").exists());
}

#[tokio::test]
async fn readonly_export_preserves_old_file_and_reports_failure() {
    let mut harness = Harness::new("readonly-export", Some("export"), false);
    harness.run(false).await;
    assert_eq!(harness.read("/locked/current.json").await, b"original");
    assert!(harness.root.join("vfs/merged.json").exists());
}

#[tokio::test]
async fn incremental_run_repairs_changed_deleted_outputs_without_false_immutability() {
    let mut harness = Harness::new("incremental", None, false);
    harness.run(true).await;
    assert_eq!(harness.calls.load(Ordering::SeqCst), 1);
    harness.run(true).await;
    assert_eq!(harness.calls.load(Ordering::SeqCst), 1);
    harness
        .storage
        .write_bytes("/source.json", b"corrupted".to_vec())
        .await
        .unwrap();
    harness.run(true).await;
    assert_eq!(harness.calls.load(Ordering::SeqCst), 2);
    harness.assert_complete().await;
    harness
        .storage
        .write_bytes("/merged.json", b"corrupted".to_vec())
        .await
        .unwrap();
    harness.run(true).await;
    assert_eq!(harness.calls.load(Ordering::SeqCst), 2);
    harness.assert_complete().await;
    harness.storage.delete_object("/export.ris").await.unwrap();
    harness.run(true).await;
    assert_eq!(harness.calls.load(Ordering::SeqCst), 2);
    harness.assert_complete().await;
    let unchanged = harness.read("/source.json").await;
    harness
        .storage
        .write_bytes("/source.json", unchanged)
        .await
        .unwrap();
    harness.run(true).await;
    assert_eq!(harness.calls.load(Ordering::SeqCst), 2);
    harness.assert_complete().await;
}

#[tokio::test]
async fn memory_object_backend_runs_same_native_pipeline() {
    let mut harness = Harness::new("memory", None, true);
    harness.run(true).await;
    harness.assert_complete().await;
}
