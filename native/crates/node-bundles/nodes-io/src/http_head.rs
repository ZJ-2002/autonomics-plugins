//! Read remote representation metadata without a GET or response-body read.

use std::time::Duration;

use async_trait::async_trait;
use dag_core::node::{DagNode, NodeInput, NodePorts};
use dag_core::value::PortType;
use dag_core::{
    dag::DagError,
    dag::graph::PortOutputs,
    registry::{NodeCtx, NodeFactory},
};
use reqwest::header::{ACCEPT_ENCODING, CONTENT_LENGTH, HeaderMap, HeaderName};
use schemars::{JsonSchema, schema_for};
use serde::{Deserialize, Serialize};
use thiserror::Error;

use crate::net_policy::{
    NetworkPolicyError, ensure_host_allowed, load_allowlist_from_env, redirect_policy,
};

pub const HTTP_HEAD_KIND: &str = "http_head";

#[derive(Debug, Error)]
pub enum HttpHeadError {
    #[error("invalid http_head spec or response: {0}")]
    Invalid(String),
    #[error(transparent)]
    Policy(#[from] NetworkPolicyError),
    #[error("HTTP HEAD request failed: {details}")]
    Request {
        #[source]
        source: reqwest::Error,
        details: String,
    },
    #[error("HTTP HEAD returned {0}; no GET fallback was attempted")]
    Status(reqwest::StatusCode),
    #[error(transparent)]
    Write(#[from] crate::http_fetch::HttpFetchError),
}

impl From<reqwest::Error> for HttpHeadError {
    fn from(source: reqwest::Error) -> Self {
        let mut details = source.to_string();
        let mut cause = std::error::Error::source(&source);
        while let Some(error) = cause {
            details.push_str(": ");
            details.push_str(&error.to_string());
            cause = error.source();
        }
        Self::Request { source, details }
    }
}

impl dag_core::dag::NodeError for HttpHeadError {
    fn node_type(&self) -> &str {
        HTTP_HEAD_KIND
    }
}

#[derive(Debug, Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct HttpHeadSpec {
    /// Absolute HTTP(S) URL. Embedded username/password and fragments are refused.
    url: String,
    /// JSON metadata output path, including vfs:///… paths.
    path: String,
    /// Total request timeout in seconds, including redirects (1 through 300).
    #[serde(default = "default_timeout")]
    #[schemars(range(min = 1, max = 300))]
    timeout_secs: u64,
    /// Fail if the server omits Content-Length. Never substitute zero or a directory estimate.
    #[serde(default = "default_require_length")]
    require_content_length: bool,
}

fn default_timeout() -> u64 {
    30
}
fn default_require_length() -> bool {
    true
}

#[derive(Debug, Serialize, Deserialize)]
pub struct HttpHeadMetadata {
    pub schema_version: u32,
    pub method: String,
    pub requested_url: String,
    pub final_url: String,
    pub status_code: u16,
    pub requested_at_utc: String,
    pub observed_at_utc: String,
    /// Server-declared representation bytes, not measured payload bytes or decompressed size.
    pub content_length: Option<u64>,
    pub etag: Option<String>,
    pub last_modified: Option<String>,
    pub accept_ranges: Option<String>,
    pub content_type: Option<String>,
    pub content_encoding: Option<String>,
    pub request_accept_encoding: String,
    pub response_body_read: bool,
    pub payload_checksum_verified: bool,
}

fn validate(spec: &HttpHeadSpec) -> Result<reqwest::Url, HttpHeadError> {
    let url = reqwest::Url::parse(&spec.url).map_err(|e| HttpHeadError::Invalid(e.to_string()))?;
    if !matches!(url.scheme(), "http" | "https")
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.fragment().is_some()
        || spec.path.trim().is_empty()
        || !(1..=300).contains(&spec.timeout_secs)
    {
        return Err(HttpHeadError::Invalid(
            "HTTP(S) URL without credentials/fragment, output path and timeout_secs in 1..=300 required"
                .into(),
        ));
    }
    Ok(url)
}

fn header(headers: &HeaderMap, name: HeaderName) -> Result<Option<String>, HttpHeadError> {
    let mut values = headers.get_all(&name).iter();
    let Some(value) = values.next() else {
        return Ok(None);
    };
    if values.next().is_some() {
        return Err(HttpHeadError::Invalid(format!("multiple {name} headers")));
    }
    value
        .to_str()
        .map(|v| Some(v.to_string()))
        .map_err(|_| HttpHeadError::Invalid(format!("non-text {name} header")))
}

fn length(headers: &HeaderMap, required: bool) -> Result<Option<u64>, HttpHeadError> {
    // Response::content_length() can describe HEAD's empty body. Read the actual header.
    let value = header(headers, CONTENT_LENGTH)?;
    match value {
        Some(v) if !v.is_empty() && v.bytes().all(|c| c.is_ascii_digit()) => v
            .parse()
            .map(Some)
            .map_err(|_| HttpHeadError::Invalid("Content-Length overflows u64".into())),
        Some(_) => Err(HttpHeadError::Invalid("invalid Content-Length".into())),
        None if required => Err(HttpHeadError::Invalid(
            "Content-Length is absent; exact remote size is unknown".into(),
        )),
        None => Ok(None),
    }
}

fn ports() -> NodePorts {
    NodePorts::new().add_output_port_of_type(None, PortType::File)
}

#[derive(Clone)]
pub struct HttpHeadNode {
    meta: NodePorts,
    spec: HttpHeadSpec,
}

impl HttpHeadNode {
    pub fn new(spec: HttpHeadSpec) -> Self {
        Self {
            meta: ports(),
            spec,
        }
    }

    async fn observe(&self, allowed: Vec<String>) -> Result<HttpHeadMetadata, HttpHeadError> {
        let url = validate(&self.spec)?;
        ensure_host_allowed(&url, &allowed)?;
        let client = reqwest::Client::builder()
            .user_agent(crate::net_policy::HTTP_USER_AGENT)
            .timeout(Duration::from_secs(self.spec.timeout_secs))
            .redirect(redirect_policy(allowed))
            .no_gzip()
            .no_brotli()
            .no_deflate()
            .no_zstd()
            .build()?;
        let requested_at_utc = chrono::Utc::now().to_rfc3339();
        let response = client
            .head(url)
            .header(ACCEPT_ENCODING, "identity")
            .send()
            .await?;
        if response.status() != reqwest::StatusCode::OK {
            return Err(HttpHeadError::Status(response.status()));
        }
        let headers = response.headers();
        if headers.contains_key(reqwest::header::CONTENT_RANGE) {
            return Err(HttpHeadError::Invalid(
                "Content-Range cannot describe a complete representation".into(),
            ));
        }
        let content_length = length(headers, self.spec.require_content_length)?;
        let content_encoding = header(headers, reqwest::header::CONTENT_ENCODING)?;
        if content_encoding
            .as_deref()
            .is_some_and(|v| !v.eq_ignore_ascii_case("identity"))
        {
            return Err(HttpHeadError::Invalid(
                "server ignored Accept-Encoding: identity".into(),
            ));
        }
        Ok(HttpHeadMetadata {
            schema_version: 1,
            method: "HEAD".into(),
            requested_url: self.spec.url.clone(),
            final_url: response.url().to_string(),
            status_code: response.status().as_u16(),
            requested_at_utc,
            observed_at_utc: chrono::Utc::now().to_rfc3339(),
            content_length,
            etag: header(headers, reqwest::header::ETAG)?,
            last_modified: header(headers, reqwest::header::LAST_MODIFIED)?,
            accept_ranges: header(headers, reqwest::header::ACCEPT_RANGES)?,
            content_type: header(headers, reqwest::header::CONTENT_TYPE)?,
            content_encoding,
            request_accept_encoding: "identity".into(),
            response_body_read: false,
            payload_checksum_verified: false,
        })
    }

    async fn run(&self, ctx: &NodeCtx, allowed: Vec<String>) -> Result<PortOutputs, HttpHeadError> {
        let metadata = self.observe(allowed).await?;
        let path = crate::file_to_dataframe::source_path(
            ctx,
            &crate::file_to_dataframe::normalize_path(&self.spec.path),
        );
        let mut bytes = serde_json::to_vec_pretty(&metadata).expect("metadata is serializable");
        bytes.push(b'\n');
        crate::http_fetch::write_body(ctx, &path, bytes).await?;
        let mut outputs = PortOutputs::new();
        outputs.insert_file(0, crate::http_fetch::file_output(&path));
        Ok(outputs)
    }
}

#[async_trait]
impl DagNode for HttpHeadNode {
    fn ports(&self) -> &NodePorts {
        &self.meta
    }
    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(self.clone())
    }
    fn kind(&self) -> &'static str {
        HTTP_HEAD_KIND
    }
    fn allows_cache_reuse(&self) -> bool {
        false
    }
    fn sink_path(&self) -> Option<&str> {
        Some(&self.spec.path)
    }
    fn as_any(&self) -> &dyn std::any::Any {
        self
    }
    async fn execute(
        &mut self,
        ctx: &NodeCtx,
        _inputs: &[NodeInput],
        _reporter: &dag_core::dag::node_event::NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        self.run(ctx, load_allowlist_from_env().map_err(HttpHeadError::from)?)
            .await
            .map_err(Into::into)
    }
}

pub struct HttpHeadNodeFactory;
impl NodeFactory for HttpHeadNodeFactory {
    fn kind(&self) -> &'static str {
        HTTP_HEAD_KIND
    }
    fn desc(&self) -> &'static str {
        "Queries allowlisted HTTP HEAD metadata without downloading the response body."
    }
    fn doc(&self) -> &'static str {
        "No inputs; one JSON File output. Sends HEAD only, with Accept-Encoding: identity; never falls back to GET. \
        Uses the shared deny-by-default host allowlist at every redirect and default TLS verification. \
        Records requested/final URL, HTTP status, UTC query times, server-declared Content-Length, ETag, \
        Last-Modified, Accept-Ranges and content type/encoding. Requires HTTP 200 and, by default, an exact \
        Content-Length; set require_content_length=false to record an unknown size as null. \
        Refuses partial or encoded representations. ETag is opaque, not a verified MD5. \
        HEAD metadata does not verify payload bytes, reserve resources or grant scientific admission."
    }
    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(HttpHeadSpec)
    }
    fn ports(&self) -> NodePorts {
        ports()
    }
    fn build(
        &self,
        spec: serde_json::Value,
        _ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec = serde_json::from_value(spec)?;
        validate(&spec).map_err(|e| dag_core::registry::error::Error::Unknown(e.to_string()))?;
        Ok(Box::new(HttpHeadNode::new(spec)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    fn spec(url: &str) -> HttpHeadSpec {
        HttpHeadSpec {
            url: url.into(),
            path: "/unused.json".into(),
            timeout_secs: 2,
            require_content_length: true,
        }
    }

    fn allowed() -> Vec<String> {
        vec!["127.0.0.1".into()]
    }

    async fn server(responses: Vec<String>) -> (String, tokio::task::JoinHandle<Vec<String>>) {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!(
            "http://127.0.0.1:{}/file.gz",
            listener.local_addr().unwrap().port()
        );
        let task = tokio::spawn(async move {
            let mut requests = Vec::new();
            for response in responses {
                let (mut socket, _) = listener.accept().await.unwrap();
                let mut bytes = Vec::new();
                while !bytes.ends_with(b"\r\n\r\n") {
                    let mut byte = [0u8; 1];
                    socket.read_exact(&mut byte).await.unwrap();
                    bytes.push(byte[0]);
                    assert!(bytes.len() < 16384);
                }
                requests.push(String::from_utf8(bytes).unwrap());
                socket.write_all(response.as_bytes()).await.unwrap();
            }
            requests
        });
        (url, task)
    }

    fn response(headers: &str) -> String {
        format!("HTTP/1.1 200 OK\r\nConnection: close\r\n{headers}\r\n")
    }

    #[test]
    fn validates_spec_and_rejects_unknown_fields() {
        for url in [
            "ftp://example.org/f",
            "file:///x",
            "https://u:p@example.org/f",
            "https://example.org/f#x",
        ] {
            assert!(validate(&spec(url)).is_err(), "{url}");
        }
        let mut s = spec("https://example.org/f");
        s.timeout_secs = 0;
        assert!(validate(&s).is_err());
        s.timeout_secs = u64::MAX;
        assert!(validate(&s).is_err());
        s.timeout_secs = 1;
        s.path = " ".into();
        assert!(validate(&s).is_err());
        assert!(
            serde_json::from_value::<HttpHeadSpec>(serde_json::json!({
                "url":"https://example.org/f", "path":"/x", "method":"GET"
            }))
            .is_err()
        );
    }

    #[test]
    fn lengths_are_exact_and_missing_is_not_zero() {
        let mut headers = HeaderMap::new();
        assert_eq!(length(&headers, false).unwrap(), None);
        assert!(length(&headers, true).is_err());
        for bad in ["-1", "+1", "1.4G", "1, 1", "18446744073709551616"] {
            headers.insert(CONTENT_LENGTH, bad.parse().unwrap());
            assert!(length(&headers, false).is_err(), "{bad}");
        }
        headers.insert(CONTENT_LENGTH, "0".parse().unwrap());
        assert_eq!(length(&headers, true).unwrap(), Some(0));
        headers.insert(CONTENT_LENGTH, "18446744073709551615".parse().unwrap());
        assert_eq!(length(&headers, true).unwrap(), Some(u64::MAX));
        headers.append(CONTENT_LENGTH, "1".parse().unwrap());
        assert!(length(&headers, false).is_err());
    }

    #[tokio::test]
    async fn head_preserves_large_representation_length_and_opaque_etag_without_a_body() {
        let (url, task) = server(vec![response("Content-Length: 1500000000\r\nETag: W/\"opaque\"\r\nLast-Modified: Tue, 01 Oct 2024 00:00:00 GMT\r\nAccept-Ranges: bytes\r\nContent-Type: application/gzip\r\n")]).await;
        let metadata = HttpHeadNode::new(spec(&url))
            .observe(allowed())
            .await
            .unwrap();
        assert_eq!(metadata.content_length, Some(1500000000));
        assert_eq!(metadata.etag.as_deref(), Some("W/\"opaque\""));
        assert_eq!(
            metadata.last_modified.as_deref(),
            Some("Tue, 01 Oct 2024 00:00:00 GMT")
        );
        assert_eq!(metadata.accept_ranges.as_deref(), Some("bytes"));
        assert_eq!(metadata.content_type.as_deref(), Some("application/gzip"));
        assert!(!metadata.response_body_read && !metadata.payload_checksum_verified);
        assert_eq!(metadata.requested_url, url);
        assert_eq!(metadata.final_url, url);
        chrono::DateTime::parse_from_rfc3339(&metadata.observed_at_utc).unwrap();
        let requests = task.await.unwrap();
        assert!(requests[0].starts_with("HEAD /file.gz HTTP/1.1\r\n"));
        assert!(
            requests[0]
                .to_lowercase()
                .contains("accept-encoding: identity\r\n")
        );
    }

    #[tokio::test]
    async fn missing_length_can_be_recorded_as_unknown_but_is_required_by_default() {
        let (url, task) = server(vec![response(""), response("")]).await;
        assert!(
            HttpHeadNode::new(spec(&url))
                .observe(allowed())
                .await
                .unwrap_err()
                .to_string()
                .contains("absent")
        );
        let mut s = spec(&url);
        s.require_content_length = false;
        let metadata = HttpHeadNode::new(s).observe(allowed()).await.unwrap();
        assert_eq!(metadata.content_length, None);
        assert_eq!(task.await.unwrap().len(), 2);
    }

    #[tokio::test]
    async fn error_statuses_never_trigger_get_or_publish_a_report() {
        for status in [
            "403 Forbidden",
            "404 Not Found",
            "405 Method Not Allowed",
            "500 Internal Server Error",
            "206 Partial Content",
        ] {
            let (url, task) = server(vec![format!(
                "HTTP/1.1 {status}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
            )])
            .await;
            let dir = tempfile::tempdir().unwrap();
            let mut s = spec(&url);
            s.path = dir.path().join("report.json").to_str().unwrap().into();
            let ctx = NodeCtx::new(
                datafusion::prelude::SessionContext::new().runtime_env(),
                None,
            );
            assert!(matches!(
                HttpHeadNode::new(s).run(&ctx, allowed()).await.unwrap_err(),
                HttpHeadError::Status(_)
            ));
            assert!(!dir.path().join("report.json").exists());
            let requests = task.await.unwrap();
            assert_eq!(requests.len(), 1);
            assert!(requests[0].starts_with("HEAD "));
        }
    }

    #[tokio::test]
    async fn initial_host_denial_happens_before_connecting() {
        let error = HttpHeadNode::new(spec("http://127.0.0.1:1/f"))
            .observe(vec!["example.org".into()])
            .await
            .unwrap_err();
        assert!(matches!(
            error,
            HttpHeadError::Policy(NetworkPolicyError::DomainNotAllowed { .. })
        ));
    }

    #[tokio::test]
    async fn allowed_redirect_stays_head_and_records_final_url() {
        let (url, task) = server(vec![
            "HTTP/1.1 302 Found\r\nLocation: /final.gz\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".into(),
            response("Content-Length: 1234\r\n")]).await;
        let metadata = HttpHeadNode::new(spec(&url))
            .observe(allowed())
            .await
            .unwrap();
        assert!(metadata.final_url.ends_with("/final.gz"));
        assert_eq!(metadata.requested_url, url);
        assert!(task.await.unwrap().iter().all(|r| r.starts_with("HEAD ")));
    }

    #[tokio::test]
    async fn denied_redirect_never_connects_to_target() {
        let (url, task) = server(vec!["HTTP/1.1 302 Found\r\nLocation: http://localhost:1/private\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".into()]).await;
        let error = HttpHeadNode::new(spec(&url))
            .observe(allowed())
            .await
            .unwrap_err();
        assert!(matches!(error, HttpHeadError::Request { ref source, .. } if source.is_redirect()));
        assert!(
            error
                .to_string()
                .contains("not on the HTTP fetch allowlist")
        );
        assert_eq!(task.await.unwrap().len(), 1);
    }

    #[tokio::test]
    async fn partial_or_encoded_metadata_is_refused() {
        for headers in [
            "Content-Length: 1\r\nContent-Range: bytes 0-0/100\r\n",
            "Content-Length: 1\r\nContent-Encoding: gzip\r\n",
        ] {
            let (url, task) = server(vec![response(headers)]).await;
            assert!(
                HttpHeadNode::new(spec(&url))
                    .observe(allowed())
                    .await
                    .is_err()
            );
            task.await.unwrap();
        }
    }

    #[tokio::test]
    async fn report_is_a_real_json_file_output() {
        let (url, task) = server(vec![response("Content-Length: 321\r\n")]).await;
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("metadata.json");
        let mut s = spec(&url);
        s.path = path.to_str().unwrap().into();
        let ctx = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        let outputs = HttpHeadNode::new(s).run(&ctx, allowed()).await.unwrap();
        assert!(matches!(
            outputs.get(&0),
            Some(dag_core::value::NodeValue::File(_))
        ));
        let metadata: HttpHeadMetadata =
            serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        assert_eq!(metadata.content_length, Some(321));
        task.await.unwrap();
    }

    #[test]
    fn http_head_is_registered_and_invalid_specs_fail_during_build() {
        let ctx = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        let mut registry = dag_core::NodeRegistry::new(ctx);
        registry.register_plugin(&crate::Plugin::new());
        assert!(
            registry
                .list_nodes()
                .iter()
                .any(|n| n.kind == HTTP_HEAD_KIND)
        );
        assert!(!HttpHeadNode::new(spec("https://example.org/f")).allows_cache_reuse());
        assert!(
            registry
                .build_node(
                    HTTP_HEAD_KIND,
                    serde_json::json!({
                        "url":"https://example.org/f", "path":"/metadata.json"
                    })
                )
                .is_ok()
        );
        assert!(
            registry
                .build_node(
                    HTTP_HEAD_KIND,
                    serde_json::json!({
                        "url":"ftp://example.org/f", "path":"/metadata.json"
                    })
                )
                .is_err()
        );
    }

    #[tokio::test]
    async fn request_timeout_is_enforced_without_get_fallback() {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let mut s = spec(&format!(
            "http://127.0.0.1:{}/slow",
            listener.local_addr().unwrap().port()
        ));
        s.timeout_secs = 1;
        let task = tokio::spawn(async move {
            let (_socket, _) = listener.accept().await.unwrap();
            std::future::pending::<()>().await;
        });
        let error = HttpHeadNode::new(s).observe(allowed()).await.unwrap_err();
        task.abort();
        assert!(task.await.unwrap_err().is_cancelled());
        assert!(matches!(error, HttpHeadError::Request { ref source, .. } if source.is_timeout()));
    }

    #[tokio::test]
    async fn metadata_publishes_through_vfs() {
        let (url, task) = server(vec![response("Content-Length: 456\r\n")]).await;
        let root = tempfile::tempdir().unwrap();
        let workspace = tempfile::tempdir().unwrap();
        let manifest = vfs::VfsManifest {
            backend: vec![vfs::BackendDefinition {
                id: "local".into(),
                config: vfs::BackendConfig::local("/"),
            }],
            mount: vec![vfs::MountDefinition {
                path: "/".into(),
                backend: "local".into(),
                source: root.path().to_str().unwrap().into(),
                read_only: false,
                permissions: Default::default(),
            }],
        };
        let mounted = vfs::MountedObjectStore::from_manifest(&manifest).unwrap();
        let storage = std::sync::Arc::new(vfs::OpendalFileStorage::with_mounts(
            workspace.path(),
            std::sync::Arc::new(mounted),
        ));
        let mut ctx = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        ctx.opendal = Some(storage);
        let mut s = spec(&url);
        s.path = "vfs:///metadata.json".into();
        let output = HttpHeadNode::new(s).run(&ctx, allowed()).await.unwrap();
        let dag_core::value::NodeValue::File(file) = output.get(&0).unwrap() else {
            panic!("not a file")
        };
        assert_eq!(file.path, "vfs:///metadata.json");
        let metadata: HttpHeadMetadata =
            serde_json::from_slice(&std::fs::read(root.path().join("metadata.json")).unwrap())
                .unwrap();
        assert_eq!(metadata.content_length, Some(456));
        task.await.unwrap();
    }
}
