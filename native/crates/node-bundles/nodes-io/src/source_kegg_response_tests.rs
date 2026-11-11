use async_trait::async_trait;
use kegg::client::{CapturedResponse, KeggClient, ResponseTransport};
use kegg::error::Result;
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::sync::Arc;

#[derive(Debug)]
struct Reply {
    status: u16,
    body: String,
    content_type: Option<String>,
    wrong_final_url: bool,
}

#[async_trait]
impl ResponseTransport for Reply {
    async fn response(&self, url: &str) -> Result<CapturedResponse> {
        Ok(CapturedResponse {
            url: url.into(),
            response_url: if self.wrong_final_url {
                "https://wrong.example/".into()
            } else {
                url.into()
            },
            status: self.status,
            body: self.body.clone(),
            headers: self
                .content_type
                .clone()
                .map(|value| BTreeMap::from([("content-type".into(), value)]))
                .unwrap_or_default(),
        })
    }
}

fn mapping() -> String {
    "hsa:10458\tpath:hsa00010\n".into()
}
fn hierarchy() -> String {
    json!({"name":"br08901","children":[{"name":"Metabolism","children":[{"name":"00010 Synthetic pathway"}]}]}).to_string()
}

async fn observe(
    name: &str,
    status: u16,
    body: String,
    content_type: Option<&str>,
    wrong_final_url: bool,
    json_route: bool,
    rejects_before: bool,
    rejects_after: bool,
) {
    let fixed = true;
    let client = KeggClient::with_rate_limit(3)
        .unwrap()
        .with_transport(Arc::new(Reply {
            status,
            body: body.clone(),
            content_type: content_type.map(str::to_owned),
            wrong_final_url,
        }));
    let result = if json_route {
        client
            .brite_json::<Value>("br:br08901")
            .await
            .map(|value| json!(value))
    } else {
        client.link("pathway", "hsa").await.map(|pairs| {
            json!(
                pairs
                    .iter()
                    .map(|pair| (&pair.source, &pair.target))
                    .collect::<Vec<_>>()
            )
        })
    };
    assert_eq!(
        result.is_err(),
        if fixed { rejects_after } else { rejects_before },
        "{name}: {result:?}"
    );
    let received = client.captured_responses();
    assert_eq!(received.len(), 1);
    assert_eq!(received[0].body, body);
    let record = json!({"name":name,"fixed":fixed,"status":status,"body":body,"content_type":content_type,"wrong_final_url":wrong_final_url,"json_route":json_route,"accepted":result.is_ok(),"error":result.err().map(|error|error.to_string()),"synthetic_transport":true,"captured_response_count":received.len(),"g0_granted":false});
    let Some(root) = std::env::var_os("KEGG_COUNTER_DIR") else {
        return;
    };
    let root = std::path::PathBuf::from(root);
    std::fs::write(
        root.join(format!("response-{name}.json")),
        serde_json::to_vec_pretty(&record).unwrap(),
    )
    .unwrap();
}

#[tokio::test]
async fn only_complete_200_response_is_success() {
    for status in [201, 202, 204, 206] {
        observe(
            &format!("status-{status}"),
            status,
            mapping(),
            Some("text/plain"),
            false,
            false,
            false,
            true,
        )
        .await;
    }
}

#[tokio::test]
async fn final_url_must_match_both_declared_operations() {
    observe(
        "text-wrong-url",
        200,
        mapping(),
        Some("text/plain"),
        true,
        false,
        false,
        true,
    )
    .await;
    observe(
        "json-wrong-url",
        200,
        hierarchy(),
        Some("application/json"),
        true,
        true,
        false,
        true,
    )
    .await;
}

#[tokio::test]
async fn link_requires_plain_text_media_type() {
    for (name, mime) in [
        ("text-missing-mime", None),
        ("text-html-mime", Some("text/html")),
        ("text-json-mime", Some("application/json")),
    ] {
        observe(name, 200, mapping(), mime, false, false, false, true).await;
    }
}

#[tokio::test]
async fn brite_requires_json_media_type() {
    for (name, mime) in [
        ("json-missing-mime", None),
        ("json-html-mime", Some("text/html")),
        ("json-plain-mime", Some("text/plain")),
    ] {
        observe(name, 200, hierarchy(), mime, false, true, false, true).await;
    }
}

#[tokio::test]
async fn brite_error_documents_cannot_become_success() {
    for field in ["error", "errors", "detail", "message", "status"] {
        let mut value: Value = serde_json::from_str(&hierarchy()).unwrap();
        value[field] = json!("Synthetic diagnostic");
        observe(
            &format!("json-{field}"),
            200,
            value.to_string(),
            Some("application/json"),
            false,
            true,
            false,
            true,
        )
        .await;
    }
}

#[tokio::test]
async fn valid_text_json_and_empty_controls_are_preserved() {
    for (name, mime) in [
        ("text-control", "text/plain"),
        ("text-charset-control", "text/plain; charset=utf-8"),
        ("text-case-control", "TEXT/PLAIN"),
    ] {
        observe(name, 200, mapping(), Some(mime), false, false, false, false).await;
    }
    for (name, mime) in [
        ("json-control", "application/json"),
        ("json-charset-control", "application/json; charset=utf-8"),
        ("json-case-control", "APPLICATION/JSON"),
    ] {
        observe(
            name,
            200,
            hierarchy(),
            Some(mime),
            false,
            true,
            false,
            false,
        )
        .await;
    }
    observe(
        "text-empty-control",
        200,
        String::new(),
        Some("text/plain"),
        false,
        false,
        false,
        false,
    )
    .await;
}

#[tokio::test]
async fn official_failure_status_controls_stay_rejected_and_captured() {
    for status in [400, 404] {
        observe(
            &format!("status-{status}-control"),
            status,
            String::new(),
            Some("text/plain"),
            false,
            false,
            true,
            true,
        )
        .await;
    }
}
