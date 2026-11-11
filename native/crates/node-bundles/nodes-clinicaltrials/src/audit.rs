use crate::ClinicalTrialsClient;
use dag_core::dag::DagError;
use dag_core::registry::NodeCtx;

pub async fn save(
    ctx: &NodeCtx,
    path: &Option<String>,
    client: &ClinicalTrialsClient,
    details: serde_json::Value,
) -> Result<(), DagError> {
    let Some(path) = path else {
        return Ok(());
    };
    let mut responses = Vec::new();
    for (index, response) in client.captured_responses().into_iter().enumerate() {
        let json_body = response.headers.get("content-type").is_some_and(|value| {
            value
                .split(';')
                .next()
                .unwrap_or("")
                .trim()
                .eq_ignore_ascii_case("application/json")
        }) && serde_json::from_str::<serde_json::Value>(&response.body).is_ok();
        let extension = if json_body { "json" } else { "txt" };
        let format = if json_body { "json" } else { "text" };
        let file = crate::publication::write_artifact(
            ctx,
            &format!("{path}.response-{index}.{extension}"),
            response.body.into_bytes(),
            format,
        )
        .await?;
        responses
            .push(serde_json::json!({"url":response.url,"response_url":response.response_url,"status":response.status,"headers":response.headers,"response":file}));
    }
    let body = serde_json::json!({"schema_version":2,"stage":"RAW_LOOKUP_NOT_NODE_COMPLETION","responses":responses,"details":details,
        "scope":"CLINICALTRIALS_RECEIVED_UTF8_QUERY_AUDIT_NOT_OFFICIAL_SOURCE_OR_SCIENTIFIC_QUALIFICATION","g0_granted":false});
    crate::publication::write_artifact(
        ctx,
        path,
        serde_json::to_vec_pretty(&body).map_err(|error| DagError::Schedule(error.to_string()))?,
        "json",
    )
    .await?;
    Ok(())
}
