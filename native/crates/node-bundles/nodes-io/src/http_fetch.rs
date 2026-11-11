//! Allowlist-gated HTTP fetch node.
//!
//! The node downloads a single URL into a File output, but only when the
//! URL's host is listed in the network allowlist — a deny-by-default guard so
//! a runaway workflow cannot exfiltrate or pull arbitrary hosts. The
//! allowlist lives in `state_dir/network-allowlist.toml`; the gateway daemon
//! creates a commented template there on startup and points
//! [`ENV_NETWORK_ALLOWLIST`] at it. An allowlist entry matches its own host
//! and every subdomain (`ebi.ac.uk` also covers `ftp.ebi.ac.uk`). The
//! allowlist machinery itself is shared with `file_download` via
//! [`crate::net_policy`].

use std::time::Duration;

use async_trait::async_trait;
use futures::StreamExt;
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;
use thiserror::Error;

use dag_core::node::{DagNode, NodeInput, NodePorts};
use dag_core::value::{FileRef, PortType};
use dag_core::{
    dag::DagError,
    dag::graph::PortOutputs,
    registry::{NodeCtx, NodeFactory},
};

pub use crate::net_policy::{
    ALLOWLIST_FILE_NAME, ENV_NETWORK_ALLOWLIST, NetworkPolicyError, default_allowlist_toml,
    host_allowed, load_allowlist_from_env, parse_allowlist, redirect_policy,
};

pub const HTTP_FETCH_KIND: &str = "http_fetch";

#[path = "http_fetch_publication.rs"]
mod publication;

#[cfg(test)]
#[path = "http_fetch_publication_tests.rs"]
mod publication_tests;

const DEFAULT_TIMEOUT_SECS: u64 = 300;
const DEFAULT_MAX_BYTES: u64 = 256 * 1024 * 1024;

#[derive(Debug, Error)]
pub enum HttpFetchError {
    #[error("invalid http_fetch spec: {message}")]
    InvalidSpec { message: String },

    #[error(transparent)]
    Policy(#[from] NetworkPolicyError),

    #[error("HTTP request to `{url}` failed: {source}")]
    Request {
        url: String,
        #[source]
        source: reqwest::Error,
    },

    #[error("redirect from `{url}` was refused: {reason}")]
    RedirectRefused { url: String, reason: String },

    #[error("HTTP `{url}` answered {status}")]
    HttpStatus {
        url: String,
        status: reqwest::StatusCode,
    },

    #[error("`{url}` body exceeds http_fetch max_bytes ({max_bytes})")]
    TooLarge { url: String, max_bytes: u64 },

    #[error("cannot write fetched body to `{path}`: {reason}")]
    Write { path: String, reason: String },
}

impl ::dag_core::dag::NodeError for HttpFetchError {
    fn node_type(&self) -> &str {
        "http_fetch"
    }
}

#[derive(Debug, Clone, JsonSchema, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct HttpFetchSpec {
    /// Absolute http(s) URL to download.
    url: String,
    /// Output path for the response body (`/…`, `file://…`, or `vfs://…`).
    path: String,
    #[serde(default = "default_timeout_secs")]
    timeout_secs: u64,
    /// Refuse bodies larger than this many bytes (buffered in memory).
    #[serde(default = "default_max_bytes")]
    max_bytes: u64,
}

fn default_timeout_secs() -> u64 {
    DEFAULT_TIMEOUT_SECS
}

fn default_max_bytes() -> u64 {
    DEFAULT_MAX_BYTES
}

#[derive(Clone)]
pub struct HttpFetchNode {
    meta: NodePorts,
    spec: HttpFetchSpec,
}

pub struct HttpFetchNodeFactory;

fn port_layout() -> NodePorts {
    NodePorts::new().add_output_port_of_type(None, PortType::File)
}

fn validate_spec(spec: &HttpFetchSpec) -> Result<(), HttpFetchError> {
    if spec.timeout_secs == 0 {
        return Err(HttpFetchError::InvalidSpec {
            message: "timeout_secs must be greater than zero".into(),
        });
    }
    if spec.max_bytes == 0 {
        return Err(HttpFetchError::InvalidSpec {
            message: "max_bytes must be greater than zero".into(),
        });
    }
    let url = parse_url(&spec.url)?;
    if spec.path.trim().is_empty() {
        return Err(HttpFetchError::InvalidSpec {
            message: "path cannot be empty".into(),
        });
    }
    let output = spec
        .path
        .strip_prefix("vfs://")
        .or_else(|| spec.path.strip_prefix("file://"))
        .unwrap_or(&spec.path);
    if !std::path::Path::new(output).is_absolute()
        || std::path::Path::new(output)
            .components()
            .any(|component| matches!(component, std::path::Component::ParentDir))
    {
        return Err(HttpFetchError::InvalidSpec {
            message: "output must be an absolute local/VFS path without parent traversal".into(),
        });
    }
    if url.host_str().is_none_or(str::is_empty) {
        return Err(HttpFetchError::InvalidSpec {
            message: format!("URL `{}` has no host", spec.url),
        });
    }
    Ok(())
}

fn parse_url(url: &str) -> Result<reqwest::Url, HttpFetchError> {
    let parsed = reqwest::Url::parse(url).map_err(|error| HttpFetchError::InvalidSpec {
        message: format!("cannot parse URL `{url}`: {error}"),
    })?;
    if parsed.scheme() != "http" && parsed.scheme() != "https" {
        return Err(HttpFetchError::InvalidSpec {
            message: format!(
                "unsupported scheme `{}` in `{url}`; only http and https are allowed",
                parsed.scheme()
            ),
        });
    }
    Ok(parsed)
}

/// reqwest's own Display for redirect failures hides the policy message (it
/// lives in the source chain); surface it so refusals explain themselves.
fn describe_request_error(url: &str, source: reqwest::Error) -> HttpFetchError {
    if source.is_redirect() {
        let reason = std::error::Error::source(&source)
            .map(|cause| cause.to_string())
            .unwrap_or_else(|| "no reason given".to_string());
        return HttpFetchError::RedirectRefused {
            url: url.to_string(),
            reason,
        };
    }
    HttpFetchError::Request {
        url: url.to_string(),
        source,
    }
}

pub(super) async fn write_body(
    node_ctx: &NodeCtx,
    path: &str,
    bytes: Vec<u8>,
) -> Result<(), HttpFetchError> {
    if let Some(virtual_path) = path.strip_prefix("vfs://") {
        let storage = node_ctx
            .opendal
            .as_ref()
            .ok_or_else(|| HttpFetchError::Write {
                path: path.to_string(),
                reason: "vfs:// output requires mounted object storage".into(),
            })?;
        let operator = storage.resolve(virtual_path);
        operator
            .write(&storage.resolve_path(virtual_path), bytes)
            .await
            .map_err(|error| HttpFetchError::Write {
                path: path.to_string(),
                reason: error.to_string(),
            })?;
        return Ok(());
    }
    if let Some(parent) = std::path::Path::new(path).parent() {
        tokio::fs::create_dir_all(parent)
            .await
            .map_err(|error| HttpFetchError::Write {
                path: path.to_string(),
                reason: format!("cannot create `{}`: {error}", parent.display()),
            })?;
    }
    tokio::fs::write(path, bytes)
        .await
        .map_err(|error| HttpFetchError::Write {
            path: path.to_string(),
            reason: error.to_string(),
        })
}

pub(super) fn file_output(path: &str) -> FileRef {
    let format = std::path::Path::new(path)
        .extension()
        .and_then(|extension| extension.to_str())
        .map(|extension| extension.to_ascii_lowercase());
    if path.starts_with("vfs://") {
        return FileRef::new(path.to_string(), format);
    }
    FileRef::local(path, format).unwrap_or_else(|_| FileRef::new(path.to_string(), None))
}

impl HttpFetchNode {
    pub fn new(spec: HttpFetchSpec) -> Self {
        Self {
            meta: port_layout(),
            spec,
        }
    }

    /// Execute against an explicit allowlist instead of the environment
    /// variable (test seam; `None` behaves like an unset variable).
    async fn execute_with_allowlist(
        &mut self,
        node_ctx: &NodeCtx,
        allowlist: Option<Vec<String>>,
    ) -> Result<PortOutputs, HttpFetchError> {
        validate_spec(&self.spec)?;
        let entries = match allowlist {
            Some(entries) => entries,
            None => load_allowlist_from_env()?,
        };
        let url = parse_url(&self.spec.url)?;
        crate::net_policy::ensure_host_allowed(&url, &entries)?;

        let client = reqwest::Client::builder()
            .user_agent(crate::net_policy::HTTP_USER_AGENT)
            .connect_timeout(Duration::from_secs(self.spec.timeout_secs.min(60)))
            .read_timeout(Duration::from_secs(self.spec.timeout_secs))
            .redirect(redirect_policy(entries))
            .build()
            .map_err(|source| describe_request_error(&self.spec.url, source))?;
        for attempt in 1..=3 {
            let result = self.fetch_once(node_ctx, &client, url.clone()).await;
            let retry = match &result {
                Err(HttpFetchError::Request { source, .. }) => {
                    let mut cause = std::error::Error::source(source);
                    let mut trust_failure = false;
                    while let Some(error) = cause {
                        let text = error.to_string().to_ascii_lowercase();
                        trust_failure |= text.contains("certificate")
                            || text.contains("unknownissuer") || text.contains("unknown issuer");
                        cause = error.source();
                    }
                    !trust_failure && (source.is_connect() || source.is_timeout()
                        || source.is_body() || source.is_decode())
                }
                _ => false,
            };
            if retry && attempt < 3 {
                // fetch_once drops the incomplete body before retrying. It
                // only publishes after EOF, and never retries a write/commit,
                // an HTTP denial, or a certificate failure.
                tokio::time::sleep(Duration::from_millis(250 * attempt)).await;
                continue;
            }
            return result;
        }
        unreachable!("the final attempt always returns its result")
    }

    async fn fetch_once(
        &self,
        node_ctx: &NodeCtx,
        client: &reqwest::Client,
        url: reqwest::Url,
    ) -> Result<PortOutputs, HttpFetchError> {
        let response = client
            .get(url.clone())
            .send()
            .await
            .map_err(|source| describe_request_error(&self.spec.url, source))?;
        let status = response.status();
        if !status.is_success() {
            return Err(HttpFetchError::HttpStatus {
                url: self.spec.url.clone(),
                status,
            });
        }
        if let Some(length) = response.content_length()
            && length > self.spec.max_bytes
        {
            return Err(HttpFetchError::TooLarge {
                url: self.spec.url.clone(),
                max_bytes: self.spec.max_bytes,
            });
        }
        let expected_length = response.content_length();

        let mut body: Vec<u8> = Vec::new();
        let mut stream = response.bytes_stream();
        while let Some(chunk) = stream.next().await {
            let chunk = chunk.map_err(|source| describe_request_error(&self.spec.url, source))?;
            if body.len() as u64 + chunk.len() as u64 > self.spec.max_bytes {
                return Err(HttpFetchError::TooLarge {
                    url: self.spec.url.clone(),
                    max_bytes: self.spec.max_bytes,
                });
            }
            body.extend_from_slice(&chunk);
        }
        if expected_length.is_some_and(|length| body.len() as u64 != length) {
            return Err(HttpFetchError::InvalidSpec {
                message: "HTTP response ended before its declared content length; no output was published".into(),
            });
        }

        let path = crate::file_to_dataframe::source_path(
            node_ctx,
            &crate::file_to_dataframe::normalize_path(&self.spec.path),
        );
        let file = publication::write_body(node_ctx, &path, body).await?;
        let mut outputs = PortOutputs::new();
        outputs.insert_file(0, file);
        Ok(outputs)
    }
}

#[async_trait]
impl DagNode for HttpFetchNode {
    fn ports(&self) -> &NodePorts {
        &self.meta
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(self.clone())
    }

    fn kind(&self) -> &'static str {
        HTTP_FETCH_KIND
    }

    fn sink_path(&self) -> Option<&str> {
        Some(&self.spec.path)
    }

    fn as_any(&self) -> &dyn std::any::Any {
        self
    }

    async fn execute(
        &mut self,
        node_ctx: &NodeCtx,
        inputs: &[NodeInput],
        _reporter: &dag_core::dag::node_event::NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        if !inputs.is_empty() {
            return Err(DagError::Schedule("http_fetch has no input ports".into()));
        }
        self.execute_with_allowlist(node_ctx, None)
            .await
            .map_err(Into::into)
    }
}

impl NodeFactory for HttpFetchNodeFactory {
    fn kind(&self) -> &'static str {
        HTTP_FETCH_KIND
    }

    fn desc(&self) -> &'static str {
        "Downloads an allowlisted http(s) URL into a File output."
    }

    fn doc(&self) -> &'static str {
        "No input ports; one File output holding the response body. The URL host must be \
        on the network allowlist (deny-by-default): the gateway daemon creates \
        state_dir/network-allowlist.toml on first start and points the \
        AUTONOMICS_NETWORK_ALLOWLIST environment variable at it. An entry matches its own \
        host and any subdomain. Redirects must stay on the allowlist at every hop; bodies \
        larger than max_bytes are refused; the body is buffered in memory. \
        CPU, memory and walltime belong to the executor, not this node spec: in dag_shell \
        call task_resources(id, #{cpus: 4, memory_bytes: 17179869184, max_duration_ms: 7200000}) \
        before commit(), then dry-run and inspect physical_task_resources. These requests \
        still require target admission; compute_readiness is configuration-only. \
        On an admitted remote worker use an unmounted owned output such as \
        vfs:///acquisition/project/file, then consume the returned File reference. \
        Legacy /downloads and retained data-home mounts may be read-only; do not \
        route acquisition back through the coordinator resource_download tools."
    }

    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(HttpFetchSpec)
    }

    fn ports(&self) -> NodePorts {
        port_layout()
    }

    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec: HttpFetchSpec = serde_json::from_value(spec)?;
        validate_spec(&spec)
            .map_err(|error| dag_core::registry::error::Error::Unknown(error.to_string()))?;
        Ok(Box::new(HttpFetchNode::new(spec)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn spec(url: &str, path: &str) -> HttpFetchSpec {
        HttpFetchSpec {
            url: url.to_string(),
            path: path.to_string(),
            timeout_secs: 10,
            max_bytes: DEFAULT_MAX_BYTES,
        }
    }

    fn file_output_of(outputs: &PortOutputs) -> &FileRef {
        match outputs.get(&0).unwrap() {
            dag_core::value::NodeValue::File(file) => file,
            other => panic!("expected a File output, got {other:?}"),
        }
    }

    #[tokio::test]
    async fn fetch_identifies_application_to_header_requiring_servers() {
        use tokio::io::{AsyncReadExt, AsyncWriteExt};
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = tokio::spawn(async move {
            let (mut stream, _) = listener.accept().await.unwrap();
            let mut request = Vec::new();
            while !request.ends_with(b"\r\n\r\n") {
                request.push(stream.read_u8().await.unwrap());
                assert!(request.len() < 8192);
            }
            let request = String::from_utf8(request).unwrap().to_ascii_lowercase();
            let identified = request.contains(&format!("\r\nuser-agent: {}\r\n", crate::net_policy::HTTP_USER_AGENT));
            let response: &[u8] = if identified {
                b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok"
            } else {
                b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            };
            stream.write_all(response).await.unwrap();
            identified
        });
        let directory = tempfile::tempdir().unwrap();
        let destination = directory.path().join("body.txt");
        let mut node = HttpFetchNode::new(spec(&format!("http://127.0.0.1:{port}/data"), &destination.to_string_lossy()));
        let ctx = NodeCtx::new(datafusion::prelude::SessionContext::new().runtime_env(), None);
        let result = node.execute_with_allowlist(&ctx, Some(vec!["127.0.0.1".into()])).await;
        assert!(server.await.unwrap(), "the actual request must identify the application");
        assert!(result.is_ok(), "{result:?}");
        assert_eq!(std::fs::read(destination).unwrap(), b"ok");
    }

    #[test]
    fn unknown_spec_fields_cannot_silently_discard_resource_controls() {
        for unknown_field in ["max_byte", "timeout_sec"] {
            let mut specification = serde_json::json!({
                "url": "https://example.org/input.tsv",
                "path": "/tmp/http-input.tsv"
            });
            specification[unknown_field] = serde_json::json!(1);
            let parsed = serde_json::from_value::<HttpFetchSpec>(specification);
            assert!(parsed.is_err(), "silently accepted {unknown_field}");
            assert!(parsed.unwrap_err().to_string().contains(unknown_field));
        }
    }

    #[test]
    fn declared_resource_controls_and_defaults_are_preserved() {
        let explicit: HttpFetchSpec = serde_json::from_value(serde_json::json!({
            "url": "https://example.org/input.tsv",
            "path": "/tmp/http-input.tsv",
            "timeout_secs": 7,
            "max_bytes": 4096
        }))
        .unwrap();
        assert_eq!(explicit.timeout_secs, 7);
        assert_eq!(explicit.max_bytes, 4096);
        let defaults: HttpFetchSpec = serde_json::from_value(serde_json::json!({
            "url": "https://example.org/input.tsv",
            "path": "/tmp/http-input.tsv"
        }))
        .unwrap();
        assert_eq!(defaults.timeout_secs, DEFAULT_TIMEOUT_SECS);
        assert_eq!(defaults.max_bytes, DEFAULT_MAX_BYTES);
    }

    #[test]
    fn factory_rejects_invalid_output_paths_and_zero_resource_limits() {
        let context = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        let valid = serde_json::json!({
            "url":"https://example.invalid/body.tsv",
            "path":"/tmp/http-body.tsv",
            "timeout_secs":5,
            "max_bytes":1024
        });
        assert!(
            HttpFetchNodeFactory
                .build(valid.clone(), context.clone())
                .is_ok()
        );
        for (field, value) in [
            ("path", serde_json::json!("relative.tsv")),
            ("path", serde_json::json!("vfs:///a/../body.tsv")),
            ("timeout_secs", serde_json::json!(0)),
            ("max_bytes", serde_json::json!(0)),
        ] {
            let mut invalid = valid.clone();
            invalid[field] = value;
            assert!(
                HttpFetchNodeFactory
                    .build(invalid, context.clone())
                    .is_err()
            );
        }
    }

    #[test]
    fn url_validation_rejects_non_http_schemes_and_missing_hosts() {
        assert!(validate_spec(&spec("ftp://ebi.ac.uk/file", "/out.bin")).is_err());
        assert!(validate_spec(&spec("file:///etc/passwd", "/out.bin")).is_err());
        // `http:///x` collapses to host `x` per WHATWG; a truly empty host
        // fails at parse time instead.
        assert!(validate_spec(&spec("http:///", "/out.bin")).is_err());
        assert!(validate_spec(&spec("https://ebi.ac.uk/f", " ")).is_err());
        assert!(validate_spec(&spec("https://ebi.ac.uk/f?q=1", "/dir/out.tsv.gz")).is_ok());
        let mut zero = spec("https://ebi.ac.uk/", "/out");
        zero.timeout_secs = 0;
        assert!(validate_spec(&zero).is_err());
        zero.timeout_secs = 10;
        zero.max_bytes = 0;
        assert!(validate_spec(&zero).is_err());
    }

    #[tokio::test]
    async fn fetch_fails_without_an_allowlist() {
        let mut node = HttpFetchNode::new(spec("https://ebi.ac.uk/x", "/tmp/http_fetch_out"));
        let ctx = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        let error = node.execute_with_allowlist(&ctx, None).await.unwrap_err();
        assert!(
            error
                .to_string()
                .contains("no HTTP fetch allowlist is configured"),
            "{error}"
        );
    }

    #[tokio::test]
    async fn fetch_refuses_hosts_off_the_allowlist() {
        let mut node =
            HttpFetchNode::new(spec("https://example.org/data.tsv", "/tmp/http_fetch_out"));
        let ctx = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        let error = node
            .execute_with_allowlist(&ctx, Some(vec!["ebi.ac.uk".into()]))
            .await
            .unwrap_err();
        assert!(error.to_string().contains("example.org"), "{error}");
        assert!(
            error
                .to_string()
                .contains("not on the HTTP fetch allowlist"),
            "{error}"
        );
    }

    /// Bind 127.0.0.1:0 and answer exactly one request with `response`.
    async fn one_shot_server(response: &'static [u8]) -> u16 {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = listener.local_addr().unwrap().port();
        tokio::spawn(async move {
            use tokio::io::{AsyncReadExt, AsyncWriteExt};
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut buffer = [0u8; 4096];
            let _ = socket.read(&mut buffer).await;
            let _ = socket.write_all(response).await;
        });
        port
    }

    #[tokio::test]
    async fn fetch_downloads_an_allowlisted_host_into_the_output_file() {
        let port = one_shot_server(
            b"HTTP/1.1 200 OK\r\ncontent-length: 5\r\nconnection: close\r\n\r\nhello",
        )
        .await;
        let out = tempfile::tempdir().unwrap().keep().join("body.tsv");
        let mut node = HttpFetchNode::new(spec(
            &format!("http://127.0.0.1:{port}/data.tsv"),
            &out.to_string_lossy(),
        ));
        let ctx = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        let outputs = node
            .execute_with_allowlist(&ctx, Some(vec!["127.0.0.1".into()]))
            .await
            .unwrap();
        let file = file_output_of(&outputs);
        assert_eq!(std::fs::read(&file.path).unwrap(), b"hello");
        assert_eq!(file.format.as_deref(), Some("tsv"));
    }

    #[tokio::test]
    async fn redirects_must_stay_on_the_allowlist() {
        // 127.0.0.1 is allowlisted; the redirect hop to `localhost` is not,
        // even though it is the same socket.
        let port = one_shot_server(
            b"HTTP/1.1 302 Found\r\ncontent-length: 0\r\nlocation: http://localhost:9/x\r\nconnection: close\r\n\r\n",
        )
        .await;
        let out = tempfile::tempdir().unwrap().keep().join("body.bin");
        let mut node = HttpFetchNode::new(spec(
            &format!("http://127.0.0.1:{port}/jump"),
            &out.to_string_lossy(),
        ));
        let ctx = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        let error = node
            .execute_with_allowlist(&ctx, Some(vec!["127.0.0.1".into()]))
            .await
            .unwrap_err();
        assert!(
            error
                .to_string()
                .contains("not on the HTTP fetch allowlist"),
            "{error}"
        );
        assert!(
            matches!(error, HttpFetchError::RedirectRefused { .. }),
            "{error}"
        );
        assert!(
            !out.exists(),
            "no body may be written for a refused redirect"
        );
    }

    #[tokio::test]
    async fn oversized_bodies_are_refused() {
        let port = one_shot_server(
            b"HTTP/1.1 200 OK\r\ncontent-length: 100\r\nconnection: close\r\n\r\n0123456789\
              0123456789012345678901234567890123456789012345678901234567890123456789012345678\
              90123456789",
        )
        .await;
        let out = tempfile::tempdir().unwrap().keep().join("big.bin");
        let mut http_spec = spec(
            &format!("http://127.0.0.1:{port}/big.bin"),
            &out.to_string_lossy(),
        );
        http_spec.max_bytes = 50;
        let mut node = HttpFetchNode::new(http_spec);
        let ctx = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        let error = node
            .execute_with_allowlist(&ctx, Some(vec!["127.0.0.1".into()]))
            .await
            .unwrap_err();
        assert!(error.to_string().contains("max_bytes (50)"), "{error}");
    }
}
