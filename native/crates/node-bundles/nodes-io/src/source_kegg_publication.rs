use dag_core::dag::DagError;
use dag_core::registry::NodeCtx;
use dag_core::value::{FileFingerprint, FileRef};
use sha2::{Digest, Sha256};

pub(crate) fn validate_output_path(path: &str) -> Result<(), DagError> {
    if path.starts_with("vfs://") || path.starts_with("file://") {
        let stripped = path.split_once("://").unwrap().1;
        if stripped.is_empty()
            || (path.starts_with("file://") && !std::path::Path::new(stripped).is_absolute())
            || stripped
                .split('/')
                .any(|component| component == ".." || component == ".")
        {
            return Err(DagError::Schedule("invalid evidence artifact URI".into()));
        }
        return Ok(());
    }
    if !std::path::Path::new(path).is_absolute() {
        return Err(DagError::Schedule(format!(
            "output path must be a `vfs://` URI or an absolute path (auto-routed \
             through the mounted runtime VFS so the agent and engine share one \
             object-store namespace); got `{path}`"
        )));
    }
    Ok(())
}

pub(crate) fn to_vfs_uri(path: &str) -> String {
    if let Some(stripped) = path.strip_prefix("vfs://") {
        format!("vfs://{stripped}")
    } else if let Some(stripped) = path.strip_prefix("file://") {
        format!("vfs://{stripped}")
    } else if std::path::Path::new(path).is_absolute() {
        format!("vfs://{path}")
    } else {
        path.to_string()
    }
}

pub(crate) async fn read_file_bytes(ctx: &NodeCtx, path: &str) -> Result<Vec<u8>, DagError> {
    validate_output_path(path)?;
    if !path.starts_with("vfs://") && ctx.opendal.is_none() {
        let local = path.strip_prefix("file://").unwrap_or(path);
        return tokio::fs::read(local)
            .await
            .map_err(|error| DagError::Schedule(format!("cannot read file `{path}`: {error}")));
    }
    let virtual_path = to_vfs_uri(path).strip_prefix("vfs://").unwrap().to_string();
    let storage = ctx.opendal.as_ref().ok_or_else(|| {
        DagError::Schedule(format!("VFS input `{path}` requires a mounted runtime VFS"))
    })?;
    let operator = storage.resolve(&virtual_path);
    operator
        .read(&storage.resolve_path(&virtual_path))
        .await
        .map(|buffer| buffer.to_vec())
        .map_err(|error| DagError::Schedule(format!("cannot read VFS file `{path}`: {error}")))
}

pub(crate) async fn write_artifact(
    ctx: &NodeCtx,
    path: &str,
    bytes: Vec<u8>,
    format: &str,
) -> Result<FileRef, DagError> {
    validate_output_path(path)?;
    let size = bytes.len() as u64;
    let content_hash = format!("sha256:{:x}", Sha256::digest(&bytes));

    if !path.starts_with("vfs://") && ctx.opendal.is_none() {
        let local = path.strip_prefix("file://").unwrap_or(path);
        publish_local(std::path::Path::new(local), &bytes)?;
        let mtime_ns = tokio::fs::metadata(local)
            .await
            .ok()
            .and_then(|meta| meta.modified().ok())
            .and_then(|mtime| mtime.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|duration| duration.as_nanos() as i128)
            .unwrap_or_default();
        return Ok(FileRef {
            path: path.to_string(),
            format: Some(format.to_string()),
            fingerprint: Some(FileFingerprint {
                size,
                mtime_ns,
                content_hash: Some(content_hash),
                immutable_remote: false,
            }),
        });
    }

    let vfs_uri = to_vfs_uri(path);
    let virtual_path = vfs_uri.strip_prefix("vfs://").unwrap().to_string();
    let storage = ctx.opendal.as_ref().ok_or_else(|| {
        DagError::Schedule(format!(
            "VFS output `{path}` requires a mounted runtime VFS"
        ))
    })?;
    storage.write_new_filesystem_bytes(&virtual_path, bytes).await
        .map_err(|error| DagError::Schedule(error.to_string()))?;

    Ok(FileRef {
        path: vfs_uri,
        format: Some(format.to_string()),
        fingerprint: Some(FileFingerprint {
            size,
            mtime_ns: 0,
            content_hash: Some(content_hash),
            immutable_remote: false,
        }),
    })
}

fn publish_local(path: &std::path::Path, bytes: &[u8]) -> Result<(), DagError> {
    use std::io::Write;
    for ancestor in path.ancestors() {
        match std::fs::symlink_metadata(ancestor) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(DagError::Schedule(
                    "symlink destination component rejected".into(),
                ));
            }
            Ok(_) if ancestor == path => {
                return Err(DagError::Schedule("existing output not overwritten".into()));
            }
            Ok(metadata) if !metadata.is_dir() => {
                return Err(DagError::Schedule(
                    "destination ancestor is not a directory".into(),
                ));
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => {
                return Err(DagError::Schedule(format!(
                    "cannot establish output freshness: {error}"
                )));
            }
        }
    }
    let parent = path
        .parent()
        .ok_or_else(|| DagError::Schedule("output parent required".into()))?;
    std::fs::create_dir_all(parent).map_err(|error| DagError::Schedule(error.to_string()))?;
    let mut pending = tempfile::Builder::new()
        .prefix(".pending-evidence-")
        .tempfile_in(parent)
        .map_err(|error| DagError::Schedule(error.to_string()))?;
    pending
        .write_all(bytes)
        .map_err(|error| DagError::Schedule(error.to_string()))?;
    pending
        .as_file()
        .sync_all()
        .map_err(|error| DagError::Schedule(error.to_string()))?;
    pending.persist_noclobber(path).map_err(|error| {
        DagError::Schedule(format!(
            "cannot publish fresh evidence output: {}",
            error.error
        ))
    })?;
    Ok(())
}
