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
    let filename = std::env::args()
        .nth(1)
        .ok_or("usage: official_plugin_dag JOB.json")?;
    let job: Value = serde_json::from_slice(&std::fs::read(filename)?)?;
    if job["scope"] != "TECHNICAL_PLUGIN_DAG_NOT_G0" {
        return Err("explicit synthetic technical scope required".into());
    }
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
        "scope": "TECHNICAL_PLUGIN_DAG_NOT_G0",
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
        "panel_bindings_are_explicit_synthetic_overrides": true,
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
