use container_plugin::{factory::Plugin, manifest::PluginManifest};
use container_runtime::{PanelCache, PodmanConfig, PodmanRuntime};
use dag_core::{BundleRegistry, DataBundle};
use dag_core::{
    dag::{
        DAG,
        runtime::{InputHashing, SchedulerConfig},
    },
    registry::{NodeCtx, NodeRegistry},
    resource::MemoryGuardConfig,
};
use datafusion::{execution::object_store::ObjectStoreUrl, prelude::SessionContext};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::{path::PathBuf, sync::Arc, time::Duration};
use vfs::{
    BackendConfig, BackendDefinition, MountDefinition, MountedObjectStore, OpendalFileStorage,
    VfsManifest,
};

const TRANSPORT_SCOPE: &str = "LOCKED_LEGACY_SOURCE_TRANSPORT_NO_FIT_NOT_G0";
const REPLAY_SCOPE: &str = "LOCKED_LEGACY_B_THREE_MODEL_REPLAY_NOT_G0";
const A_HARMONISATION_SCOPE: &str = "LOCKED_LEGACY_A_HARMONISATION_NO_FIT_NOT_G0";
const A_RAW_SCOPE: &str = "LOCKED_LEGACY_A_RAW_QC_LD_NO_MR_NOT_G0";
const A_RAW_MANIFEST: &str = "eb62df8d8ee4e4c18d84b66a141c6ec51e35cceff5dd42017c8723e470e4b908";
const A_RAW_SCRIPT: &str = "81421c4467c4d204e576949b9a364dd487ffb647e9e429bb922ed7938b1f5a69";
const A_RAW_PANEL_ID: &str = "wjixiang/catalog-plink-ref-1000g-eur-binary";
const A_RAW_PANEL_DIGEST: &str =
    "sha256:9f483fd11fbb2e73a97ab1af172e45e569c7b8ed7edec5572e35a2b3fa614b21";
const A_RAW_PANEL_SHA: &str = "fe6a3d9717ea70714dcf1c8c9d15b2790501f030a93283042adebab3e8f1ed2b";
const A_RAW_PANEL_VPATH: &str = "/locked-panels/1000g-eur";
const A_RAW_PANEL_HOST: &str = "/home/zj-normal/.autonomics/panels/wjixiang/catalog-plink-ref-1000g-eur-binary@sha256:9f483fd11fbb2e73a97ab1af172e45e569c7b8ed7edec5572e35a2b3fa614b21";
const A_RAW_SOURCE_FILES: [&str; 9] = [
    "/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0/04_DATA/G0_MINIMUM_A/GCST90652391.h.tsv.gz",
    "/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0/04_DATA/G0_MINIMUM_A/GCST90002393.h.tsv.gz",
    "/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0/03_AUDIT/G0_v4.3.2_2026-10-11/A_ANALYSIS_CONFIG.json",
    "/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0/03_AUDIT/G0_v4.3.2_2026-10-11/G0_V432_CERTIFICATE.json",
    "/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0/02_EXECUTION/prepare_minimum_g0.py",
    "/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0/02_EXECUTION/verify_minimum_ld.py",
    "/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0/04_SOFTWARE/bin/plink",
    "/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0/04_DATA/LD_REF_1000G_EUR_489/manifest.json",
    "/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0/02_EXECUTION/SOFTWARE_LOCK.tsv",
];
const A_HARMONISATION_MANIFEST: &str =
    "07051b9e8351ae30a74ac8b25074e256bfb9d2fb0af53922864d0c16101a01fb";
const A_HARMONISATION_SCRIPT: &str =
    "03a7325619dd1ff927db37875c7d0c040c0d2bf9e97ef1b8af72c2f5533a91f1";
const AUTHORIZATION_SHA: &str = "fd8d56a7dd76eea82bab82d4a07c94d4e1e2f9040d69881e02810cf84e916299";
const SOURCE_SESSION: &str = "d585c6c7ef5f49b7bc3845d722572eec";
const SOURCE_SEAL: &str = "ae4bdb186263789615ad6123376b2c9a090f850e2f0920528eb79f53a9b81bf7";
const SOURCE_VERIFIER: &str = "1a928da15243316facd63358c9f33dbc69f399de41b1f7b8f341f05c647a1073";
const SOURCE_MANIFEST: &str = "1bf0699bffde16a419a308d66654610cdca3170aa3fab2b8b50d93656e80e2a5";
const TRANSPORT_MANIFEST: &str = "939a180cafbdeb45899ea216fe71db7e0a2a77a6fc360d09258e14532dbfbcef";

fn transport_mode(job: &Value) -> Result<bool, Box<dyn std::error::Error>> {
    if job["scope"] == "TECHNICAL_PLUGIN_DAG_NOT_G0" {
        if matches!(
            job["expected_plugin_name"].as_str(),
            Some("frozen-b-project" | "frozen-a-harmonisation" | "frozen-a-input-qualification")
        ) || job["additional_plugins"].as_array().is_some_and(|plugins| {
            plugins.iter().any(|plugin| {
                matches!(
                    plugin["expected_plugin_name"].as_str(),
                    Some(
                        "frozen-b-project"
                            | "frozen-a-harmonisation"
                            | "frozen-a-input-qualification"
                    )
                )
            })
        }) {
            return Err("fixed real legacy source cannot be relabelled as synthetic".into());
        }
        validate_synthetic_kinds(
            job,
            job["nodes"]
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|node| node["kind"].as_str()),
        )?;
        return Ok(false);
    }
    if job["scope"] == A_HARMONISATION_SCOPE {
        validate_a_harmonisation_job(job)?;
        return Ok(true);
    }
    if job["scope"] == A_RAW_SCOPE {
        validate_a_raw_job(job)?;
        return Ok(true);
    }
    let full_replay = job["scope"] == REPLAY_SCOPE;
    if job["scope"] != TRANSPORT_SCOPE && !full_replay {
        return Err("explicit synthetic or locked legacy no-fit transport scope required".into());
    }
    let scripts = json!({
        "scripts/run-intake.py": "6d6f6aac6c57c873886864fb700db6628a974bc370b18c21dbb1e04e47217ac1",
        "scripts/run-family.py": "fd934edefd44aeecb50bafd6a9d832e71618c18409762c585e7838bded144b0b"
    });
    if job["expected_plugin_name"] != "frozen-b-project"
        || job["plugin_manifest_sha256"] != TRANSPORT_MANIFEST
        || job["script_sha256"] != scripts
        || job["panel_manifest_sha256"] != json!({})
        || job["panel_overrides"] != json!([])
        || job["bundles"] != json!([])
        || (!full_replay
            && job
                .get("additional_plugins")
                .is_some_and(|value| value != &json!([])))
    {
        return Err(
            "exact efb691f frozen-B transport without extra plugins or panels required".into(),
        );
    }
    if full_replay {
        let plugins = job["additional_plugins"]
            .as_array()
            .ok_or("exact normalized replay plugin required")?;
        if plugins.len() != 1 || !plugins[0]["plugin_manifest"].is_string() {
            return Err("one additional normalized replay manifest required".into());
        }
        let expected = json!({"plugin_manifest":plugins[0]["plugin_manifest"],
            "expected_plugin_name":"bulk-limma-normalized",
            "plugin_manifest_sha256":"d643744bb9c96c31f3e0f86b8782ff61a66ec4281ca3b0c45bbc041dbcda09f2",
            "script_sha256":{
                "scripts/run-design.R":"ed9ab1fd7b4c5f4533a7fac14d50ded9c829a840e849d974486945534648d707",
                "scripts/run-limma.R":"a300208080b1cf6c8d3361fe4f0dbea50977a45f7e76fed00bfe49dc7def738c"},
            "panel_overrides":[]});
        if plugins[0] != expected || job["operator_authorization_sha256"] != AUTHORIZATION_SHA {
            return Err(
                "exact efb normalized plugin and bounded replay authorization required".into(),
            );
        }
    }
    let nodes = job["nodes"].as_array().ok_or("transport nodes required")?;
    if nodes.is_empty()
        || nodes.len() > 128
        || job["edges"]
            .as_array()
            .ok_or("transport edges required")?
            .len()
            > 512
    {
        return Err("bounded nonempty transport graph required".into());
    }
    for node in nodes {
        match node["kind"].as_str() {
            Some("file_reference") => {
                let path = node["spec"]["path"]
                    .as_str()
                    .ok_or("literal VFS file required")?;
                if !path.starts_with("vfs:///")
                    || path.contains('\\')
                    || path.chars().any(char::is_control)
                    || path[7..]
                        .split('/')
                        .any(|part| matches!(part, "" | "." | ".."))
                {
                    return Err(
                        "transport references must stay within the owned VFS fixture".into(),
                    );
                }
            }
            Some("frozen_b_legacy_intake" | "frozen_b_legacy_family")
                if node["spec"] == json!({}) => {}
            Some("bulk_normalized_design" | "bulk_normalized_limma")
                if full_replay && node["spec"] == json!({}) => {}
            _ => return Err("fit, SQL, conversion or unreviewed transport node forbidden".into()),
        }
    }
    if full_replay {
        validate_replay_graph(job)?;
    }
    Ok(true)
}

fn validate_synthetic_kinds<'a>(
    job: &Value,
    kinds: impl IntoIterator<Item = &'a str>,
) -> Result<(), Box<dyn std::error::Error>> {
    if job["scope"] == "TECHNICAL_PLUGIN_DAG_NOT_G0"
        && kinds.into_iter().any(|kind| {
            matches!(
                kind,
                "frozen_b_legacy_intake"
                    | "frozen_b_legacy_family"
                    | "frozen_a_v432_harmonisation"
                    | "frozen_a_v432_input_qualification"
            )
        })
    {
        return Err("fixed real legacy node kinds cannot be relabelled as synthetic through a renamed family".into());
    }
    Ok(())
}

fn validate_a_harmonisation_job(job: &Value) -> Result<(), Box<dyn std::error::Error>> {
    if job["expected_plugin_name"] != "frozen-a-harmonisation"
        || job["plugin_manifest_sha256"] != A_HARMONISATION_MANIFEST
        || job["script_sha256"] != json!({"scripts/harmonise.R": A_HARMONISATION_SCRIPT})
        || job["panel_overrides"] != json!([])
        || job["panel_manifest_sha256"] != json!({})
        || job["bundles"] != json!([])
        || job
            .get("additional_plugins")
            .is_some_and(|value| value != &json!([]))
    {
        return Err("exact official frozen A qualification source without panels or additional plugins required".into());
    }
    validate_a_graph(job, 6, "frozen_a_v432_harmonisation")
}

fn a_raw_bundle() -> Value {
    json!({"ident":A_RAW_PANEL_ID,"desc":"Frozen official 1000G EUR panel; read-only; not synthetic",
        "vpath":A_RAW_PANEL_VPATH,"source":A_RAW_PANEL_VPATH,"digest":A_RAW_PANEL_DIGEST})
}

fn a_raw_source_path(port: usize) -> String {
    let name = std::path::Path::new(A_RAW_SOURCE_FILES[port])
        .file_name()
        .unwrap()
        .to_str()
        .unwrap();
    format!("/locked-inputs/{port}/{name}")
}

fn validate_a_raw_job(job: &Value) -> Result<(), Box<dyn std::error::Error>> {
    if job["expected_plugin_name"] != "frozen-a-input-qualification"
        || job["plugin_manifest_sha256"] != A_RAW_MANIFEST
        || job["script_sha256"] != json!({"scripts/qualify.py":A_RAW_SCRIPT})
        || job["panel_overrides"] != json!([])
        || job["panel_manifest_sha256"] != json!({A_RAW_PANEL_VPATH:A_RAW_PANEL_SHA})
        || job["bundles"] != json!([a_raw_bundle()])
        || job["locked_panel_source"] != A_RAW_PANEL_HOST
        || job
            .get("additional_plugins")
            .is_some_and(|value| value != &json!([]))
    {
        return Err(
            "exact frozen raw A qualification and original read-only catalog panel required".into(),
        );
    }
    validate_a_graph(job, 9, "frozen_a_v432_input_qualification")?;
    for edge in job["edges"].as_array().ok_or("raw A edges required")? {
        let port = edge["to_port"].as_u64().ok_or("raw A port required")? as usize;
        let node = job["nodes"]
            .as_array()
            .ok_or("raw A nodes required")?
            .iter()
            .find(|node| node["id"] == edge["from"])
            .ok_or("raw A source node required")?;
        if node["spec"]["path"] != format!("vfs://{}", a_raw_source_path(port)) {
            return Err(
                "raw A input ports must directly bind their exact read-only canonical source mount"
                    .into(),
            );
        }
    }
    Ok(())
}

fn validate_a_graph(
    job: &Value,
    count: u64,
    method_kind: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let nodes = job["nodes"]
        .as_array()
        .ok_or("A qualification nodes required")?;
    let mut kinds = BTreeMap::new();
    for node in nodes {
        let id = node["id"].as_str().ok_or("A node identity required")?;
        let kind = node["kind"].as_str().ok_or("A node kind required")?;
        if id.is_empty() || kinds.insert(id, kind).is_some() {
            return Err("unique A qualification node identities required".into());
        }
        match kind {
            "file_reference" => {
                let path = node["spec"]["path"]
                    .as_str()
                    .ok_or("literal A input VFS path required")?;
                if !path.starts_with("vfs:///")
                    || path.contains('\\')
                    || path.chars().any(char::is_control)
                    || path[7..]
                        .split('/')
                        .any(|part| matches!(part, "" | "." | ".."))
                {
                    return Err("A references must stay within the owned VFS fixture".into());
                }
            }
            kind if kind == method_kind && node["spec"] == json!({}) => {}
            _ => {
                return Err(
                    "A qualification permits no MR, fit, SQL or other processing node".into(),
                );
            }
        }
    }
    let references = kinds
        .iter()
        .filter_map(|(id, kind)| (*kind == "file_reference").then_some(*id))
        .collect::<std::collections::BTreeSet<_>>();
    let method = kinds
        .iter()
        .filter_map(|(id, kind)| (*kind == method_kind).then_some(*id))
        .collect::<Vec<_>>();
    if nodes.len() as u64 != count + 1 || references.len() as u64 != count || method.len() != 1 {
        return Err("exact frozen source count and one A qualification node required".into());
    }
    let edges = job["edges"]
        .as_array()
        .ok_or("A qualification edges required")?;
    let mut ports = std::collections::BTreeSet::new();
    let mut sources = std::collections::BTreeSet::new();
    for edge in edges {
        let source = edge["from"].as_str().ok_or("A edge source required")?;
        let port = edge["to_port"].as_u64().ok_or("A input port required")?;
        if !references.contains(source)
            || edge["from_port"].as_u64() != Some(0)
            || edge["to"].as_str() != Some(method[0])
            || port >= count
            || !ports.insert(port)
            || !sources.insert(source)
        {
            return Err("each exact A source must bind one unique qualification input port".into());
        }
    }
    if edges.len() as u64 != count || ports.len() as u64 != count || sources != references {
        return Err("exact complete frozen A qualification edge inventory required".into());
    }
    Ok(())
}

fn locked_a_panel_records() -> Result<Value, Box<dyn std::error::Error>> {
    use std::io::Read;
    use std::os::unix::fs::MetadataExt;
    let directory = PathBuf::from(A_RAW_PANEL_HOST);
    if directory.canonicalize()? != directory
        || directory.symlink_metadata()?.file_type().is_symlink()
    {
        return Err("frozen panel source must have its exact unaliased host identity".into());
    }
    let path = directory.join("manifest.json");
    let bytes = std::fs::read(&path)?;
    if path.symlink_metadata()?.file_type().is_symlink()
        || format!("{:x}", Sha256::digest(&bytes)) != A_RAW_PANEL_SHA
    {
        return Err("actual frozen panel manifest differs from its admitted byte identity".into());
    }
    let manifest: container_runtime::PanelManifest = serde_json::from_slice(&bytes)?;
    manifest.validate()?;
    if manifest.id != A_RAW_PANEL_ID
        || manifest.digest != A_RAW_PANEL_DIGEST
        || manifest.files.len() != 66
    {
        return Err("exact original 66-file catalog panel required".into());
    }
    let metadata = directory.metadata()?;
    let mut records = Vec::new();
    let mut expected = std::collections::BTreeSet::from([
        "manifest.json".to_owned(),
        ".autonomics-panel-complete".to_owned(),
    ]);
    for file in manifest.files {
        if file.path.contains('/') || file.path == "." || file.path == ".." {
            return Err("only original top-level frozen panel payload files permitted".into());
        }
        expected.insert(file.path.clone());
        let path = directory.join(&file.path);
        let info = path.symlink_metadata()?;
        if !info.is_file() || info.file_type().is_symlink() || info.len() != file.size {
            return Err("frozen panel payload metadata differs".into());
        }
        let mut input = std::fs::File::open(&path)?;
        let mut hasher = Sha256::new();
        let mut buffer = vec![0u8; 1024 * 1024];
        loop {
            let count = input.read(&mut buffer)?;
            if count == 0 {
                break;
            }
            hasher.update(&buffer[..count]);
        }
        if format!("sha256:{:x}", hasher.finalize()) != file.sha256 {
            return Err("frozen panel payload content differs".into());
        }
        records.push(
            json!({"path":file.path,"bytes":file.size,"sha256":file.sha256,
            "device":info.dev(),"inode":info.ino(),"uid":info.uid(),"mode":info.mode(),
            "nlink":info.nlink(),"mtime":info.mtime(),"mtime_nsec":info.mtime_nsec(),
            "ctime":info.ctime(),"ctime_nsec":info.ctime_nsec()}),
        );
    }
    let actual = std::fs::read_dir(&directory)?
        .map(|entry| {
            let entry = entry?;
            Ok(entry
                .file_name()
                .into_string()
                .map_err(|_| "non-UTF8 panel path")?)
        })
        .collect::<Result<std::collections::BTreeSet<_>, Box<dyn std::error::Error>>>()?;
    if actual != expected {
        return Err("canonical frozen panel file universe changed".into());
    }
    Ok(
        json!({"host_source":A_RAW_PANEL_HOST,"catalog_bundle":A_RAW_PANEL_ID,
        "digest":A_RAW_PANEL_DIGEST,"manifest_sha256":A_RAW_PANEL_SHA,"payload_files":records,
        "source_directory":{"device":metadata.dev(),"inode":metadata.ino(),"uid":metadata.uid(),
            "mtime":metadata.mtime(),"mtime_nsec":metadata.mtime_nsec(),"ctime":metadata.ctime(),"ctime_nsec":metadata.ctime_nsec()}}),
    )
}

fn seed_locked_a_panel_cache(root: &std::path::Path) -> Result<(), Box<dyn std::error::Error>> {
    use std::os::unix::fs::MetadataExt;
    let destination = root.join(format!("{A_RAW_PANEL_ID}@{A_RAW_PANEL_DIGEST}"));
    std::fs::create_dir_all(destination.parent().ok_or("panel cache parent required")?)?;
    std::fs::create_dir(&destination)?;
    let manifest: container_runtime::PanelManifest = serde_json::from_slice(&std::fs::read(
        PathBuf::from(A_RAW_PANEL_HOST).join("manifest.json"),
    )?)?;
    for file in manifest.files {
        let source = PathBuf::from(A_RAW_PANEL_HOST).join(&file.path);
        let target = destination.join(&file.path);
        let status = std::process::Command::new("/usr/bin/cp")
            .args(["--reflink=always", "--no-clobber", "--"])
            .arg(&source)
            .arg(&target)
            .status()?;
        if !status.success() {
            return Err("temporary CoW panel transport unavailable; ordinary copy and hardlink fallback forbidden".into());
        }
        let before = source.symlink_metadata()?;
        let after = target.symlink_metadata()?;
        if !after.is_file()
            || after.file_type().is_symlink()
            || before.len() != after.len()
            || (before.dev(), before.ino()) == (after.dev(), after.ino())
        {
            return Err("temporary CoW panel must use separate regular payload inodes".into());
        }
    }
    std::fs::write(
        destination.join(".autonomics-panel-complete"),
        format!("digest={A_RAW_PANEL_DIGEST}\n"),
    )?;
    Ok(())
}

fn validate_replay_graph(job: &Value) -> Result<(), Box<dyn std::error::Error>> {
    type Edge = (String, u8, String, u8);
    let nodes = job["nodes"].as_array().ok_or("nodes required")?;
    let mut kinds = BTreeMap::new();
    for node in nodes {
        let id = node["id"].as_str().ok_or("node identity required")?;
        let kind = node["kind"].as_str().ok_or("node kind required")?;
        if id.is_empty() || kinds.insert(id, kind).is_some() {
            return Err("unique replay node identities required".into());
        }
    }
    let ids = |kind| {
        kinds
            .iter()
            .filter_map(|(id, value)| (*value == kind).then_some(*id))
            .collect::<Vec<_>>()
    };
    if nodes.len() != 29
        || ids("file_reference").len() != 19
        || ids("frozen_b_legacy_intake").len() != 1
        || ids("frozen_b_legacy_family").len() != 3
        || ids("bulk_normalized_design").len() != 3
        || ids("bulk_normalized_limma").len() != 3
    {
        return Err(
            "exact 19 sources, intake and three DESIGN/LIMMA/family chains required".into(),
        );
    }
    let raw_edges = job["edges"].as_array().ok_or("edges required")?;
    let mut edges = std::collections::BTreeSet::<Edge>::new();
    for edge in raw_edges {
        edges.insert((
            edge["from"].as_str().ok_or("edge source required")?.into(),
            u8::try_from(edge["from_port"].as_u64().ok_or("source port required")?)?,
            edge["to"].as_str().ok_or("edge target required")?.into(),
            u8::try_from(edge["to_port"].as_u64().ok_or("target port required")?)?,
        ));
    }
    if raw_edges.len() != 64 || edges.len() != 64 {
        return Err("exact unique 64 replay edges required".into());
    }
    let intake = ids("frozen_b_legacy_intake")[0];
    let mut expected = std::collections::BTreeSet::<Edge>::new();
    let mut sources = std::collections::BTreeSet::new();
    for port in 0..19 {
        let incoming = edges
            .iter()
            .filter(|edge| edge.2 == intake && edge.3 == port)
            .collect::<Vec<_>>();
        if incoming.len() != 1
            || incoming[0].1 != 0
            || kinds.get(incoming[0].0.as_str()) != Some(&"file_reference")
            || !sources.insert(incoming[0].0.clone())
        {
            return Err(
                "nineteen distinct actual file sources must bind frozen intake ports in order"
                    .into(),
            );
        }
        expected.insert((*incoming[0]).clone());
    }
    let mut configurations = std::collections::BTreeSet::new();
    for design in ids("bulk_normalized_design") {
        let incoming = edges
            .iter()
            .filter(|edge| edge.2 == design && edge.3 == 0)
            .collect::<Vec<_>>();
        if incoming.len() != 1
            || incoming[0].0 != intake
            || ![0, 6, 8].contains(&incoming[0].1)
            || !configurations.insert(incoming[0].1)
        {
            return Err("exact three prespecified configuration ports required".into());
        }
        let config = incoming[0].1;
        let receipt = match config {
            0 => 5,
            6 => 7,
            8 => 9,
            _ => unreachable!(),
        };
        let candidates = edges
            .iter()
            .filter(|edge| {
                edge.0 == design
                    && edge.1 == 0
                    && edge.3 == 5
                    && kinds.get(edge.2.as_str()) == Some(&"bulk_normalized_limma")
            })
            .collect::<Vec<_>>();
        if candidates.len() != 1 {
            return Err("actual DESIGN must bind exactly one matching LIMMA".into());
        }
        let limma = candidates[0].2.clone();
        let candidates = edges
            .iter()
            .filter(|edge| {
                edge.0 == limma
                    && edge.1 == 0
                    && edge.3 == 0
                    && kinds.get(edge.2.as_str()) == Some(&"frozen_b_legacy_family")
            })
            .collect::<Vec<_>>();
        if candidates.len() != 1 {
            return Err("actual LIMMA must bind exactly one matching family".into());
        }
        let family = candidates[0].2.clone();
        for target in [design, limma.as_str()] {
            expected.insert((intake.into(), config, target.into(), 0));
            for port in 1..5 {
                expected.insert((intake.into(), port, target.into(), port));
            }
        }
        expected.insert((design.into(), 0, limma.clone(), 5));
        expected.insert((limma.clone(), 0, family.clone(), 0));
        expected.insert((intake.into(), 2, family.clone(), 1));
        expected.insert((intake.into(), receipt, family.clone(), 2));
        expected.insert((limma.clone(), 1, family.clone(), 3));
    }
    if edges != expected || expected.len() != 64 {
        return Err("replay edges differ from the exact frozen three-model topology".into());
    }
    Ok(())
}

fn replay_authorization(job: &Value) -> Result<Value, Box<dyn std::error::Error>> {
    let path = PathBuf::from(
        job["operator_authorization_file"]
            .as_str()
            .ok_or("private authorization file required")?,
    );
    let metadata = path.symlink_metadata()?;
    if !path.is_absolute() || !metadata.file_type().is_file() || metadata.len() != 2504 {
        return Err("exact regular bounded replay authorization file required".into());
    }
    let bytes = std::fs::read(path)?;
    if format!("{:x}", Sha256::digest(&bytes)) != AUTHORIZATION_SHA {
        return Err("actual user-authorized replay receipt identity differs".into());
    }
    let value: Value = serde_json::from_slice(&bytes)?;
    if value["authorized_scope"] != REPLAY_SCOPE
        || value["plugin_code_revision"] != "efb691f43a47037a3b9fff48a6cb08dff472426e"
        || value["frozen_project_runtime_manifest_sha256"] != SOURCE_MANIFEST
        || value["fresh_original_byte_verifier_session"] != SOURCE_SESSION
        || value["fresh_original_byte_verifier_manifest_sha256"] != SOURCE_SEAL
        || value["scientific_authorization_granted"] != false
        || value["g0_granted"] != false
    {
        return Err(
            "bounded legacy technical authority cannot become scientific permission".into(),
        );
    }
    Ok(
        json!({"sha256":AUTHORIZATION_SHA,"authorized_scope":REPLAY_SCOPE,
        "plugin_code_revision":"efb691f43a47037a3b9fff48a6cb08dff472426e",
        "technical_execution_authorized":true,"scientific_authorization_granted":false,"g0_granted":false}),
    )
}

fn validate_source_report(
    evidence: &Value,
    actual: &Value,
) -> Result<(), Box<dyn std::error::Error>> {
    if evidence["scope"] != "FROZEN_EXISTING_MINIMUM_SOURCE_INTEGRITY_ONLY_NOT_NEW_G0"
        || evidence["actual_exit"] != 0
        || evidence["script_sha256"] != SOURCE_VERIFIER
        || evidence["runtime_manifest_sha256"] != SOURCE_MANIFEST
        || evidence["actual_report"] != *actual
        || actual["passed"] != true
        || actual["read_only"] != true
        || actual["status"] != "G0_V432_MINIMUM_COMPLETE"
        || actual["errors"] != json!([])
        || [
            "all_project_scientific_gates_passed",
            "scientific_truth_certified",
            "scientific_results_computed",
        ]
        .iter()
        .any(|key| actual[*key] != false)
        || [
            "daemon_restarted",
            "study_configuration_changed",
            "scientific_results_computed",
            "scientific_authorization_granted",
            "g0_granted",
        ]
        .iter()
        .any(|key| evidence[*key] != false)
    {
        return Err(
            "actual passed read-only source verification without scientific authority required"
                .into(),
        );
    }
    Ok(())
}

fn archive_members(
    root: &std::path::Path,
    directory: &std::path::Path,
    members: &mut std::collections::BTreeSet<String>,
) -> Result<(), Box<dyn std::error::Error>> {
    for entry in std::fs::read_dir(directory)? {
        let path = entry?.path();
        let kind = path.symlink_metadata()?.file_type();
        if kind.is_symlink() {
            return Err("source proof capsule aliases forbidden".into());
        }
        if kind.is_dir() {
            if path.strip_prefix(root)?.components().count() > 8 {
                return Err("source proof capsule exceeds bounded depth".into());
            }
            archive_members(root, &path, members)?;
        } else if kind.is_file() {
            members.insert(
                path.strip_prefix(root)?
                    .to_str()
                    .ok_or("UTF-8 proof member required")?
                    .to_owned(),
            );
            if members.len() > 7 {
                return Err("source proof capsule has unexpected members".into());
            }
        } else {
            return Err("regular source proof files required".into());
        }
    }
    Ok(())
}

fn verify_source_capsule(
    root: &std::path::Path,
    expected_seal: &str,
) -> Result<Value, Box<dyn std::error::Error>> {
    let mut actual_members = std::collections::BTreeSet::new();
    archive_members(root, root, &mut actual_members)?;
    if root.join("MANIFEST.json").metadata()?.len() > 65536 {
        return Err("bounded source proof manifest required".into());
    }
    let manifest_bytes = std::fs::read(root.join("MANIFEST.json"))?;
    if format!("{:x}", Sha256::digest(&manifest_bytes)) != expected_seal {
        return Err("exact fresh source proof seal required".into());
    }
    let manifest: Value = serde_json::from_slice(&manifest_bytes)?;
    let files = manifest["files"]
        .as_object()
        .ok_or("complete proof inventory required")?;
    if files.len() != 6 || manifest["session"] != SOURCE_SESSION {
        return Err("fixed source proof session and six members required".into());
    }
    let expected_members: std::collections::BTreeSet<String> = files
        .keys()
        .cloned()
        .chain(std::iter::once("MANIFEST.json".into()))
        .collect();
    if actual_members != expected_members {
        return Err("source proof capsule membership differs".into());
    }
    for (name, identity) in files {
        let path = std::path::Path::new(name);
        if path.is_absolute()
            || path
                .components()
                .any(|part| !matches!(part, std::path::Component::Normal(_)))
        {
            return Err("local source proof members required".into());
        }
        let expected_bytes = identity["bytes"].as_u64().ok_or("proof size required")?;
        if expected_bytes > 64 * 1024 * 1024 || root.join(path).metadata()?.len() != expected_bytes
        {
            return Err("bounded exact source proof file size required".into());
        }
        let bytes = std::fs::read(root.join(path))?;
        if bytes.len() as u64 != expected_bytes
            || format!("{:x}", Sha256::digest(&bytes))
                != identity["sha256"].as_str().ok_or("proof SHA required")?
        {
            return Err("source proof capsule bytes differ".into());
        }
    }
    let evidence: Value = serde_json::from_slice(&std::fs::read(
        root.join("permanent/frozen-project-readonly-byte-audit/VERIFICATION.json"),
    )?)?;
    let actual: Value = serde_json::from_slice(&std::fs::read(
        root.join("permanent/frozen-project-readonly-byte-audit/verifier.stdout.json"),
    )?)?;
    validate_source_report(&evidence, &actual)?;
    Ok(
        json!({"session": SOURCE_SESSION, "manifest_sha256": expected_seal,
        "script_sha256": SOURCE_VERIFIER, "runtime_manifest_sha256": SOURCE_MANIFEST,
        "passed": true, "read_only": true, "scientific_results_computed": false,
        "scientific_authorization_granted": false, "g0_granted": false}),
    )
}

fn locked_source_proof() -> Result<Value, Box<dyn std::error::Error>> {
    let archive = PathBuf::from(std::env::var("HOME")?)
        .join(".local/state/autonomics/validation-archives")
        .join(SOURCE_SESSION);
    let session: Value = serde_json::from_slice(&std::fs::read(archive.join("SESSION.json"))?)?;
    if session["session"] != SOURCE_SESSION
        || session["state"] != "CLEANED"
        || session["worker_exit_status"] != 0
        || session["manifest_sha256"] != SOURCE_SEAL
        || session["scientific_authorization_granted"] != false
        || session["g0_granted"] != false
    {
        return Err("completed fresh source-proof worker required".into());
    }
    verify_source_capsule(&archive.join("artifacts"), SOURCE_SEAL)
}

fn inline_scripts(
    manifest: &mut PluginManifest,
    manifest_path: &std::path::Path,
    identities: &Value,
) -> Result<(), Box<dyn std::error::Error>> {
    let family_root = manifest_path
        .parent()
        .ok_or("plugin parent missing")?
        .canonicalize()?;
    for entry in &mut manifest.nodes {
        let script = entry
            .command
            .script_file
            .take()
            .ok_or("actual plugin script required")?;
        let relative = std::path::Path::new(&script);
        if relative.is_absolute()
            || relative.components().any(|part| {
                matches!(
                    part,
                    std::path::Component::ParentDir | std::path::Component::Prefix(_)
                )
            })
        {
            return Err("nonlocal script path forbidden".into());
        }
        let script_path = family_root.join(relative);
        if script_path.symlink_metadata()?.file_type().is_symlink()
            || !script_path.canonicalize()?.starts_with(&family_root)
        {
            return Err("script source escapes the pinned family".into());
        }
        let script_bytes = std::fs::read(script_path)?;
        if format!("{:x}", Sha256::digest(&script_bytes))
            != identities[&script]
                .as_str()
                .ok_or("script identity required")?
        {
            return Err("actual dispatched script differs".into());
        }
        entry.command.script = Some(String::from_utf8(script_bytes)?);
        container_plugin::node_definition::validate(entry)?;
    }
    Ok(())
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut arguments = std::env::args().skip(1);
    let first = arguments
        .next()
        .ok_or("usage: official_plugin_dag [--validate-job] JOB.json")?;
    let validate_only = first == "--validate-job";
    let filename = if validate_only {
        arguments.next().ok_or("job filename required")?
    } else {
        first
    };
    let job: Value = serde_json::from_slice(&std::fs::read(filename)?)?;
    let real_transport = transport_mode(&job)?;
    let full_replay = job["scope"] == REPLAY_SCOPE;
    let a_harmonisation = job["scope"] == A_HARMONISATION_SCOPE;
    let a_raw = job["scope"] == A_RAW_SCOPE;
    let source_proof = if real_transport {
        Some(locked_source_proof()?)
    } else {
        None
    };
    let authorization = if full_replay {
        Some(replay_authorization(&job)?)
    } else {
        None
    };
    let original_panel = if a_raw {
        Some(locked_a_panel_records()?)
    } else {
        None
    };
    let root = PathBuf::from(job["run_root"].as_str().ok_or("run_root required")?);
    let permanent = PathBuf::from(std::env::var("AUTONOMICS_VALIDATION_PERMANENT")?);
    if !root.is_absolute()
        || !root.canonicalize()?.starts_with(permanent.canonicalize()?)
        || root.join("artifacts").exists()
        || root.join("materialized.tsv").exists()
    {
        return Err("new owned technical fixture root required".into());
    }
    let manifest_path = PathBuf::from(
        job["plugin_manifest"]
            .as_str()
            .ok_or("plugin_manifest required")?,
    );
    let manifest_bytes = std::fs::read(&manifest_path)?;
    if format!("{:x}", Sha256::digest(&manifest_bytes))
        != job["plugin_manifest_sha256"]
            .as_str()
            .ok_or("manifest identity required")?
    {
        return Err("canonical manifest bytes differ".into());
    }
    let mut manifest: PluginManifest = toml::from_str(std::str::from_utf8(&manifest_bytes)?)?;
    if manifest.plugin_name
        != job["expected_plugin_name"]
            .as_str()
            .ok_or("explicit plugin identity required")?
        || manifest.nodes.is_empty()
    {
        return Err("exact nonempty plugin identity required".into());
    }
    let mut methods: std::collections::BTreeSet<String> = manifest
        .nodes
        .iter()
        .map(|entry| entry.kind.clone())
        .collect();
    validate_synthetic_kinds(&job, methods.iter().map(String::as_str))?;
    if methods.len() != manifest.nodes.len() {
        return Err("duplicate declared method kind".into());
    }
    if methods.iter().any(|kind| {
        matches!(
            kind.as_str(),
            "file_reference" | "file_to_dataframe" | "dataframe_to_file" | "datafusion_sql"
        )
    }) {
        return Err("plugin cannot replace an engineering factory".into());
    }
    let overrides = job["panel_overrides"]
        .as_array()
        .ok_or("explicit panel override array required")?;
    if !a_raw && overrides.len() != manifest.panels.len() {
        return Err("complete explicit technical panel mapping required".into());
    }
    let mut panel_ids = std::collections::BTreeSet::new();
    if a_raw {
        if manifest.panels.len() != 1
            || manifest.panels[0].binding != "ld_ref"
            || manifest.panels[0].mount != "/panels/ld_ref"
            || manifest.panels[0].bundle.to_string() != A_RAW_PANEL_ID
            || !overrides.is_empty()
        {
            return Err(
                "raw A scope must preserve the exact original catalog panel binding".into(),
            );
        }
        panel_ids.insert(A_RAW_PANEL_ID.to_owned());
    }
    for (panel, replacement) in manifest.panels.iter_mut().zip(overrides) {
        let synthetic = replacement["synthetic_bundle"]
            .as_str()
            .ok_or("synthetic identity required")?;
        if replacement["binding"] != panel.binding
            || replacement["declared_bundle"] != panel.bundle.to_string()
            || replacement["mount"] != panel.mount
            || !synthetic.starts_with("autonomics-technical/")
            || !panel_ids.insert(synthetic.to_owned())
        {
            return Err("declared panel mapping differs or is not explicitly synthetic".into());
        }
        panel.bundle = data_catalog::HfRepoId::new(synthetic)?;
    }
    let synthetic_manifest_bytes = toml::to_string(&manifest)?.into_bytes();
    inline_scripts(&mut manifest, &manifest_path, &job["script_sha256"])?;
    let mut plugin_names = std::collections::BTreeSet::from([manifest.plugin_name.clone()]);
    let mut additional_plugins = Vec::new();
    let mut additional_identities = Vec::new();
    if let Some(entries) = job.get("additional_plugins") {
        for record in entries
            .as_array()
            .ok_or("additional plugins must be an explicit array")?
        {
            let path = PathBuf::from(
                record["plugin_manifest"]
                    .as_str()
                    .ok_or("additional manifest required")?,
            );
            let bytes = std::fs::read(&path)?;
            let hash = format!("{:x}", Sha256::digest(&bytes));
            if hash
                != record["plugin_manifest_sha256"]
                    .as_str()
                    .ok_or("additional manifest identity required")?
            {
                return Err("additional canonical manifest bytes differ".into());
            }
            let mut extra: PluginManifest = toml::from_str(std::str::from_utf8(&bytes)?)?;
            validate_synthetic_kinds(&job, extra.nodes.iter().map(|entry| entry.kind.as_str()))?;
            if extra.plugin_name
                != record["expected_plugin_name"]
                    .as_str()
                    .ok_or("additional plugin identity required")?
                || extra.nodes.is_empty()
                || !plugin_names.insert(extra.plugin_name.clone())
            {
                return Err("additional plugin identity empty, repeated or mismatched".into());
            }
            if !extra.panels.is_empty()
                || record["panel_overrides"]
                    .as_array()
                    .ok_or("additional explicit empty panel mapping required")?
                    .len()
                    != 0
            {
                return Err(
                    "additional plugins with panels are not supported by this technical probe"
                        .into(),
                );
            }
            for entry in &extra.nodes {
                if matches!(
                    entry.kind.as_str(),
                    "file_reference" | "file_to_dataframe" | "dataframe_to_file" | "datafusion_sql"
                ) {
                    return Err("additional plugin cannot replace an engineering factory".into());
                }
                if !methods.insert(entry.kind.clone()) {
                    return Err("duplicate method kind across plugin manifests".into());
                }
            }
            inline_scripts(&mut extra, &path, &record["script_sha256"])?;
            additional_identities.push(json!({
                "plugin_name": extra.plugin_name,
                "original_manifest_sha256": hash,
                "script_sha256": record["script_sha256"],
                "panels": [],
            }));
            additional_plugins.push((extra, bytes));
        }
    }
    if validate_only {
        println!(
            "{}",
            json!({"scope":job["scope"],"job_validated_without_execution":true,
            "source_integrity_proof":source_proof,"operator_authorization":authorization,
            "locked_actual_panel_source":original_panel,
            "containers_started":false,"scientific_results_computed":false,"g0_granted":false})
        );
        return Ok(());
    }
    let mut bundles = BundleRegistry::new();
    for record in job["bundles"]
        .as_array()
        .ok_or("synthetic bundles required")?
    {
        let bundle: DataBundle = serde_json::from_value(record.clone())?;
        if !panel_ids.contains(&bundle.ident)
            || (!a_raw && !bundle.vpath.starts_with("/synthetic-panels/"))
            || bundle.source.as_deref() != Some(bundle.vpath.as_str())
            || bundle.digest.is_none()
        {
            return Err("explicit synthetic panel identity required".into());
        }
        bundles.register(bundle)?;
    }
    if job["bundles"].as_array().ok_or("bundles missing")?.len() != panel_ids.len() {
        return Err("exact complete synthetic bundle inventory required".into());
    }
    let panel_manifest_hashes: BTreeMap<String, String> =
        serde_json::from_value(job["panel_manifest_sha256"].clone())?;
    let panel_cache_root = PathBuf::from(std::env::var("TMPDIR")?)
        .join("official-plugin-panel-cache")
        .join(root.file_name().ok_or("fixture name missing")?);
    if a_raw {
        seed_locked_a_panel_cache(&panel_cache_root)?;
        if original_panel.as_ref() != Some(&locked_a_panel_records()?) {
            return Err(
                "canonical panel source changed during independent temporary CoW transport".into(),
            );
        }
    }
    let panel_cache = Arc::new(
        PanelCache::content_required(&panel_cache_root)
            .with_manifest_hashes(panel_manifest_hashes)?,
    );
    let mut mounts = VfsManifest {
        backend: vec![BackendDefinition {
            id: "technical".into(),
            config: BackendConfig::local("/"),
        }],
        mount: vec![MountDefinition {
            path: "/".into(),
            backend: "technical".into(),
            source: root.to_string_lossy().into_owned(),
            read_only: false,
            permissions: Default::default(),
        }],
    };
    if a_raw {
        mounts.mount.push(MountDefinition {
            path: A_RAW_PANEL_VPATH.into(),
            backend: "technical".into(),
            source: A_RAW_PANEL_HOST.into(),
            read_only: true,
            permissions: Default::default(),
        });
        for (port, filename) in A_RAW_SOURCE_FILES.iter().enumerate() {
            let path = std::path::Path::new(filename);
            mounts.mount.push(MountDefinition {
                path: format!("/locked-inputs/{port}"),
                backend: "technical".into(),
                source: path
                    .parent()
                    .ok_or("canonical source parent required")?
                    .to_string_lossy()
                    .into_owned(),
                read_only: true,
                permissions: Default::default(),
            });
        }
    }
    let mounted = Arc::new(MountedObjectStore::from_manifest(&mounts)?);
    let storage = Arc::new(OpendalFileStorage::with_mounts(&root, mounted.clone()));
    let session = SessionContext::new();
    session
        .runtime_env()
        .register_object_store(ObjectStoreUrl::parse("vfs://")?.as_ref(), mounted);
    let context =
        NodeCtx::new(session.runtime_env(), Some(storage)).with_bundle_registry(Arc::new(bundles));
    let runtime = Arc::new(PodmanRuntime::new(PodmanConfig {
        program: "podman".into(),
        workspace_root: PathBuf::from(std::env::var("TMPDIR")?)
            .join("official-plugin-container-workspaces")
            .join(root.file_name().ok_or("fixture root name missing")?),
        panel_cache_root: panel_cache_root,
        storage_root: None,
        run_root: None,
        storage_driver: None,
        cgroup_manager: None,
        cgroup_parent: None,
        inherit_user_namespace: false,
        disable_swap: false,
    }));
    let mut registry = NodeRegistry::new(context.clone());
    registry.register(Box::new(
        nodes_io::file_reference::FileReferenceNodeFactory {},
    ));
    registry.register(Box::new(
        nodes_io::file_to_dataframe::FileToDataFrameNodeFactory {},
    ));
    registry.register(Box::new(
        nodes_io::dataframe_to_file::DataFrameToFileNodeFactory {},
    ));
    registry.register(Box::new(nodes_io::parquet_sql::DataFusionSqlNodeFactory {}));
    registry.register_plugin(&Plugin::new(
        manifest,
        &synthetic_manifest_bytes,
        runtime.clone(),
        panel_cache.clone(),
    ));
    for (extra, bytes) in additional_plugins {
        registry.register_plugin(&Plugin::new(
            extra,
            &bytes,
            runtime.clone(),
            panel_cache.clone(),
        ));
    }
    let mut dag = DAG::default();
    for record in job["nodes"].as_array().ok_or("nodes required")? {
        let identifier = record["id"].as_str().ok_or("id required")?;
        let kind = record["kind"].as_str().ok_or("kind required")?;
        if !methods.contains(kind)
            && !matches!(
                kind,
                "file_reference" | "file_to_dataframe" | "dataframe_to_file" | "datafusion_sql"
            )
        {
            return Err("undeclared node or native statistical fallback forbidden".into());
        }
        let spec = record["spec"].clone();
        dag.add_node_with_spec(
            identifier.into(),
            registry.build_node(kind, spec.clone())?,
            kind.into(),
            spec,
        )?;
    }
    for edge in job["edges"].as_array().ok_or("edges required")? {
        dag.add_edge(
            edge["from"].as_str().ok_or("from required")?,
            edge["to"].as_str().ok_or("to required")?,
            u8::try_from(edge["from_port"].as_u64().ok_or("from_port required")?)?,
            u8::try_from(edge["to_port"].as_u64().ok_or("to_port required")?)?,
        )?;
    }
    let configuration = SchedulerConfig {
        max_concurrency: 1,
        compute_row_counts: true,
        incremental: false,
        input_hashing: InputHashing::ContentRequired,
        memory_guard: MemoryGuardConfig::new(0.90, Duration::from_millis(250)),
        ..SchedulerConfig::default()
    };
    let report = dag.run(&configuration, &context, None).await?;
    let final_panel = if a_raw {
        Some(locked_a_panel_records()?)
    } else {
        None
    };
    if original_panel != final_panel {
        return Err(
            "canonical frozen panel contents or metadata changed during technical DAG".into(),
        );
    }
    let evidence = json!({
        "scope": if full_replay { "REAL_LOCKED_LEGACY_THREE_MODEL_TECHNICAL_REPLAY" } else if a_harmonisation { "REAL_LOCKED_LEGACY_A_HARMONISATION_NO_FIT" } else if a_raw { "REAL_LOCKED_LEGACY_A_RAW_QC_LD_NO_MR" } else if real_transport { "REAL_LOCKED_LEGACY_TRANSPORT_NO_FIT" } else { "TECHNICAL_PLUGIN_DAG_NOT_G0" },
        "source_integrity_proof": source_proof,
        "operator_authorization": authorization,
        "real_locked_legacy_transport_no_fit": real_transport && !full_replay,
        "explicit_replay_scope_allows_fit": full_replay,
        "engine_source_revision": dag_core::source_revision(),
        "first_run": report,
        "max_concurrency": 1,
        "incremental": false,
        "input_hashing": "ContentRequired",
        "current_daemon_verified": false,
        "plugin_name": job["expected_plugin_name"],
        "additional_plugin_identities": additional_identities,
        "native_statistical_factories_registered": false,
        "original_manifest_sha256": format!("{:x}", Sha256::digest(&manifest_bytes)),
        "effective_manifest_sha256": format!("{:x}", Sha256::digest(&synthetic_manifest_bytes)),
        "effective_synthetic_manifest_sha256": if a_raw { None } else { Some(format!("{:x}", Sha256::digest(&synthetic_manifest_bytes))) },
        "locked_actual_panel_source_before":original_panel,
        "locked_actual_panel_source_after":final_panel,
        "panel_transport":if a_raw { Some("TEMPORARY_REFLINK_ALWAYS_INDEPENDENT_COW_INODES_NO_FALLBACK_READONLY_MOUNT") } else { None },
        "panel_bindings_are_explicit_synthetic_overrides": !real_transport,
        "actual_research_panels_qualified": false,
        "scientific_authorized": false,
        "g0_granted": false,
    });
    std::fs::write(
        root.join("dag-report.json"),
        serde_json::to_vec_pretty(&evidence)?,
    )?;
    println!("{}", root.join("dag-report.json").display());
    Ok(())
}

#[cfg(test)]
mod transport_tests {
    use super::*;

    fn job() -> Value {
        json!({"scope": TRANSPORT_SCOPE, "expected_plugin_name": "frozen-b-project",
            "plugin_manifest_sha256": TRANSPORT_MANIFEST,
            "script_sha256": {
                "scripts/run-intake.py": "6d6f6aac6c57c873886864fb700db6628a974bc370b18c21dbb1e04e47217ac1",
                "scripts/run-family.py": "fd934edefd44aeecb50bafd6a9d832e71618c18409762c585e7838bded144b0b"},
            "panel_overrides": [], "bundles": [], "panel_manifest_sha256": {},
            "nodes": [{"id":"source","kind":"file_reference","spec":{"path":"vfs:///source.json"}},
                {"id":"intake","kind":"frozen_b_legacy_intake","spec":{}},
                {"id":"family","kind":"frozen_b_legacy_family","spec":{}}], "edges":[]})
    }

    fn reports() -> (Value, Value) {
        let actual = json!({"passed": true, "read_only": true, "status": "G0_V432_MINIMUM_COMPLETE",
            "errors": [], "all_project_scientific_gates_passed": false,
            "scientific_truth_certified": false, "scientific_results_computed": false});
        let evidence = json!({"scope": "FROZEN_EXISTING_MINIMUM_SOURCE_INTEGRITY_ONLY_NOT_NEW_G0",
            "actual_exit": 0, "script_sha256": SOURCE_VERIFIER,
            "runtime_manifest_sha256": SOURCE_MANIFEST, "actual_report": actual,
            "daemon_restarted": false, "study_configuration_changed": false,
            "scientific_results_computed": false, "scientific_authorization_granted": false,
            "g0_granted": false});
        (evidence, actual)
    }

    fn a_harmonisation_job() -> Value {
        let mut value = json!({"scope":A_HARMONISATION_SCOPE,
            "expected_plugin_name":"frozen-a-harmonisation",
            "plugin_manifest_sha256":A_HARMONISATION_MANIFEST,
            "script_sha256":{"scripts/harmonise.R":A_HARMONISATION_SCRIPT},
            "panel_overrides":[],"bundles":[],"panel_manifest_sha256":{},
            "nodes":[{"id":"qualification","kind":"frozen_a_v432_harmonisation","spec":{}}],
            "edges":[]});
        for port in 0..6 {
            value["nodes"]
                .as_array_mut()
                .unwrap()
                .push(json!({"id":format!("source{port}"),
                "kind":"file_reference","spec":{"path":format!("vfs:///source{port}.input")}}));
            value["edges"]
                .as_array_mut()
                .unwrap()
                .push(json!({"from":format!("source{port}"),
                "from_port":0,"to":"qualification","to_port":port}));
        }
        value
    }

    fn a_raw_job() -> Value {
        let mut value = a_harmonisation_job();
        value["scope"] = json!(A_RAW_SCOPE);
        value["expected_plugin_name"] = json!("frozen-a-input-qualification");
        value["plugin_manifest_sha256"] = json!(A_RAW_MANIFEST);
        value["script_sha256"] = json!({"scripts/qualify.py":A_RAW_SCRIPT});
        value["nodes"][0]["kind"] = json!("frozen_a_v432_input_qualification");
        value["panel_manifest_sha256"] = json!({A_RAW_PANEL_VPATH:A_RAW_PANEL_SHA});
        value["bundles"] = json!([a_raw_bundle()]);
        value["locked_panel_source"] = json!(A_RAW_PANEL_HOST);
        for port in 6..9 {
            value["nodes"]
                .as_array_mut()
                .unwrap()
                .push(json!({"id":format!("source{port}"),
                "kind":"file_reference","spec":{"path":format!("vfs:///source{port}.input")}}));
            value["edges"]
                .as_array_mut()
                .unwrap()
                .push(json!({"from":format!("source{port}"),
                "from_port":0,"to":"qualification","to_port":port}));
        }
        for port in 0..9 {
            value["nodes"][port + 1]["spec"]["path"] =
                json!(format!("vfs://{}", a_raw_source_path(port)));
        }
        value
    }

    #[test]
    fn a_raw_sources_require_exact_canonical_readonly_mount_and_port_roles() {
        let value = a_raw_job();
        assert!(transport_mode(&value).unwrap());
        let mut changed = value.clone();
        changed["nodes"][1]["spec"]["path"] = json!("vfs:///owned-input-link.gz");
        assert!(transport_mode(&changed).is_err());
        changed = value.clone();
        changed["nodes"][1]["spec"]["path"] = value["nodes"][2]["spec"]["path"].clone();
        assert!(transport_mode(&changed).is_err());
        changed = value;
        changed["edges"][0]["from"] = json!("source1");
        changed["edges"][1]["from"] = json!("source0");
        assert!(transport_mode(&changed).is_err());
    }

    #[test]
    fn a_raw_requires_exact_nine_sources_and_one_no_mr_method() {
        let value = a_raw_job();
        assert!(transport_mode(&value).unwrap());
        for kind in [
            "twosamplemr",
            "mrlap",
            "datafusion_sql",
            "frozen_a_v432_harmonisation",
            "unknown",
        ] {
            let mut changed = value.clone();
            changed["nodes"][0]["kind"] = json!(kind);
            assert!(transport_mode(&changed).is_err(), "{kind}");
        }
        let mut changed = value;
        changed["nodes"].as_array_mut().unwrap().pop();
        assert!(transport_mode(&changed).is_err());
    }

    #[test]
    fn a_raw_rejects_changed_panel_source_digest_manifest_and_plugins() {
        let value = a_raw_job();
        for (field, replacement) in [
            ("expected_plugin_name", json!("frozen-a-harmonisation")),
            ("plugin_manifest_sha256", json!("0".repeat(64))),
            ("script_sha256", json!({})),
            ("additional_plugins", json!([{}])),
            ("panel_overrides", json!([{}])),
            ("bundles", json!([])),
            ("panel_manifest_sha256", json!({})),
            ("locked_panel_source", json!("/tmp/alternative")),
        ] {
            let mut changed = value.clone();
            changed[field] = replacement;
            assert!(transport_mode(&changed).is_err(), "{field}");
        }
        for (field, replacement) in [
            ("ident", json!("autonomics-technical/relabelled")),
            ("vpath", json!("/synthetic-panels/ld_ref")),
            ("source", json!("/other/source")),
            ("digest", json!("sha256:".to_owned() + &"0".repeat(64))),
        ] {
            let mut changed = value.clone();
            changed["bundles"][0][field] = replacement;
            assert!(transport_mode(&changed).is_err(), "{field}");
        }
    }

    #[test]
    fn a_raw_requires_all_nine_unique_input_bindings() {
        let value = a_raw_job();
        for (field, replacement) in [
            ("from", json!("source1")),
            ("from_port", json!(1)),
            ("to", json!("source0")),
            ("to_port", json!(1)),
            ("to_port", json!(9)),
        ] {
            let mut changed = value.clone();
            changed["edges"][0][field] = replacement;
            assert!(transport_mode(&changed).is_err(), "{field}");
        }
        let mut changed = value;
        changed["edges"].as_array_mut().unwrap().pop();
        assert!(transport_mode(&changed).is_err());
    }

    #[test]
    fn a_raw_cannot_be_relabelled_synthetic_or_other_no_fit_scope() {
        let mut value = a_raw_job();
        for scope in [
            "TECHNICAL_PLUGIN_DAG_NOT_G0",
            A_HARMONISATION_SCOPE,
            TRANSPORT_SCOPE,
            REPLAY_SCOPE,
        ] {
            value["scope"] = json!(scope);
            assert!(transport_mode(&value).is_err(), "{scope}");
        }
        value["scope"] = json!("TECHNICAL_PLUGIN_DAG_NOT_G0");
        value["expected_plugin_name"] = json!("bulk-limma-normalized");
        value["additional_plugins"] =
            json!([{"expected_plugin_name":"frozen-a-input-qualification"}]);
        assert!(transport_mode(&value).is_err());
    }

    #[test]
    fn a_harmonisation_requires_exact_six_sources_and_one_method() {
        let value = a_harmonisation_job();
        assert!(transport_mode(&value).unwrap());
        let mut changed = value.clone();
        changed["nodes"].as_array_mut().unwrap().pop();
        assert!(transport_mode(&changed).is_err());
        changed = value.clone();
        changed["nodes"]
            .as_array_mut()
            .unwrap()
            .push(value["nodes"][0].clone());
        assert!(transport_mode(&changed).is_err());
        changed = value;
        changed["nodes"][1]["id"] = json!("qualification");
        assert!(transport_mode(&changed).is_err());
    }

    #[test]
    fn a_harmonisation_rejects_fit_sql_other_plugins_and_source_substitution() {
        let value = a_harmonisation_job();
        for kind in [
            "twosamplemr",
            "mrlap",
            "bulk_normalized_limma",
            "datafusion_sql",
            "frozen_b_legacy_intake",
            "unknown",
        ] {
            let mut changed = value.clone();
            changed["nodes"][0]["kind"] = json!(kind);
            assert!(transport_mode(&changed).is_err(), "{kind}");
        }
        for (field, replacement) in [
            ("expected_plugin_name", json!("another-plugin")),
            ("plugin_manifest_sha256", json!("0".repeat(64))),
            ("script_sha256", json!({})),
            ("panel_overrides", json!([{}])),
            ("panel_manifest_sha256", json!({"unexpected":"panel"})),
            ("bundles", json!([{}])),
            ("additional_plugins", json!([{}])),
        ] {
            let mut changed = value.clone();
            changed[field] = replacement;
            assert!(transport_mode(&changed).is_err(), "{field}");
        }
        let mut changed = value.clone();
        changed["nodes"][0]["spec"] = json!({"action":1});
        assert!(transport_mode(&changed).is_err());
        for path in [
            "vfs:///../source.input",
            "vfs:///a//b",
            "file:///tmp/source",
            "vfs:///a\\b",
            "vfs:///a\nb",
        ] {
            changed = value.clone();
            changed["nodes"][1]["spec"]["path"] = json!(path);
            assert!(transport_mode(&changed).is_err(), "{path}");
        }
    }

    #[test]
    fn a_harmonisation_requires_all_six_unique_input_bindings() {
        let value = a_harmonisation_job();
        let mut changed = value.clone();
        changed["edges"].as_array_mut().unwrap().pop();
        assert!(transport_mode(&changed).is_err());
        for (field, replacement) in [
            ("from", json!("source1")),
            ("from_port", json!(1)),
            ("to", json!("source0")),
            ("to_port", json!(1)),
            ("to_port", json!(6)),
        ] {
            changed = value.clone();
            changed["edges"][0][field] = replacement;
            assert!(transport_mode(&changed).is_err(), "{field}");
        }
        changed = value.clone();
        changed["edges"]
            .as_array_mut()
            .unwrap()
            .push(value["edges"][0].clone());
        assert!(transport_mode(&changed).is_err());
    }

    #[test]
    fn a_harmonisation_cannot_be_relabelled_synthetic() {
        let mut value = a_harmonisation_job();
        value["scope"] = json!("TECHNICAL_PLUGIN_DAG_NOT_G0");
        assert!(transport_mode(&value).is_err());
        value["expected_plugin_name"] = json!("bulk-limma-normalized");
        value["additional_plugins"] = json!([{"expected_plugin_name":"frozen-a-harmonisation"}]);
        assert!(transport_mode(&value).is_err());
        value["scope"] = json!(TRANSPORT_SCOPE);
        assert!(transport_mode(&value).is_err());
    }

    fn replay_job() -> Value {
        let mut value = job();
        value["scope"] = json!(REPLAY_SCOPE);
        value["operator_authorization_sha256"] = json!(AUTHORIZATION_SHA);
        value["additional_plugins"] = json!([{"plugin_manifest":"normalized/manifest.toml",
            "expected_plugin_name":"bulk-limma-normalized",
            "plugin_manifest_sha256":"d643744bb9c96c31f3e0f86b8782ff61a66ec4281ca3b0c45bbc041dbcda09f2",
            "script_sha256":{
                "scripts/run-design.R":"ed9ab1fd7b4c5f4533a7fac14d50ded9c829a840e849d974486945534648d707",
                "scripts/run-limma.R":"a300208080b1cf6c8d3361fe4f0dbea50977a45f7e76fed00bfe49dc7def738c"},
            "panel_overrides":[]}]);
        let mut nodes = vec![json!({"id":"intake","kind":"frozen_b_legacy_intake","spec":{}})];
        let mut edges = Vec::new();
        for port in 0..19 {
            nodes.push(json!({"id":format!("source{port}"),"kind":"file_reference","spec":{"path":format!("vfs:///source{port}.input")}}));
            edges.push(
                json!({"from":format!("source{port}"),"from_port":0,"to":"intake","to_port":port}),
            );
        }
        for (model, config, receipt) in [
            ("primary", 0, 5),
            ("unadjusted", 6, 7),
            ("therapy_sensitivity", 8, 9),
        ] {
            for (stage, kind) in [
                ("design", "bulk_normalized_design"),
                ("limma", "bulk_normalized_limma"),
                ("family", "frozen_b_legacy_family"),
            ] {
                nodes.push(json!({"id":format!("{model}_{stage}"),"kind":kind,"spec":{}}));
            }
            for stage in ["design", "limma"] {
                edges.push(json!({"from":"intake","from_port":config,"to":format!("{model}_{stage}"),"to_port":0}));
                for port in 1..5 {
                    edges.push(json!({"from":"intake","from_port":port,"to":format!("{model}_{stage}"),"to_port":port}));
                }
            }
            edges.push(json!({"from":format!("{model}_design"),"from_port":0,"to":format!("{model}_limma"),"to_port":5}));
            for (source, output, target) in [
                (format!("{model}_limma"), 0, 0),
                ("intake".into(), 2, 1),
                ("intake".into(), receipt, 2),
                (format!("{model}_limma"), 1, 3),
            ] {
                edges.push(json!({"from":source,"from_port":output,"to":format!("{model}_family"),"to_port":target}));
            }
        }
        value["nodes"] = json!(nodes);
        value["edges"] = json!(edges);
        value
    }

    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            static COUNTER: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
            let root = std::env::temp_dir().join(format!(
                "locked-b-source-guard-{}-{}",
                std::process::id(),
                COUNTER.fetch_add(1, std::sync::atomic::Ordering::SeqCst)
            ));
            std::fs::create_dir(&root).unwrap();
            Self(root)
        }
        fn capsule(&self) -> String {
            let (evidence, actual) = reports();
            let mut files = serde_json::Map::new();
            for (name, bytes) in [
                (
                    "permanent/frozen-project-readonly-byte-audit/VERIFICATION.json",
                    serde_json::to_vec(&evidence).unwrap(),
                ),
                (
                    "permanent/frozen-project-readonly-byte-audit/verifier.stdout.json",
                    serde_json::to_vec(&actual).unwrap(),
                ),
                (
                    "permanent/frozen-project-readonly-byte-audit/verifier.stderr.log",
                    Vec::new(),
                ),
                ("permanent/cache-policy.json", b"{}".to_vec()),
                ("permanent/stdout.log", Vec::new()),
                ("permanent/stderr.log", Vec::new()),
            ] {
                let path = self.0.join(name);
                std::fs::create_dir_all(path.parent().unwrap()).unwrap();
                std::fs::write(path, &bytes).unwrap();
                files.insert(
                    name.into(),
                    json!({"bytes":bytes.len(),"sha256":format!("{:x}",Sha256::digest(&bytes))}),
                );
            }
            let bytes =
                serde_json::to_vec(&json!({"session": SOURCE_SESSION,"files":files})).unwrap();
            std::fs::write(self.0.join("MANIFEST.json"), &bytes).unwrap();
            format!("{:x}", Sha256::digest(&bytes))
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.0).unwrap();
        }
    }

    #[test]
    fn original_synthetic_scope_remains_available() {
        assert!(!transport_mode(&json!({"scope":"TECHNICAL_PLUGIN_DAG_NOT_G0"})).unwrap());
    }
    #[test]
    fn synthetic_scope_rejects_renamed_families_with_locked_kinds() {
        for kind in [
            "frozen_b_legacy_intake",
            "frozen_b_legacy_family",
            "frozen_a_v432_harmonisation",
            "frozen_a_v432_input_qualification",
        ] {
            let value = json!({"scope":"TECHNICAL_PLUGIN_DAG_NOT_G0",
                "expected_plugin_name":"renamed-display-family",
                "nodes":[{"id":"real-method","kind":kind,"spec":{}}]});
            assert!(transport_mode(&value).is_err(), "{kind}");
        }
        for kind in ["bulk_normalized_design", "bulk_normalized_limma"] {
            let value = json!({"scope":"TECHNICAL_PLUGIN_DAG_NOT_G0",
                "expected_plugin_name":"bulk-limma-normalized",
                "nodes":[{"id":"toy-method","kind":kind,"spec":{}}]});
            assert!(!transport_mode(&value).unwrap());
        }
    }
    #[test]
    fn synthetic_manifest_kinds_cannot_hide_locked_nodes_by_renaming() {
        let scope = json!({"scope":"TECHNICAL_PLUGIN_DAG_NOT_G0"});
        for name in ["renamed-primary-family", "renamed-additional-family"] {
            for kind in [
                "frozen_b_legacy_intake",
                "frozen_b_legacy_family",
                "frozen_a_v432_harmonisation",
                "frozen_a_v432_input_qualification",
            ] {
                let definition =
                    serde_json::from_value(json!({"kind":kind,"desc":"technical fixture",
                    "doc":"No method is executed","ports":{"inputs":[],"outputs":[]},
                    "command":{"interpreter":"sh","script":"true"}}))
                    .unwrap();
                let manifest = PluginManifest {
                    plugin_name: name.into(),
                    nodes: vec![definition],
                    ..Default::default()
                };
                assert!(
                    validate_synthetic_kinds(
                        &scope,
                        manifest.nodes.iter().map(|entry| entry.kind.as_str())
                    )
                    .is_err(),
                    "{name}/{kind}"
                );
            }
        }
        assert!(
            validate_synthetic_kinds(&scope, ["bulk_normalized_design", "bulk_normalized_limma"])
                .is_ok()
        );
        assert!(validate_synthetic_kinds(&job(), ["frozen_b_legacy_intake"]).is_ok());
    }
    #[test]
    fn synthetic_scope_cannot_relabel_fixed_real_frozen_b_plugin() {
        let mut value = job();
        value["scope"] = json!("TECHNICAL_PLUGIN_DAG_NOT_G0");
        assert!(transport_mode(&value).is_err());
        value["expected_plugin_name"] = json!("bulk-limma-normalized");
        value["additional_plugins"] = json!([{"expected_plugin_name":"frozen-b-project"}]);
        assert!(transport_mode(&value).is_err());
        value["additional_plugins"] = json!([]);
        assert_eq!(
            transport_mode(&value).unwrap_err().to_string(),
            "fixed real legacy node kinds cannot be relabelled as synthetic through a renamed family"
        );
    }
    #[test]
    fn exact_transport_job_is_accepted_without_executing_it() {
        assert!(transport_mode(&job()).unwrap());
    }
    #[test]
    fn full_replay_requires_exact_typed_29_node_64_edge_topology() {
        let value = replay_job();
        assert!(transport_mode(&value).unwrap());
        for (from, to_port) in [("intake", 2), ("source0", 0)] {
            let mut changed = value.clone();
            changed["edges"][63]["from"] = json!(from);
            changed["edges"][63]["to_port"] = json!(to_port);
            assert!(transport_mode(&changed).is_err());
        }
        let mut changed = value.clone();
        changed["nodes"].as_array_mut().unwrap().pop();
        assert!(transport_mode(&changed).is_err());
        changed = value;
        changed["edges"].as_array_mut().unwrap().pop();
        assert!(transport_mode(&changed).is_err());
    }
    #[test]
    fn full_replay_cannot_change_source_images_methods_or_authorization_identity() {
        let value = replay_job();
        for (field, replacement) in [
            ("plugin_manifest_sha256", json!("0".repeat(64))),
            ("script_sha256", json!({})),
            ("panel_overrides", json!([{}])),
        ] {
            let mut changed = value.clone();
            changed["additional_plugins"][0][field] = replacement;
            assert!(transport_mode(&changed).is_err());
        }
        let mut changed = value;
        changed["operator_authorization_sha256"] = json!("0".repeat(64));
        assert!(transport_mode(&changed).is_err());
    }
    #[test]
    fn full_replay_does_not_relax_no_fit_mode() {
        let mut value = replay_job();
        value["scope"] = json!(TRANSPORT_SCOPE);
        assert!(transport_mode(&value).is_err());
        value["additional_plugins"] = json!([]);
        assert!(transport_mode(&value).is_err());
        assert!(replay_authorization(&json!({})).is_err());
    }
    #[test]
    fn fit_sql_conversion_and_unknown_kinds_are_rejected() {
        for kind in [
            "bulk_normalized_design",
            "bulk_normalized_limma",
            "twosamplemr",
            "mrlap",
            "datafusion_sql",
            "file_to_dataframe",
            "dataframe_to_file",
            "unknown",
        ] {
            let mut value = job();
            value["nodes"][1]["kind"] = json!(kind);
            assert!(transport_mode(&value).is_err(), "{kind}");
        }
    }
    #[test]
    fn plugin_identity_panels_and_additional_plugins_cannot_be_substituted() {
        for (key, value) in [
            ("expected_plugin_name", json!("bulk-limma-normalized")),
            ("plugin_manifest_sha256", json!("0".repeat(64))),
            ("script_sha256", json!({})),
            ("panel_overrides", json!([{}])),
            ("bundles", json!([{}])),
            ("panel_manifest_sha256", json!({"unexpected":"panel"})),
            ("additional_plugins", json!([{}])),
        ] {
            let mut candidate = job();
            candidate[key] = value;
            assert!(transport_mode(&candidate).is_err(), "{key}");
        }
    }
    #[test]
    fn unsafe_paths_specs_and_unknown_scope_are_rejected() {
        for path in [
            "file:///etc/passwd",
            "vfs:///../secret",
            "vfs:///x/./y",
            "vfs:///x//y",
            "vfs:///x\\y",
        ] {
            let mut value = job();
            value["nodes"][0]["spec"]["path"] = json!(path);
            assert!(transport_mode(&value).is_err(), "{path}");
        }
        let mut value = job();
        value["nodes"][1]["spec"] = json!({"script":"fit()"});
        assert!(transport_mode(&value).is_err());
        value = job();
        value["scope"] = json!("UNREVIEWED_LEGACY");
        assert!(transport_mode(&value).is_err());
    }
    #[test]
    fn source_report_requires_actual_readonly_success_without_scientific_authority() {
        let (evidence, actual) = reports();
        validate_source_report(&evidence, &actual).unwrap();
        for key in ["passed", "read_only"] {
            let mut changed = actual.clone();
            changed[key] = json!(false);
            let mut receipt = evidence.clone();
            receipt["actual_report"] = changed.clone();
            assert!(validate_source_report(&receipt, &changed).is_err());
        }
        for key in [
            "scientific_truth_certified",
            "all_project_scientific_gates_passed",
            "scientific_results_computed",
        ] {
            let mut changed = actual.clone();
            changed[key] = json!(true);
            let mut receipt = evidence.clone();
            receipt["actual_report"] = changed.clone();
            assert!(validate_source_report(&receipt, &changed).is_err());
        }
        for key in [
            "scientific_authorization_granted",
            "g0_granted",
            "daemon_restarted",
        ] {
            let mut changed = evidence.clone();
            changed[key] = json!(true);
            assert!(validate_source_report(&changed, &actual).is_err());
        }
        for key in ["script_sha256", "runtime_manifest_sha256"] {
            let mut changed = evidence.clone();
            changed[key] = json!("0".repeat(64));
            assert!(validate_source_report(&changed, &actual).is_err());
        }
    }
    #[test]
    fn source_capsule_checks_seal_membership_and_each_file_hash() {
        let fixture = Fixture::new();
        let seal = fixture.capsule();
        verify_source_capsule(&fixture.0, &seal).unwrap();
        assert!(verify_source_capsule(&fixture.0, SOURCE_SEAL).is_err());
        std::fs::write(fixture.0.join("permanent/stdout.log"), b"mutated").unwrap();
        assert!(verify_source_capsule(&fixture.0, &seal).is_err());
    }
    #[test]
    fn source_capsule_rejects_extra_members_symlinks_and_missing_evidence() {
        let fixture = Fixture::new();
        let seal = fixture.capsule();
        std::fs::write(fixture.0.join("extra"), b"unexpected").unwrap();
        assert!(verify_source_capsule(&fixture.0, &seal).is_err());
        std::fs::remove_file(fixture.0.join("extra")).unwrap();
        std::os::unix::fs::symlink("permanent/stdout.log", fixture.0.join("alias")).unwrap();
        assert!(verify_source_capsule(&fixture.0, &seal).is_err());
        std::fs::remove_file(fixture.0.join("alias")).unwrap();
        std::fs::remove_file(
            fixture
                .0
                .join("permanent/frozen-project-readonly-byte-audit/VERIFICATION.json"),
        )
        .unwrap();
        assert!(verify_source_capsule(&fixture.0, &seal).is_err());
    }
}
