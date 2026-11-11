use std::collections::BTreeMap;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::process::Stdio;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use arrow_array::{ArrayRef, Float64Array, Int32Array, Int64Array, RecordBatch, StringArray};
use arrow_schema::{DataType, SchemaRef};
use dag_core::dag::node_event::NodeReporter;
use dag_core::dag::runtime::NodeRunDetails;
use dag_core::value::{FileFingerprint, FileRef};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use tokio::process::Command;

pub type Result<ValueType> = std::result::Result<ValueType, String>;

static AUTHOR_JOB: tokio::sync::Semaphore = tokio::sync::Semaphore::const_new(1);
static JOB_SEQUENCE: AtomicU64 = AtomicU64::new(0);
const SCRIPT: &str = include_str!("official_backend.R");

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeProfile {
    pub runtime: Value,
    pub rscript: PathBuf,
    pub prlimit: PathBuf,
    pub workspace_root: PathBuf,
    pub locked_files: BTreeMap<PathBuf, String>,
    pub memory_limit_bytes: u64,
    pub file_limit_bytes: u64,
    pub timeout_seconds: u64,
    pub workspace_limit_bytes: u64,
    pub workspace_limit_entries: u64,
}

#[derive(Clone)]
pub struct AuthorRuntime {
    profile: RuntimeProfile,
    profile_path: PathBuf,
    profile_sha256: String,
}

fn failure(error: impl std::fmt::Display) -> String {
    error.to_string()
}

pub fn sha256(path: &Path) -> Result<String> {
    let mut stream = File::open(path).map_err(failure)?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 65536];
    loop {
        let size = stream.read(&mut buffer).map_err(failure)?;
        if size == 0 {
            break;
        }
        digest.update(&buffer[..size]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn create_file(path: &Path, bytes: &[u8]) -> Result<()> {
    OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .and_then(|mut file| file.write_all(bytes))
        .map_err(failure)
}

fn write_json(path: &Path, value: &Value) -> Result<()> {
    create_file(path, &serde_json::to_vec_pretty(value).map_err(failure)?)
}

fn file_ref(path: &Path) -> Result<FileRef> {
    let metadata = fs::metadata(path).map_err(failure)?;
    if !metadata.is_file() {
        return Err("execution artifact is not a regular file".into());
    }
    let mut fingerprint = FileFingerprint::from_metadata(&metadata);
    fingerprint.content_hash = Some(sha256(path)?);
    Ok(FileRef {
        path: path.to_string_lossy().into_owned(),
        format: path
            .extension()
            .map(|value| value.to_string_lossy().into_owned()),
        fingerprint: Some(fingerprint),
    })
}

fn replace_owned_details(reporter: &NodeReporter, details: NodeRunDetails) -> Result<()> {
    if let Some(previous) = reporter.take_run_details() {
        if previous.workspace != details.workspace || previous.run_name != details.run_name {
            reporter.set_run_details(previous);
            return Err("cannot replace execution details owned by another run".into());
        }
    }
    reporter.set_run_details(details);
    Ok(())
}

fn usage(directory: &Path) -> Result<(u64, u64)> {
    let mut bytes = 0_u64;
    let mut entries = 0_u64;
    let mut queue = vec![directory.to_path_buf()];
    while let Some(current) = queue.pop() {
        for entry in fs::read_dir(current).map_err(failure)? {
            let entry = entry.map_err(failure)?;
            let metadata = fs::symlink_metadata(entry.path()).map_err(failure)?;
            entries = entries
                .checked_add(1)
                .ok_or("workspace entry count overflow")?;
            if metadata.is_symlink() || !(metadata.is_dir() || metadata.is_file()) {
                return Err("unexpected symlink or special file in author workspace".into());
            }
            if metadata.is_dir() {
                queue.push(entry.path());
            } else {
                bytes = bytes
                    .checked_add(metadata.len())
                    .ok_or("workspace size overflow")?;
            }
        }
    }
    Ok((bytes, entries))
}

impl AuthorRuntime {
    pub fn load(profile_path: &Path) -> Result<Self> {
        if !profile_path.is_absolute() {
            return Err("official runtime profile path must be absolute".into());
        }
        let bytes = fs::read(profile_path).map_err(failure)?;
        let profile: RuntimeProfile = serde_json::from_slice(&bytes).map_err(failure)?;
        if !profile.rscript.is_absolute()
            || !profile.prlimit.is_absolute()
            || !profile.workspace_root.is_absolute()
            || profile.memory_limit_bytes == 0
            || profile.file_limit_bytes == 0
            || profile.timeout_seconds == 0
            || profile.workspace_limit_bytes == 0
            || profile.workspace_limit_entries == 0
        {
            return Err(
                "official runtime requires absolute paths and positive resource budgets".into(),
            );
        }
        for executable in [&profile.rscript, &profile.prlimit] {
            if !profile.locked_files.contains_key(executable) {
                return Err("official runtime executable is not content-locked".into());
            }
        }
        if profile.locked_files.keys().any(|path| !path.is_absolute())
            || profile.locked_files.values().any(|value| {
                value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit())
            })
        {
            return Err("invalid runtime content lock".into());
        }
        let result = Self {
            profile,
            profile_path: profile_path.to_path_buf(),
            profile_sha256: format!("{:x}", Sha256::digest(&bytes)),
        };
        result.verify()?;
        Ok(result)
    }

    pub fn from_environment() -> Result<Self> {
        let path = std::env::var_os("AUTONOMICS_LCMM_RUNTIME_PROFILE")
            .ok_or("complete official hlme requires AUTONOMICS_LCMM_RUNTIME_PROFILE; native fallback is not permitted")?;
        Self::load(Path::new(&path))
    }

    fn verify(&self) -> Result<()> {
        if sha256(&self.profile_path)? != self.profile_sha256 {
            return Err("official runtime profile changed after binding".into());
        }
        for (path, expected) in &self.profile.locked_files {
            if sha256(path)? != *expected {
                return Err(format!(
                    "official runtime dependency identity mismatch: {}",
                    path.display()
                ));
            }
        }
        Ok(())
    }

    pub async fn identity(&self) -> Result<Value> {
        let runtime = self.clone();
        tokio::task::spawn_blocking(move || runtime.verify())
            .await
            .map_err(failure)??;
        Ok(json!({
            "official_runtime_profile_sha256": self.profile_sha256,
            "author_adapter_sha256": format!("{:x}", Sha256::digest(SCRIPT.as_bytes())),
            "locked_files": self.profile.locked_files,
            "no_native_fallback": true,
        }))
    }

    pub async fn execute(
        &self,
        mut request: Value,
        binary_inputs: BTreeMap<String, Vec<f64>>,
        schemas: Vec<SchemaRef>,
        reporter: &NodeReporter,
    ) -> Result<Vec<RecordBatch>> {
        let _permit = AUTHOR_JOB.acquire().await.map_err(failure)?;
        self.identity().await?;
        if !matches!(
            request["operation"].as_str(),
            Some("fit" | "predict" | "compare")
        ) {
            return Err("unknown official author operation".into());
        }
        let workspace = self.workspace()?;
        let request_path = workspace.join("request.json");
        let script_path = workspace.join("official_backend.R");
        let stdout_path = workspace.join("stdout.log");
        let stderr_path = workspace.join("stderr.log");
        request["runtime"] = self.profile.runtime.clone();
        for (name, values) in binary_inputs {
            let destination = leaf_path(&workspace, &name)?;
            if values.iter().any(|value| !value.is_finite()) {
                return Err("nonfinite binary input is not permitted".into());
            }
            let size = values
                .len()
                .checked_mul(8)
                .ok_or("binary input length overflow")?;
            if size as u64 > self.profile.file_limit_bytes {
                return Err("binary input exceeds frozen execution file budget".into());
            }
            let mut output = Vec::with_capacity(size);
            for value in values {
                output.extend_from_slice(&value.to_le_bytes());
            }
            create_file(&destination, &output)?;
        }
        rewrite_binary_paths(&mut request, &workspace)?;
        write_json(&request_path, &request)?;
        create_file(&script_path, SCRIPT.as_bytes())?;
        let stdout = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&stdout_path)
            .map_err(failure)?;
        let stderr = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&stderr_path)
            .map_err(failure)?;
        fs::create_dir(workspace.join("tmp")).map_err(failure)?;
        let library_paths = self.profile.runtime["library_paths"]
            .as_array()
            .ok_or("runtime library_paths must be a nonempty array")?;
        if library_paths.is_empty() {
            return Err("runtime library_paths must not be empty".into());
        }
        let libraries = library_paths
            .iter()
            .map(|value| value.as_str().ok_or("invalid library path"))
            .collect::<std::result::Result<Vec<_>, _>>()?
            .join(":");
        let mut command = Command::new(&self.profile.prlimit);
        command
            .arg(format!("--as={}", self.profile.memory_limit_bytes))
            .arg(format!("--fsize={}", self.profile.file_limit_bytes))
            .arg("--")
            .arg(&self.profile.rscript)
            .arg("--vanilla")
            .arg(&script_path)
            .arg(&request_path)
            .arg(workspace.join("outputs"))
            .current_dir(&workspace)
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .env("LANG", "C")
            .env("LC_ALL", "C")
            .env("HOME", &workspace)
            .env("TMPDIR", workspace.join("tmp"))
            .env("R_LIBS", libraries)
            .env("R_LIBS_USER", "")
            .env("R_LIBS_SITE", "")
            .env("OPENBLAS_NUM_THREADS", "1")
            .env("OMP_NUM_THREADS", "1")
            .env("MKL_NUM_THREADS", "1")
            .env("RCPP_PARALLEL_NUM_THREADS", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::from(stdout))
            .stderr(Stdio::from(stderr))
            .kill_on_drop(true);
        #[cfg(unix)]
        {
            use std::os::unix::process::CommandExt;
            command.as_std_mut().process_group(0);
        }
        #[cfg(target_os = "linux")]
        {
            use std::os::unix::process::CommandExt;
            let parent = std::process::id() as libc::pid_t;
            unsafe {
                command.as_std_mut().pre_exec(move || {
                    if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGKILL) != 0 {
                        return Err(std::io::Error::last_os_error());
                    }
                    if libc::getppid() != parent {
                        return Err(std::io::Error::from_raw_os_error(libc::ESRCH));
                    }
                    Ok(())
                });
            }
        }
        #[cfg(not(unix))]
        return Err(
            "managed official lcmm execution currently requires Unix process groups".into(),
        );
        let mut child = command.spawn().map_err(failure)?;
        let process_id = child
            .id()
            .ok_or("author process has no process identifier")?;
        let mut guard = ProcessGroupGuard {
            process_id: process_id as i32,
            active: true,
            workspace: workspace.clone(),
        };
        write_json(
            &workspace.join("PROCESS_STARTED.json"),
            &json!({
                "pid": process_id, "private_process_group": process_id,
                "profile_sha256": self.profile_sha256,
                "memory_limit_bytes": self.profile.memory_limit_bytes,
                "file_limit_bytes": self.profile.file_limit_bytes,
                "timeout_seconds": self.profile.timeout_seconds,
                "nproc": 1, "inherited_credentials": false,
            }),
        )?;
        let mut details = NodeRunDetails {
            workspace: Some(workspace.to_string_lossy().into_owned()),
            run_name: workspace
                .file_name()
                .map(|value| value.to_string_lossy().into_owned()),
            task_manifest: Some(file_ref(&request_path)?),
            ..Default::default()
        };
        replace_owned_details(reporter, details.clone())?;
        let waited = tokio::time::timeout(
            Duration::from_secs(self.profile.timeout_seconds),
            child.wait(),
        )
        .await;
        let status = match waited {
            Ok(status) => status.map_err(failure)?,
            Err(_) => {
                write_json(
                    &workspace.join("TIMEOUT.json"),
                    &json!({"status":"FAILED_TIMEOUT", "no_outputs_published":true}),
                )?;
                return Err("official author process exceeded frozen timeout".into());
            }
        };
        guard.active = false;
        details.exit_code = status.code();
        details.stdout_log = Some(file_ref(&stdout_path)?);
        details.stderr_log = Some(file_ref(&stderr_path)?);
        replace_owned_details(reporter, details.clone())?;
        write_json(
            &workspace.join("PROCESS_EXIT.json"),
            &json!({"exit_code": status.code(), "success": status.success()}),
        )?;
        self.identity().await?;
        if !status.success() {
            return Err(format!(
                "official author process failed: {status}; evidence retained at {}",
                workspace.display()
            ));
        }
        let output = workspace.join("outputs");
        let declaration: Value =
            serde_json::from_slice(&fs::read(output.join("PORTS.json")).map_err(failure)?)
                .map_err(failure)?;
        if declaration["operation"] != request["operation"] {
            return Err("author output operation differs from the submitted request".into());
        }
        let batches = read_outputs(&output, &schemas)?;
        for entry in fs::read_dir(&output).map_err(failure)? {
            let entry = entry.map_err(failure)?;
            if !fs::symlink_metadata(entry.path())
                .map_err(failure)?
                .is_file()
            {
                return Err("non-regular author output artifact".into());
            }
            details.output_artifacts.push(file_ref(&entry.path())?);
        }
        replace_owned_details(reporter, details)?;
        write_json(
            &workspace.join("ACCEPTED_OUTPUT_IDENTITY.json"),
            &json!({
                "ports": batches.iter().map(|batch| batch.num_rows()).collect::<Vec<_>>(),
                "runtime_identity": self.identity().await?,
                "technical_output_validation_only": true,
            }),
        )?;
        Ok(batches)
    }

    fn workspace(&self) -> Result<PathBuf> {
        if !self.profile.workspace_root.exists() {
            let mut builder = fs::DirBuilder::new();
            #[cfg(unix)]
            {
                use std::os::unix::fs::DirBuilderExt;
                builder.mode(0o700);
            }
            builder
                .create(&self.profile.workspace_root)
                .map_err(failure)?;
        }
        let metadata = fs::symlink_metadata(&self.profile.workspace_root).map_err(failure)?;
        if !metadata.is_dir() || metadata.is_symlink() {
            return Err("author workspace root must be a real directory".into());
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::{MetadataExt, PermissionsExt};
            if metadata.uid() != unsafe { libc::geteuid() }
                || metadata.permissions().mode() & 0o077 != 0
            {
                return Err(
                    "author workspace root must be private and owned by the current user".into(),
                );
            }
        }
        let (bytes, entries) = usage(&self.profile.workspace_root)?;
        if bytes >= self.profile.workspace_limit_bytes
            || entries >= self.profile.workspace_limit_entries
        {
            return Err("author workspace retention budget exhausted; preserve evidence and archive explicitly before continuing".into());
        }
        let sequence = JOB_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(failure)?
            .as_nanos();
        let workspace = self
            .profile
            .workspace_root
            .join(format!("hlme-{}-{nanos}-{sequence}", std::process::id()));
        let mut builder = fs::DirBuilder::new();
        #[cfg(unix)]
        {
            use std::os::unix::fs::DirBuilderExt;
            builder.mode(0o700);
        }
        builder.create(&workspace).map_err(failure)?;
        Ok(workspace)
    }
}

struct ProcessGroupGuard {
    process_id: i32,
    active: bool,
    workspace: PathBuf,
}

impl Drop for ProcessGroupGuard {
    fn drop(&mut self) {
        if self.active {
            #[cfg(unix)]
            unsafe {
                libc::kill(-self.process_id, libc::SIGKILL);
            }
            let _ = write_json(
                &self.workspace.join("PROCESS_DROPPED.json"),
                &json!({"status":"CANCELLED_OR_DROPPED", "private_process_group":self.process_id, "no_outputs_published":true}),
            );
        }
    }
}

fn leaf_path(root: &Path, filename: &str) -> Result<PathBuf> {
    let mut components = Path::new(filename).components();
    if !matches!(components.next(), Some(Component::Normal(_))) || components.next().is_some() {
        return Err("author artifact name must be one relative normal path component".into());
    }
    let path = root.join(filename);
    match fs::symlink_metadata(&path) {
        Ok(metadata) if !metadata.is_file() => {
            return Err("author artifact must be a regular file".into());
        }
        Err(error) if error.kind() != std::io::ErrorKind::NotFound => return Err(failure(error)),
        _ => {}
    }
    Ok(path)
}

fn rewrite_binary_paths(request: &mut Value, workspace: &Path) -> Result<()> {
    if let Some(binary) = request.pointer_mut("/design/binary") {
        let name = binary
            .as_str()
            .ok_or("design binary path is not a string")?;
        *binary = json!(leaf_path(workspace, name)?);
    }
    for name in ["outcome_binary", "initial_binary", "best_binary"] {
        if let Some(binary) = request.get_mut(name) {
            if !binary.is_null() {
                let filename = binary.as_str().ok_or("binary path is not a string")?;
                *binary = json!(leaf_path(workspace, filename)?);
            }
        }
    }
    Ok(())
}

pub fn read_outputs(directory: &Path, schemas: &[SchemaRef]) -> Result<Vec<RecordBatch>> {
    let declaration: Value =
        serde_json::from_slice(&fs::read(leaf_path(directory, "PORTS.json")?).map_err(failure)?)
            .map_err(failure)?;
    if declaration["protocol"].as_str() != Some("lcmm-author-dataframe-adapter-candidate-v1") {
        return Err("unknown author output protocol".into());
    }
    let ports = declaration["ports"]
        .as_array()
        .ok_or("author output has no ports")?;
    if ports.len() != schemas.len() {
        return Err("author output port count does not match original node contract".into());
    }
    let mut batches = Vec::new();
    for (port_index, (port, schema)) in ports.iter().zip(schemas).enumerate() {
        if port["port"].as_u64() != Some(port_index as u64) {
            return Err("author output ports are missing, duplicated, or reordered".into());
        }
        let rows = usize::try_from(port["rows"].as_u64().ok_or("invalid author row count")?)
            .map_err(failure)?;
        let columns = port["columns"]
            .as_array()
            .ok_or("missing author output columns")?;
        if columns.len() != schema.fields().len() {
            return Err("author output column count differs from original schema".into());
        }
        let mut arrays: Vec<ArrayRef> = Vec::new();
        for (column, field) in columns.iter().zip(schema.fields()) {
            if column["name"].as_str() != Some(field.name())
                || column["nullable"].as_bool() != Some(field.is_nullable())
                || column["kind"].as_str() != Some(&field.data_type().to_string())
            {
                return Err(format!(
                    "author output schema mismatch for {}",
                    field.name()
                ));
            }
            let array: ArrayRef = match field.data_type() {
                DataType::Float64 => {
                    let binary = fs::read(leaf_path(
                        directory,
                        column["binary"].as_str().ok_or("missing Float64 binary")?,
                    )?)
                    .map_err(failure)?;
                    let validity = fs::read(leaf_path(
                        directory,
                        column["validity"]
                            .as_str()
                            .ok_or("missing Float64 validity")?,
                    )?)
                    .map_err(failure)?;
                    if rows.checked_mul(8) != Some(binary.len())
                        || validity.len() != rows
                        || validity.iter().any(|value| *value > 1)
                    {
                        return Err("author Float64 length/validity mismatch".into());
                    }
                    let mut values = Vec::with_capacity(rows);
                    for (bytes, valid) in binary.chunks_exact(8).zip(validity) {
                        let value = f64::from_le_bytes(bytes.try_into().map_err(failure)?);
                        if valid == 0 {
                            if !field.is_nullable() {
                                return Err("missing author value in nonnullable column".into());
                            }
                            values.push(None);
                        } else if value.is_finite() {
                            values.push(Some(value));
                        } else {
                            return Err("nonfinite author output cannot be published".into());
                        }
                    }
                    std::sync::Arc::new(Float64Array::from(values))
                }
                DataType::Int32 | DataType::Int64 | DataType::Utf8 => {
                    let values = column["values"]
                        .as_array()
                        .ok_or("missing author integer/string values")?;
                    if values.len() != rows || values.iter().any(Value::is_null) {
                        return Err(
                            "author integer/string cardinality or missingness mismatch".into()
                        );
                    }
                    match field.data_type() {
                        DataType::Int32 => std::sync::Arc::new(Int32Array::from(values.iter().map(|value| {
                            i32::try_from(value.as_i64().ok_or("author Int32 value is not an integer")?).map_err(failure)
                        }).collect::<Result<Vec<_>>>()?)),
                        DataType::Int64 => std::sync::Arc::new(Int64Array::from(values.iter().map(|value| {
                            value.as_str().ok_or("exact Int64 identity must use decimal string transport")?
                                .parse::<i64>().map_err(failure)
                        }).collect::<Result<Vec<_>>>()?)),
                        _ => std::sync::Arc::new(StringArray::from(values.iter().map(|value| {
                            value.as_str().ok_or("author Utf8 value is not a string")
                        }).collect::<std::result::Result<Vec<_>, _>>()?)),
                    }
                }
                _ => return Err("unsupported original author output schema type".into()),
            };
            arrays.push(array);
        }
        batches.push(RecordBatch::try_new(schema.clone(), arrays).map_err(failure)?);
    }
    Ok(batches)
}

#[cfg(test)]
mod tests {
    use super::*;
    use arrow_schema::{Field, Schema};
    use std::sync::Arc;

    struct Fixture(PathBuf);

    impl Fixture {
        fn new() -> Self {
            let sequence = JOB_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let directory = std::env::temp_dir().join(format!(
                "lcmm-runtime-unit-{}-{sequence}",
                std::process::id()
            ));
            fs::create_dir(&directory).unwrap();
            Self(directory)
        }

        fn declaration(&self, column: Value) {
            write_json(
                &self.0.join("PORTS.json"),
                &json!({"protocol":"lcmm-author-dataframe-adapter-candidate-v1",
                    "ports":[{"port":0,"rows":1,"columns":[column]}]}),
            )
            .unwrap();
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn schema(kind: DataType, nullable: bool) -> Vec<SchemaRef> {
        vec![Arc::new(Schema::new(vec![Field::new(
            "value", kind, nullable,
        )]))]
    }

    #[test]
    fn decimal_int64_transport_preserves_maximum_identifier() {
        let fixture = Fixture::new();
        fixture.declaration(json!({"name":"value","kind":"Int64","nullable":false,
            "values":[i64::MAX.to_string()]}));
        let batches = read_outputs(&fixture.0, &schema(DataType::Int64, false)).unwrap();
        let column = batches[0]
            .column(0)
            .as_any()
            .downcast_ref::<Int64Array>()
            .unwrap();
        assert_eq!(column.value(0), i64::MAX);
    }

    #[test]
    fn numeric_int64_transport_is_rejected_instead_of_rounded() {
        let fixture = Fixture::new();
        fixture.declaration(json!({"name":"value","kind":"Int64","nullable":false,
            "values":[9007199254740993_i64]}));
        assert!(
            read_outputs(&fixture.0, &schema(DataType::Int64, false))
                .unwrap_err()
                .contains("decimal string")
        );
    }

    #[test]
    fn nonfinite_float_cannot_be_published() {
        let fixture = Fixture::new();
        create_file(&fixture.0.join("value.bin"), &f64::INFINITY.to_le_bytes()).unwrap();
        create_file(&fixture.0.join("mask.bin"), &[1]).unwrap();
        fixture.declaration(json!({"name":"value","kind":"Float64","nullable":false,
            "binary":"value.bin","validity":"mask.bin"}));
        assert!(
            read_outputs(&fixture.0, &schema(DataType::Float64, false))
                .unwrap_err()
                .contains("nonfinite")
        );
    }

    #[test]
    fn nonnullable_float_cannot_accept_a_missing_value() {
        let fixture = Fixture::new();
        create_file(&fixture.0.join("value.bin"), &0_f64.to_le_bytes()).unwrap();
        create_file(&fixture.0.join("mask.bin"), &[0]).unwrap();
        fixture.declaration(json!({"name":"value","kind":"Float64","nullable":false,
            "binary":"value.bin","validity":"mask.bin"}));
        assert!(
            read_outputs(&fixture.0, &schema(DataType::Float64, false))
                .unwrap_err()
                .contains("nonnullable")
        );
    }

    #[test]
    fn artifact_parent_traversal_is_rejected() {
        let fixture = Fixture::new();
        assert!(leaf_path(&fixture.0, "../outside.bin").is_err());
        assert!(leaf_path(&fixture.0, "/absolute.bin").is_err());
    }

    #[cfg(unix)]
    #[test]
    fn artifact_symlink_is_rejected() {
        let fixture = Fixture::new();
        create_file(&fixture.0.join("original.bin"), &[1]).unwrap();
        std::os::unix::fs::symlink("original.bin", fixture.0.join("alias.bin")).unwrap();
        assert!(leaf_path(&fixture.0, "alias.bin").is_err());
    }

    #[test]
    fn reporter_updates_owned_details_despite_first_write_wins() {
        let reporter = NodeReporter::noop();
        let mut details = NodeRunDetails {
            workspace: Some("owned-workspace".into()),
            run_name: Some("owned-run".into()),
            ..Default::default()
        };
        replace_owned_details(&reporter, details.clone()).unwrap();
        details.exit_code = Some(0);
        replace_owned_details(&reporter, details).unwrap();
        assert_eq!(reporter.take_run_details().unwrap().exit_code, Some(0));
    }

    #[test]
    fn reporter_does_not_replace_other_runs_details() {
        let reporter = NodeReporter::noop();
        let first = NodeRunDetails {
            workspace: Some("first-workspace".into()),
            run_name: Some("first-run".into()),
            ..Default::default()
        };
        replace_owned_details(&reporter, first).unwrap();
        let second = NodeRunDetails {
            workspace: Some("second-workspace".into()),
            run_name: Some("second-run".into()),
            ..Default::default()
        };
        assert!(replace_owned_details(&reporter, second).is_err());
        assert_eq!(
            reporter.take_run_details().unwrap().workspace.as_deref(),
            Some("first-workspace")
        );
    }
}
