use dag_core::dag::DagError;
use dag_core::registry::NodeCtx;
use opentargets::OpenTargetsClient;

pub async fn save(
    ctx: &NodeCtx,
    path: &Option<String>,
    client: &OpenTargetsClient,
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
        let file = super::search_publication::write_artifact(
            ctx,
            &format!("{path}.response-{index}.{format}"),
            response.body.into_bytes(),
            format,
        )
        .await?;
        responses
            .push(serde_json::json!({"url":response.url,"request":response.request,"status":response.status,"response":file}));
    }
    let body = serde_json::json!({"schema_version":1,"stage":"RAW_LOOKUP_NOT_NODE_COMPLETION","responses":responses,"details":details,
        "scope":"OPENTARGETS_RECEIVED_UTF8_QUERY_AUDIT_NOT_OFFICIAL_SOURCE_OR_SCIENTIFIC_QUALIFICATION","g0_granted":false});
    super::search_publication::write_artifact(
        ctx,
        path,
        serde_json::to_vec_pretty(&body).map_err(|error| DagError::Schedule(error.to_string()))?,
        "json",
    )
    .await?;
    Ok(())
}
