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
const AUTHORIZATION_SHA: &str = "fd8d56a7dd76eea82bab82d4a07c94d4e1e2f9040d69881e02810cf84e916299";
const SOURCE_SESSION: &str = "d585c6c7ef5f49b7bc3845d722572eec";
const SOURCE_SEAL: &str = "ae4bdb186263789615ad6123376b2c9a090f850e2f0920528eb79f53a9b81bf7";
const SOURCE_VERIFIER: &str = "1a928da15243316facd63358c9f33dbc69f399de41b1f7b8f341f05c647a1073";
const SOURCE_MANIFEST: &str = "1bf0699bffde16a419a308d66654610cdca3170aa3fab2b8b50d93656e80e2a5";
const TRANSPORT_MANIFEST: &str = "939a180cafbdeb45899ea216fe71db7e0a2a77a6fc360d09258e14532dbfbcef";

fn transport_mode(job: &Value) -> Result<bool, Box<dyn std::error::Error>> {
    if job["scope"] == "TECHNICAL_PLUGIN_DAG_NOT_G0" {
        if job["expected_plugin_name"] == "frozen-b-project"
            || job["additional_plugins"].as_array().is_some_and(|plugins| {
                plugins
                    .iter()
                    .any(|plugin| plugin["expected_plugin_name"] == "frozen-b-project")
            })
        {
            return Err("fixed real legacy B source cannot be relabelled as synthetic".into());
        }
        return Ok(false);
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
    if overrides.len() != manifest.panels.len() {
        return Err("complete explicit technical panel mapping required".into());
    }
    let mut panel_ids = std::collections::BTreeSet::new();
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
            || !bundle.vpath.starts_with("/synthetic-panels/")
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
    let panel_cache = Arc::new(
        PanelCache::content_required(&panel_cache_root)
            .with_manifest_hashes(panel_manifest_hashes)?,
    );
    let mounts = VfsManifest {
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
    let evidence = json!({
        "scope": if full_replay { "REAL_LOCKED_LEGACY_THREE_MODEL_TECHNICAL_REPLAY" } else if real_transport { "REAL_LOCKED_LEGACY_TRANSPORT_NO_FIT" } else { "TECHNICAL_PLUGIN_DAG_NOT_G0" },
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
        "effective_synthetic_manifest_sha256": format!("{:x}", Sha256::digest(&synthetic_manifest_bytes)),
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
    fn synthetic_scope_cannot_relabel_fixed_real_frozen_b_plugin() {
        let mut value = job();
        value["scope"] = json!("TECHNICAL_PLUGIN_DAG_NOT_G0");
        assert!(transport_mode(&value).is_err());
        value["expected_plugin_name"] = json!("bulk-limma-normalized");
        value["additional_plugins"] = json!([{"expected_plugin_name":"frozen-b-project"}]);
        assert!(transport_mode(&value).is_err());
        value["additional_plugins"] = json!([]);
        assert!(!transport_mode(&value).unwrap());
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
