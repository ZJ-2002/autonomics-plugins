use super::HttpFetchError;
use dag_core::registry::NodeCtx;
use dag_core::value::{FileFingerprint, FileRef};
use sha2::{Digest, Sha256};
use std::io::Write;
use std::path::{Path, PathBuf};

fn failure(path: &str, reason: impl ToString) -> HttpFetchError {
    HttpFetchError::Write {
        path: path.to_string(),
        reason: reason.to_string(),
    }
}

fn publish_local(path: &Path, bytes: &[u8]) -> Result<(), HttpFetchError> {
    let display = path.to_string_lossy();
    crate::file_decompress::ensure_local_target(path).map_err(|error| failure(&display, error))?;
    let parent = path
        .parent()
        .ok_or_else(|| failure(&display, "output parent required"))?;
    std::fs::create_dir_all(parent).map_err(|error| failure(&display, error))?;
    let mut pending = tempfile::Builder::new()
        .prefix(".pending-http-body-")
        .tempfile_in(parent)
        .map_err(|error| failure(&display, error))?;
    pending
        .write_all(bytes)
        .and_then(|_| pending.as_file().sync_all())
        .map_err(|error| failure(&display, error))?;
    pending
        .persist_noclobber(path)
        .map_err(|error| failure(&display, error.error))?;
    Ok(())
}

fn output_file(path: &str, size: u64, content_hash: String, mtime_ns: i128) -> FileRef {
    FileRef {
        path: path.to_string(),
        format: Path::new(path)
            .extension()
            .and_then(|extension| extension.to_str())
            .map(str::to_ascii_lowercase),
        fingerprint: Some(FileFingerprint {
            size,
            mtime_ns,
            content_hash: Some(content_hash),
            immutable_remote: false,
        }),
    }
}

pub(super) async fn write_body(
    context: &NodeCtx,
    path: &str,
    bytes: Vec<u8>,
) -> Result<FileRef, HttpFetchError> {
    let size = bytes.len() as u64;
    let content_hash = format!("sha256:{:x}", Sha256::digest(&bytes));
    let local_path = if let Some(virtual_path) = path.strip_prefix("vfs://") {
        crate::file_decompress::ensure_vfs_target(context, path)
            .await
            .map_err(|error| failure(path, error))?;
        let storage = context
            .opendal
            .as_ref()
            .ok_or_else(|| failure(path, "VFS output requires mounted storage"))?;
        let operator = storage.resolve(virtual_path);
        let key = storage.resolve_path(virtual_path);
        if operator.info().scheme() == "fs" {
            Path::new(&operator.info().root()).join(key)
        } else {
            operator
                .write(&key, bytes)
                .await
                .map_err(|error| failure(path, error))?;
            return Ok(output_file(path, size, content_hash, 0));
        }
    } else {
        PathBuf::from(path.strip_prefix("file://").unwrap_or(path))
    };
    publish_local(&local_path, &bytes)?;
    let mtime_ns = if path.starts_with("vfs://") {
        0
    } else {
        std::fs::metadata(&local_path)
            .and_then(|metadata| metadata.modified())
            .ok()
            .and_then(|modified| modified.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|duration| duration.as_nanos() as i128)
            .unwrap_or_default()
    };
    Ok(output_file(path, size, content_hash, mtime_ns))
}
