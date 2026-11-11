use chembl::ChEMBLClient;
use dag_core::dag::DagError;
use dag_core::registry::NodeCtx;

pub async fn save(
    ctx: &NodeCtx,
    path: &Option<String>,
    client: &ChEMBLClient,
    details: serde_json::Value,
) -> Result<(), DagError> {
    let Some(path) = path else {
        return Ok(());
    };
    let mut responses = Vec::new();
    for (index, response) in client.captured_responses().into_iter().enumerate() {
        let format = if serde_json::from_str::<serde_json::Value>(&response.body).is_ok() {
            "json"
        } else {
            "txt"
        };
        let file = super::publication::write_artifact(
            ctx,
            &format!("{path}.response-{index}.{format}"),
            response.body.into_bytes(),
            format,
        )
        .await?;
        responses
            .push(serde_json::json!({"url":response.url,"status":response.status,"response":file}));
    }
    let body = serde_json::json!({"schema_version":1,"stage":"RAW_LOOKUP_NOT_NODE_COMPLETION","responses":responses,"details":details,
        "scope":"CHEMBL_RECEIVED_UTF8_QUERY_AUDIT_NOT_OFFICIAL_SOURCE_OR_SCIENTIFIC_QUALIFICATION","g0_granted":false});
    super::publication::write_artifact(
        ctx,
        path,
        serde_json::to_vec_pretty(&body).map_err(|error| DagError::Schedule(error.to_string()))?,
        "json",
    )
    .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use chembl::client::{CapturedResponse, ResponseTransport};
    use std::sync::Arc;

    #[derive(Debug)]
    struct ErrorBody(String);

    #[async_trait::async_trait]
    impl ResponseTransport for ErrorBody {
        async fn response(&self, url: &str) -> chembl::error::Result<CapturedResponse> {
            Ok(CapturedResponse {
                url: url.into(),
                status: 503,
                body: self.0.clone(),
            })
        }
    }

    #[tokio::test]
    async fn error_audit_labels_actual_json_and_text_without_changing_received_bytes() {
        for (body, format) in [
            ("<html>temporarily unavailable</html>\n", "txt"),
            ("service unavailable\n", "txt"),
            ("{\"error_message\":\"temporarily unavailable\"}\n", "json"),
        ] {
            let ctx = NodeCtx::new(
                datafusion::prelude::SessionContext::new().runtime_env(),
                Some(Arc::new(vfs::OpendalFileStorage::new_temp())),
            );
            let client = ChEMBLClient::with_endpoint("http://fixture.invalid")
                .with_transport(Arc::new(ErrorBody(body.into())));
            assert!(client.get_json("activity.json", None).await.is_err());
            let path = Some("vfs:///audit.json".to_owned());
            save(
                &ctx,
                &path,
                &client,
                serde_json::json!({"lookup_failed":true}),
            )
            .await
            .unwrap();
            let metadata: serde_json::Value = serde_json::from_slice(
                &super::super::publication::read_file_bytes(&ctx, "vfs:///audit.json")
                    .await
                    .unwrap(),
            )
            .unwrap();
            assert_eq!(metadata["stage"], "RAW_LOOKUP_NOT_NODE_COMPLETION");
            assert_eq!(metadata["g0_granted"], false);
            assert_eq!(metadata["responses"].as_array().unwrap().len(), 1);
            let response = &metadata["responses"][0];
            assert_eq!(response["status"], 503);
            assert_eq!(response["url"], "http://fixture.invalid/activity.json");
            let file: dag_core::value::FileRef =
                serde_json::from_value(response["response"].clone()).unwrap();
            assert_eq!(file.format.as_deref(), Some(format));
            assert_eq!(file.path, format!("vfs:///audit.json.response-0.{format}"));
            let received = super::super::publication::read_file_bytes(&ctx, &file.path)
                .await
                .unwrap();
            assert_eq!(received, body.as_bytes());
            assert_eq!(file.fingerprint.unwrap().size, received.len() as u64);
            assert!(
                save(&ctx, &path, &client, serde_json::json!({}))
                    .await
                    .is_err()
            );
            assert_eq!(
                super::super::publication::read_file_bytes(&ctx, &file.path)
                    .await
                    .unwrap(),
                received
            );
        }
    }
}
