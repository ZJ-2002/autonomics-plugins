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

const METHODS: [&str; 3] = ["ldsc_h2", "ldsc_munge", "ldsc_rg"];
const PANEL_IDS: [(&str, &str, &str); 2] = [
    (
        "ref_ld",
        "wjixiang/catalog-ldsc-ref-ld-1000g-eur-basic",
        "autonomics-technical/ldsc-synthetic-ref",
    ),
    (
        "w_ld",
        "wjixiang/catalog-ldsc-w-ld-1000g-eur-hm3-no-mhc",
        "autonomics-technical/ldsc-synthetic-weight",
    ),
];

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let filename = std::env::args()
        .nth(1)
        .ok_or("usage: official_ldsc_dag JOB.json")?;
    let job: Value = serde_json::from_slice(&std::fs::read(filename)?)?;
    if job["scope"] != "SYNTHETIC_LDSC_DAG_NOT_G0" {
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
    if manifest.plugin_name != "ldsc"
        || manifest.nodes.len() != METHODS.len()
        || manifest.panels.len() != PANEL_IDS.len()
    {
        return Err("exact three-entry canonical LDSC plugin required".into());
    }
    for (panel, (binding, original, synthetic)) in manifest.panels.iter_mut().zip(PANEL_IDS) {
        if panel.binding != binding
            || panel.bundle.to_string() != original
            || panel.mount != format!("/panels/{binding}")
        {
            return Err("original canonical panel declarations differ".into());
        }
        panel.bundle = synthetic.parse()?;
    }
    let synthetic_manifest_bytes = toml::to_string(&manifest)?.into_bytes();
    for entry in &mut manifest.nodes {
        if !METHODS.contains(&entry.kind.as_str()) {
            return Err("native statistical fallback forbidden".into());
        }
        let script = entry
            .command
            .script_file
            .take()
            .ok_or("actual plugin script required")?;
        let script_bytes = std::fs::read(
            manifest_path
                .parent()
                .ok_or("plugin parent missing")?
                .join(&script),
        )?;
        if format!("{:x}", Sha256::digest(&script_bytes))
            != job["script_sha256"][&script]
                .as_str()
                .ok_or("script identity required")?
        {
            return Err("actual dispatched script differs".into());
        }
        entry.command.script = Some(String::from_utf8(script_bytes)?);
        container_plugin::node_definition::validate(entry)?;
    }
    let mut bundles = BundleRegistry::new();
    for record in job["bundles"]
        .as_array()
        .ok_or("synthetic bundles required")?
    {
        let bundle: DataBundle = serde_json::from_value(record.clone())?;
        let (_, _, expected) = PANEL_IDS
            .iter()
            .find(|(_, _, ident)| *ident == bundle.ident)
            .ok_or("non-synthetic bundle forbidden")?;
        if bundle.ident != *expected
            || !bundle.vpath.starts_with("/synthetic-panels/")
            || bundle.source.as_deref() != Some(bundle.vpath.as_str())
            || bundle.digest.is_none()
        {
            return Err("explicit synthetic panel identity required".into());
        }
        bundles.register(bundle)?;
    }
    if job["bundles"].as_array().ok_or("bundles missing")?.len() != 2 {
        return Err("exactly two synthetic bundles required".into());
    }
    let panel_manifest_hashes: BTreeMap<String, String> =
        serde_json::from_value(job["panel_manifest_sha256"].clone())?;
    let panel_cache_root = PathBuf::from(std::env::var("TMPDIR")?)
        .join("official-ldsc-panel-cache")
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
            .join("official-ldsc-container-workspaces")
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
        runtime,
        panel_cache,
    ));
    let mut dag = DAG::default();
    for record in job["nodes"].as_array().ok_or("nodes required")? {
        let identifier = record["id"].as_str().ok_or("id required")?;
        let kind = record["kind"].as_str().ok_or("kind required")?;
        if !METHODS.contains(&kind)
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
        "scope": "SYNTHETIC_LDSC_DAG_NOT_G0",
        "engine_source_revision": dag_core::source_revision(),
        "first_run": report,
        "max_concurrency": 1,
        "incremental": false,
        "input_hashing": "ContentRequired",
        "current_daemon_verified": false,
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
