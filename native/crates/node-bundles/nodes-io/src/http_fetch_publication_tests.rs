use super::*;
use dag_core::dag::node_event::NodeReporter;
use sha2::{Digest, Sha256};
use std::path::Path;
use std::sync::Arc;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use vfs::{
    BackendConfig, BackendDefinition, MountDefinition, MountedObjectStore, OpendalFileStorage,
    VfsManifest,
};

fn specification(url: &str, path: &str) -> HttpFetchSpec {
    HttpFetchSpec {
        url: url.into(),
        path: path.into(),
        timeout_secs: 5,
        max_bytes: 1024,
    }
}

fn context(root: Option<&Path>, read_only: bool) -> NodeCtx {
    let session = datafusion::prelude::SessionContext::new();
    let storage = root.map(|root| {
        let mounted = Arc::new(
            MountedObjectStore::from_manifest(&VfsManifest {
                backend: vec![BackendDefinition {
                    id: "fixture".into(),
                    config: BackendConfig::local(root.to_string_lossy().into_owned()),
                }],
                mount: vec![MountDefinition {
                    path: "/".into(),
                    backend: "fixture".into(),
                    source: "/".into(),
                    read_only,
                    permissions: Default::default(),
                }],
            })
            .unwrap(),
        );
        Arc::new(OpendalFileStorage::with_mounts(root, mounted))
    });
    NodeCtx::new(session.runtime_env(), storage)
}

async fn response_server() -> (String, tokio::task::JoinHandle<()>) {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let worker = tokio::spawn(async move {
        let (mut socket, _) = listener.accept().await.unwrap();
        let mut request = [0u8; 4096];
        socket.read(&mut request).await.unwrap();
        socket
            .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\nConnection: close\r\n\r\nhello")
            .await
            .unwrap();
    });
    (format!("http://{address}/body.tsv"), worker)
}

async fn fetch(node: &mut HttpFetchNode, context: &NodeCtx) -> Result<PortOutputs, HttpFetchError> {
    node.execute_with_allowlist(context, Some(vec!["127.0.0.1".into()]))
        .await
}

#[test]
fn output_paths_require_absolute_nontraversing_namespace() {
    for path in [
        "relative.tsv",
        "../body.tsv",
        "/tmp/../body.tsv",
        "vfs:///a/../body.tsv",
    ] {
        assert!(
            validate_spec(&specification("https://example.invalid/body.tsv", path)).is_err(),
            "accepted invalid output path {path}"
        );
    }
    for path in ["/tmp/body.tsv", "file:///tmp/body.tsv", "vfs:///body.tsv"] {
        assert!(validate_spec(&specification("https://example.invalid/body.tsv", path)).is_ok());
    }
}

#[tokio::test]
async fn injected_file_is_rejected_before_network_admission() {
    let mut node = HttpFetchNode::new(specification(
        "https://example.invalid/no-request",
        "/tmp/unused-http-publication.tsv",
    ));
    let error = node
        .execute(
            &context(None, false),
            &[NodeInput::file(
                0,
                FileRef::new("vfs:///not-read.tsv", Some("tsv".into())),
            )],
            &NodeReporter::noop(),
        )
        .await
        .unwrap_err();
    assert!(error.to_string().contains("no input ports"), "{error}");
}

#[tokio::test]
async fn existing_local_output_is_preserved() {
    let root = tempfile::tempdir().unwrap();
    let path = root.path().join("body.tsv");
    std::fs::write(&path, b"historical evidence\n").unwrap();
    let (url, worker) = response_server().await;
    let mut node = HttpFetchNode::new(specification(&url, path.to_str().unwrap()));
    let result = fetch(&mut node, &context(None, false)).await;
    worker.await.unwrap();
    assert!(result.is_err(), "existing output was silently overwritten");
    assert_eq!(std::fs::read(path).unwrap(), b"historical evidence\n");
}

#[cfg(unix)]
#[tokio::test]
async fn symlink_destination_ancestor_is_rejected() {
    let root = tempfile::tempdir().unwrap();
    let actual = root.path().join("actual");
    std::fs::create_dir(&actual).unwrap();
    let alias = root.path().join("alias");
    std::os::unix::fs::symlink(&actual, &alias).unwrap();
    let path = alias.join("body.tsv");
    let (url, worker) = response_server().await;
    let mut node = HttpFetchNode::new(specification(&url, path.to_str().unwrap()));
    let result = fetch(&mut node, &context(None, false)).await;
    worker.await.unwrap();
    assert!(result.is_err(), "symlink destination was followed");
    assert!(!actual.join("body.tsv").exists());
}

#[tokio::test]
async fn mounted_output_has_complete_content_identity() {
    let root = tempfile::tempdir().unwrap();
    let (url, worker) = response_server().await;
    let mut node = HttpFetchNode::new(specification(&url, "vfs:///body.tsv"));
    let outputs = fetch(&mut node, &context(Some(root.path()), false))
        .await
        .unwrap();
    worker.await.unwrap();
    let file = outputs.get(&0).unwrap().as_file().unwrap();
    assert_eq!(file.path, "vfs:///body.tsv");
    assert_eq!(file.format.as_deref(), Some("tsv"));
    assert_eq!(
        std::fs::read(root.path().join("body.tsv")).unwrap(),
        b"hello"
    );
    let fingerprint = file
        .fingerprint
        .as_ref()
        .expect("missing received-body identity");
    assert_eq!(fingerprint.size, 5);
    assert_eq!(
        fingerprint.content_hash,
        Some(format!("sha256:{:x}", Sha256::digest(b"hello")))
    );
    assert!(!fingerprint.immutable_remote);
}

#[tokio::test]
async fn readonly_mount_cannot_publish_received_body() {
    let root = tempfile::tempdir().unwrap();
    let (url, worker) = response_server().await;
    let mut node = HttpFetchNode::new(specification(&url, "vfs:///body.tsv"));
    let result = fetch(&mut node, &context(Some(root.path()), true)).await;
    worker.await.unwrap();
    assert!(result.is_err(), "read-only VFS mount accepted a write");
    assert!(!root.path().join("body.tsv").exists());
}
