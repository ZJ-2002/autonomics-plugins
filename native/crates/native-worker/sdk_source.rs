//! Exact source verification for the SDK materialized into this workspace.
//! The outer qualified builder also checks source immutability after Cargo
//! stops; this build-time check binds the embedded interface fingerprint to
//! the actual source files rather than trusting a manifest's claims.
use std::{collections::{BTreeMap, BTreeSet}, fs, io::Read, path::Path};
use serde::Deserialize;
use sha2::{Digest, Sha256};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Manifest {
    schema: String,
    source_revision: String,
    roots: Vec<String>,
    #[serde(default)]
    assets: Vec<String>,
    files: BTreeMap<String, File>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct File { bytes: u64, sha256: String }

fn hex(value: &str, length: usize) -> bool {
    value.len() == length && value.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn relative(value: &str) -> bool {
    !value.is_empty() && !value.contains('\\') && !value.chars().any(char::is_control)
        && value.split('/').all(|part| !part.is_empty() && !matches!(part, "." | ".." | ".git"))
}
fn census(root: &Path, directory: &Path, found: &mut BTreeSet<String>) -> Result<(), String> {
    let metadata = fs::symlink_metadata(directory).map_err(|e| e.to_string())?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err("SDK directories must be real directories".into());
    }
    println!("cargo:rerun-if-changed={}", directory.display());
    for entry in fs::read_dir(directory).map_err(|e| e.to_string())? {
        let path = entry.map_err(|e| e.to_string())?.path();
        let metadata = fs::symlink_metadata(&path).map_err(|e| e.to_string())?;
        if metadata.file_type().is_symlink() { return Err("SDK aliases are forbidden".into()); }
        if metadata.is_dir() { census(root, &path, found)?; }
        else if metadata.is_file() {
            let name = path.strip_prefix(root).map_err(|e| e.to_string())?
                .to_str().ok_or("non-UTF-8 SDK path")?.to_owned();
            if !relative(&name) || !found.insert(name) || found.len() > 65536 {
                return Err("invalid or excessive SDK source inventory".into());
            }
        } else { return Err("SDK source contains a special file".into()); }
    }
    Ok(())
}

pub fn verify(workspace: &Path, raw: &[u8]) -> Result<(), String> {
    if raw.is_empty() || raw.len() > 16 * 1024 * 1024 { return Err("invalid SDK manifest size".into()); }
    let manifest: Manifest = serde_json::from_slice(raw).map_err(|e| e.to_string())?;
    if manifest.schema != "NATIVE_NODE_SDK_SOURCE_V1" || !hex(&manifest.source_revision, 40)
        || manifest.roots.is_empty() || manifest.roots.len() > 256
        || manifest.assets.len() > 65536 || manifest.files.is_empty() || manifest.files.len() > 65536 {
        return Err("invalid SDK manifest identity or bounds".into());
    }
    let root = fs::canonicalize(workspace).map_err(|e| e.to_string())?;
    let mut roots = BTreeSet::new();
    let mut found = BTreeSet::new();
    for name in &manifest.roots {
        if !relative(name) || !name.starts_with("crates/") || name.split('/').count() != 2
            || !roots.insert(name.clone()) || !manifest.files.contains_key(&format!("{name}/Cargo.toml")) {
            return Err("SDK roots must be distinct crate directories with manifests".into());
        }
        let path = root.join(name);
        if fs::canonicalize(&path).map_err(|e| e.to_string())? != path {
            return Err("SDK root traverses an alias".into());
        }
        census(&root, &path, &mut found)?;
    }
    for name in &manifest.assets {
        if !relative(name) || roots.iter().any(|directory| name.starts_with(&format!("{directory}/")))
            || !found.insert(name.clone()) {
            return Err("SDK assets must be distinct source-relative files outside crate roots".into());
        }
        let path = root.join(name);
        if fs::canonicalize(&path).map_err(|e| e.to_string())? != path {
            return Err("SDK asset traverses an alias".into());
        }
    }
    if found != manifest.files.keys().cloned().collect() {
        return Err("SDK source inventory differs from its manifest".into());
    }
    for (name, expected) in &manifest.files {
        if !relative(name) || expected.bytes > 64 * 1024 * 1024 || !hex(&expected.sha256, 64) {
            return Err("invalid SDK file identity".into());
        }
        let path = root.join(name);
        let mut file = fs::File::open(&path).map_err(|e| e.to_string())?;
        let before = file.metadata().map_err(|e| e.to_string())?;
        if !before.is_file() || before.len() != expected.bytes {
            return Err(format!("SDK file size differs: {name}"));
        }
        let mut digest = Sha256::new();
        let mut buffer = [0u8; 65536];
        let mut size = 0u64;
        loop {
            let count = file.read(&mut buffer).map_err(|e| e.to_string())?;
            if count == 0 { break; }
            size += count as u64;
            if size > expected.bytes { return Err(format!("SDK file grew: {name}")); }
            digest.update(&buffer[..count]);
        }
        let after = file.metadata().map_err(|e| e.to_string())?;
        let named = fs::symlink_metadata(&path).map_err(|e| e.to_string())?;
        use std::os::unix::fs::MetadataExt;
        let identity = |m: &fs::Metadata| (m.dev(), m.ino(), m.mode(), m.nlink(), m.len(), m.mtime(), m.mtime_nsec(), m.ctime(), m.ctime_nsec());
        if identity(&before) != identity(&after) || identity(&after) != identity(&named)
            || size != expected.bytes || format!("{:x}", digest.finalize()) != expected.sha256 {
            return Err(format!("SDK source changed or digest differs: {name}"));
        }
        println!("cargo:rerun-if-changed={}", path.display());
    }
    Ok(())
}
