use std::path::PathBuf;
use sha2::{Digest, Sha256};
mod sdk_source;

fn main() {
    println!("cargo:rerun-if-env-changed=AUTONOMICS_NATIVE_SOURCE_REVISION");
    println!("cargo:rerun-if-env-changed=AUTONOMICS_NATIVE_SDK_MANIFEST");
    let revision = std::env::var("AUTONOMICS_NATIVE_SOURCE_REVISION")
        .expect("the qualified build must provide its frozen full source revision");
    assert!(revision.len() == 40 && revision.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)),
        "native source revision must be a full lowercase Git commit");
    let workspace = PathBuf::from(std::env::var_os("CARGO_MANIFEST_DIR").unwrap()).join("../..");
    let lock = workspace.join("Cargo.lock");
    let sdk = PathBuf::from(std::env::var_os("AUTONOMICS_NATIVE_SDK_MANIFEST")
        .expect("the qualified build must provide its exact source SDK manifest"));
    let lock_bytes = std::fs::read(&lock).expect("a frozen dependency lock is required");
    let sdk_bytes = std::fs::read(&sdk).expect("the source SDK manifest is required");
    sdk_source::verify(&workspace, &sdk_bytes)
        .expect("the compiled SDK source must exactly match its frozen manifest");
    println!("cargo:rerun-if-changed={}", lock.display());
    println!("cargo:rerun-if-changed={}", sdk.display());
    println!("cargo:rustc-env=AUTONOMICS_NATIVE_SOURCE_REVISION={revision}");
    println!("cargo:rustc-env=AUTONOMICS_NATIVE_LOCK_SHA256={:x}", Sha256::digest(lock_bytes));
    println!("cargo:rustc-env=AUTONOMICS_NATIVE_INTERFACE_SHA256={:x}", Sha256::digest(sdk_bytes));
}
