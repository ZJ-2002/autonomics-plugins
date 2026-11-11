use std::sync::Arc;

use dag_core::fingerprint::cached_file_changed;
use dag_core::registry::NodeCtx;
use datafusion::prelude::SessionContext;
use futures::FutureExt;
use vfs::{
    BackendConfig, BackendDefinition, MountDefinition, MountedObjectStore, OpendalFileStorage,
    VfsManifest,
};

use super::{read_file_bytes, validate_output_path, write_artifact};

struct ReadonlyFixture {
    root: std::path::PathBuf,
    context: NodeCtx,
}

impl ReadonlyFixture {
    fn new() -> Self {
        let root =
            std::env::temp_dir().join(format!("bibliography-readonly-{}", uuid::Uuid::new_v4()));
        std::fs::create_dir_all(root.join("locked")).unwrap();
        std::fs::write(root.join("locked/current.json"), b"original").unwrap();
        let mounts = Arc::new(
            MountedObjectStore::from_manifest(&VfsManifest {
                backend: vec![BackendDefinition {
                    id: "host".into(),
                    config: BackendConfig::local(root.to_string_lossy()),
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
                        source: root.join("locked").to_string_lossy().into_owned(),
                        read_only: true,
                        permissions: Default::default(),
                    },
                ],
            })
            .unwrap(),
        );
        let storage = Arc::new(OpendalFileStorage::with_mounts(&root, mounts));
        let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(storage));
        Self { root, context }
    }
}

impl Drop for ReadonlyFixture {
    fn drop(&mut self) {
        std::fs::remove_dir_all(&self.root).unwrap();
    }
}

fn context(storage: Arc<OpendalFileStorage>) -> NodeCtx {
    NodeCtx::new(SessionContext::new().runtime_env(), Some(storage))
}

#[tokio::test]
async fn mutable_overwrite_invalidates_native_cache() {
    let storage = Arc::new(OpendalFileStorage::new_temp());
    let context = context(storage.clone());
    let first = write_artifact(&context, "/result.json", b"first".to_vec(), "evidence")
        .await
        .unwrap();
    assert!(!cached_file_changed(&first, Some(&storage)).await);
    write_artifact(&context, "/result.json", b"other".to_vec(), "evidence")
        .await
        .unwrap();
    assert!(cached_file_changed(&first, Some(&storage)).await);
    assert!(!first.fingerprint.unwrap().immutable_remote);
}

#[tokio::test]
async fn deleted_output_invalidates_native_cache() {
    let storage = Arc::new(OpendalFileStorage::new_temp());
    let context = context(storage.clone());
    let file = write_artifact(&context, "/result.json", b"value".to_vec(), "evidence")
        .await
        .unwrap();
    storage.delete_object("/result.json").await.unwrap();
    assert!(cached_file_changed(&file, Some(&storage)).await);
}

#[tokio::test]
async fn readonly_aliases_never_mutate_existing_data() {
    let fixture = ReadonlyFixture::new();
    assert_eq!(
        read_file_bytes(&fixture.context, "/locked/current.json")
            .await
            .unwrap(),
        b"original"
    );
    assert!(
        fixture
            .context
            .opendal
            .as_ref()
            .unwrap()
            .check_writable("/locked/current.json")
            .is_err()
    );
    println!("READONLY_FIXTURE_READY");
    let mut outcomes = Vec::new();
    for path in [
        "/locked/current.json",
        "file:///locked/current.json",
        "vfs:///locked/current.json",
        "vfs://locked/current.json",
    ] {
        std::fs::write(fixture.root.join("locked/current.json"), b"original").unwrap();
        let result = write_artifact(&fixture.context, path, b"changed".to_vec(), "evidence").await;
        outcomes.push((
            result.is_err(),
            std::fs::read(fixture.root.join("locked/current.json")).unwrap() == b"original",
        ));
    }
    assert_eq!(outcomes, vec![(true, true); 4]);
}

#[tokio::test]
async fn normalized_path_cannot_bypass_readonly() {
    let fixture = ReadonlyFixture::new();
    assert_eq!(
        read_file_bytes(&fixture.context, "/locked/current.json")
            .await
            .unwrap(),
        b"original"
    );
    assert!(
        fixture
            .context
            .opendal
            .as_ref()
            .unwrap()
            .check_writable("/locked/current.json")
            .is_err()
    );
    println!("READONLY_FIXTURE_READY");
    let result = write_artifact(
        &fixture.context,
        "vfs:///writable/../locked/current.json",
        b"changed".to_vec(),
        "evidence",
    )
    .await;
    assert!(result.is_err());
    assert_eq!(
        std::fs::read(fixture.root.join("locked/current.json")).unwrap(),
        b"original"
    );
}

#[test]
fn rejects_empty_roots_relative_file_alias_and_controls() {
    let paths = [
        "file://relative/out.json",
        "file://",
        "vfs://",
        "vfs:///",
        "vfs://.",
        "/",
        "/bad\0name",
        "/bad\nname",
    ];
    let outcomes: Vec<bool> = paths
        .iter()
        .map(|path| validate_output_path(path).is_err())
        .collect();
    assert_eq!(outcomes, vec![true; paths.len()]);
}

#[tokio::test]
async fn unsupported_input_scheme_returns_error_not_panic() {
    let storage = Arc::new(OpendalFileStorage::new_temp());
    let context = context(storage);
    let outcome = std::panic::AssertUnwindSafe(read_file_bytes(
        &context,
        "https://example.invalid/evidence.json",
    ))
    .catch_unwind()
    .await;
    assert!(outcome.is_ok(), "unsupported input must not panic the node");
    assert!(outcome.unwrap().is_err());
}

#[tokio::test]
async fn vfs_aliases_have_one_canonical_output_identity() {
    let storage = Arc::new(OpendalFileStorage::new_temp());
    let context = context(storage);
    let mut paths = Vec::new();
    for path in [
        "vfs://artifacts/result.json",
        "vfs:///artifacts/result.json",
        "file:///artifacts/result.json",
        "/scratch/../artifacts/result.json",
    ] {
        paths.push(
            write_artifact(&context, path, b"same".to_vec(), "evidence")
                .await
                .unwrap()
                .path,
        );
    }
    assert_eq!(paths, vec!["vfs:///artifacts/result.json"; 4]);
}

#[tokio::test]
async fn memory_object_backend_preserves_roundtrip_and_mutable_identity() {
    let operator = opendal::Operator::new(opendal::services::Memory::default())
        .unwrap()
        .finish();
    let storage = Arc::new(OpendalFileStorage::from_operator(operator));
    let context = context(storage.clone());
    let first = write_artifact(
        &context,
        "vfs:///result.json",
        b"first".to_vec(),
        "evidence",
    )
    .await
    .unwrap();
    assert_eq!(
        read_file_bytes(&context, &first.path).await.unwrap(),
        b"first"
    );
    assert!(!cached_file_changed(&first, Some(&storage)).await);
    write_artifact(
        &context,
        "vfs:///result.json",
        b"first".to_vec(),
        "evidence",
    )
    .await
    .unwrap();
    assert!(!cached_file_changed(&first, Some(&storage)).await);
    write_artifact(
        &context,
        "vfs:///result.json",
        b"other".to_vec(),
        "evidence",
    )
    .await
    .unwrap();
    assert!(cached_file_changed(&first, Some(&storage)).await);
    assert!(!first.fingerprint.unwrap().immutable_remote);
}

#[tokio::test]
async fn legacy_host_overwrite_remains_supported_and_mutable() {
    let root = std::env::temp_dir().join(format!(
        "bibliography-host-control-{}",
        uuid::Uuid::new_v4()
    ));
    let path = root.join("result.json");
    let context = NodeCtx::new(SessionContext::new().runtime_env(), None);
    let first = write_artifact(
        &context,
        path.to_str().unwrap(),
        b"first".to_vec(),
        "evidence",
    )
    .await
    .unwrap();
    assert!(!first.fingerprint.as_ref().unwrap().immutable_remote);
    assert!(!cached_file_changed(&first, None).await);
    write_artifact(
        &context,
        path.to_str().unwrap(),
        b"changed".to_vec(),
        "evidence",
    )
    .await
    .unwrap();
    assert!(cached_file_changed(&first, None).await);
    assert_eq!(
        read_file_bytes(&context, &first.path).await.unwrap(),
        b"changed"
    );
    std::fs::remove_dir_all(root).unwrap();
}
