use crate::ReactomeClient;
use crate::client::{CapturedRequest, CapturedResponse, ResponseTransport};
use crate::nodes::analysis::{ReactomeAnalysisNode, ReactomeAnalysisSpec};
use crate::nodes::mapping::{ReactomeMappingNode, ReactomeMappingSpec};
use crate::nodes::pathways::{ReactomePathwaysNode, ReactomePathwaysSpec};
use arrow_array::{Array, BooleanArray, Float64Array, StringArray, UInt64Array};
use async_trait::async_trait;
use dag_core::dag::node_event::NodeReporter;
use dag_core::dag::{DagError, DagNode, NodeInput};
use dag_core::registry::NodeCtx;
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};
use std::sync::Arc;

#[derive(Debug)]
struct Reply {
    body: Value,
    status: u16,
    wrong_request: bool,
    requests: std::sync::Mutex<Vec<CapturedRequest>>,
}

#[async_trait]
impl ResponseTransport for Reply {
    async fn response(&self, request: &CapturedRequest) -> crate::Result<CapturedResponse> {
        self.requests.lock().unwrap().push(request.clone());
        let mut identity = request.clone();
        if self.wrong_request {
            identity.url.push_str("?wrong-response-identity");
        }
        Ok(CapturedResponse {
            request: identity,
            status: self.status,
            response_url: request.url.clone(),
            headers: std::collections::BTreeMap::from([(
                "content-type".into(),
                "application/json".into(),
            )]),
            body: self.body.to_string(),
        })
    }
}

fn fixed() -> bool {
    true
}

fn save(name: &str, value: Value) {
    let Some(root) = std::env::var_os("REACTOME_COUNTER_DIR") else {
        return;
    };
    let root = std::path::PathBuf::from(root);
    std::fs::write(
        root.join(format!("{name}.json")),
        serde_json::to_vec_pretty(&value).unwrap(),
    )
    .unwrap();
}

fn config(kind: &str) -> Value {
    match kind {
        "analysis" => json!({"identifiers":["TP53","BRCA1"],"project_to_human":true}),
        "mapping" => json!({"resource":"UniProt","identifier":"P04637"}),
        "pathways" => json!({"species":"Homo sapiens"}),
        _ => panic!("Unknown source kind"),
    }
}

fn valid(kind: &str) -> Value {
    match kind {
        "analysis" => {
            json!({"summary":{"token":"synthetic-analysis-token","projection":true,"interactors":false,"type":"OVERREPRESENTATION","includeDisease":true},"pathwaysFound":1,"identifiersNotFound":0,"pathways":[{"stId":"R-HSA-6796648","name":"Synthetic analysis pathway","entities":{"resource":"TOTAL","found":2,"total":86,"pValue":0.2,"fdr":0.8}}],"resourceSummary":[{"resource":"TOTAL","pathways":1,"filtered":1}]})
        }
        "mapping" => {
            json!([{"dbId":6796648,"stId":"R-HSA-6796648","displayName":"Synthetic mapped pathway","schemaClass":"Pathway"}])
        }
        "pathways" => {
            json!([{"dbId":1640170,"stId":"R-HSA-1640170","displayName":"Synthetic top-level pathway","schemaClass":"TopLevelPathway","speciesName":"Homo sapiens","isInDisease":false,"isInferred":false,"hasDiagram":true,"hasEHLD":false}])
        }
        _ => panic!("Unknown source kind"),
    }
}

async fn run(
    kind: &str,
    spec: Value,
    body: Value,
    status: u16,
    extra: bool,
    wrong_request: bool,
) -> std::result::Result<Value, DagError> {
    let transport = Arc::new(Reply {
        body,
        status,
        wrong_request,
        requests: std::sync::Mutex::new(vec![]),
    });
    let client = ReactomeClient::new().with_transport(transport.clone());
    let mut node: Box<dyn DagNode> = match kind {
        "analysis" => Box::new(ReactomeAnalysisNode::with_client(
            serde_json::from_value(spec).unwrap(),
            client,
        )),
        "mapping" => Box::new(ReactomeMappingNode::with_client(
            serde_json::from_value(spec).unwrap(),
            client,
        )),
        "pathways" => Box::new(ReactomePathwaysNode::with_client(
            serde_json::from_value(spec).unwrap(),
            client,
        )),
        _ => panic!("Unknown source kind"),
    };
    let ctx = NodeCtx::new(SessionContext::new().runtime_env(), None);
    let inputs = if extra {
        vec![NodeInput::file(
            0,
            dag_core::value::FileRef::new("vfs:///unused.tsv", Some("tsv".into())),
        )]
    } else {
        vec![]
    };
    let outputs = node.execute(&ctx, &inputs, &NodeReporter::noop()).await?;
    let table = outputs
        .dataframe(0)
        .map_err(|error| DagError::Schedule(error.to_string()))?;
    let fields = table.schema().fields().iter().map(|field|json!({"name":field.name(),"type":field.data_type().to_string(),"nullable":field.is_nullable()})).collect::<Vec<_>>();
    let batches = table
        .clone()
        .collect()
        .await
        .map_err(|error| DagError::Schedule(error.to_string()))?;
    let mut rows = vec![];
    for batch in batches {
        for row_index in 0..batch.num_rows() {
            let mut row = serde_json::Map::new();
            for (column_index, field) in batch.schema().fields().iter().enumerate() {
                let array = batch.column(column_index);
                let value = if array.is_null(row_index) {
                    Value::Null
                } else if let Some(array) = array.as_any().downcast_ref::<UInt64Array>() {
                    json!(array.value(row_index))
                } else if let Some(array) = array.as_any().downcast_ref::<Float64Array>() {
                    json!(array.value(row_index))
                } else if let Some(array) = array.as_any().downcast_ref::<BooleanArray>() {
                    json!(array.value(row_index))
                } else {
                    json!(
                        array
                            .as_any()
                            .downcast_ref::<StringArray>()
                            .unwrap()
                            .value(row_index)
                    )
                };
                row.insert(field.name().clone(), value);
            }
            rows.push(Value::Object(row));
        }
    }
    Ok(json!({"fields":fields,"rows":rows,"requests":transport.requests.lock().unwrap().clone()}))
}

async fn rejected(
    name: &str,
    kind: &str,
    spec: Value,
    body: Value,
    status: u16,
    extra: bool,
    wrong_request: bool,
) {
    let result = run(
        kind,
        spec.clone(),
        body.clone(),
        status,
        extra,
        wrong_request,
    )
    .await;
    assert_eq!(result.is_err(), fixed(), "{name}: {result:?}");
    save(
        name,
        json!({"fixed":fixed(),"kind":kind,"config":spec,"synthetic_raw_body":body,"status":status,"accepted":result.is_ok(),"output":result.as_ref().ok(),"error":result.err().map(|error|error.to_string()),"g0_granted":false}),
    );
}

#[test]
fn all_selected_specs_reject_unknown_controls() {
    for kind in ["analysis", "mapping", "pathways"] {
        let mut spec = config(kind);
        spec["invented_official"] = json!(true);
        let accepted = match kind {
            "analysis" => serde_json::from_value::<ReactomeAnalysisSpec>(spec.clone()).is_ok(),
            "mapping" => serde_json::from_value::<ReactomeMappingSpec>(spec.clone()).is_ok(),
            _ => serde_json::from_value::<ReactomePathwaysSpec>(spec.clone()).is_ok(),
        };
        assert_eq!(accepted, !fixed());
        save(
            &format!("{kind}-unknown-control"),
            json!({"fixed":fixed(),"kind":kind,"config":spec,"accepted":accepted}),
        );
    }
}

#[tokio::test]
async fn zero_input_sources_reject_extra_inputs() {
    for kind in ["analysis", "mapping", "pathways"] {
        rejected(
            &format!("{kind}-extra-input"),
            kind,
            config(kind),
            valid(kind),
            200,
            true,
            false,
        )
        .await;
    }
}

#[tokio::test]
async fn analysis_identifiers_do_not_inject_or_change_the_submitted_universe() {
    for (name, identifiers) in [
        ("blank-gene", json!([" "])),
        ("duplicate-gene", json!(["TP53", " TP53 "])),
        ("newline-gene", json!(["TP53\nBRCA1"])),
        ("tab-gene", json!(["TP53\t1"])),
        ("header-gene", json!(["#Genes"])),
    ] {
        let mut spec = config("analysis");
        spec["identifiers"] = identifiers;
        rejected(name, "analysis", spec, valid("analysis"), 200, false, false).await;
    }
}

#[tokio::test]
async fn analysis_response_identity_and_completeness_are_checked() {
    for name in [
        "expression-response",
        "wrong-projection",
        "blank-token",
        "truncated-pathways",
        "missing-pathways",
        "missing-count",
        "duplicate-analysis-pathway",
        "blank-analysis-stable-id",
        "blank-analysis-name",
    ] {
        let mut body = valid("analysis");
        match name {
            "expression-response" => body["summary"]["type"] = json!("EXPRESSION"),
            "wrong-projection" => body["summary"]["projection"] = json!(false),
            "blank-token" => body["summary"]["token"] = json!(""),
            "truncated-pathways" => body["pathwaysFound"] = json!(2),
            "missing-pathways" => {
                body.as_object_mut().unwrap().remove("pathways");
                body["pathwaysFound"] = json!(0);
            }
            "missing-count" => {
                body.as_object_mut().unwrap().remove("pathwaysFound");
            }
            "duplicate-analysis-pathway" => {
                let row = body["pathways"][0].clone();
                body["pathways"].as_array_mut().unwrap().push(row);
                body["pathwaysFound"] = json!(2);
            }
            "blank-analysis-stable-id" => body["pathways"][0]["stId"] = json!(""),
            "blank-analysis-name" => body["pathways"][0]["name"] = json!(" "),
            _ => unreachable!(),
        }
        rejected(
            name,
            "analysis",
            config("analysis"),
            body,
            200,
            false,
            false,
        )
        .await;
    }
}

#[tokio::test]
async fn analysis_statistics_cannot_be_impossible_or_outside_probability_range() {
    for (name, field, value) in [
        ("found-exceeds-total", "found", json!(87)),
        ("negative-p", "pValue", json!(-0.1)),
        ("large-p", "pValue", json!(1.1)),
        ("negative-fdr", "fdr", json!(-0.1)),
        ("large-fdr", "fdr", json!(1.1)),
    ] {
        let mut body = valid("analysis");
        body["pathways"][0]["entities"][field] = value;
        rejected(
            name,
            "analysis",
            config("analysis"),
            body,
            200,
            false,
            false,
        )
        .await;
    }
}

#[tokio::test]
async fn content_source_rows_require_real_and_unique_identity() {
    for kind in ["mapping", "pathways"] {
        for suffix in [
            "zero-db-id",
            "missing-stable-id",
            "blank-name",
            "duplicate-event",
        ] {
            let mut body = valid(kind);
            match suffix {
                "zero-db-id" => body[0]["dbId"] = json!(0),
                "missing-stable-id" => {
                    body[0].as_object_mut().unwrap().remove("stId");
                }
                "blank-name" => body[0]["displayName"] = json!(""),
                "duplicate-event" => {
                    let row = body[0].clone();
                    body.as_array_mut().unwrap().push(row);
                }
                _ => unreachable!(),
            }
            rejected(
                &format!("{kind}-{suffix}"),
                kind,
                config(kind),
                body,
                200,
                false,
                false,
            )
            .await;
        }
    }
}

#[tokio::test]
async fn pending_http_status_is_not_a_successful_completed_result() {
    for kind in ["analysis", "mapping", "pathways"] {
        rejected(
            &format!("{kind}-http-202"),
            kind,
            config(kind),
            valid(kind),
            202,
            false,
            false,
        )
        .await;
    }
}

#[tokio::test]
async fn response_request_identity_is_not_silently_trusted() {
    for kind in ["analysis", "mapping", "pathways"] {
        rejected(
            &format!("{kind}-request-identity"),
            kind,
            config(kind),
            valid(kind),
            200,
            false,
            true,
        )
        .await;
    }
}

#[tokio::test]
async fn request_identifier_normalization_is_explicit() {
    let mut spec = config("analysis");
    spec["identifiers"] = json!([" TP53 ", " BRCA1 "]);
    let output = run(
        "analysis",
        spec.clone(),
        valid("analysis"),
        200,
        false,
        false,
    )
    .await
    .unwrap();
    assert_eq!(
        output["requests"][0]["body"],
        if fixed() {
            "TP53\nBRCA1"
        } else {
            " TP53 \n BRCA1 "
        }
    );
    save(
        "normalized-analysis-identifiers",
        json!({"fixed":fixed(),"config":spec,"output":output}),
    );
}

#[tokio::test]
async fn resource_is_encoded_as_one_url_segment() {
    let mut spec = config("mapping");
    spec["resource"] = json!("Synthetic/Resource");
    let output = run("mapping", spec.clone(), valid("mapping"), 200, false, false)
        .await
        .unwrap();
    let url = output["requests"][0]["url"].as_str().unwrap();
    assert!(url.contains(if fixed() {
        "/Synthetic%2FResource/"
    } else {
        "/Synthetic/Resource/"
    }));
    save(
        "mapping-resource-segment",
        json!({"fixed":fixed(),"config":spec,"output":output}),
    );
}

#[tokio::test]
async fn absent_boolean_properties_remain_unknown_not_false() {
    let mut body = valid("pathways");
    for key in ["isInDisease", "isInferred", "hasDiagram", "hasEHLD"] {
        body[0].as_object_mut().unwrap().remove(key);
    }
    let output = run(
        "pathways",
        config("pathways"),
        body.clone(),
        200,
        false,
        false,
    )
    .await
    .unwrap();
    for key in ["is_in_disease", "is_inferred", "has_diagram", "has_ehld"] {
        assert_eq!(
            output["rows"][0][key],
            if fixed() { Value::Null } else { json!(false) }
        );
    }
    save(
        "optional-boolean-null",
        json!({"fixed":fixed(),"synthetic_raw_body":body,"output":output}),
    );
}

#[tokio::test]
async fn all_full_typed_outputs_and_real_empty_schemas_are_preserved() {
    for (kind, width) in [("analysis", 6), ("mapping", 4), ("pathways", 9)] {
        let full = run(kind, config(kind), valid(kind), 200, false, false)
            .await
            .unwrap();
        assert_eq!(full["fields"].as_array().unwrap().len(), width);
        assert_eq!(full["rows"].as_array().unwrap().len(), 1);
        assert!(
            full["fields"]
                .as_array()
                .unwrap()
                .iter()
                .all(|field| field["nullable"] == true)
        );
        let mut body = valid(kind);
        if kind == "analysis" {
            body["pathways"] = json!([]);
            body["pathwaysFound"] = json!(0);
        } else {
            body = json!([]);
        }
        let empty = run(kind, config(kind), body, 200, false, false)
            .await
            .unwrap();
        assert_eq!(empty["rows"].as_array().unwrap().len(), 0);
        assert_eq!(empty["fields"], full["fields"]);
        save(
            &format!("{kind}-complete-output"),
            json!({"fixed":fixed(),"full":full,"empty":empty}),
        );
    }
}

#[tokio::test]
async fn existing_failures_still_propagate() {
    for kind in ["analysis", "mapping", "pathways"] {
        for status in [400, 404, 429, 500, 503] {
            assert!(
                run(kind, config(kind), valid(kind), status, false, false)
                    .await
                    .is_err()
            );
        }
    }
}
