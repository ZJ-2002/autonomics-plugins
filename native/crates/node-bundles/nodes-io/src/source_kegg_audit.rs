use dag_core::dag::DagError;
use dag_core::registry::NodeCtx;
use kegg::KeggClient;

pub async fn save(
    ctx: &NodeCtx,
    path: &Option<String>,
    client: &KeggClient,
    details: serde_json::Value,
) -> Result<(), DagError> {
    let Some(path) = path else {
        return Ok(());
    };
    let mut responses = Vec::new();
    for (index, response) in client.captured_responses().into_iter().enumerate() {
        let file = super::publication::write_artifact(
            ctx,
            &format!("{path}.response-{index}.txt"),
            response.body.into_bytes(),
            "txt",
        )
        .await?;
        responses
            .push(serde_json::json!({"url":response.url,"response_url":response.response_url,"headers":response.headers,"status":response.status,"response":file}));
    }
    let body = serde_json::json!({"schema_version":2,"stage":"RAW_LOOKUP_NOT_NODE_COMPLETION","responses":responses,"details":details,
        "scope":"KEGG_RECEIVED_UTF8_QUERY_AUDIT_NOT_OFFICIAL_SOURCE_OR_SCIENTIFIC_QUALIFICATION","g0_granted":false});
    super::publication::write_artifact(
        ctx,
        path,
        serde_json::to_vec_pretty(&body).map_err(|error| DagError::Schedule(error.to_string()))?,
        "json",
    )
    .await?;
    Ok(())
}
