use super::*;
use crate::client::{CapturedResponse, ResponseTransport};
use crate::error::Result as ClientResult;
use dag_core::dag::node_event::NodeReporter;
use serde_json::{Value, json};

#[derive(Debug)]
struct Reply {
    status: u16,
    body: String,
    wrong_url: bool,
}

#[async_trait]
impl ResponseTransport for Reply {
    async fn response(&self, url: &str) -> ClientResult<CapturedResponse> {
        Ok(CapturedResponse {
            url: if self.wrong_url {
                "https://wrong.example/".into()
            } else {
                url.into()
            },
            status: self.status,
            body: self.body.clone(),
            headers: std::collections::BTreeMap::from([(
                "content-type".into(),
                "application/json".into(),
            )]),
        })
    }
}

fn fixed() -> bool {
    true
}

fn save(name: &str, value: Value) {
    let Some(root) = std::env::var_os("PUBCHEM_COUNTER_DIR") else {
        return;
    };
    let root = std::path::PathBuf::from(root);
    std::fs::write(
        root.join(format!("{name}.json")),
        serde_json::to_vec_pretty(&value).unwrap(),
    )
    .unwrap();
}

fn valid() -> Value {
    json!({"PropertyTable":{"Properties":[{"CID":2244,"MolecularFormula":"C9H8O4","MolecularWeight":"180.16","SMILES":"STEREO_SYNTHETIC","ConnectivitySMILES":"CONNECTIVITY_SYNTHETIC","InChI":"InChI=1S/SYNTHETIC","InChIKey":"BSYNRYMUTXBXSQ-UHFFFAOYSA-N","IUPACName":"Synthetic IUPAC name","Title":"Synthetic title"}]}})
}

fn spec(kind: &str, identifier: &str) -> Value {
    json!({"identifier_type":kind,"identifier":identifier})
}

async fn run(
    config: Value,
    status: u16,
    body: Value,
    extra: bool,
    wrong_url: bool,
) -> std::result::Result<Value, DagError> {
    let client = PubChemClient::new().with_transport(Arc::new(Reply {
        status,
        body: body.to_string(),
        wrong_url,
    }));
    let mut node =
        PubChemCompoundNode::with_client(serde_json::from_value(config).unwrap(), client);
    let ctx = NodeCtx::new(SessionContext::new().runtime_env(), None);
    let inputs = if extra {
        vec![dag_core::dag::NodeInput::file(
            0,
            dag_core::value::FileRef::new("vfs:///unused.tsv", Some("tsv".into())),
        )]
    } else {
        vec![]
    };
    let output = node.execute(&ctx, &inputs, &NodeReporter::noop()).await?;
    let batches = output
        .dataframe(0)
        .map_err(|error| DagError::Schedule(error.to_string()))?
        .clone()
        .collect()
        .await
        .map_err(|error| DagError::Schedule(error.to_string()))?;
    let mut rows = vec![];
    for batch in &batches {
        assert_eq!(batch.num_columns(), 10);
        for row_index in 0..batch.num_rows() {
            let mut row = serde_json::Map::new();
            for (column_index, field) in batch.schema().fields().iter().enumerate() {
                let array = batch.column(column_index);
                let value = if array.is_null(row_index) {
                    Value::Null
                } else if column_index == 0 {
                    json!(
                        array
                            .as_any()
                            .downcast_ref::<UInt64Array>()
                            .unwrap()
                            .value(row_index)
                    )
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
    Ok(
        json!({"rows":rows,"fields":batches.first().map(|batch|batch.schema().fields().iter().map(|field|json!({"name":field.name(),"type":field.data_type().to_string(),"nullable":field.is_nullable()})).collect::<Vec<_>>())}),
    )
}

async fn rejected(
    name: &str,
    config: Value,
    status: u16,
    body: Value,
    extra: bool,
    wrong_url: bool,
) {
    let result = run(config.clone(), status, body.clone(), extra, wrong_url).await;
    assert_eq!(result.is_err(), fixed(), "{name}: {result:?}");
    save(
        name,
        json!({"fixed":fixed(),"accepted":result.is_ok(),"config":config,"status":status,"synthetic_raw_body":body,"extra_input":extra,"wrong_url":wrong_url,"output":result.as_ref().ok(),"error":result.err().map(|error|error.to_string()),"g0_granted":false}),
    );
}

#[test]
fn rejects_unknown_spec_controls() {
    let config = json!({"identifier":"aspirin","invented_official":true});
    let result = serde_json::from_value::<PubChemCompoundSpec>(config.clone());
    assert_eq!(result.is_err(), fixed());
    save(
        "unknown-controls",
        json!({"fixed":fixed(),"config":config,"accepted":result.is_ok(),"error":result.err().map(|error|error.to_string())}),
    );
}

#[tokio::test]
async fn paired_rejections() {
    let cases = [
        (
            "not-found",
            404,
            json!({"Fault":{"Code":"PUGREST.NotFound","Message":"Synthetic missing compound"}}),
        ),
        ("404-html", 404, json!("Synthetic HTML route failure")),
        ("missing-property-table", 200, json!({})),
        ("missing-properties", 200, json!({"PropertyTable":{}})),
        (
            "empty-success-properties",
            200,
            json!({"PropertyTable":{"Properties":[]}}),
        ),
        (
            "fault-in-success-body",
            200,
            json!({"Fault":{"Code":"PUGREST.NotFound"}}),
        ),
        (
            "202-pending",
            202,
            json!({"Waiting":{"ListKey":"synthetic"}}),
        ),
    ];
    for (name, status, body) in cases {
        rejected(name, spec("name", "aspirin"), status, body, false, false).await;
    }
    let mut body = valid();
    body["PropertyTable"]["Properties"]
        .as_array_mut()
        .unwrap()
        .push(json!({"CID":5793,"Title":"Synthetic second hit"}));
    rejected(
        "ambiguous-name",
        spec("name", "glucose"),
        200,
        body,
        false,
        false,
    )
    .await;
    for (name, cid) in [
        ("missing-cid", Value::Null),
        ("zero-response-cid", json!(0)),
        ("wrong-response-cid", json!(5793)),
    ] {
        let mut body = valid();
        body["PropertyTable"]["Properties"][0]["CID"] = cid;
        rejected(name, spec("cid", "2244"), 200, body, false, false).await;
    }
    rejected(
        "zero-request-cid",
        spec("cid", "0"),
        200,
        valid(),
        false,
        false,
    )
    .await;
    rejected(
        "malformed-inchikey",
        spec("inchikey", "123456789012345678901234567"),
        200,
        valid(),
        false,
        false,
    )
    .await;
    let mut body = valid();
    body["PropertyTable"]["Properties"][0]["InChIKey"] = json!("AAAAAAAAAAAAAA-BBBBBBBBBB-N");
    rejected(
        "wrong-response-inchikey",
        spec("inchikey", "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"),
        200,
        body,
        false,
        false,
    )
    .await;
    rejected(
        "name-control-character",
        spec("name", "synthetic\nname"),
        200,
        valid(),
        false,
        false,
    )
    .await;
    rejected(
        "unexpected-dag-input",
        spec("name", "aspirin"),
        200,
        valid(),
        true,
        false,
    )
    .await;
    rejected(
        "captured-url-mismatch",
        spec("name", "aspirin"),
        200,
        valid(),
        false,
        true,
    )
    .await;
}

#[tokio::test]
async fn query_identity_matches_trimmed_request() {
    let output = run(spec(" CID ", " 2244 "), 200, valid(), false, false)
        .await
        .unwrap();
    assert_eq!(
        output["rows"][0]["query"],
        if fixed() { "2244" } else { " 2244 " }
    );
    assert_eq!(output["rows"][0]["query_type"], "cid");
    save("normalized-query", json!({"fixed":fixed(),"output":output}));
}

#[tokio::test]
async fn connectivity_is_not_reported_as_stereochemical_smiles() {
    let mut body = valid();
    body["PropertyTable"]["Properties"][0]
        .as_object_mut()
        .unwrap()
        .remove("SMILES");
    let output = run(spec("name", "aspirin"), 200, body.clone(), false, false)
        .await
        .unwrap();
    assert_eq!(
        output["rows"][0]["smiles"],
        if fixed() {
            Value::Null
        } else {
            json!("CONNECTIVITY_SYNTHETIC")
        }
    );
    save(
        "connectivity-not-stereo",
        json!({"fixed":fixed(),"synthetic_raw_body":body,"output":output}),
    );
}

#[tokio::test]
async fn legacy_smiles_keys_are_deserialized_without_losing_capitals() {
    let body = json!({"PropertyTable":{"Properties":[{"CID":2244,"CanonicalSMILES":"LEGACY_CONNECTIVITY","IsomericSMILES":"LEGACY_STEREO"}]}});
    let response: crate::types::PropertyResponse = serde_json::from_value(body.clone()).unwrap();
    let compound = &response.property_table.properties[0];
    assert_eq!(
        compound.canonical_smiles.as_deref(),
        fixed().then_some("LEGACY_CONNECTIVITY")
    );
    assert_eq!(
        compound.isomeric_smiles.as_deref(),
        fixed().then_some("LEGACY_STEREO")
    );
    let output = run(spec("cid", "2244"), 200, body.clone(), false, false)
        .await
        .unwrap();
    assert_eq!(
        output["rows"][0]["smiles"],
        if fixed() {
            json!("LEGACY_STEREO")
        } else {
            Value::Null
        }
    );
    save(
        "legacy-smiles-caps",
        json!({"fixed":fixed(),"synthetic_raw_body":body,"output":output}),
    );
}

#[tokio::test]
async fn complete_ten_column_output_preserves_all_values_and_nulls() {
    let output = run(spec("cid", "2244"), 200, valid(), false, false)
        .await
        .unwrap();
    assert_eq!(
        output["rows"][0],
        json!({"cid":2244,"query":"2244","query_type":"cid","molecular_formula":"C9H8O4","molecular_weight":"180.16","smiles":"STEREO_SYNTHETIC","inchi":"InChI=1S/SYNTHETIC","inchikey":"BSYNRYMUTXBXSQ-UHFFFAOYSA-N","iupac_name":"Synthetic IUPAC name","title":"Synthetic title"})
    );
    let empty_optional = run(
        spec("cid", "2244"),
        200,
        json!({"PropertyTable":{"Properties":[{"CID":2244}]}}),
        false,
        false,
    )
    .await
    .unwrap();
    for name in [
        "molecular_formula",
        "molecular_weight",
        "smiles",
        "inchi",
        "inchikey",
        "iupac_name",
        "title",
    ] {
        assert!(empty_optional["rows"][0][name].is_null());
    }
    save(
        "complete-output",
        json!({"fixed":fixed(),"full":output,"optional_nulls":empty_optional}),
    );
}

#[tokio::test]
async fn existing_error_cases_remain_errors() {
    for status in [400, 405, 500, 503, 504] {
        let result = run(
            spec("cid", "2244"),
            status,
            json!({"Fault":{"Code":"PUGREST.SyntheticError","Summary":"Synthetic"}}),
            false,
            false,
        )
        .await;
        assert!(result.is_err());
    }
    assert!(
        run(spec("cid", "invalid"), 200, valid(), false, false)
            .await
            .is_err()
    );
    assert!(
        run(spec("name", "bad/name"), 200, valid(), false, false)
            .await
            .is_err()
    );
    assert!(
        run(spec("name", ""), 200, valid(), false, false)
            .await
            .is_err()
    );
}
