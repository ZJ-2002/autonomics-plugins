use std::sync::Arc;

use arrow_array::{RecordBatch, StringArray, UInt64Array};
use arrow_schema::{DataType, Field, Schema};
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
const TRACE: &str = include_str!("../../../scripts/cachexia_mtag_native_trace.py");
const QUALIFICATION: &str = "SYNTHETIC_INPUT_FROZEN_METHOD_HOST_DAG_NOT_SCIENTIFIC_RELEASE";

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
    pub force: bool,
    pub no_overlap: bool,
    pub perfect_gencov: bool,
    pub equal_h2: bool,
    pub std_betas: bool,
    pub numerical_omega: bool,
    pub time_limit_hours: f64,
    pub tol: f64,
}

#[derive(Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Spec {
    pub input_sha256: Vec<String>,
    pub qualification: String,
    pub interpreter: String,
    pub source_root: String,
    pub guard_script: String,
    pub panel_root: String,
    pub environment: std::collections::BTreeMap<String, String>,
    pub runtime_bindings: Vec<Binding>,
    pub parameters: Parameters,
    pub artifact_prefix: String,
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
            || self.input_sha256.len() != 2
            || self.input_sha256.iter().any(|value| !sha(value))
        {
            return Err(
                "two frozen input hashes and explicit synthetic host qualification required".into(),
            );
        }
        if self.parameters.equal_h2 && !self.parameters.perfect_gencov {
            return Err("equal_h2 requires perfect_gencov".into());
        }
        if [self.parameters.time_limit_hours, self.parameters.tol]
            .iter()
            .any(|value| !value.is_finite() || *value <= 0.0)
        {
            return Err("finite positive optimizer parameters required".into());
        }
        for path in [
            &self.interpreter,
            &self.source_root,
            &self.guard_script,
            &self.panel_root,
            &self.artifact_prefix,
        ] {
            if !path.starts_with('/')
                || path.contains("..")
                || path.chars().any(char::is_control)
                || path.contains(',')
            {
                return Err("absolute unambiguous comma-free host paths required".into());
            }
        }
        if self.artifact_prefix == "/" {
            return Err("fresh artifact prefix required".into());
        }
        let keys = ["PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH"];
        if self.environment.len() != keys.len()
            || keys.iter().any(|key| !self.environment.contains_key(*key))
        {
            return Err("only three explicit runtime search variables allowed".into());
        }
        for value in self.environment.values() {
            if value.is_empty()
                || value.split(':').any(|path| {
                    !path.starts_with('/')
                        || path.contains("..")
                        || path.chars().any(char::is_control)
                })
            {
                return Err("absolute runtime search paths required".into());
            }
        }
        let mut paths = std::collections::HashSet::new();
        if self.runtime_bindings.is_empty() {
            return Err("frozen source/runtime/panel closure required".into());
        }
        for binding in &self.runtime_bindings {
            if !binding.path.starts_with('/')
                || binding.path.chars().any(char::is_control)
                || !sha(&binding.sha256)
                || !paths.insert(&binding.path)
            {
                return Err("invalid or duplicate frozen host binding".into());
            }
        }
        for path in [&self.interpreter, &self.guard_script] {
            if !paths.contains(path) {
                return Err("interpreter and guard must be explicitly bound".into());
            }
        }
        for chromosome in 1..=22 {
            for suffix in [".l2.ldscore.gz", ".l2.M_5_50"] {
                if !paths.iter().any(|path| {
                    **path
                        == format!(
                            "{}/{chromosome}{suffix}",
                            self.panel_root.trim_end_matches('/')
                        )
                }) {
                    return Err("all 44 panel payload files must be explicitly bound".into());
                }
            }
        }
        Ok(())
    }
}

fn ports() -> NodePorts {
    NodePorts::new()
        .add_input_port_of_type(None, PortType::File)
        .add_input_port_of_type(None, PortType::File)
        .add_output_port_of_type(None, PortType::File)
        .add_output_port_of_type(None, PortType::File)
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
        "cachexia_mtag_frozen_host"
    }
    fn desc(&self) -> &'static str {
        "Unchanged frozen Python2 MTAG via isolated host DAG, no scientific release"
    }
    fn doc(&self) -> &'static str {
        "Two hashed GWAS File inputs; four complete bundle/log/index/audit File outputs. All six official flags explicit; no assumed independence or optimizer fallback. Finite synthetic-method proof only, no live container/resident deployment."
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

struct ProcessGroupGuard {
    identifier: u32,
}

impl Drop for ProcessGroupGuard {
    fn drop(&mut self) {
        let _ = std::process::Command::new("/usr/bin/kill")
            .args(["-KILL", "--", &format!("-{}", self.identifier)])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .status();
    }
}

#[async_trait]
impl DagNode for HostNode {
    fn ports(&self) -> &NodePorts {
        &self.ports
    }
    fn kind(&self) -> &'static str {
        "cachexia_mtag_frozen_host"
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
        if inputs.len() != 2
            || !inputs.iter().any(|input| input.port == 0)
            || !inputs.iter().any(|input| input.port == 1)
        {
            return Err(fail("exactly two GWAS File ports must be connected".into()));
        }
        let storage = context
            .opendal
            .as_ref()
            .ok_or_else(|| fail("VFS unavailable".into()))?;
        let scratch = tempfile::Builder::new()
            .prefix("mtag-frozen-host-")
            .tempdir()
            .map_err(|error| fail(error.to_string()))?;
        let directory = scratch.path();
        for port in 0..2 {
            let input = inputs
                .iter()
                .find(|input| input.port == port)
                .unwrap()
                .file_value()?;
            let path = input
                .path
                .strip_prefix("vfs://")
                .filter(|path| path.starts_with('/'))
                .ok_or_else(|| fail("absolute GWAS VFS path required".into()))?;
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
                return Err(fail("GWAS File outside declared bounded size/type".into()));
            }
            let bytes = operator
                .read_with(&key)
                .range(0..metadata.content_length())
                .await
                .map_err(|error| fail(error.to_string()))?
                .to_vec();
            if digest(&bytes) != self.spec.input_sha256[port as usize]
                || bytes.len() as u64 != metadata.content_length()
            {
                return Err(fail("GWAS File identity/size mismatch".into()));
            }
            std::fs::write(directory.join(format!("input{port}.tsv")), bytes)
                .map_err(|error| fail(error.to_string()))?;
        }
        for binding in &self.spec.runtime_bindings {
            if digest(&std::fs::read(&binding.path).map_err(|error| fail(error.to_string()))?)
                != binding.sha256
            {
                return Err(fail("frozen MTAG source/runtime/panel changed".into()));
            }
        }
        let names = [
            "results.tar",
            "official.log",
            "index.tsv",
            "audit.json",
            "diagnostic.json",
            "call-trace.json",
            "worker-runtime.json",
            "failure-official.log",
            "failure-call-trace.json",
        ];
        for name in names {
            let path = format!("{}/{name}", self.spec.artifact_prefix.trim_end_matches('/'));
            if storage
                .resolve(&path)
                .stat(&storage.resolve_path(&path))
                .await
                .is_ok()
            {
                return Err(fail("existing MTAG artifact not overwritten".into()));
            }
        }
        let parameters = json!({"force":self.spec.parameters.force,"no_overlap":self.spec.parameters.no_overlap,
            "perfect_gencov":self.spec.parameters.perfect_gencov,"equal_h2":self.spec.parameters.equal_h2,
            "std_betas":self.spec.parameters.std_betas,"numerical_omega":self.spec.parameters.numerical_omega,
            "time_limit_hours":self.spec.parameters.time_limit_hours,"tol":self.spec.parameters.tol});
        let document = json!({"source_root":self.spec.source_root,"guard_script":self.spec.guard_script,
            "panel_root":self.spec.panel_root,"parameters":parameters,"qualification":self.spec.qualification});
        for (name, bytes) in [
            ("host_worker.py", WORKER.as_bytes().to_vec()),
            ("trace.py", TRACE.as_bytes().to_vec()),
            ("spec.json", serde_json::to_vec(&document).unwrap()),
        ] {
            std::fs::write(directory.join(name), bytes).map_err(|error| fail(error.to_string()))?;
        }
        let mut command = tokio::process::Command::new(&self.spec.interpreter);
        command
            .arg(directory.join("host_worker.py"))
            .arg(directory.join("spec.json"))
            .current_dir(directory)
            .env_clear()
            .envs(&self.spec.environment)
            .env("PATH", "/usr/bin:/bin")
            .env("HOME", directory)
            .env("TMPDIR", directory)
            .env("LANG", "C.UTF-8")
            .env("LC_ALL", "C.UTF-8")
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .env("OPENBLAS_NUM_THREADS", "1")
            .env("OMP_NUM_THREADS", "1")
            .env("MKL_NUM_THREADS", "1")
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .kill_on_drop(true);
        std::os::unix::process::CommandExt::process_group(command.as_std_mut(), 0);
        let child = command.spawn().map_err(|error| fail(error.to_string()))?;
        let _process_group = ProcessGroupGuard {
            identifier: child
                .id()
                .ok_or_else(|| fail("MTAG child PID unavailable".into()))?,
        };
        let execution = tokio::time::timeout(
            std::time::Duration::from_secs(180),
            child.wait_with_output(),
        )
        .await
        .map_err(|_| fail("MTAG host wall-time exceeded; own process group terminated".into()))?
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
            for (source, name) in [
                (directory.join("official/mtag.log"), "failure-official.log"),
                (directory.join("call-trace.json"), "failure-call-trace.json"),
            ] {
                if source.is_file() {
                    let path =
                        format!("{}/{name}", self.spec.artifact_prefix.trim_end_matches('/'));
                    storage
                        .resolve(&path)
                        .write(
                            &storage.resolve_path(&path),
                            std::fs::read(source).map_err(|error| fail(error.to_string()))?,
                        )
                        .await
                        .map_err(|error| fail(error.to_string()))?;
                }
            }
            return Err(fail(
                "MTAG host analysis failed; diagnostic retained".into(),
            ));
        }
        for name in ["call-trace.json", "worker-runtime.json"] {
            let record: Value = serde_json::from_slice(
                &std::fs::read(directory.join(name)).map_err(|error| fail(error.to_string()))?,
            )
            .map_err(|error| fail(error.to_string()))?;
            for module in record["loaded_module_bindings"]
                .as_array()
                .ok_or_else(|| fail("actual runtime closure missing".into()))?
            {
                let filename = module["path"]
                    .as_str()
                    .ok_or_else(|| fail("loaded module path missing".into()))?;
                let expected = if filename == directory.join("host_worker.py").to_string_lossy() {
                    Some(digest(WORKER.as_bytes()))
                } else if filename == directory.join("trace.py").to_string_lossy() {
                    Some(digest(TRACE.as_bytes()))
                } else {
                    self.spec
                        .runtime_bindings
                        .iter()
                        .find(|binding| binding.path == filename)
                        .map(|binding| binding.sha256.clone())
                };
                if expected.as_deref() != module["sha256"].as_str() {
                    return Err(fail("loaded MTAG runtime outside frozen closure".into()));
                }
            }
        }
        let mut outputs = PortOutputs::new();
        for (index, name) in [
            "results.tar",
            "official.log",
            "index.tsv",
            "audit.json",
            "call-trace.json",
            "worker-runtime.json",
        ]
        .iter()
        .enumerate()
        {
            let path = format!("{}/{name}", self.spec.artifact_prefix.trim_end_matches('/'));
            let bytes =
                std::fs::read(directory.join(name)).map_err(|error| fail(error.to_string()))?;
            if bytes.is_empty() {
                return Err(fail("empty MTAG artifact rejected".into()));
            }
            storage
                .resolve(&path)
                .write(&storage.resolve_path(&path), bytes)
                .await
                .map_err(|error| fail(error.to_string()))?;
            if index < 4 {
                outputs.insert_file(
                    index as u8,
                    FileRef::new(format!("vfs://{path}"), Some((*name).into())),
                );
            }
        }
        Ok(outputs)
    }
}

#[derive(Clone)]
struct Identity {
    ports: NodePorts,
}
pub struct IdentityFactory;
impl NodeFactory for IdentityFactory {
    fn kind(&self) -> &'static str {
        "cachexia_mtag_file_identity"
    }
    fn desc(&self) -> &'static str {
        "Read a connected MTAG artifact File from actual VFS"
    }
    fn doc(&self) -> &'static str {
        "One File -> complete content SHA256 and byte size. Not interpretation of MTAG statistics."
    }
    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(std::collections::BTreeMap<String, String>)
    }
    fn ports(&self) -> NodePorts {
        NodePorts::new()
            .add_input_port_of_type(None, PortType::File)
            .add_output_port(None)
    }
    fn build(
        &self,
        spec: Value,
        _: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        if spec != json!({}) {
            return Err(dag_core::registry::error::Error::Unknown(
                "identity spec must be empty".into(),
            ));
        }
        Ok(Box::new(Identity {
            ports: self.ports(),
        }))
    }
}
#[async_trait]
impl DagNode for Identity {
    fn ports(&self) -> &NodePorts {
        &self.ports
    }
    fn kind(&self) -> &'static str {
        "cachexia_mtag_file_identity"
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
        if inputs.len() != 1 || inputs[0].port != 0 {
            return Err(DagError::Schedule("one artifact File required".into()));
        }
        let file = inputs[0].file_value()?;
        let path = file
            .path
            .strip_prefix("vfs://")
            .filter(|path| path.starts_with('/'))
            .ok_or_else(|| DagError::Schedule("absolute File VFS required".into()))?;
        let storage = context
            .opendal
            .as_ref()
            .ok_or_else(|| DagError::Schedule("VFS unavailable".into()))?;
        let bytes = storage
            .resolve(path)
            .read(&storage.resolve_path(path))
            .await
            .map_err(|error| DagError::Schedule(error.to_string()))?
            .to_vec();
        let schema = Arc::new(Schema::new(vec![
            Field::new("path", DataType::Utf8, false),
            Field::new("sha256", DataType::Utf8, false),
            Field::new("size_bytes", DataType::UInt64, false),
        ]));
        let batch = RecordBatch::try_new(
            schema,
            vec![
                Arc::new(StringArray::from(vec![file.path.clone()])),
                Arc::new(StringArray::from(vec![digest(&bytes)])),
                Arc::new(UInt64Array::from(vec![bytes.len() as u64])),
            ],
        )
        .map_err(|error| DagError::Schedule(error.to_string()))?;
        let mut outputs = PortOutputs::new();
        outputs.insert(0, context.session().read_batch(batch)?);
        Ok(outputs)
    }
}

pub fn register(registry: &mut NodeRegistry) {
    registry.register(Box::new(Factory));
    registry.register(Box::new(IdentityFactory));
}
