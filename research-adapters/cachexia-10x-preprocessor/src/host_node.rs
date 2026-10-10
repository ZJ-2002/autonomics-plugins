use async_trait::async_trait;
use dag_core::dag::{DagError, graph::PortOutputs};
use dag_core::node::{DagNode, NodeInput, NodePorts};
use dag_core::registry::{NodeCtx, NodeFactory, NodeRegistry};
use dag_core::value::{FileRef, PortType};
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;
use serde_json::{Value, json};
use sha2::{Digest, Sha256};

const WORKER: &str = include_str!("../scripts/host_worker.py");
const GUARD: &str = include_str!("../scripts/preprocess_guard.py");
const QUALIFICATION: &str = "SYNTHETIC_RAW_10X_HOST_DAG_NOT_SCIENTIFIC_RELEASE";

pub fn digest(bytes: &[u8]) -> String {
    Sha256::digest(bytes)
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

#[derive(Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Binding {
    pub path: String,
    pub sha256: String,
}

#[derive(Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Parameters {
    pub operation: String,
    pub min_genes: u32,
    pub min_cells: u32,
    pub normalize_total: bool,
    pub metadata_separator: String,
    pub matrix_gzip: bool,
}

#[derive(Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Spec {
    pub input_sha256: Vec<String>,
    pub qualification: String,
    pub interpreter: String,
    pub package_root: String,
    pub upstream_script: String,
    pub runtime_bindings: Vec<Binding>,
    pub parameters: Parameters,
    pub artifact_prefix: String,
}

fn absolute(value: &str) -> bool {
    value.starts_with('/') && !value.contains("..") && !value.chars().any(char::is_control)
}
fn sha(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}
impl Spec {
    pub fn validate(&self) -> Result<(), String> {
        if self.qualification != QUALIFICATION
            || self.input_sha256.len() != 4
            || self.input_sha256.iter().any(|value| !sha(value))
        {
            return Err(
                "four frozen hashes and explicit synthetic host qualification required".into(),
            );
        }
        if !matches!(self.parameters.operation.as_str(), "inspect" | "ingest")
            || !matches!(
                self.parameters.metadata_separator.as_str(),
                "tab" | "comma" | "auto"
            )
        {
            return Err("known inspect/ingest operation and separator required".into());
        }
        if self.parameters.operation == "inspect"
            && (self.parameters.min_genes != 0
                || self.parameters.min_cells != 0
                || self.parameters.normalize_total)
        {
            return Err("header-only inspect cannot filter or normalize expression".into());
        }
        if [
            &self.interpreter,
            &self.package_root,
            &self.upstream_script,
            &self.artifact_prefix,
        ]
        .iter()
        .any(|path| !absolute(path))
            || self.artifact_prefix == "/"
            || self.package_root.contains(':')
        {
            return Err("absolute unambiguous frozen host paths required".into());
        }
        let mut paths = std::collections::HashSet::new();
        for binding in &self.runtime_bindings {
            if !absolute(&binding.path) || !sha(&binding.sha256) || !paths.insert(&binding.path) {
                return Err("invalid or duplicate frozen runtime binding".into());
            }
        }
        if self.runtime_bindings.is_empty()
            || !paths.contains(&self.interpreter)
            || !paths.contains(&self.upstream_script)
        {
            return Err("interpreter and upstream source must be bound".into());
        }
        Ok(())
    }
}

fn ports() -> NodePorts {
    NodePorts::new()
        .add_input_port_of_type(None, PortType::File)
        .add_input_port_of_type(None, PortType::File)
        .add_input_port_of_type(None, PortType::File)
        .add_input_port_of_type(None, PortType::File)
        .add_output_port_of_type(None, PortType::File)
        .add_output_port_of_type(None, PortType::File)
}

#[derive(Clone)]
struct HostNode {
    ports: NodePorts,
    spec: Spec,
}
pub struct Factory;
impl NodeFactory for Factory {
    fn kind(&self) -> &'static str {
        "cachexia_10x_frozen_host"
    }
    fn desc(&self) -> &'static str {
        "Lossless four-file raw 10x inspection/ingestion using frozen official APIs"
    }
    fn doc(&self) -> &'static str {
        "Four hashed raw File inputs -> original report and H5AD File roles. Header-only inspect is not expression. Frozen Scanpy/AnnData filters and optional cp10k/log1p. Bounded host route only, not annotation/doublet/batch integration, container/resident deployment or G0."
    }
    fn ports(&self) -> NodePorts {
        ports()
    }
    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(Spec)
    }
    fn build(
        &self,
        spec: Value,
        _: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec: Spec = serde_json::from_value(spec)?;
        spec.validate()
            .map_err(dag_core::registry::error::Error::Unknown)?;
        Ok(Box::new(HostNode {
            ports: ports(),
            spec,
        }))
    }
}

#[async_trait]
impl DagNode for HostNode {
    fn ports(&self) -> &NodePorts {
        &self.ports
    }
    fn kind(&self) -> &'static str {
        "cachexia_10x_frozen_host"
    }
    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(self.clone())
    }
    fn as_any(&self) -> &dyn std::any::Any {
        self
    }
    async fn execute(
        &mut self,
        context: &NodeCtx,
        inputs: &[NodeInput],
        _: &dag_core::dag::node_event::NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        let fail = |message: String| DagError::Schedule(message);
        if inputs.len() != 4 || (0..4).any(|port| !inputs.iter().any(|input| input.port == port)) {
            return Err(fail("exactly four raw 10x File ports required".into()));
        }
        let storage = context
            .opendal
            .as_ref()
            .ok_or_else(|| fail("VFS unavailable".into()))?;
        let scratch = tempfile::Builder::new()
            .prefix("tenx-frozen-host-")
            .tempdir()
            .map_err(|error| fail(error.to_string()))?;
        let directory = scratch.path();
        let names = [
            if self.spec.parameters.matrix_gzip {
                "input0.mtx.gz"
            } else {
                "input0.mtx"
            },
            "input1.tsv",
            "input2.tsv",
            "input3.tsv",
        ];
        for port in 0..4 {
            let file = inputs
                .iter()
                .find(|input| input.port == port)
                .unwrap()
                .file_value()?;
            let path = file
                .path
                .strip_prefix("vfs://")
                .filter(|path| path.starts_with('/'))
                .ok_or_else(|| fail("absolute input VFS path required".into()))?;
            let operator = storage.resolve(path);
            let key = storage.resolve_path(path);
            let metadata = operator
                .stat(&key)
                .await
                .map_err(|error| fail(error.to_string()))?;
            if metadata.is_dir()
                || metadata.content_length() == 0
                || metadata.content_length() > 32 * 1024 * 1024
            {
                return Err(fail("input outside bounded 32MiB File profile".into()));
            }
            let bytes = operator
                .read_with(&key)
                .range(0..metadata.content_length())
                .await
                .map_err(|error| fail(error.to_string()))?
                .to_vec();
            if bytes.len() as u64 != metadata.content_length()
                || digest(&bytes) != self.spec.input_sha256[port as usize]
            {
                return Err(fail("raw input identity/size mismatch".into()));
            }
            std::fs::write(directory.join(names[port as usize]), bytes)
                .map_err(|error| fail(error.to_string()))?;
        }
        for binding in &self.spec.runtime_bindings {
            if digest(&std::fs::read(&binding.path).map_err(|error| fail(error.to_string()))?)
                != binding.sha256
            {
                return Err(fail("frozen 10x runtime/source changed".into()));
            }
        }
        for name in [
            "preprocess_report.json",
            "preprocessed.h5ad",
            "diagnostic.json",
            "worker-runtime.json",
        ] {
            let path = format!("{}/{name}", self.spec.artifact_prefix.trim_end_matches('/'));
            match storage
                .resolve(&path)
                .stat(&storage.resolve_path(&path))
                .await
            {
                Ok(_) => return Err(fail("existing 10x artifact not overwritten".into())),
                Err(error) if error.kind() == vfs::opendal::ErrorKind::NotFound => {}
                Err(error) => {
                    return Err(fail(format!(
                        "artifact freshness could not be established: {error}"
                    )));
                }
            }
        }
        for (name, bytes) in [("host_worker.py", WORKER.as_bytes().to_vec()),
            ("guard.py", GUARD.as_bytes().to_vec()), ("request.json", serde_json::to_vec(&json!({
                "upstream_script":self.spec.upstream_script,"parameters":{
                    "operation":self.spec.parameters.operation,"min_genes":self.spec.parameters.min_genes,
                    "min_cells":self.spec.parameters.min_cells,"normalize_total":self.spec.parameters.normalize_total,
                    "metadata_separator":self.spec.parameters.metadata_separator,"matrix_gzip":self.spec.parameters.matrix_gzip
                }})).unwrap())] {
            std::fs::write(directory.join(name), bytes).map_err(|error| fail(error.to_string()))?;
        }
        let execution = tokio::time::timeout(
            std::time::Duration::from_secs(180),
            tokio::process::Command::new(&self.spec.interpreter)
                .arg(directory.join("host_worker.py"))
                .current_dir(directory)
                .env_clear()
                .env("PATH", "/usr/bin:/bin")
                .env("PYTHONPATH", &self.spec.package_root)
                .env("HOME", directory)
                .env("TMPDIR", directory)
                .env("MPLCONFIGDIR", directory.join("matplotlib"))
                .env("NUMBA_CACHE_DIR", directory.join("numba"))
                .env("LANG", "C.UTF-8")
                .env("LC_ALL", "C.UTF-8")
                .env("PYTHONDONTWRITEBYTECODE", "1")
                .env("OPENBLAS_NUM_THREADS", "1")
                .env("OMP_NUM_THREADS", "1")
                .env("NUMBA_NUM_THREADS", "1")
                .kill_on_drop(true)
                .output(),
        )
        .await
        .map_err(|_| fail("10x host wall timeout".into()))?
        .map_err(|error| fail(error.to_string()))?;
        let diagnostic = json!({"exit_code":execution.status.code(),"stdout":String::from_utf8_lossy(&execution.stdout),
            "stderr":String::from_utf8_lossy(&execution.stderr),"host_not_container":true,"g0_granted":false});
        let path = format!(
            "{}/diagnostic.json",
            self.spec.artifact_prefix.trim_end_matches('/')
        );
        storage
            .resolve(&path)
            .write(
                &storage.resolve_path(&path),
                serde_json::to_vec(&diagnostic).unwrap(),
            )
            .await
            .map_err(|error| fail(error.to_string()))?;
        if !execution.status.success() {
            return Err(fail("10x host analysis failed; diagnostic retained".into()));
        }
        let runtime: Value = serde_json::from_slice(
            &std::fs::read(directory.join("worker-runtime.json"))
                .map_err(|error| fail(error.to_string()))?,
        )
        .map_err(|error| fail(error.to_string()))?;
        for module in runtime["loaded_module_bindings"]
            .as_array()
            .ok_or_else(|| fail("runtime closure missing".into()))?
        {
            let filename = module["path"]
                .as_str()
                .ok_or_else(|| fail("loaded module path missing".into()))?;
            let expected = if filename == directory.join("host_worker.py").to_string_lossy() {
                Some(digest(WORKER.as_bytes()))
            } else if filename == directory.join("guard.py").to_string_lossy() {
                Some(digest(GUARD.as_bytes()))
            } else {
                self.spec
                    .runtime_bindings
                    .iter()
                    .find(|binding| binding.path == filename)
                    .map(|binding| binding.sha256.clone())
            };
            if expected.as_deref() != module["sha256"].as_str() {
                return Err(fail(format!(
                    "loaded module outside frozen closure: {filename}"
                )));
            }
        }
        let mut outputs = PortOutputs::new();
        for (port, name) in [
            "preprocess_report.json",
            "preprocessed.h5ad",
            "worker-runtime.json",
        ]
        .iter()
        .enumerate()
        {
            let bytes =
                std::fs::read(directory.join(name)).map_err(|error| fail(error.to_string()))?;
            if bytes.is_empty() {
                return Err(fail("empty 10x product rejected".into()));
            }
            let path = format!("{}/{name}", self.spec.artifact_prefix.trim_end_matches('/'));
            storage
                .resolve(&path)
                .write(&storage.resolve_path(&path), bytes)
                .await
                .map_err(|error| fail(error.to_string()))?;
            if port < 2 {
                outputs.insert_file(
                    port as u8,
                    FileRef::new(format!("vfs://{path}"), Some((*name).into())),
                );
            }
        }
        Ok(outputs)
    }
}

pub fn register(registry: &mut NodeRegistry) {
    registry.register(Box::new(Factory));
}
