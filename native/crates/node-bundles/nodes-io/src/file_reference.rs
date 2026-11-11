//! Binds an existing file to a [`FileRef`] without parsing its payload.

use async_trait::async_trait;
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;

use opendal::ErrorKind;

use dag_core::dag::{DagError, graph::PortOutputs};
use dag_core::fingerprint::file_sha256;
use dag_core::node::{DagNode, NodeInput, NodePorts};
use dag_core::registry::{NodeCtx, NodeFactory};
use dag_core::value::{FileFingerprint, FileRef, PortType};

pub const FILE_REFERENCE_KIND: &str = "file_reference";

#[derive(Debug, Clone, JsonSchema, Deserialize)]
pub struct FileReferenceNodeSpec {
    /// Concrete file path. Use `vfs://...` for runtime-mounted object
    /// storage, or an absolute path for a local development input.
    pub path: String,
    /// Optional format label passed downstream, for example `sumstats_gz`.
    pub format: Option<String>,
    /// Read the referenced bytes once and attach a sha256 content hash to the
    /// emitted FileRef. This strengthens provenance and incremental identity,
    /// at the cost of one full read even when the payload is not parsed.
    #[serde(default = "default_hash_content")]
    pub hash_content: bool,
}

fn default_hash_content() -> bool {
    false
}

pub struct FileReferenceNode {
    ports: NodePorts,
    path: String,
    format: Option<String>,
    hash_content: bool,
}

impl FileReferenceNode {
    pub fn new(path: impl Into<String>, format: Option<String>) -> Self {
        Self::with_content_hashing(path, format, false)
    }

    pub fn with_content_hashing(
        path: impl Into<String>,
        format: Option<String>,
        hash_content: bool,
    ) -> Self {
        Self {
            ports: port_layout(format.as_deref()),
            path: path.into(),
            format,
            hash_content,
        }
    }

    pub fn path(&self) -> &str {
        &self.path
    }
}

fn port_layout(format: Option<&str>) -> NodePorts {
    match format {
        Some(format) => NodePorts::new().add_output_port_of_type_with_label_and_format(
            None,
            PortType::File,
            "file",
            format,
        ),
        None => NodePorts::new().add_output_port_of_type(None, PortType::File),
    }
}

#[async_trait]
impl DagNode for FileReferenceNode {
    fn ports(&self) -> &NodePorts {
        &self.ports
    }

    async fn execute(
        &mut self,
        ctx: &NodeCtx,
        _inputs: &[NodeInput],
        _reporter: &dag_core::dag::node_event::NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        let mut file = resolve_file(ctx, &self.path, self.format.clone()).await?;
        if self.hash_content {
            let (size, hash) = file_sha256(&file.path, ctx.opendal.as_deref())
                .await
                .ok_or_else(|| {
                    DagError::Schedule(format!(
                        "file_reference cannot hash `{}` through VFS or the local host",
                        self.path
                    ))
                })?;
            let fingerprint = file
                .fingerprint
                .get_or_insert_with(|| dag_core::FileFingerprint::remote(0, None));
            fingerprint.size = size;
            fingerprint.content_hash = Some(format!("sha256:{hash}"));
        }
        let mut outputs = PortOutputs::new();
        outputs.insert_file(0, file);
        Ok(outputs)
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(Self {
            ports: self.ports.clone(),
            path: self.path.clone(),
            format: self.format.clone(),
            hash_content: self.hash_content,
        })
    }

    fn kind(&self) -> &'static str {
        FILE_REFERENCE_KIND
    }

    fn referenced_file_paths(&self) -> Vec<String> {
        vec![self.path.clone()]
    }

    fn file_input_spec_pointers(&self, _: &[NodeInput]) -> Result<Vec<String>, DagError> {
        Ok(vec!["/path".into()])
    }

    fn as_any(&self) -> &dyn std::any::Any {
        self
    }
}

async fn resolve_file(
    ctx: &NodeCtx,
    path: &str,
    format: Option<String>,
) -> Result<FileRef, DagError> {
    if path.trim().is_empty() {
        return Err(DagError::Schedule("file path cannot be empty".into()));
    }

    // An explicit host URI must not be reinterpreted through a root VFS
    // mount. Remote typed inputs use this spelling for verified snapshots.
    if path.starts_with("file://") {
        return FileRef::local(local_path(path)?, format);
    }

    if path.starts_with("vfs://") {
        let storage = ctx.opendal.as_ref().ok_or_else(|| {
            DagError::Schedule(format!("file `{path}` requires a registered runtime VFS"))
        })?;
        let virtual_path = path
            .strip_prefix("vfs://")
            .expect("path starts with vfs://");
        return vfs_file(storage, path, virtual_path, format).await;
    }

    if let Some(storage) = ctx.opendal.as_ref()
        && let Some(file) = vfs_file(storage, path, path, format.clone()).await.ok()
    {
        return Ok(file);
    }

    let local_path = local_path(path)?;
    let file = FileRef::local(local_path, format).map_err(|error| {
        DagError::Schedule(format!(
            "file_reference cannot resolve `{path}` through VFS or the local host: {error}"
        ))
    })?;
    Ok(file)
}

async fn vfs_file(
    storage: &vfs::OpendalFileStorage,
    output_path: &str,
    virtual_path: &str,
    format: Option<String>,
) -> Result<FileRef, DagError> {
    let operator = storage.resolve(virtual_path).clone();
    let key = storage.resolve_path(virtual_path);
    let metadata = operator.stat(&key).await.map_err(|error| {
        if error.kind() == ErrorKind::NotFound {
            DagError::Schedule(format!(
                "file `{output_path}` does not exist. `file_reference` resolves its \
                 path at execution time and expects the file to exist already; if \
                 another node in this DAG writes the file, connect that node's \
                 output port directly instead of referencing the path \
                 (underlying error: {error})"
            ))
        } else {
            DagError::Schedule(format!("cannot stat file `{output_path}`: {error}"))
        }
    })?;
    if metadata.is_dir() {
        return Err(DagError::Schedule(format!(
            "file_reference path is a directory, not a file: `{output_path}`"
        )));
    }

    let mtime_ns = metadata
        .last_modified()
        .and_then(|timestamp| {
            std::time::SystemTime::from(timestamp)
                .duration_since(std::time::UNIX_EPOCH)
                .ok()
        })
        .map(|duration| duration.as_nanos() as i128)
        .unwrap_or_default();

    Ok(FileRef {
        // Resolution has established the VFS namespace; carry it explicitly
        // across file ports instead of leaving an ambiguous host-looking path.
        path: if output_path.starts_with("vfs://") {
            output_path.to_string()
        } else {
            format!("vfs:///{}", virtual_path.trim_start_matches('/'))
        },
        format,
        fingerprint: Some(FileFingerprint {
            size: metadata.content_length(),
            mtime_ns,
            content_hash: None,
            // A VFS view (including a read-only mount) does not make an
            // externally owned source immutable. Content must be rechecked.
            immutable_remote: false,
        }),
    })
}

fn local_path(path: &str) -> Result<&std::path::Path, DagError> {
    let local = path
        .strip_prefix("file://")
        .unwrap_or(path)
        .trim_start_matches("//");
    let path = std::path::Path::new(local);
    if !path.is_absolute() {
        return Err(DagError::Schedule(format!(
            "file_reference path must be a `vfs://` URI or absolute path, got `{}`",
            path.display()
        )));
    }
    Ok(path)
}

pub struct FileReferenceNodeFactory {}

impl NodeFactory for FileReferenceNodeFactory {
    fn kind(&self) -> &'static str {
        FILE_REFERENCE_KIND
    }

    fn desc(&self) -> &'static str {
        "Exposes an existing VFS or local file as a FileRef without parsing it."
    }

    fn doc(&self) -> &'static str {
        "A file reference for binary or already-normalized inputs. It validates \
        that the configured `vfs://` or absolute path names a concrete file, \
        attaches size/mtime metadata, and emits a FileRef. Set `hash_content` \
        to true to also read once and attach a sha256 content hash. Unlike \
        `file_to_dataframe`, it never reads the payload into a DataFrame. This is \
        the intended input node for file-backed dedicated container nodes such as \
        `ldsc_h2`. Set `format` whenever it is known; downstream ports \
        can reject mismatched files before execution. The path is resolved when \
        the node executes, so it must already exist: use this node for external \
        inputs, and wire files produced inside the DAG through output-port \
        edges instead."
    }

    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(FileReferenceNodeSpec)
    }

    fn ports(&self) -> NodePorts {
        port_layout(None)
    }

    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec: FileReferenceNodeSpec = serde_json::from_value(spec)?;
        Ok(Box::new(FileReferenceNode::with_content_hashing(
            spec.path,
            spec.format,
            spec.hash_content,
        )))
    }

    fn ports_for_spec(
        &self,
        spec: serde_json::Value,
    ) -> dag_core::registry::error::Result<NodePorts> {
        let spec: FileReferenceNodeSpec = serde_json::from_value(spec)?;
        Ok(port_layout(spec.format.as_deref()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use dag_core::dag::DAG;
    use dag_core::dag::runtime::SchedulerConfig;
    use datafusion::prelude::SessionContext;
    use sha2::{Digest, Sha256};
    use std::sync::Arc;
    use vfs::{
        BackendConfig, BackendDefinition, MountDefinition, MountedObjectStore, OpendalFileStorage,
        VfsManifest,
    };

    #[derive(Debug)]
    struct TaggedObject {
        tag: Option<String>,
        info: Arc<opendal::raw::AccessorInfo>,
    }

    impl opendal::raw::Access for TaggedObject {
        type Reader = opendal::Buffer;
        type Writer = ();
        type Lister = ();
        type Deleter = ();
        type Copier = ();

        fn info(&self) -> Arc<opendal::raw::AccessorInfo> {
            self.info.clone()
        }

        async fn stat(
            &self,
            _: &str,
            _: opendal::raw::OpStat,
        ) -> opendal::Result<opendal::raw::RpStat> {
            let mut metadata = opendal::Metadata::new(opendal::EntryMode::FILE)
                .with_content_length(b"reference-data".len() as u64);
            if let Some(tag) = &self.tag {
                metadata = metadata.with_etag(tag.clone());
            }
            Ok(opendal::raw::RpStat::new(metadata))
        }

        async fn read(
            &self,
            _: &str,
            _: opendal::raw::OpRead,
        ) -> opendal::Result<(opendal::raw::RpRead, Self::Reader)> {
            Ok((
                opendal::raw::RpRead::default(),
                b"reference-data".to_vec().into(),
            ))
        }
    }

    async fn check_tag_is_not_a_content_digest(tag: Option<&str>) {
        use dag_core::fingerprint::{IdentityValue, InputIdentity};

        let info = opendal::raw::AccessorInfo::default();
        info.set_scheme("file-reference-etag-fixture");
        info.set_root("/");
        info.set_native_capability(opendal::Capability {
            stat: true,
            read: true,
            ..Default::default()
        });
        let operator = opendal::OperatorBuilder::new(TaggedObject {
            tag: tag.map(str::to_string),
            info: Arc::new(info),
        })
        .finish();
        let storage = Arc::new(OpendalFileStorage::from_operator(operator));
        let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(storage));
        let mut node = FileReferenceNode::new("vfs:///input.txt", Some("txt".into()));
        let reporter = dag_core::dag::node_event::NodeReporter::noop();
        let outputs = node.execute(&context, &[], &reporter).await.unwrap();
        let file = outputs.get(&0).unwrap().as_file().unwrap();
        assert_eq!(file.path, "vfs:///input.txt");
        assert_eq!(file.format.as_deref(), Some("txt"));
        assert_eq!(file.fingerprint.as_ref().unwrap().content_hash, None);
        assert!(!file.fingerprint.as_ref().unwrap().immutable_remote);
        let mut identities = [InputIdentity {
            from: "source".into(),
            from_port: 0,
            to_port: 0,
            value: IdentityValue::File {
                path: file.path.clone(),
                fingerprint: file.fingerprint.clone(),
            },
        }];
        dag_core::fingerprint::upgrade_identities_with_content_hashes(
            &mut identities,
            context.opendal.as_deref(),
        )
        .await;
        let IdentityValue::File { fingerprint, .. } = &identities[0].value else {
            panic!("file identity expected");
        };
        let expected = Some(format!("sha256:{:x}", Sha256::digest(b"reference-data")));
        assert_eq!(fingerprint.as_ref().unwrap().content_hash, expected);
        let mut hashed_node =
            FileReferenceNode::with_content_hashing("vfs:///input.txt", Some("txt".into()), true);
        let hashed_outputs = hashed_node.execute(&context, &[], &reporter).await.unwrap();
        let hashed_file = hashed_outputs.get(&0).unwrap().as_file().unwrap();
        assert_eq!(
            hashed_file.fingerprint.as_ref().unwrap().content_hash,
            expected
        );
    }

    #[tokio::test]
    async fn opaque_etag_is_not_a_content_digest() {
        check_tag_is_not_a_content_digest(Some("object-version-7")).await;
    }

    #[tokio::test]
    async fn multipart_etag_is_not_a_content_digest() {
        check_tag_is_not_a_content_digest(Some("d41d8cd98f00b204e9800998ecf8427e-2")).await;
    }

    #[tokio::test]
    async fn sha256_shaped_etag_is_not_a_verified_digest() {
        check_tag_is_not_a_content_digest(Some(&format!("sha256:{}", "0".repeat(64)))).await;
    }

    #[tokio::test]
    async fn absent_etag_allows_actual_content_hashing() {
        check_tag_is_not_a_content_digest(None).await;
    }

    fn mounted_ctx(root: &std::path::Path) -> (Arc<OpendalFileStorage>, tempfile::TempDir) {
        let workspace = tempfile::tempdir().unwrap();
        let manifest = VfsManifest {
            backend: vec![BackendDefinition {
                id: "workspace".into(),
                config: BackendConfig::local("/"),
            }],
            mount: vec![MountDefinition {
                path: "/".into(),
                backend: "workspace".into(),
                source: root.to_string_lossy().into_owned(),
                read_only: true,
                permissions: Default::default(),
            }],
        };
        let mounted = Arc::new(MountedObjectStore::from_manifest(&manifest).unwrap());
        let storage = Arc::new(OpendalFileStorage::with_mounts(workspace.path(), mounted));
        (storage, workspace)
    }

    #[tokio::test]
    async fn emits_vfs_file_without_parsing_it() {
        let input = tempfile::tempdir().unwrap();
        std::fs::write(input.path().join("input.sumstats.gz"), b"binary-payload").unwrap();
        let (storage, _workspace) = mounted_ctx(input.path());
        let ctx = NodeCtx::new(SessionContext::new().runtime_env(), Some(storage));
        let mut node =
            FileReferenceNode::new("vfs:///input.sumstats.gz", Some("sumstats_gz".into()));

        let outputs = node
            .execute(&ctx, &[], &dag_core::dag::node_event::NodeReporter::noop())
            .await
            .unwrap();

        let file = outputs.get(&0).unwrap().as_file().unwrap();
        assert_eq!(file.path, "vfs:///input.sumstats.gz");
        assert_eq!(file.format.as_deref(), Some("sumstats_gz"));
        let fingerprint = file.fingerprint.as_ref().unwrap();
        assert_eq!(fingerprint.size, b"binary-payload".len() as u64);
    }

    #[tokio::test]
    async fn optional_content_hashing_reads_without_parsing() {
        let input = tempfile::tempdir().unwrap();
        std::fs::write(input.path().join("input.tsv"), b"input-provenance").unwrap();
        let (storage, _workspace) = mounted_ctx(input.path());
        let ctx = NodeCtx::new(SessionContext::new().runtime_env(), Some(storage));
        let mut node =
            FileReferenceNode::with_content_hashing("vfs:///input.tsv", Some("tsv".into()), true);

        let outputs = node
            .execute(&ctx, &[], &dag_core::dag::node_event::NodeReporter::noop())
            .await
            .unwrap();

        let file = outputs.get(&0).unwrap().as_file().unwrap();
        let fingerprint = file.fingerprint.as_ref().unwrap();
        let expected = format!("sha256:{:x}", Sha256::digest(b"input-provenance"));
        assert_eq!(fingerprint.content_hash.as_deref(), Some(expected.as_str()));
        assert_eq!(fingerprint.size, b"input-provenance".len() as u64);
    }

    #[test]
    fn resolves_spec_format_into_port_contract() {
        let ports = FileReferenceNodeFactory {}
            .ports_for_spec(serde_json::json!({
                "path": "/workspace/data/munged.sumstats.gz",
                "format": "sumstats_gz"
            }))
            .unwrap();
        let output = ports.output_port(0).unwrap();
        assert_eq!(output.label.as_deref(), Some("file"));
        assert_eq!(output.format.as_deref(), Some("sumstats_gz"));
    }

    #[tokio::test]
    async fn missing_vfs_file_fails() {
        let input = tempfile::tempdir().unwrap();
        let (storage, _workspace) = mounted_ctx(input.path());
        let ctx = NodeCtx::new(SessionContext::new().runtime_env(), Some(storage));
        let mut node = FileReferenceNode::new("vfs:///missing.gz", None);

        let error = node
            .execute(&ctx, &[], &dag_core::dag::node_event::NodeReporter::noop())
            .await
            .unwrap_err();
        let message = error.to_string();

        assert!(message.contains("does not exist"), "{message}");
        assert!(
            message.contains("output port"),
            "not-found error should point at port wiring: {message}"
        );
    }

    #[tokio::test]
    async fn local_file_flows_through_dag() {
        let input = tempfile::tempdir().unwrap();
        let path = input.path().join("input.txt");
        std::fs::write(&path, b"local-payload").unwrap();
        let ctx = NodeCtx::new(SessionContext::new().runtime_env(), None);
        let mut dag = DAG::default();
        dag.add_node(
            "source".into(),
            Box::new(FileReferenceNode::new(
                path.to_string_lossy().into_owned(),
                Some("txt".into()),
            )),
        )
        .unwrap();

        dag.run(&SchedulerConfig::default(), &ctx, None)
            .await
            .unwrap();

        let output = dag.output("source").unwrap().clone();
        let file = output.get(&0).unwrap().as_file().unwrap();
        assert_eq!(
            std::path::Path::new(&file.path),
            std::path::Path::new(&path)
        );
        assert_eq!(file.fingerprint.as_ref().unwrap().size, 13);
    }
}
