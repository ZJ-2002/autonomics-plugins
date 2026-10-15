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

const FAMILY_SCOPE: &str = "LOCKED_A_COMPLETE_FAMILY_TECHNICAL_NO_MR_NOT_G0";
const FAMILY_PYTHON_MANIFEST: &str =
    "a2ba1a3522b89bf4f229ca649480f9cac0348bcd581a47b287535a2ece2b64cf";
const FAMILY_PYTHON_SCRIPT: &str =
    "338a864e0cfa9c4ab4df181728f28b1a08c6a841cbea906946dc3de90c40a43a";
const FAMILY_R_MANIFEST: &str = "55ce64e5a2cc16ba43962fef7c3039c8df9e83a2670934f1a8b7ff2f383541da";
const FAMILY_R_SCRIPT: &str = "debf19afa415433aa00e9258ff82b56e562bf43a6b2fa96eae4c57d0cb93b412";
const FAMILY_PYTHON_IMAGE: &str = "docker.io/library/python@sha256:7bf6c3111fe094f8ee1a1cbcdc63c4cfb345b0e3df42d5aa9a90b3b4b022ab6d";
const FAMILY_R_IMAGE: &str = "ghcr.io/zj-2002/mrlap-official@sha256:78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d";
const FAMILY_SOURCES: [(u64, &str); 9] = [
    (
        58452,
        "1952fd61e3404364b6bef12334e9743e97f418f80f16ffabd93b4b244473afb4",
    ),
    (
        56329,
        "bdb85f7ab874d2f2d913c75a2eeb60e56bc0b6049472eeb7f45c764b6eaaa1f2",
    ),
    (
        11740332,
        "b8d7116aea0640f3677b72eb653b097c7ff2a7d4e7815819d9927b61790b782a",
    ),
    (
        21306,
        "92a49ae782060a6eb51fcc2d2bde65629f599714facbcb0ebefa53ea155f9f6a",
    ),
    (
        1907,
        "d7d1a89589fba8f8d115c0eefc9cfd4d270f2216181c70f9c528c4c1da9209c3",
    ),
    (
        6325,
        "b66a8b849068a695d65d90decad99229d8a10fe49213d4445d0dfe356f47fee6",
    ),
    (
        13853,
        "1ff187d5672c0448db193db4acb17ee78012ed2588f94bac580075b1cef2245b",
    ),
    (
        5243,
        "2dd34cf6887e829334c2b3ba49f58be5c81b503333dc9183474208ebab49f08d",
    ),
    (
        20329,
        "f7e334db38e331acc30cd0117ca9f2b82831523d1c07ce742382eacbd3aff1cd",
    ),
];

#[derive(Clone)]
struct FamilyPins {
    python_manifest: String,
    python_script: String,
    r_manifest: String,
    r_script: String,
    python_image: String,
    r_image: String,
}

fn family_hash(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn family_image(value: &str) -> bool {
    value
        .rsplit_once("@sha256:")
        .is_some_and(|(name, digest)| !name.is_empty() && family_hash(digest))
}

fn checked_family_pins(pins: &FamilyPins) -> Result<(), Box<dyn std::error::Error>> {
    if ![
        &pins.python_manifest,
        &pins.python_script,
        &pins.r_manifest,
        &pins.r_script,
    ]
    .iter()
    .all(|value| family_hash(value))
        || !family_image(&pins.python_image)
        || !family_image(&pins.r_image)
    {
        return Err(
            "complete frozen family constants are PENDING; execution is unavailable".into(),
        );
    }
    Ok(())
}

fn family_pins() -> Result<FamilyPins, Box<dyn std::error::Error>> {
    let pins = FamilyPins {
        python_manifest: FAMILY_PYTHON_MANIFEST.into(),
        python_script: FAMILY_PYTHON_SCRIPT.into(),
        r_manifest: FAMILY_R_MANIFEST.into(),
        r_script: FAMILY_R_SCRIPT.into(),
        python_image: FAMILY_PYTHON_IMAGE.into(),
        r_image: FAMILY_R_IMAGE.into(),
    };
    checked_family_pins(&pins)?;
    Ok(pins)
}

fn family_name(value: &Value) -> bool {
    matches!(
        value.as_str(),
        Some("frozen-a-family-assembly" | "frozen-a-family-adjustment")
    )
}

fn family_kind(value: &str) -> bool {
    matches!(
        value,
        "frozen_a_family_assemble" | "frozen_a_family_adjust" | "frozen_a_family_publish"
    )
}

fn reject_family_other_scope(job: &Value) -> Result<(), Box<dyn std::error::Error>> {
    if job["scope"] != FAMILY_SCOPE
        && (family_name(&job["expected_plugin_name"])
            || job["additional_plugins"].as_array().is_some_and(|plugins| {
                plugins
                    .iter()
                    .any(|plugin| family_name(&plugin["expected_plugin_name"]))
            })
            || job["nodes"].as_array().is_some_and(|nodes| {
                nodes
                    .iter()
                    .any(|node| node["kind"].as_str().is_some_and(family_kind))
            }))
    {
        return Err("complete frozen A families require their dedicated technical scope".into());
    }
    Ok(())
}

fn validate_family_job_with_pins(
    job: &Value,
    pins: &FamilyPins,
) -> Result<(), Box<dyn std::error::Error>> {
    checked_family_pins(pins)?;
    let permitted = [
        "scope",
        "family_case",
        "run_root",
        "plugin_manifest",
        "expected_plugin_name",
        "plugin_manifest_sha256",
        "script_sha256",
        "panel_overrides",
        "panel_manifest_sha256",
        "bundles",
        "additional_plugins",
        "nodes",
        "edges",
    ];
    if !job.as_object().is_some_and(|fields| {
        fields.len() == permitted.len()
            && fields
                .keys()
                .all(|field| permitted.contains(&field.as_str()))
    }) || !job["run_root"].is_string()
    {
        return Err("only the dedicated family job fields are permitted".into());
    }
    if job["scope"] != FAMILY_SCOPE
        || !matches!(
            job["family_case"].as_str(),
            Some("BOUNDARY" | "INTERIOR" | "REAL_FROZEN_NA_LEDGER")
        )
        || job["expected_plugin_name"] != "frozen-a-family-assembly"
        || job["plugin_manifest_sha256"] != pins.python_manifest
        || job["script_sha256"] != json!({"scripts/family.py": pins.python_script})
        || job["panel_overrides"] != json!([])
        || job["panel_manifest_sha256"] != json!({})
        || job["bundles"] != json!([])
        || !job["plugin_manifest"].is_string()
    {
        return Err(
            "exact frozen family identity, case, scripts and absent panels required".into(),
        );
    }
    let additional = job["additional_plugins"]
        .as_array()
        .ok_or("one official R family required")?;
    if additional.len() != 1
        || !additional[0]["plugin_manifest"].is_string()
        || additional[0]
            != json!({
                "plugin_manifest": additional[0]["plugin_manifest"],
                "expected_plugin_name": "frozen-a-family-adjustment",
                "plugin_manifest_sha256": pins.r_manifest,
                "script_sha256": {"scripts/adjust.R": pins.r_script},
                "panel_overrides": []
            })
    {
        return Err(
            "one exact official R adjustment family without additional authority required".into(),
        );
    }
    let nodes = job["nodes"]
        .as_array()
        .ok_or("exact family nodes required")?;
    let mut expected = BTreeMap::new();
    for index in 0..9 {
        expected.insert(
            format!("source{index}"),
            json!({"kind":"file_reference", "spec":{
            "path":format!("vfs:///source{index}.input"), "format":"file", "hash_content":true}}),
        );
    }
    expected.insert(
        "request".into(),
        json!({"kind":"file_reference", "spec":{
        "path":"vfs:///request.json", "format":"file", "hash_content":true}}),
    );
    for (identifier, kind) in [
        ("assemble", "frozen_a_family_assemble"),
        ("adjust", "frozen_a_family_adjust"),
        ("publish", "frozen_a_family_publish"),
    ] {
        expected.insert(identifier.into(), json!({"kind":kind,"spec":{}}));
    }
    let mut actual = BTreeMap::new();
    for node in nodes {
        let identifier = node["id"]
            .as_str()
            .ok_or("literal family node identity required")?;
        if node.as_object().map(|fields| fields.len()) != Some(3)
            || actual
                .insert(
                    identifier.to_owned(),
                    json!({"kind":node["kind"],"spec":node["spec"]}),
                )
                .is_some()
        {
            return Err("exact unique family node contract required".into());
        }
    }
    if nodes.len() != 13 || actual != expected {
        return Err("exact thirteen-node frozen complete-family graph required".into());
    }
    let mut expected_edges = std::collections::BTreeSet::new();
    for index in 0..9_u8 {
        expected_edges.insert((format!("source{index}"), 0_u8, "assemble".to_owned(), index));
    }
    expected_edges.insert(("request".into(), 0, "assemble".into(), 9));
    for (source, from_port, to_port) in [
        ("assemble", 1, 0),
        ("assemble", 0, 1),
        ("assemble", 2, 2),
        ("source8", 0, 3),
    ] {
        expected_edges.insert((source.into(), from_port, "adjust".into(), to_port));
    }
    for (source, from_port, to_port) in [
        ("assemble", 0, 0),
        ("assemble", 1, 1),
        ("assemble", 2, 2),
        ("adjust", 0, 3),
        ("adjust", 1, 4),
        ("adjust", 2, 5),
        ("source0", 0, 6),
        ("source1", 0, 7),
    ] {
        expected_edges.insert((source.into(), from_port, "publish".into(), to_port));
    }
    let edges = job["edges"].as_array().ok_or("family edges required")?;
    let mut actual_edges = std::collections::BTreeSet::new();
    for edge in edges {
        if edge.as_object().map(|fields| fields.len()) != Some(4) {
            return Err("only exact family port binding fields allowed".into());
        }
        actual_edges.insert((
            edge["from"]
                .as_str()
                .ok_or("family source required")?
                .to_owned(),
            u8::try_from(
                edge["from_port"]
                    .as_u64()
                    .ok_or("family source port required")?,
            )?,
            edge["to"]
                .as_str()
                .ok_or("family target required")?
                .to_owned(),
            u8::try_from(
                edge["to_port"]
                    .as_u64()
                    .ok_or("family target port required")?,
            )?,
        ));
    }
    if edges.len() != 22 || actual_edges != expected_edges {
        return Err("exact unique twenty-two frozen family edges required".into());
    }
    Ok(())
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct FamilyEdge {
    analysis_id: String,
    family_id: String,
    scope: String,
    scenario: String,
    overlap_class: String,
    usual_eligible: bool,
    mrlap_eligible: bool,
    ivw_p: Value,
    mrlap_p: Value,
}

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct FamilyRequest {
    schema: String,
    scope: String,
    scenario: String,
    edges: Vec<FamilyEdge>,
}

fn validate_family_request(
    request: &FamilyRequest,
    scenario: &str,
) -> Result<(), Box<dyn std::error::Error>> {
    let ledger = scenario == "REAL_FROZEN_NA_LEDGER";
    let expected_scope = if ledger {
        "FROZEN_LEDGER_MECHANICAL_ONLY_NOT_RESEARCH"
    } else {
        "SYNTHETIC_NOT_RESEARCH"
    };
    if !matches!(scenario, "BOUNDARY" | "INTERIOR" | "REAL_FROZEN_NA_LEDGER")
        || request.schema != "FROZEN_A_FAMILY_TECHNICAL_REQUEST_V1"
        || request.scope != expected_scope
        || request.scenario != scenario
        || (ledger && !request.edges.is_empty())
        || (!ledger && request.edges.len() != 276)
    {
        return Err(
            "exact technical family request scope, case and complete edge inventory required"
                .into(),
        );
    }
    let mut ids = std::collections::BTreeSet::new();
    for edge in &request.edges {
        if edge.analysis_id.is_empty()
            || !ids.insert(&edge.analysis_id)
            || !matches!(
                edge.family_id.as_str(),
                "A_PRIMARY_EDGES" | "A_EXPANDED_EDGES"
            )
            || edge.scope != expected_scope
            || edge.scenario != scenario
            || !matches!(edge.overlap_class.as_str(), "O0" | "O1" | "O2" | "O3")
            || [&edge.ivw_p, &edge.mrlap_p].iter().any(|value| {
                !value.is_null()
                    && !value
                        .as_f64()
                        .is_some_and(|number| number.is_finite() && (0.0..=1.0).contains(&number))
            })
        {
            return Err(
                "literal complete synthetic request rows without scientific authority required"
                    .into(),
            );
        }
        let _qualification_literals = (edge.usual_eligible, edge.mrlap_eligible);
    }
    Ok(())
}

fn validate_fixture_root(
    root: &std::path::Path,
    permanent: &std::path::Path,
    temporary: &std::path::Path,
    a_family: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    if !root.is_absolute()
        || root
            .components()
            .any(|component| matches!(component, std::path::Component::ParentDir))
        || !permanent.is_absolute()
        || (a_family
            && (!temporary.is_absolute()
                || root == temporary
                || !root.starts_with(temporary)
                || root.starts_with(permanent)))
        || (!a_family && !root.starts_with(permanent))
    {
        return Err("scope-bound managed fixture root required".into());
    }
    Ok(())
}

fn family_source_facts(
    root: &std::path::Path,
    job: &Value,
) -> Result<Value, Box<dyn std::error::Error>> {
    use std::os::unix::fs::MetadataExt;
    if root.canonicalize()? != root || root.symlink_metadata()?.file_type().is_symlink() {
        return Err("ordinary owned family fixture root required".into());
    }
    let owner = root.metadata()?.uid();
    let mut identities = Vec::new();
    for (index, (expected_bytes, expected_sha)) in FAMILY_SOURCES.iter().enumerate() {
        let path = root.join(format!("source{index}.input"));
        let before = path.symlink_metadata()?;
        if !before.is_file() || before.uid() != owner || before.len() != *expected_bytes {
            return Err("ordinary owned frozen family source with exact size required".into());
        }
        let bytes = std::fs::read(&path)?;
        let checksum = format!("{:x}", Sha256::digest(&bytes));
        let after = path.symlink_metadata()?;
        let metadata = |information: &std::fs::Metadata| {
            (
                information.dev(),
                information.ino(),
                information.uid(),
                information.len(),
                information.mtime(),
                information.mtime_nsec(),
                information.ctime(),
                information.ctime_nsec(),
            )
        };
        if checksum != *expected_sha
            || bytes.len() as u64 != *expected_bytes
            || metadata(&before) != metadata(&after)
        {
            return Err("frozen family source bytes or identity changed".into());
        }
        identities.push(
            json!({"port":index,"filename":format!("source{index}.input"),"bytes":bytes.len(),
            "sha256":checksum,"device":after.dev(),"inode":after.ino(),"owner":after.uid(),
            "mtime":after.mtime(),"mtime_nsec":after.mtime_nsec(),
            "ctime":after.ctime(),"ctime_nsec":after.ctime_nsec()}),
        );
    }
    let request_path = root.join("request.json");
    let request_info = request_path.symlink_metadata()?;
    if !request_info.is_file() || request_info.uid() != owner || request_info.len() > 1024 * 1024 {
        return Err("ordinary bounded technical request required".into());
    }
    let request_bytes = std::fs::read(&request_path)?;
    let request: FamilyRequest = serde_json::from_slice(&request_bytes)?;
    validate_family_request(
        &request,
        job["family_case"].as_str().ok_or("family case required")?,
    )?;
    let request_after = request_path.symlink_metadata()?;
    if request_info.dev() != request_after.dev()
        || request_info.ino() != request_after.ino()
        || request_info.uid() != request_after.uid()
        || request_info.len() != request_after.len()
        || request_info.mtime() != request_after.mtime()
        || request_info.mtime_nsec() != request_after.mtime_nsec()
        || request_info.ctime() != request_after.ctime()
        || request_info.ctime_nsec() != request_after.ctime_nsec()
    {
        return Err("technical request changed while reading".into());
    }
    Ok(
        json!({"case":request.scenario,"request_scope":request.scope,"source_files":identities,
        "request_sha256":format!("{:x}",Sha256::digest(&request_bytes)),"request_bytes":request_bytes.len(),
        "request_device":request_after.dev(),"request_inode":request_after.ino(),"request_owner":request_after.uid(),
        "request_mtime":request_after.mtime(),"request_mtime_nsec":request_after.mtime_nsec(),
        "request_ctime":request_after.ctime(),"request_ctime_nsec":request_after.ctime_nsec(),
        "real_overlap_classes_assigned":false,"scientific_authorization_granted":false,"g0_granted":false}),
    )
}

fn validate_family_manifest(
    manifest: &PluginManifest,
    pins: &FamilyPins,
    python: bool,
) -> Result<(), Box<dyn std::error::Error>> {
    checked_family_pins(pins)?;
    let (name, image, expected): (&str, &str, std::collections::BTreeSet<&str>) = if python {
        (
            "frozen-a-family-assembly",
            &pins.python_image,
            std::collections::BTreeSet::from([
                "frozen_a_family_assemble",
                "frozen_a_family_publish",
            ]),
        )
    } else {
        (
            "frozen-a-family-adjustment",
            &pins.r_image,
            std::collections::BTreeSet::from(["frozen_a_family_adjust"]),
        )
    };
    let kinds = manifest
        .nodes
        .iter()
        .map(|node| node.kind.as_str())
        .collect::<std::collections::BTreeSet<_>>();
    if manifest.plugin_name != name
        || manifest.image.reference.as_str() != image
        || !manifest.panels.is_empty()
        || manifest.nodes.len() != expected.len()
        || kinds != expected
    {
        return Err(
            "actual frozen family manifest, kinds, image and panel absence required".into(),
        );
    }
    Ok(())
}

fn transport_mode(job: &Value) -> Result<bool, Box<dyn std::error::Error>> {
    if job["scope"] == CONNECTED_SCOPE {
        validate_connected_job_with_pins(job, &connected_plugin_pins())?;
        return Ok(true);
    }
    reject_family_other_scope(job)?;
    if job["scope"] == FAMILY_SCOPE {
        validate_family_job_with_pins(job, &family_pins()?)?;
        return Ok(true);
    }
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
    let kinds = kinds.into_iter().collect::<Vec<_>>();
    if job["scope"] != CONNECTED_SCOPE && kinds.contains(&"frozen_a_legacy_family_gate") {
        return Err("legacy family gate cannot be registered outside connected scope".into());
    }
    if job["scope"] != FAMILY_SCOPE && job["scope"] != CONNECTED_SCOPE && kinds.iter().any(|kind| family_kind(kind)) {
        return Err(
            "complete frozen A kinds cannot be registered outside their dedicated scope".into(),
        );
    }
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
    let a_connected = job["scope"] == CONNECTED_SCOPE;
    let a_raw = job["scope"] == A_RAW_SCOPE || a_connected;
    let a_family = job["scope"] == FAMILY_SCOPE;
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
    let temporary = PathBuf::from(std::env::var("TMPDIR")?);
    validate_fixture_root(&root, &permanent, &temporary, a_family || a_connected)?;
    validate_fixture_root(
        &root.canonicalize()?,
        &permanent.canonicalize()?,
        &temporary.canonicalize()?,
        a_family || a_connected,
    )?;
    if !root.is_absolute()
        || root.join("artifacts").exists()
        || root.join("materialized.tsv").exists()
    {
        return Err("new owned technical fixture root required".into());
    }
    let original_connected_sources = if a_connected { Some(connected_source_facts()?) } else { None };
    let original_family_sources = if a_family {
        Some(family_source_facts(&root, &job)?)
    } else {
        None
    };
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
    if a_family {
        validate_family_manifest(&manifest, &family_pins()?, true)?;
    }
    if a_connected { validate_connected_manifest(&manifest)?; }
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
            if a_family {
                validate_family_manifest(&extra, &family_pins()?, false)?;
            }
            if a_connected { validate_connected_manifest(&extra)?; }
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
            "family_case":job.get("family_case"),"frozen_family_source_facts":original_family_sources,"connected_source_facts":original_connected_sources,
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
    if a_connected {
        for (port, filename) in connected_source_paths().iter().enumerate().skip(9) {
            mounts.mount.push(MountDefinition {
                path: format!("/connected-inputs/{port}"), backend: "technical".into(),
                source: std::path::Path::new(filename).parent().ok_or("canonical connected parent required")?.to_string_lossy().into_owned(),
                read_only: true, permissions: Default::default(),
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
    let final_family_sources = if a_family {
        Some(family_source_facts(&root, &job)?)
    } else {
        None
    };
    if original_family_sources != final_family_sources {
        return Err("frozen family sources or technical request changed during DAG".into());
    }
    let final_connected_sources = if a_connected { Some(connected_source_facts()?) } else { None };
    if original_connected_sources != final_connected_sources {
        return Err("canonical connected sources changed during technical DAG".into());
    }
    let evidence = json!({
        "scope": if a_connected { "REAL_LOCKED_A_LEGACY_CONNECTED_O2_PRIMARY_NA_TECHNICAL_NOT_G0" } else if a_family { "LOCKED_COMPLETE_A_FAMILY_TECHNICAL_NO_MR" } else if full_replay { "REAL_LOCKED_LEGACY_THREE_MODEL_TECHNICAL_REPLAY" } else if a_harmonisation { "REAL_LOCKED_LEGACY_A_HARMONISATION_NO_FIT" } else if a_raw { "REAL_LOCKED_LEGACY_A_RAW_QC_LD_NO_MR" } else if real_transport { "REAL_LOCKED_LEGACY_TRANSPORT_NO_FIT" } else { "TECHNICAL_PLUGIN_DAG_NOT_G0" },
        "source_integrity_proof": source_proof,
        "operator_authorization": authorization,
        "real_locked_legacy_transport_no_fit": real_transport && !full_replay && !a_family && !a_connected,
        "family_case":job.get("family_case"),
        "frozen_family_source_facts_before":original_family_sources,
        "frozen_family_source_facts_after":final_family_sources,
        "real_overlap_classes_assigned":false,
        "mr_computed":a_connected,
        "connected_source_facts_before":original_connected_sources,
        "connected_source_facts_after":final_connected_sources,
        "connected_primary_p_remains_missing":a_connected,
        "explicit_replay_scope_allows_fit": full_replay || a_connected,
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
        "effective_synthetic_manifest_sha256": if a_raw || a_family { None } else { Some(format!("{:x}", Sha256::digest(&synthetic_manifest_bytes))) },
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

#[cfg(test)]
mod family_tests {
    use super::*;

    #[test]
    fn family_sources_require_managed_temporary_root_not_permanent_evidence() {
        let permanent = std::path::Path::new("/managed/permanent");
        let temporary = std::path::Path::new("/managed/tmp");
        assert!(
            validate_fixture_root(
                std::path::Path::new("/managed/tmp/case"),
                permanent,
                temporary,
                true
            )
            .is_ok()
        );
        for path in [
            "/managed/permanent/case",
            "/managed/tmp",
            "/managed/tmp-other/case",
            "/other/case",
            "relative/case",
            "/managed/tmp/../foreign",
        ] {
            assert!(
                validate_fixture_root(std::path::Path::new(path), permanent, temporary, true)
                    .is_err(),
                "{path}"
            );
        }
    }

    #[test]
    fn other_scopes_do_not_gain_temporary_fixture_root_permission() {
        let permanent = std::path::Path::new("/managed/permanent");
        let temporary = std::path::Path::new("/managed/tmp");
        assert!(
            validate_fixture_root(
                std::path::Path::new("/managed/permanent/case"),
                permanent,
                temporary,
                false
            )
            .is_ok()
        );
        assert!(
            validate_fixture_root(
                std::path::Path::new("/managed/tmp/case"),
                permanent,
                temporary,
                false
            )
            .is_err()
        );
    }

    fn pins() -> FamilyPins {
        FamilyPins {
            python_manifest: "a".repeat(64),
            python_script: "b".repeat(64),
            r_manifest: "c".repeat(64),
            r_script: "d".repeat(64),
            python_image: format!("registry/python@sha256:{}", "e".repeat(64)),
            r_image: format!("registry/r@sha256:{}", "f".repeat(64)),
        }
    }

    fn job() -> Value {
        let identities = pins();
        let mut nodes = Vec::new();
        let mut edges = Vec::new();
        for index in 0..9 {
            nodes.push(
                json!({"id":format!("source{index}"),"kind":"file_reference","spec":{
                "path":format!("vfs:///source{index}.input"),"format":"file","hash_content":true}}),
            );
            edges.push(json!({"from":format!("source{index}"),"from_port":0,"to":"assemble","to_port":index}));
        }
        nodes.push(json!({"id":"request","kind":"file_reference","spec":{
            "path":"vfs:///request.json","format":"file","hash_content":true}}));
        edges.push(json!({"from":"request","from_port":0,"to":"assemble","to_port":9}));
        for (identifier, kind) in [
            ("assemble", "frozen_a_family_assemble"),
            ("adjust", "frozen_a_family_adjust"),
            ("publish", "frozen_a_family_publish"),
        ] {
            nodes.push(json!({"id":identifier,"kind":kind,"spec":{}}));
        }
        for (source, from_port, to_port) in [
            ("assemble", 1, 0),
            ("assemble", 0, 1),
            ("assemble", 2, 2),
            ("source8", 0, 3),
        ] {
            edges
                .push(json!({"from":source,"from_port":from_port,"to":"adjust","to_port":to_port}));
        }
        for (source, from_port, to_port) in [
            ("assemble", 0, 0),
            ("assemble", 1, 1),
            ("assemble", 2, 2),
            ("adjust", 0, 3),
            ("adjust", 1, 4),
            ("adjust", 2, 5),
            ("source0", 0, 6),
            ("source1", 0, 7),
        ] {
            edges.push(
                json!({"from":source,"from_port":from_port,"to":"publish","to_port":to_port}),
            );
        }
        json!({"scope":FAMILY_SCOPE,"family_case":"BOUNDARY","run_root":"/owned/synthetic-fixture",
            "plugin_manifest":"python/manifest.toml","expected_plugin_name":"frozen-a-family-assembly",
            "plugin_manifest_sha256":identities.python_manifest,
            "script_sha256":{"scripts/family.py":identities.python_script},
            "panel_overrides":[],"panel_manifest_sha256":{},"bundles":[],
            "additional_plugins":[{"plugin_manifest":"r/manifest.toml",
                "expected_plugin_name":"frozen-a-family-adjustment",
                "plugin_manifest_sha256":identities.r_manifest,
                "script_sha256":{"scripts/adjust.R":identities.r_script},"panel_overrides":[]}],
            "nodes":nodes,"edges":edges})
    }

    fn request(scenario: &str) -> Value {
        let ledger = scenario == "REAL_FROZEN_NA_LEDGER";
        let scope = if ledger {
            "FROZEN_LEDGER_MECHANICAL_ONLY_NOT_RESEARCH"
        } else {
            "SYNTHETIC_NOT_RESEARCH"
        };
        let edges = if ledger {
            Vec::new()
        } else {
            (0..276)
                .map(|index| {
                    json!({
                        "analysis_id":format!("SYNTHETIC_{index}"),
                        "family_id":if index<88 {"A_PRIMARY_EDGES"} else {"A_EXPANDED_EDGES"},
                        "scope":scope,"scenario":scenario,"overlap_class":"O1",
                        "usual_eligible":true,"mrlap_eligible":false,
                        "ivw_p":0.001,"mrlap_p":null
                    })
                })
                .collect()
        };
        json!({"schema":"FROZEN_A_FAMILY_TECHNICAL_REQUEST_V1",
            "scope":scope,"scenario":scenario,"edges":edges})
    }

    fn validate_request(value: &Value, scenario: &str) -> bool {
        serde_json::from_value::<FamilyRequest>(value.clone())
            .ok()
            .is_some_and(|request| validate_family_request(&request, scenario).is_ok())
    }

    fn manifest(python: bool) -> PluginManifest {
        let identities = pins();
        let (name, image, kinds) = if python {
            (
                "frozen-a-family-assembly",
                identities.python_image,
                vec!["frozen_a_family_assemble", "frozen_a_family_publish"],
            )
        } else {
            (
                "frozen-a-family-adjustment",
                identities.r_image,
                vec!["frozen_a_family_adjust"],
            )
        };
        let mut text =
            format!("schema_version=1\nplugin_name={name:?}\n[image]\nreference={image:?}\n");
        for kind in kinds {
            text.push_str(&format!("[[nodes]]\nkind={kind:?}\ndesc=\"synthetic guard fixture\"\ndoc=\"synthetic guard fixture\"\n[nodes.command]\ninterpreter=\"python3\"\nscript=\"pass\"\n[nodes.ports]\ninputs=[]\noutputs=[]\n"));
        }
        toml::from_str(&text).unwrap()
    }

    #[test]
    fn exact_thirteen_nodes_twenty_two_edges_accept_all_three_cases() {
        for scenario in ["BOUNDARY", "INTERIOR", "REAL_FROZEN_NA_LEDGER"] {
            let mut value = job();
            value["family_case"] = json!(scenario);
            assert!(validate_family_job_with_pins(&value, &pins()).is_ok());
        }
    }

    #[test]
    fn pending_identity_never_authorizes_a_family() {
        let mut identities = pins();
        identities.python_script = "PENDING".into();
        assert!(checked_family_pins(&identities).is_err());
        identities = pins();
        identities.r_image = "registry/r:mutable".into();
        assert!(checked_family_pins(&identities).is_err());
    }

    #[test]
    fn source_reference_path_format_and_content_hash_are_exact() {
        for (field, replacement) in [
            ("path", json!("vfs:///other.input")),
            ("format", json!("tsv")),
            ("hash_content", json!(false)),
        ] {
            let mut value = job();
            value["nodes"][0]["spec"][field] = replacement;
            assert!(validate_family_job_with_pins(&value, &pins()).is_err());
        }
        let mut value = job();
        value["nodes"][0]["id"] = json!("renamed");
        assert!(validate_family_job_with_pins(&value, &pins()).is_err());
    }

    #[test]
    fn missing_duplicate_and_rewired_edges_are_rejected() {
        let mut value = job();
        value["edges"].as_array_mut().unwrap().pop();
        assert!(validate_family_job_with_pins(&value, &pins()).is_err());
        let mut value = job();
        value["edges"][21] = value["edges"][20].clone();
        assert!(validate_family_job_with_pins(&value, &pins()).is_err());
        let mut value = job();
        value["edges"][10]["from_port"] = json!(0);
        assert!(validate_family_job_with_pins(&value, &pins()).is_err());
        let mut value = job();
        value["edges"][0]["to_port"] = json!(true);
        assert!(validate_family_job_with_pins(&value, &pins()).is_err());
    }

    #[test]
    fn fit_sql_parameters_extra_and_duplicate_nodes_are_rejected() {
        for kind in ["twosamplemr", "frozen_b_legacy_limma", "datafusion_sql"] {
            let mut value = job();
            value["nodes"][11]["kind"] = json!(kind);
            assert!(validate_family_job_with_pins(&value, &pins()).is_err());
        }
        let mut value = job();
        value["nodes"][10]["spec"] = json!({"method":"BH"});
        assert!(validate_family_job_with_pins(&value, &pins()).is_err());
        let mut value = job();
        value["nodes"]
            .as_array_mut()
            .unwrap()
            .push(json!({"id":"extra","kind":"file_reference","spec":{}}));
        assert!(validate_family_job_with_pins(&value, &pins()).is_err());
        let mut value = job();
        value["nodes"][12] = value["nodes"][11].clone();
        assert!(validate_family_job_with_pins(&value, &pins()).is_err());
    }

    #[test]
    fn plugin_manifest_script_name_and_additional_family_are_pinned() {
        for (field, replacement) in [
            ("expected_plugin_name", json!("renamed")),
            ("plugin_manifest_sha256", json!("0".repeat(64))),
            ("script_sha256", json!({"scripts/other.py":"b".repeat(64)})),
            ("family_case", json!("REAL_RESEARCH")),
        ] {
            let mut value = job();
            value[field] = replacement;
            assert!(validate_family_job_with_pins(&value, &pins()).is_err());
        }
        for (field, replacement) in [
            ("expected_plugin_name", json!("other")),
            ("plugin_manifest_sha256", json!("0".repeat(64))),
            ("script_sha256", json!({"scripts/adjust.R":"0".repeat(64)})),
        ] {
            let mut value = job();
            value["additional_plugins"][0][field] = replacement;
            assert!(validate_family_job_with_pins(&value, &pins()).is_err());
        }
        let mut value = job();
        value["additional_plugins"]
            .as_array_mut()
            .unwrap()
            .push(json!({}));
        assert!(validate_family_job_with_pins(&value, &pins()).is_err());
    }

    #[test]
    fn panels_bundles_and_extra_authority_are_rejected() {
        for (field, replacement) in [
            ("panel_overrides", json!([{}])),
            ("panel_manifest_sha256", json!({"fake":"0".repeat(64)})),
            ("bundles", json!([{}])),
        ] {
            let mut value = job();
            value[field] = replacement;
            assert!(validate_family_job_with_pins(&value, &pins()).is_err());
        }
        let mut value = job();
        value["additional_plugins"][0]["scientific_authorized"] = json!(true);
        assert!(validate_family_job_with_pins(&value, &pins()).is_err());
        let mut value = job();
        value["scientific_authorized"] = json!(true);
        assert!(validate_family_job_with_pins(&value, &pins()).is_err());
    }

    #[test]
    fn dedicated_families_and_loaded_kinds_cannot_use_other_scopes() {
        for scope in [
            "SYNTHETIC_PLUGIN_TEST_NOT_G0",
            TRANSPORT_SCOPE,
            REPLAY_SCOPE,
            A_RAW_SCOPE,
            A_HARMONISATION_SCOPE,
        ] {
            let mut value = job();
            value["scope"] = json!(scope);
            assert!(reject_family_other_scope(&value).is_err());
            value["expected_plugin_name"] = json!("renamed");
            value["additional_plugins"] = json!([]);
            value["nodes"] = json!([]);
            assert!(validate_synthetic_kinds(&value, ["frozen_a_family_publish"]).is_err());
        }
    }

    #[test]
    fn actual_manifest_family_kind_and_immutable_image_are_checked() {
        let identities = pins();
        assert!(validate_family_manifest(&manifest(true), &identities, true).is_ok());
        assert!(validate_family_manifest(&manifest(false), &identities, false).is_ok());
        let mut value = manifest(true);
        value.image.reference = container_runtime::image::ImageReference::parse(
            "registry/wrong@sha256:1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        )
        .unwrap();
        assert!(validate_family_manifest(&value, &identities, true).is_err());
        let mut value = manifest(true);
        value.nodes[0].kind = "fit".into();
        assert!(validate_family_manifest(&value, &identities, true).is_err());
        let mut value = manifest(false);
        value.plugin_name = "renamed".into();
        assert!(validate_family_manifest(&value, &identities, false).is_err());
    }

    #[test]
    fn technical_requests_accept_literal_complete_synthetic_or_empty_ledger_only() {
        for scenario in ["BOUNDARY", "INTERIOR", "REAL_FROZEN_NA_LEDGER"] {
            assert!(validate_request(&request(scenario), scenario));
        }
        let mut value = request("REAL_FROZEN_NA_LEDGER");
        value["edges"] = request("BOUNDARY")["edges"].clone();
        assert!(!validate_request(&value, "REAL_FROZEN_NA_LEDGER"));
        assert!(!validate_request(&request("BOUNDARY"), "INTERIOR"));
    }

    #[test]
    fn request_schema_missing_duplicate_and_unknown_fields_are_rejected() {
        let mut value = request("BOUNDARY");
        value["authority"] = json!(true);
        assert!(!validate_request(&value, "BOUNDARY"));
        let mut value = request("BOUNDARY");
        value["edges"][0].as_object_mut().unwrap().remove("ivw_p");
        assert!(!validate_request(&value, "BOUNDARY"));
        let mut value = request("BOUNDARY");
        value["edges"][0]["scientific_pass"] = json!(true);
        assert!(!validate_request(&value, "BOUNDARY"));
        assert!(serde_json::from_str::<FamilyRequest>(
            "{\"schema\":\"FROZEN_A_FAMILY_TECHNICAL_REQUEST_V1\",\"scope\":\"a\",\"scope\":\"b\",\"scenario\":\"BOUNDARY\",\"edges\":[]}").is_err());
    }

    #[test]
    fn request_incomplete_ids_invalid_probabilities_and_scientific_scope_are_rejected() {
        let mut value = request("BOUNDARY");
        value["edges"].as_array_mut().unwrap().pop();
        assert!(!validate_request(&value, "BOUNDARY"));
        for (field, replacement) in [
            ("analysis_id", json!("SYNTHETIC_1")),
            ("scope", json!("SCIENTIFIC_CONFIRMED")),
            ("overlap_class", json!("PENDING")),
            ("usual_eligible", json!(1)),
            ("ivw_p", json!(true)),
            ("mrlap_p", json!(-0.01)),
            ("mrlap_p", json!(1.01)),
        ] {
            let mut value = request("BOUNDARY");
            value["edges"][0][field] = replacement;
            assert!(!validate_request(&value, "BOUNDARY"), "{field}");
        }
    }
}

const CONNECTED_SCOPE: &str = "LOCKED_A_LEGACY_CONNECTED_TECHNICAL_O2_PRIMARY_NA_NOT_G0";
const CONNECTED_GATE_MANIFEST: &str = "f07cd4c67cd01037dc9285670fcf3ec021990a4e2e0ebe356a601358e24bf1c1";
const CONNECTED_GATE_SCRIPT: &str = "6c921c4ed2cfece1bc56031a0a40b83c1c1efbdd643d6e32f370ee851da42537";
const CONNECTED_STUDY: &str = "/home/zj-normal/Work/BONE_MARROW_CACHEXIA/versions/v4.3.2/bm_cachexia_v432_g0";
const CONNECTED_REPOSITORY: &str = "/home/zj-normal/Work/autonomics-plugins";

#[derive(Clone)]
struct ConnectedPluginPin {
    manifest: String,
    script: String,
    script_path: String,
    image: String,
    kinds: Vec<String>,
}

fn connected_plugin_pins() -> BTreeMap<String, ConnectedPluginPin> {
    [
        ("frozen-a-input-qualification", A_RAW_MANIFEST, "scripts/qualify.py", A_RAW_SCRIPT,
            FAMILY_PYTHON_IMAGE, vec!["frozen_a_v432_input_qualification"]),
        ("frozen-a-harmonisation", A_HARMONISATION_MANIFEST, "scripts/harmonise.R", A_HARMONISATION_SCRIPT,
            FAMILY_R_IMAGE, vec!["frozen_a_v432_harmonisation"]),
        ("twosamplemr-v432-a", "661e12b231f7b38540d5cba2fca8a31ee3d5d0831305998f00fa0e898d980324", "scripts/mr.R",
            "33009c9f40ca8964b4aa6e5729eff1856913838dce35679e5169eab4ed3595fe", FAMILY_R_IMAGE,
            vec!["twosamplemr_v432_a_exploratory"]),
        ("frozen-a-legacy-family-gate", CONNECTED_GATE_MANIFEST, "scripts/gate.py", CONNECTED_GATE_SCRIPT,
            FAMILY_PYTHON_IMAGE, vec!["frozen_a_legacy_family_gate"]),
        ("frozen-a-family-assembly", FAMILY_PYTHON_MANIFEST, "scripts/family.py", FAMILY_PYTHON_SCRIPT,
            FAMILY_PYTHON_IMAGE, vec!["frozen_a_family_assemble", "frozen_a_family_publish"]),
        ("frozen-a-family-adjustment", FAMILY_R_MANIFEST, "scripts/adjust.R", FAMILY_R_SCRIPT,
            FAMILY_R_IMAGE, vec!["frozen_a_family_adjust"]),
    ].into_iter().map(|(name, manifest, path, script, image, kinds)| (name.into(), ConnectedPluginPin {
        manifest: manifest.into(), script: script.into(), script_path: path.into(), image: image.into(),
        kinds: kinds.into_iter().map(str::to_owned).collect(),
    })).collect()
}

fn checked_connected_pins(pins: &BTreeMap<String, ConnectedPluginPin>) -> Result<(), Box<dyn std::error::Error>> {
    let expected = connected_plugin_pins();
    if pins.keys().collect::<Vec<_>>() != expected.keys().collect::<Vec<_>>() || pins.values().any(|pin|
        !family_hash(&pin.manifest) || !family_hash(&pin.script) || !family_image(&pin.image)) {
        return Err("connected plugin identities are PENDING or invalid; execution unavailable".into());
    }
    Ok(())
}

fn connected_source_paths() -> Vec<String> {
    let mut paths = A_RAW_SOURCE_FILES.iter().map(|value| (*value).to_owned()).collect::<Vec<_>>();
    paths.push(format!("{CONNECTED_STUDY}/03_AUDIT/G0_v4.3.2_2026-10-11/R_DEPENDENCY_LOCK.tsv"));
    paths.push(format!("{CONNECTED_REPOSITORY}/plugins/twosamplemr-v432-a/contracts/frozen-method-proof.json"));
    for relative in ["01_REGISTRIES/GENETIC_EDGE_UNIVERSE.tsv", "01_REGISTRIES/GENETIC_PATH_UNIVERSE.tsv",
        "01_REGISTRIES/G0_LOCKED_HYPOTHESIS_UNIVERSE.tsv", "01_REGISTRIES/PRIMARY_P_DECISION_REGISTER.tsv",
        "01_REGISTRIES/FAMILY_LOCK_REGISTER.tsv", "01_REGISTRIES/MULTIPLICITY_REGISTER.tsv",
        "02_EXECUTION/EXECUTION_RULES_v4.3.2.json", "02_EXECUTION/execution_utils.py", "02_EXECUTION/g0_v432_methods.R"] {
        paths.push(format!("{CONNECTED_STUDY}/{relative}"));
    }
    paths.push(format!("{CONNECTED_REPOSITORY}/research-adapters/frozen-a-family-assembly/scripts/family.py"));
    paths
}

fn connected_source_path(port: usize) -> String {
    let paths = connected_source_paths();
    let name = std::path::Path::new(&paths[port]).file_name().unwrap().to_str().unwrap();
    if port < 9 { a_raw_source_path(port) } else { format!("/connected-inputs/{port}/{name}") }
}

fn connected_edges() -> std::collections::BTreeSet<(String, u8, String, u8)> {
    let mut edges = std::collections::BTreeSet::new();
    let mut bind = |source: String, from: u8, target: &str, to: u8| { edges.insert((source, from, target.to_owned(), to)); };
    for port in 0..9_u8 { bind(format!("source{port}"), 0, "raw", port); }
    for (source, from, to) in [("raw",5,0),("raw",3,1),("source2",0,2),("source3",0,3),("source9",0,4),("source19",0,5)] {
        bind(source.into(), from, "harmonise", to);
    }
    for (source, from, to) in [("harmonise",1,0),("source2",0,1),("source3",0,2),("source9",0,3),("source10",0,4)] {
        bind(source.into(), from, "mr", to);
    }
    for port in 0..9_u8 { bind("mr".into(), port, "gate", port); }
    for (source, port) in [(2,9),(3,10),(9,11),(10,12)] { bind(format!("source{source}"), 0, "gate", port); }
    for index in 0..9_u8 {
        bind(format!("source{}", index+11), 0, "gate", index+13);
        bind(format!("source{}", index+11), 0, "assemble", index);
    }
    bind("source20".into(), 0, "gate", 22);
    bind("gate".into(), 0, "assemble", 9);
    for (source, from, to) in [("assemble",1,0),("assemble",0,1),("assemble",2,2),("source19",0,3)] { bind(source.into(), from, "adjust", to); }
    for (source, from, to) in [("assemble",0,0),("assemble",1,1),("assemble",2,2),("adjust",0,3),("adjust",1,4),("adjust",2,5),("source11",0,6),("source12",0,7)] { bind(source.into(), from, "publish", to); }
    edges
}

fn connected_nodes() -> BTreeMap<String, Value> {
    let mut nodes = (0..21).map(|port| (format!("source{port}"), json!({"kind":"file_reference","spec":{
        "path":format!("vfs://{}", connected_source_path(port)),"format":"file","hash_content":true}}))).collect::<BTreeMap<_,_>>();
    for (name, kind) in [("raw","frozen_a_v432_input_qualification"),("harmonise","frozen_a_v432_harmonisation"),
        ("mr","twosamplemr_v432_a_exploratory"),("gate","frozen_a_legacy_family_gate"),("assemble","frozen_a_family_assemble"),
        ("adjust","frozen_a_family_adjust"),("publish","frozen_a_family_publish")] { nodes.insert(name.into(), json!({"kind":kind,"spec":{}})); }
    nodes
}

fn validate_connected_job_with_pins(job: &Value, pins: &BTreeMap<String, ConnectedPluginPin>) -> Result<(), Box<dyn std::error::Error>> {
    checked_connected_pins(pins)?;
    let fields = ["scope","run_root","plugin_manifest","expected_plugin_name","plugin_manifest_sha256","script_sha256",
        "panel_overrides","panel_manifest_sha256","bundles","locked_panel_source","additional_plugins","nodes","edges"];
    if !job.as_object().is_some_and(|record| record.len()==fields.len() && record.keys().all(|key| fields.contains(&key.as_str())))
        || job["scope"] != CONNECTED_SCOPE || !job["run_root"].is_string()
        || job["panel_overrides"] != json!([]) || job["panel_manifest_sha256"] != json!({A_RAW_PANEL_VPATH:A_RAW_PANEL_SHA})
        || job["bundles"] != json!([a_raw_bundle()]) || job["locked_panel_source"] != A_RAW_PANEL_HOST {
        return Err("exact connected legacy technical fields and original read-only panel required".into());
    }
    let check = |record: &Value, name: &str, primary: bool| -> Result<(), Box<dyn std::error::Error>> {
        let pin = pins.get(name).ok_or("unknown connected plugin")?;
        if !record["plugin_manifest"].as_str().is_some_and(|path| {
            let path = std::path::Path::new(path);
            path.is_absolute() && !path.components().any(|part| matches!(part,std::path::Component::ParentDir | std::path::Component::CurDir))
        }) || record["expected_plugin_name"] != name || record["plugin_manifest_sha256"] != pin.manifest
            || record["script_sha256"] != json!({(pin.script_path.clone()):pin.script.clone()}) || record["panel_overrides"] != json!([])
            || (!primary && record.as_object().map(|value| value.len()) != Some(5)) {
            return Err("exact connected plugin manifest and script identities required".into());
        }
        Ok(())
    };
    check(job,"frozen-a-input-qualification",true)?;
    let plugins = job["additional_plugins"].as_array().ok_or("five exact connected plugins required")?;
    let names = ["frozen-a-harmonisation","twosamplemr-v432-a","frozen-a-legacy-family-gate","frozen-a-family-assembly","frozen-a-family-adjustment"];
    if plugins.len()!=names.len() { return Err("five exact connected plugins required".into()); }
    for (record,name) in plugins.iter().zip(names) { check(record,name,false)?; }
    let records = job["nodes"].as_array().ok_or("exact connected nodes required")?;
    let mut actual = BTreeMap::new();
    for node in records {
        let name = node["id"].as_str().ok_or("literal connected node ID required")?;
        if node.as_object().map(|value| value.len())!=Some(3)
            || actual.insert(name.to_owned(),json!({"kind":node["kind"],"spec":node["spec"]})).is_some() {
            return Err("unique exact connected node fields required".into());
        }
    }
    if records.len()!=28 || actual!=connected_nodes() { return Err("exact 21 sources and seven connected methods required".into()); }
    let records = job["edges"].as_array().ok_or("exact connected edges required")?;
    let mut actual = std::collections::BTreeSet::new();
    for edge in records {
        if edge.as_object().map(|value| value.len())!=Some(4) { return Err("exact connected typed edge fields required".into()); }
        actual.insert((edge["from"].as_str().ok_or("literal connected source required")?.to_owned(),
            u8::try_from(edge["from_port"].as_u64().ok_or("literal connected source port required")?)?,
            edge["to"].as_str().ok_or("literal connected destination required")?.to_owned(),
            u8::try_from(edge["to_port"].as_u64().ok_or("literal connected target port required")?)?));
    }
    if records.len()!=65 || actual!=connected_edges() { return Err("exact 65 unique connected bindings including mandatory gate required".into()); }
    Ok(())
}

fn validate_connected_manifest(manifest: &PluginManifest) -> Result<(), Box<dyn std::error::Error>> {
    let pins = connected_plugin_pins();
    validate_connected_manifest_with_pins(manifest, &pins)
}

fn validate_connected_manifest_with_pins(manifest: &PluginManifest, pins: &BTreeMap<String, ConnectedPluginPin>) -> Result<(), Box<dyn std::error::Error>> {
    checked_connected_pins(pins)?;
    let pin = pins.get(&manifest.plugin_name).ok_or("unknown actual connected plugin")?;
    let kinds = manifest.nodes.iter().map(|node| node.kind.clone()).collect::<std::collections::BTreeSet<_>>();
    if manifest.image.reference.as_str()!=pin.image || manifest.nodes.len()!=pin.kinds.len()
        || kinds!=pin.kinds.iter().cloned().collect() || (manifest.plugin_name!="frozen-a-input-qualification" && !manifest.panels.is_empty()) {
        return Err("actual connected immutable image, complete kinds and absent extra panels required".into());
    }
    Ok(())
}

fn connected_source_facts() -> Result<Value, Box<dyn std::error::Error>> {
    use std::io::Read;
    use std::os::unix::fs::MetadataExt;
    let raw = [(242104432,"ed3b562cd73337e23d31c5facf8d2646eeb4399b14003513729f85743c5d4f16"),
        (2577239641,"8d0d508e5373af82839ed92a5dc9c175779ac2ad02dc8566c087b85ff77b568f"),
        (3499,"8ccb70529da5c4b8494e31cbbe45e62e1b333f603d19517b671671a2fafd404f"),
        (2324,"aa8905a9d830839e88d3da1081f50732f290fbd561a832ca2a6841ca364ecbb2"),
        (11745,"dfd51939dd2d7d6c5ed9322c047a86df0f65cbc0ac5522e69c008c8a698e9208"),
        (2841,"34ac788b92f17a8f2ce19596108eb8f7e5d1c21dbcf448b38e6c61e90dc3f7b0"),
        (41730792,"03ed6dd8882fddee7a89396c59ea56e4b17bbc4411d3049910e5d713fc8a135f"),
        (11272,A_RAW_PANEL_SHA),(2319,"3deee8b8e390fc1da21886c170241515889c06adab0cbe74bc31c9d5d87675d6")];
    let mut expected = raw.to_vec();
    expected.push((11542,"8aeaa7bb2b22b2c4ae9852dc65d32d4f81cb927d875ecdd135822f2f1c2b8a56"));
    expected.push((577,"a79c4469321bcef7ffabb9f94ad557ca185409bd9177868a3c158d8debb484c2"));
    expected.extend(FAMILY_SOURCES);
    expected.push((26620,FAMILY_PYTHON_SCRIPT));
    let mut records = Vec::new();
    for (index,(path,(length,hash))) in connected_source_paths().iter().zip(expected).enumerate() {
        let path = std::path::Path::new(path);
        if path.canonicalize()?!=path { return Err("canonical unaliased connected source required".into()); }
        let before = path.symlink_metadata()?;
        if !before.is_file() || before.file_type().is_symlink() || (length!=0 && before.len()!=length) { return Err("connected source size or type differs".into()); }
        let mut stream = std::fs::File::open(path)?;
        let mut digest = Sha256::new();
        let mut buffer = vec![0_u8;1024*1024];
        loop { let count = stream.read(&mut buffer)?; if count==0 { break; } digest.update(&buffer[..count]); }
        let checksum = format!("{:x}",digest.finalize());
        let after = path.symlink_metadata()?;
        let fact = |meta:&std::fs::Metadata| (meta.dev(),meta.ino(),meta.uid(),meta.gid(),meta.mode(),meta.len(),meta.mtime(),meta.mtime_nsec(),meta.ctime(),meta.ctime_nsec());
        if fact(&before)!=fact(&after) || checksum!=hash { return Err("connected source bytes or identity changed".into()); }
        records.push(json!({"source":format!("source{index}"),"path":path,"sha256":checksum,"bytes":after.len(),
            "device":after.dev(),"inode":after.ino(),"uid":after.uid(),"gid":after.gid(),"mode":after.mode(),
            "mtime":after.mtime(),"mtime_nsec":after.mtime_nsec(),"ctime":after.ctime(),"ctime_nsec":after.ctime_nsec()}));
    }
    Ok(json!(records))
}

#[cfg(test)]
mod connected_tests {
    use super::*;

    fn pins() -> BTreeMap<String, ConnectedPluginPin> {
        let mut pins = connected_plugin_pins();
        let gate = pins.get_mut("frozen-a-legacy-family-gate").unwrap();
        gate.manifest = "a".repeat(64);
        gate.script = "b".repeat(64);
        pins
    }

    fn plugin_record(name: &str, pins: &BTreeMap<String, ConnectedPluginPin>) -> Value {
        let pin = &pins[name];
        json!({"plugin_manifest":format!("/technical/source/{name}/manifest.toml"),
            "expected_plugin_name":name,"plugin_manifest_sha256":pin.manifest,
            "script_sha256":{(pin.script_path.clone()):pin.script.clone()},"panel_overrides":[]})
    }

    fn job() -> Value {
        let pins = pins();
        let mut value = plugin_record("frozen-a-input-qualification",&pins);
        value["scope"] = json!(CONNECTED_SCOPE);
        value["run_root"] = json!("/managed/tmp/connected-a");
        value["panel_manifest_sha256"] = json!({A_RAW_PANEL_VPATH:A_RAW_PANEL_SHA});
        value["bundles"] = json!([a_raw_bundle()]);
        value["locked_panel_source"] = json!(A_RAW_PANEL_HOST);
        value["additional_plugins"] = json!(["frozen-a-harmonisation","twosamplemr-v432-a","frozen-a-legacy-family-gate",
            "frozen-a-family-assembly","frozen-a-family-adjustment"].map(|name|plugin_record(name,&pins)));
        value["nodes"] = json!(connected_nodes().into_iter().map(|(id,node)|json!({"id":id,"kind":node["kind"],"spec":node["spec"]})).collect::<Vec<_>>());
        value["edges"] = json!(connected_edges().into_iter().map(|(source,from,target,to)|json!({"from":source,"from_port":from,"to":target,"to_port":to})).collect::<Vec<_>>());
        value
    }

    #[test]
    fn exact_twenty_eight_nodes_sixty_five_edges_and_seven_methods_are_accepted() {
        let value = job();
        assert_eq!(value["nodes"].as_array().unwrap().len(),28);
        assert_eq!(value["edges"].as_array().unwrap().len(),65);
        assert_eq!(connected_source_paths().len(),21);
        assert_eq!(connected_source_paths().iter().collect::<std::collections::BTreeSet<_>>().len(),21);
        assert!(validate_connected_job_with_pins(&value,&pins()).is_ok());
    }

    #[test]
    fn pending_gate_identity_never_authorizes_connected_execution() {
        let mut values = pins();
        values.get_mut("frozen-a-legacy-family-gate").unwrap().script="PENDING".into();
        assert!(validate_connected_job_with_pins(&job(),&values).is_err());
    }

    #[test]
    fn source_paths_roles_and_required_content_hashing_cannot_change() {
        for field in ["path","format","hash_content"] {
            let mut value=job();
            let node=value["nodes"].as_array_mut().unwrap().iter_mut().find(|node|node["id"]=="source9").unwrap();
            node["spec"][field]=json!(false);
            assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
        }
        let mut value=job();
        let node=value["nodes"].as_array_mut().unwrap().iter_mut().find(|node|node["id"]=="source10").unwrap();
        node["spec"]["path"]=json!(format!("vfs://{}",connected_source_path(9)));
        assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
    }

    #[test]
    fn missing_duplicate_and_unknown_nodes_are_rejected() {
        let mut missing=job(); missing["nodes"].as_array_mut().unwrap().pop();
        assert!(validate_connected_job_with_pins(&missing,&pins()).is_err());
        let mut duplicate=job(); let node=duplicate["nodes"][0].clone(); duplicate["nodes"].as_array_mut().unwrap().push(node);
        assert!(validate_connected_job_with_pins(&duplicate,&pins()).is_err());
        let mut unknown=job(); unknown["nodes"][0]["kind"]=json!("datafusion_sql");
        assert!(validate_connected_job_with_pins(&unknown,&pins()).is_err());
    }

    #[test]
    fn method_parameter_and_node_authority_injection_are_rejected() {
        for field in ["p_primary","overlap_class","methods","scientific_authorized"] {
            let mut value=job();
            let node=value["nodes"].as_array_mut().unwrap().iter_mut().find(|node|node["id"]=="mr").unwrap();
            node["spec"][field]=json!(true);
            assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
        }
        let mut value=job(); value["nodes"][0]["g0_granted"]=json!(false);
        assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
    }

    #[test]
    fn missing_duplicate_and_crosswired_edges_are_rejected() {
        let mut missing=job();missing["edges"].as_array_mut().unwrap().pop();
        assert!(validate_connected_job_with_pins(&missing,&pins()).is_err());
        let mut duplicate=job();let edge=duplicate["edges"][0].clone();duplicate["edges"].as_array_mut().unwrap().push(edge);
        assert!(validate_connected_job_with_pins(&duplicate,&pins()).is_err());
        let mut value=job();value["edges"][0]["to_port"]=json!(100);
        assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
    }

    #[test]
    fn mr_cannot_bypass_gate_to_family_request_or_adjustment() {
        for target in ["assemble","adjust","publish"] {
            let mut value=job();
            let edge=value["edges"].as_array_mut().unwrap().iter_mut().find(|edge|edge["from"]=="gate").unwrap();
            edge["from"]=json!("mr");edge["to"]=json!(target);
            assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
        }
    }

    #[test]
    fn all_nine_mr_outputs_and_gate_source_program_are_mandatory() {
        for port in (0..9_u64).chain([22]) {
            let mut value=job();
            let edge=value["edges"].as_array_mut().unwrap().iter_mut().find(|edge|edge["to"]=="gate" && edge["to_port"]==port).unwrap();
            edge["from_port"]=json!(255);
            assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
        }
    }

    #[test]
    fn actual_source_ports_cannot_be_bool_negative_or_overflow() {
        for port in [json!(true),json!(-1),json!(256),json!(0.0),Value::Null] {
            let mut value=job();value["edges"][0]["from_port"]=port;
            assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
        }
    }

    #[test]
    fn unknown_job_fields_and_scientific_scope_injection_are_rejected() {
        for field in ["max_concurrency","incremental","input_hashing","p_primary","scientific_authorized","g0_granted"] {
            let mut value=job();value[field]=json!(true);
            assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
        }
        let mut value=job();value["scope"]=json!("TECHNICAL_PLUGIN_DAG_NOT_G0");
        assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
    }

    #[test]
    fn panel_alias_digest_manifest_or_bundle_substitution_is_rejected() {
        for field in ["locked_panel_source","panel_overrides","panel_manifest_sha256","bundles"] {
            let mut value=job();value[field]=json!([]);
            assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
        }
    }

    #[test]
    fn all_six_plugin_manifest_and_script_identities_are_pinned() {
        for field in ["expected_plugin_name","plugin_manifest_sha256","script_sha256","plugin_manifest"] {
            let mut value=job();value[field]=Value::Null;
            assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
            for index in 0..5 {
                let mut value=job();value["additional_plugins"][index][field]=Value::Null;
                assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
            }
        }
        let text=format!("schema_version=1\nplugin_name=\"frozen-a-legacy-family-gate\"\n[image]\nreference={FAMILY_PYTHON_IMAGE:?}\n[[nodes]]\nkind=\"frozen_a_legacy_family_gate\"\ndesc=\"guard fixture\"\ndoc=\"guard fixture\"\n[nodes.command]\ninterpreter=\"python3\"\nscript=\"pass\"\n[nodes.ports]\ninputs=[]\noutputs=[]\n");
        let mut manifest: PluginManifest=toml::from_str(&text).unwrap();
        assert!(validate_connected_manifest_with_pins(&manifest,&pins()).is_ok());
        manifest.image.reference=serde_json::from_value(json!(FAMILY_R_IMAGE)).unwrap();
        assert!(validate_connected_manifest_with_pins(&manifest,&pins()).is_err());
        manifest=toml::from_str(&text).unwrap();
        manifest.nodes[0].kind="unknown_kind".into();
        assert!(validate_connected_manifest_with_pins(&manifest,&pins()).is_err());
    }

    #[test]
    fn extra_duplicate_or_authorized_additional_plugins_are_rejected() {
        let mut value=job();let extra=value["additional_plugins"][0].clone();value["additional_plugins"].as_array_mut().unwrap().push(extra);
        assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
        let mut value=job();value["additional_plugins"][1]=value["additional_plugins"][0].clone();
        assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
        let mut value=job();value["additional_plugins"][2]["scientific_authorized"]=json!(false);
        assert!(validate_connected_job_with_pins(&value,&pins()).is_err());
    }

    #[test]
    fn gate_kind_is_rejected_outside_its_exact_connected_scope() {
        for scope in [FAMILY_SCOPE,A_RAW_SCOPE,A_HARMONISATION_SCOPE,"TECHNICAL_PLUGIN_DAG_NOT_G0"] {
            assert!(validate_synthetic_kinds(&json!({"scope":scope}),["frozen_a_legacy_family_gate"]).is_err());
        }
    }

    #[test]
    fn legacy_family_scope_still_rejects_the_connected_graph() {
        let mut value=job();value["scope"]=json!(FAMILY_SCOPE);
        assert!(validate_family_job_with_pins(&value,&family_pins().unwrap()).is_err());
        assert!(reject_family_other_scope(&json!({"scope":"TECHNICAL_PLUGIN_DAG_NOT_G0","nodes":[{"kind":"frozen_a_family_publish"}]})).is_err());
    }

    #[test]
    fn connected_fixture_root_must_stay_in_managed_temporary_storage() {
        assert!(validate_fixture_root(std::path::Path::new("/managed/tmp/job"),std::path::Path::new("/managed/permanent"),std::path::Path::new("/managed/tmp"),true).is_ok());
        assert!(validate_fixture_root(std::path::Path::new("/managed/permanent/job"),std::path::Path::new("/managed/permanent"),std::path::Path::new("/managed/tmp"),true).is_err());
    }
}
