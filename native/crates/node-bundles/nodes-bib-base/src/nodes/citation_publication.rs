use dag_core::dag::DagError;
use dag_core::registry::NodeCtx;
use dag_core::value::{FileFingerprint, FileRef};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

pub(crate) async fn ensure_fresh(ctx: &NodeCtx, path: &str) -> Result<(), DagError> {
    super::validate_output_path(path)?;
    if path.starts_with("vfs://") || ctx.opendal.is_some() {
        let uri = super::to_vfs_uri(path);
        let storage = ctx.opendal.as_ref()
            .ok_or_else(|| DagError::Schedule("citation output requires the runtime VFS".into()))?;
        return storage.require_fresh_filesystem_path(uri.strip_prefix("vfs://").unwrap()).await
            .map_err(|error| DagError::Schedule(error.to_string()));
    }
    let local = PathBuf::from(path.strip_prefix("file://").unwrap_or(path));
    for ancestor in local.ancestors() {
        match std::fs::symlink_metadata(ancestor) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(DagError::Schedule(
                    "symlink destination component rejected".into(),
                ));
            }
            Ok(_) if ancestor == local => {
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
    Ok(())
}

pub(crate) async fn write_artifact(
    ctx: &NodeCtx,
    path: &str,
    bytes: Vec<u8>,
    format: &str,
) -> Result<FileRef, DagError> {
    super::validate_output_path(path)?;
    let size = bytes.len() as u64;
    let content_hash = format!("sha256:{:x}", Sha256::digest(&bytes));
    let uri = if path.starts_with("vfs://") || ctx.opendal.is_some() {
        let uri = super::to_vfs_uri(path);
        let storage = ctx.opendal.as_ref()
            .ok_or_else(|| DagError::Schedule("citation output requires the runtime VFS".into()))?;
        storage.write_new_filesystem_bytes(uri.strip_prefix("vfs://").unwrap(), bytes).await
            .map_err(|error| DagError::Schedule(error.to_string()))?;
        uri
    } else {
        publish_local(Path::new(path.strip_prefix("file://").unwrap_or(path)), &bytes)?;
        path.to_owned()
    };
    Ok(FileRef {
        path: uri,
        format: Some(format.to_owned()),
        fingerprint: Some(FileFingerprint {
            size, mtime_ns: 0, content_hash: Some(content_hash), immutable_remote: false,
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
