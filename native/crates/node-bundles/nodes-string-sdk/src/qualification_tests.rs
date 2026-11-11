use crate::StringDbClient;
use crate::client::{CapturedRequest, CapturedResponse, ResponseTransport};
use crate::nodes::{StringIdMapNode, StringIdMapSpec, StringNetworkNode, StringNetworkSpec};
use arrow_array::{Array, Float64Array, StringArray, UInt64Array};
use async_trait::async_trait;
use dag_core::dag::node_event::NodeReporter;
use dag_core::dag::{DagNode, NodeInput};
use dag_core::registry::NodeCtx;
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};
use std::sync::{Arc, Mutex};

#[derive(Debug)]
struct Reply {
    body: String,
    status: u16,
    mismatch: bool,
    requests: Mutex<Vec<CapturedRequest>>,
}

#[async_trait]
impl ResponseTransport for Reply {
    async fn response(&self, request: &CapturedRequest) -> crate::Result<CapturedResponse> {
        self.requests.lock().unwrap().push(request.clone());
        let mut returned = request.clone();
        if self.mismatch {
            returned.url.push_str("?wrong-request");
        }
        Ok(CapturedResponse {
            request: returned,
            status: self.status,
            body: self.body.clone(),
        })
    }
}

fn fixed() -> bool {
    true
}
fn save(name: &str, value: Value) {
    let Some(root) = std::env::var_os("STRING_COUNTER_DIR") else {
        return;
    };
    let root = std::path::PathBuf::from(root);
    std::fs::write(
        root.join(format!("{name}.json")),
        serde_json::to_vec_pretty(&value).unwrap(),
    )
    .unwrap();
}
fn spec(kind: &str) -> Value {
    let mut value = json!({"identifiers":["TP53","CDK2"],"species":"9606","endpoint":"https://version-12-0.string-db.org","caller_identity":"synthetic-node-test"});
    if kind == "network" {
        value["network_type"] = json!("physical");
        value["required_score"] = json!(400);
    }
    value
}
fn valid(kind: &str) -> Value {
    if kind == "idmap" {
        json!([
            {"queryIndex":0,"queryItem":"TP53","stringId":"9606.ENSP00000269305","preferredName":"TP53","ncbiTaxonId":9606,"taxonName":"Homo sapiens","annotation":"Synthetic protein annotation"},
            {"queryIndex":1,"queryItem":"CDK2","stringId":"9606.ENSP00000266970","preferredName":"CDK2","ncbiTaxonId":9606,"taxonName":"Homo sapiens","annotation":"Synthetic protein annotation"}
        ])
    } else {
        json!([{"stringId_A":"9606.ENSP00000269305","stringId_B":"9606.ENSP00000266970","preferredName_A":"TP53","preferredName_B":"CDK2","ncbiTaxonId":"9606","score":0.8,"nscore":0.1,"fscore":0.2,"pscore":0.3,"ascore":0.4,"escore":0.5,"dscore":0.6,"tscore":0.7}])
    }
}

async fn execute(
    kind: &str,
    config: Value,
    body: String,
    status: u16,
    mismatch: bool,
    extra_input: bool,
) -> (Result<Value, String>, Value) {
    let reply = Arc::new(Reply {
        body: body.clone(),
        status,
        mismatch,
        requests: Mutex::new(vec![]),
    });
    let session = SessionContext::new();
    let context = NodeCtx::new(session.runtime_env(), None);
    let result = async {
        let client = Arc::new(StringDbClient::builder().endpoint(config["endpoint"].as_str().unwrap()).caller_identity(config["caller_identity"].as_str().unwrap()).disable_rate_limit().build().map_err(|error| error.to_string())?.with_transport(reply.clone()));
        let mut node: Box<dyn DagNode> = if kind == "idmap" {
            Box::new(StringIdMapNode::with_client(serde_json::from_value::<StringIdMapSpec>(config.clone()).map_err(|error| error.to_string())?, client))
        } else {
            Box::new(StringNetworkNode::with_client(serde_json::from_value::<StringNetworkSpec>(config.clone()).map_err(|error| error.to_string())?, client))
        };
        let inputs = if extra_input { vec![NodeInput::file(0,dag_core::value::FileRef::new("vfs:///unrequested.tsv",Some("tsv".into())))] } else { vec![] };
        let outputs = node.execute(&context,&inputs,&NodeReporter::noop()).await.map_err(|error| error.to_string())?;
        let table = outputs.dataframe(0).map_err(|error| error.to_string())?;
        let fields = table.schema().fields().iter().map(|field|json!({"name":field.name(),"type":field.data_type().to_string(),"nullable":field.is_nullable()})).collect::<Vec<_>>();
        let mut rows = vec![];
        for batch in table.clone().collect().await.map_err(|error| error.to_string())? {
            for row_index in 0..batch.num_rows() {
                let mut row = serde_json::Map::new();
                for (column_index,field) in batch.schema().fields().iter().enumerate() {
                    let array = batch.column(column_index);
                    let value = if array.is_null(row_index) { Value::Null }
                    else if let Some(array) = array.as_any().downcast_ref::<UInt64Array>() { json!(array.value(row_index)) }
                    else if let Some(array) = array.as_any().downcast_ref::<Float64Array>() { json!(array.value(row_index)) }
                    else if let Some(array) = array.as_any().downcast_ref::<StringArray>() { json!(array.value(row_index)) }
                    else { return Err(format!("unexpected original publisher type: {}",field.data_type())); };
                    row.insert(field.name().clone(),value);
                }
                rows.push(Value::Object(row));
            }
        }
        Ok(json!({"fields":fields,"rows":rows}))
    }.await;
    let trace = json!({"raw":body,"status":status,"returned_request_mismatch":mismatch,"extra_input":extra_input,"requests":*reply.requests.lock().unwrap()});
    (result, trace)
}

async fn blocked(
    name: &str,
    kind: &str,
    config: Value,
    payload: String,
    status: u16,
    mismatch: bool,
    extra: bool,
) {
    let (result, trace) = execute(kind, config.clone(), payload, status, mismatch, extra).await;
    save(
        name,
        json!({"fixed":fixed(),"kind":kind,"config":config,"accepted":result.is_ok(),"output":result.as_ref().ok(),"error":result.as_ref().err(),"trace":trace,"g0_granted":false}),
    );
    assert_eq!(
        result.is_ok(),
        !fixed(),
        "actual before/after acceptance differs for {name}: {result:?}"
    );
}

#[tokio::test]
async fn config_and_input_cannot_be_silently_ignored() {
    for kind in ["idmap", "network"] {
        let mut config = spec(kind);
        config["invented_official"] = json!(true);
        blocked(
            &format!("{kind}-unknown-control"),
            kind,
            config,
            valid(kind).to_string(),
            200,
            false,
            false,
        )
        .await;
        blocked(
            &format!("{kind}-extra-input"),
            kind,
            spec(kind),
            valid(kind).to_string(),
            200,
            false,
            true,
        )
        .await;
    }
}

#[tokio::test]
async fn identifiers_and_numeric_species_cannot_change_request_meaning() {
    for kind in ["idmap", "network"] {
        for name in [
            "newline-id",
            "carriage-return-id",
            "zero-species",
            "nonnumeric-species",
        ] {
            let mut config = spec(kind);
            match name {
                "newline-id" => config["identifiers"] = json!(["TP53\nUNREQUESTED", "CDK2"]),
                "carriage-return-id" => {
                    config["identifiers"] = json!(["TP53\rUNREQUESTED", "CDK2"])
                }
                "zero-species" => config["species"] = json!("0"),
                _ => config["species"] = json!("not-a-numeric-taxon"),
            }
            blocked(
                &format!("{kind}-{name}"),
                kind,
                config,
                valid(kind).to_string(),
                200,
                false,
                false,
            )
            .await;
        }
    }
}

#[tokio::test]
async fn repeated_input_identifiers_keep_their_distinct_query_positions() {
    for kind in ["idmap", "network"] {
        let mut config = spec(kind);
        config["identifiers"] = json!(["TP53", "TP53"]);
        let mut payload = valid(kind);
        if kind == "idmap" {
            payload[1] = payload[0].clone();
            payload[1]["queryIndex"] = json!(1);
        }
        let (result, trace) =
            execute(kind, config.clone(), payload.to_string(), 200, false, false).await;
        let output = result.unwrap();
        if kind == "idmap" {
            assert_eq!(output["rows"].as_array().unwrap().len(), 2);
            assert_eq!(output["rows"][0]["query_index"], json!(0));
            assert_eq!(output["rows"][1]["query_index"], json!(1));
        }
        save(
            &format!("{kind}-duplicate-id"),
            json!({"fixed":fixed(),"kind":kind,"config":config,"accepted":true,"output":output,"trace":trace,"g0_granted":false}),
        );
    }
}

#[tokio::test]
async fn mapping_index_identity_and_species_are_checked() {
    for name in [
        "out-of-range-query-index",
        "duplicate-query-index",
        "blank-string-id",
        "zero-taxon",
        "wrong-taxon",
        "wrong-protein-taxon",
        "wrong-query-echo",
    ] {
        let mut payload = valid("idmap");
        match name {
            "out-of-range-query-index" => payload[0]["queryIndex"] = json!(99),
            "duplicate-query-index" => payload[1]["queryIndex"] = json!(0),
            "blank-string-id" => payload[0]["stringId"] = json!(""),
            "zero-taxon" => payload[0]["ncbiTaxonId"] = json!(0),
            "wrong-taxon" => payload[0]["ncbiTaxonId"] = json!(10090),
            "wrong-protein-taxon" => payload[0]["stringId"] = json!("10090.UNREQUESTED"),
            _ => payload[0]["queryItem"] = json!("UNREQUESTED"),
        }
        blocked(
            name,
            "idmap",
            spec("idmap"),
            payload.to_string(),
            200,
            false,
            false,
        )
        .await;
    }
}

#[tokio::test]
async fn all_network_confidence_fields_and_taxon_identity_are_checked() {
    for field in [
        "score", "nscore", "fscore", "pscore", "ascore", "escore", "dscore", "tscore",
    ] {
        for value in [-0.1, 1.1] {
            let mut payload = valid("network");
            payload[0][field] = json!(value);
            blocked(
                &format!(
                    "{field}-{}",
                    if value < 0.0 { "negative" } else { "too-large" }
                ),
                "network",
                spec("network"),
                payload.to_string(),
                200,
                false,
                false,
            )
            .await;
        }
    }
    for name in [
        "blank-network-id",
        "wrong-network-taxon",
        "zero-network-taxon",
        "unprojectable-network-taxon",
        "wrong-network-id-taxon",
        "below-required-score",
    ] {
        let mut payload = valid("network");
        match name {
            "blank-network-id" => payload[0]["stringId_A"] = json!(" "),
            "wrong-network-taxon" => payload[0]["ncbiTaxonId"] = json!("10090"),
            "zero-network-taxon" => payload[0]["ncbiTaxonId"] = json!(0),
            "unprojectable-network-taxon" => payload[0]["ncbiTaxonId"] = json!("not-a-taxon"),
            "wrong-network-id-taxon" => payload[0]["stringId_B"] = json!("10090.UNREQUESTED"),
            _ => payload[0]["score"] = json!(0.1),
        }
        blocked(
            name,
            "network",
            spec("network"),
            payload.to_string(),
            200,
            false,
            false,
        )
        .await;
    }
}

#[tokio::test]
async fn complete_response_protocol_is_not_inferred_from_successful_decode() {
    for kind in ["idmap", "network"] {
        blocked(
            &format!("{kind}-http-202"),
            kind,
            spec(kind),
            valid(kind).to_string(),
            202,
            false,
            false,
        )
        .await;
        blocked(
            &format!("{kind}-request-identity"),
            kind,
            spec(kind),
            valid(kind).to_string(),
            200,
            true,
            false,
        )
        .await;
        let mut payload = valid(kind);
        let error_index = 1usize.min(payload.as_array().unwrap().len() - 1);
        payload[error_index]["status"] = json!("error");
        if kind == "network" {
            let first = valid(kind)[0].clone();
            payload.as_array_mut().unwrap().insert(0, first);
        }
        blocked(
            &format!("{kind}-later-shaped-error-row"),
            kind,
            spec(kind),
            payload.to_string(),
            200,
            false,
            false,
        )
        .await;
        let mut config = spec(kind);
        config["endpoint"] = json!("https://version-12-0.string-db.org?shadow=1");
        blocked(
            &format!("{kind}-endpoint-query"),
            kind,
            config,
            valid(kind).to_string(),
            200,
            false,
            false,
        )
        .await;
    }
    let payload = valid("network")
        .to_string()
        .replace("\"score\":0.8", "\"score\":0.1,\"score\":0.8");
    blocked(
        "duplicate-json-score-key",
        "network",
        spec("network"),
        payload,
        200,
        false,
        false,
    )
    .await;
}

#[tokio::test]
async fn absent_channels_are_not_invented_as_zero() {
    let mut payload = valid("network");
    for field in [
        "nscore", "fscore", "pscore", "ascore", "escore", "dscore", "tscore",
    ] {
        payload[0].as_object_mut().unwrap().remove(field);
    }
    let (result, trace) = execute(
        "network",
        spec("network"),
        payload.to_string(),
        200,
        false,
        false,
    )
    .await;
    let output = result.unwrap();
    for column in [
        "neighborhood_score",
        "fusion_score",
        "cooccurrence_score",
        "coexpression_score",
        "experimental_score",
        "database_score",
        "textmining_score",
    ] {
        assert_eq!(
            output["rows"][0][column],
            if fixed() { Value::Null } else { json!(0.0) }
        );
    }
    save(
        "missing-channels",
        json!({"fixed":fixed(),"kind":"network","config":spec("network"),"output":output,"trace":trace,"g0_granted":false}),
    );
}

#[tokio::test]
async fn all_original_output_columns_and_semantics_are_preserved() {
    for kind in ["idmap", "network"] {
        let (result, trace) =
            execute(kind, spec(kind), valid(kind).to_string(), 200, false, false).await;
        let output = result.unwrap();
        assert_eq!(
            output["fields"].as_array().unwrap().len(),
            if kind == "idmap" { 7 } else { 13 }
        );
        save(
            &format!("{kind}-complete-output"),
            json!({"fixed":fixed(),"kind":kind,"config":spec(kind),"output":output,"trace":trace,"g0_granted":false}),
        );
    }
}

#[tokio::test]
async fn validated_network_identifiers_are_actually_sent_normalized() {
    let mut config = spec("network");
    config["identifiers"] = json!([" TP53 ", " CDK2 "]);
    let (result, trace) = execute(
        "network",
        config.clone(),
        valid("network").to_string(),
        200,
        false,
        false,
    )
    .await;
    assert!(result.is_ok());
    let body = trace["requests"][0]["body"].as_str().unwrap();
    assert_eq!(body.contains("identifiers=TP53%0DCDK2"), fixed());
    save(
        "normalized-network-identifiers",
        json!({"fixed":fixed(),"kind":"network","config":config,"output":result.unwrap(),"trace":trace,"g0_granted":false}),
    );
}
