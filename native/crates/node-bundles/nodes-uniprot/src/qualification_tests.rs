use crate::UniProtClient;
use crate::client::{CapturedRequest, CapturedResponse, ResponseTransport};
use crate::nodes::idmap::{UniprotIdmapNode, UniprotIdmapSpec};
use crate::nodes::search::{UniprotSearchNode, UniprotSearchSpec};
use arrow_array::{
    Array, BooleanArray, Float64Array, LargeStringArray, RecordBatch, StringArray, StringViewArray,
    UInt64Array,
};
use arrow_schema::{DataType, Field, Schema};
use async_trait::async_trait;
use dag_core::dag::node_event::NodeReporter;
use dag_core::dag::{DagNode, NodeInput};
use dag_core::registry::NodeCtx;
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};
use std::collections::BTreeMap;
use std::sync::{Arc, Mutex};

#[derive(Debug, Clone)]
struct Page {
    body: Value,
    status: u16,
    headers: BTreeMap<String, String>,
}

#[derive(Debug)]
struct Reply {
    kind: String,
    pages: Vec<Page>,
    returned_request_mismatch: bool,
    job_id: String,
    post_status: u16,
    status_status: u16,
    status_headers: BTreeMap<String, String>,
    status_body: Value,
    requests: Mutex<Vec<CapturedRequest>>,
    page_index: Mutex<usize>,
}

#[async_trait]
impl ResponseTransport for Reply {
    async fn response(&self, request: &CapturedRequest) -> crate::error::Result<CapturedResponse> {
        self.requests.lock().unwrap().push(request.clone());
        let (body, status, mut headers) = if request.url.contains("/idmapping/run") {
            (
                json!({"jobId":self.job_id}),
                self.post_status,
                BTreeMap::new(),
            )
        } else if request.url.contains("/idmapping/status/") {
            (
                self.status_body.clone(),
                self.status_status,
                self.status_headers.clone(),
            )
        } else {
            let mut index = self.page_index.lock().unwrap();
            let page = self
                .pages
                .get(*index)
                .ok_or_else(|| {
                    crate::UniProtError::Param(
                        "synthetic replay exhausted; no native fallback".into(),
                    )
                })?
                .clone();
            *index += 1;
            (page.body, page.status, page.headers)
        };
        headers.insert("content-type".into(), "application/json".into());
        let mut identity = request.clone();
        if self.returned_request_mismatch {
            identity.url.push_str("?wrong-response-identity");
        }
        Ok(CapturedResponse {
            request: identity,
            status,
            headers,
            body: body.to_string(),
        })
    }
}

fn fixed() -> bool {
    true
}
fn save(name: &str, value: Value) {
    let Some(root) = std::env::var_os("UNIPROT_COUNTER_DIR") else {
        return;
    };
    let root = std::path::PathBuf::from(root);
    std::fs::write(
        root.join(format!("{name}.json")),
        serde_json::to_vec_pretty(&value).unwrap(),
    )
    .unwrap();
}
fn entry(accession: &str) -> Value {
    json!({"entryType":"UniProtKB reviewed (Swiss-Prot)","primaryAccession":accession,"uniProtkbId":format!("{accession}_SYNTHETIC"),"organism":{"scientificName":"Homo sapiens","commonName":"Human","taxonId":9606},"proteinDescription":{"recommendedName":{"fullName":{"value":"Synthetic protein"}}},"genes":[{"geneName":{"value":"INS"}}],"sequence":{"length":110},"annotationScore":5.0,"proteinExistence":"1: Evidence at protein level","comments":[{"commentType":"FUNCTION","texts":[{"value":"Synthetic function annotation"}]}]})
}
fn spec(kind: &str) -> Value {
    if kind == "search" {
        json!({"gene":["INS"],"organism_id":9606,"size":2,"max_results":2})
    } else {
        json!({"from_db":"Gene_Name","to_db":"UniProtKB","ids":["INS"]})
    }
}
fn body(kind: &str) -> Value {
    if kind == "search" {
        json!({"results":[entry("P01308")]})
    } else {
        json!({"results":[{"from":"INS","to":entry("P01308")}]})
    }
}
fn transport(kind: &str, payload: Value) -> Reply {
    let total = payload
        .get("results")
        .and_then(Value::as_array)
        .map_or(0, Vec::len);
    Reply {
        kind: kind.into(),
        pages: vec![Page {
            body: payload,
            status: 200,
            headers: BTreeMap::from([
                ("x-total-results".into(), total.to_string()),
                ("x-uniprot-release".into(), "SYNTHETIC_RELEASE".into()),
            ]),
        }],
        returned_request_mismatch: false,
        job_id: "synthetic-job".into(),
        post_status: 200,
        status_status: 303,
        status_headers: BTreeMap::from([(
            "location".into(),
            "https://rest.uniprot.org/idmapping/uniprotkb/results/synthetic-job".into(),
        )]),
        status_body: json!({"jobStatus":"FINISHED"}),
        requests: Mutex::new(vec![]),
        page_index: Mutex::new(0),
    }
}

async fn input(session: &SessionContext, mode: &str) -> Vec<NodeInput> {
    if mode == "none" {
        return vec![];
    }
    if mode == "file" {
        return vec![NodeInput::file(
            0,
            dag_core::value::FileRef::new("vfs:///unused.tsv", Some("tsv".into())),
        )];
    }
    let values = if mode == "null" {
        vec![Some("INS"), None]
    } else {
        vec![Some("INS")]
    };
    let (array, datatype): (Arc<dyn Array>, DataType) = match mode {
        "large" => (
            Arc::new(LargeStringArray::from(values)),
            DataType::LargeUtf8,
        ),
        "view" => (Arc::new(StringViewArray::from(values)), DataType::Utf8View),
        _ => (Arc::new(StringArray::from(values)), DataType::Utf8),
    };
    let batch = RecordBatch::try_new(
        Arc::new(Schema::new(vec![Field::new("id", datatype, true)])),
        vec![array],
    )
    .unwrap();
    let table = session.read_batch(batch).unwrap();
    let mut inputs = vec![NodeInput::new_dataframe(0, table.clone())];
    if mode == "extra" {
        inputs.push(NodeInput::new_dataframe(1, table));
    }
    inputs
}

async fn execute(
    specification: Value,
    reply: Reply,
    input_mode: &str,
) -> (std::result::Result<Value, String>, Value) {
    let kind = reply.kind.clone();
    let raw = json!({"pages":reply.pages.iter().map(|page|json!({"body":page.body,"status":page.status,"headers":page.headers})).collect::<Vec<_>>(),"job_id":reply.job_id,"post_status":reply.post_status,"status_status":reply.status_status,"status_headers":reply.status_headers,"status_body":reply.status_body,"wrong_request":reply.returned_request_mismatch});
    let reply = Arc::new(reply);
    let client = UniProtClient::new().with_transport(reply.clone());
    let mut node: Box<dyn DagNode> = if kind == "search" {
        Box::new(UniprotSearchNode::with_client(
            serde_json::from_value(specification).unwrap(),
            client,
        ))
    } else {
        Box::new(UniprotIdmapNode::with_client(
            serde_json::from_value(specification).unwrap(),
            client,
        ))
    };
    let session = SessionContext::new();
    let context = NodeCtx::new(session.runtime_env(), None);
    let inputs = input(&session, input_mode).await;
    let result = async {
        let outputs = node.execute(&context,&inputs,&NodeReporter::noop()).await.map_err(|error|error.to_string())?;
        let table = outputs.dataframe(0).map_err(|error|error.to_string())?;
        let fields = table.schema().fields().iter().map(|field|json!({"name":field.name(),"type":field.data_type().to_string(),"nullable":field.is_nullable()})).collect::<Vec<_>>();
        let mut rows = vec![];
        for batch in table.clone().collect().await.map_err(|error|error.to_string())? {
            for row_index in 0..batch.num_rows() {
                let mut row = serde_json::Map::new();
                for (column_index,field) in batch.schema().fields().iter().enumerate() {
                    let array = batch.column(column_index);
                    let value = if array.is_null(row_index) { Value::Null }
                    else if let Some(array) = array.as_any().downcast_ref::<UInt64Array>() { json!(array.value(row_index)) }
                    else if let Some(array) = array.as_any().downcast_ref::<BooleanArray>() { json!(array.value(row_index)) }
                    else if let Some(array) = array.as_any().downcast_ref::<Float64Array>() { json!(array.value(row_index)) }
                    else { json!(array.as_any().downcast_ref::<StringArray>().unwrap().value(row_index)) };
                    row.insert(field.name().clone(),value);
                }
                rows.push(Value::Object(row));
            }
        }
        Ok(json!({"fields":fields,"rows":rows}))
    }.await;
    (
        result,
        json!({"raw":raw,"requests":reply.requests.lock().unwrap().clone()}),
    )
}

async fn blocked(name: &str, kind: &str, specification: Value, reply: Reply, input_mode: &str) {
    let (result, trace) = execute(specification.clone(), reply, input_mode).await;
    assert_eq!(result.is_err(), fixed(), "{name}: {result:?}");
    save(
        name,
        json!({"fixed":fixed(),"kind":kind,"config":specification,"input_mode":input_mode,"accepted":result.is_ok(),"output":result.as_ref().ok(),"error":result.err(),"trace":trace,"g0_granted":false}),
    );
}

#[test]
fn unknown_controls_do_not_disappear() {
    for kind in ["search", "idmap"] {
        let mut config = spec(kind);
        config["invented_official"] = json!(true);
        let accepted = if kind == "search" {
            serde_json::from_value::<UniprotSearchSpec>(config.clone()).is_ok()
        } else {
            serde_json::from_value::<UniprotIdmapSpec>(config.clone()).is_ok()
        };
        assert_eq!(accepted, !fixed());
        save(
            &format!("{kind}-unknown-control"),
            json!({"fixed":fixed(),"kind":kind,"config":config,"accepted":accepted}),
        );
    }
}

#[tokio::test]
async fn configured_search_filters_are_never_silently_replaced() {
    for name in [
        "mixed-search-modes",
        "blank-typed-member",
        "blank-raw-mode",
        "zero-page-size",
        "zero-max-results",
    ] {
        let mut config = spec("search");
        match name {
            "mixed-search-modes" => config["query"] = json!("accession:P01308"),
            "blank-typed-member" => config["gene"] = json!(["INS", ""]),
            "blank-raw-mode" => config["query"] = json!(" "),
            "zero-page-size" => config["size"] = json!(0),
            _ => config["max_results"] = json!(0),
        }
        blocked(
            name,
            "search",
            config,
            transport("search", body("search")),
            "none",
        )
        .await;
    }
}

#[tokio::test]
async fn mapping_identifiers_and_target_contract_are_not_ambiguous() {
    for name in [
        "comma-id",
        "control-id",
        "duplicate-id",
        "blank-id",
        "unsupported-entry-target",
    ] {
        let mut config = spec("idmap");
        match name {
            "comma-id" => config["ids"] = json!(["INS,GCG"]),
            "control-id" => config["ids"] = json!(["INS\nGCG"]),
            "duplicate-id" => config["ids"] = json!(["INS", " INS "]),
            "blank-id" => config["ids"] = json!([""]),
            _ => config["to_db"] = json!("PDB"),
        }
        blocked(
            name,
            "idmap",
            config,
            transport("idmap", body("idmap")),
            "none",
        )
        .await;
    }
}

#[tokio::test]
async fn unexpected_inputs_and_null_ids_cannot_be_ignored() {
    blocked(
        "search-extra-input",
        "search",
        spec("search"),
        transport("search", body("search")),
        "file",
    )
    .await;
    for mode in ["extra", "null"] {
        let mut config = spec("idmap");
        config["id_column"] = json!("id");
        blocked(
            &format!("mapping-{mode}-input"),
            "idmap",
            config,
            transport("idmap", body("idmap")),
            mode,
        )
        .await;
    }
}

#[tokio::test]
async fn mapping_stream_identity_coverage_and_failure_are_checked() {
    for name in [
        "empty-mapping-envelope",
        "missing-id-status",
        "foreign-id",
        "missing-mapped-entry",
        "blank-mapped-accession",
        "duplicate-mapped-pair",
        "overlap-success-failure",
        "duplicate-failed-id",
        "foreign-failed-id",
        "stream-error",
    ] {
        let mut payload = body("idmap");
        let mut config = spec("idmap");
        match name {
            "empty-mapping-envelope" => payload = json!({}),
            "missing-id-status" => payload = json!({"results":[]}),
            "foreign-id" => payload["results"][0]["from"] = json!("UNREQUESTED"),
            "missing-mapped-entry" => payload["results"][0]["to"] = Value::Null,
            "blank-mapped-accession" => payload["results"][0]["to"]["primaryAccession"] = json!(""),
            "duplicate-mapped-pair" => {
                let row = payload["results"][0].clone();
                payload["results"].as_array_mut().unwrap().push(row);
            }
            "overlap-success-failure" => payload["failedIds"] = json!(["INS"]),
            "duplicate-failed-id" => {
                config["ids"] = json!(["INS", "NOPE"]);
                payload["failedIds"] = json!(["NOPE", "NOPE"]);
            }
            "foreign-failed-id" => payload["failedIds"] = json!(["UNREQUESTED"]),
            _ => payload["error"] = json!("synthetic stop-stream failure"),
        }
        blocked(name, "idmap", config, transport("idmap", payload), "none").await;
    }
}

#[tokio::test]
async fn mapping_unmapped_members_are_retained_without_inference() {
    for name in ["mixed-mapping-failed-ids", "all-unmapped"] {
        let (config, payload, old_count, new_count) = if name == "all-unmapped" {
            (
                spec("idmap"),
                json!({"results":[],"failedIds":["INS"]}),
                0,
                1,
            )
        } else {
            (
                json!({"from_db":"Gene_Name","to_db":"UniProtKB","ids":["INS","NOPE"]}),
                json!({"results":[{"from":"INS","to":entry("P01308")}],"failedIds":["NOPE"]}),
                1,
                2,
            )
        };
        let (result, trace) = execute(config.clone(), transport("idmap", payload), "none").await;
        let output = result.unwrap();
        assert_eq!(
            output["rows"].as_array().unwrap().len(),
            if fixed() { new_count } else { old_count }
        );
        if fixed() {
            assert_eq!(
                output["rows"].as_array().unwrap().last().unwrap()["mapped"],
                false
            );
        }
        save(
            name,
            json!({"fixed":fixed(),"kind":"idmap","config":config,"output":output,"trace":trace,"g0_granted":false}),
        );
    }
}

#[tokio::test]
async fn search_entry_identity_is_not_fabricated_from_defaults() {
    for name in [
        "missing-accession",
        "missing-entry-type",
        "unknown-entry-type",
        "zero-taxon",
        "blank-entry-name",
        "invalid-score",
        "wrong-requested-taxon",
        "duplicate-search-accession",
    ] {
        let mut payload = body("search");
        match name {
            "missing-accession" => {
                payload["results"][0]
                    .as_object_mut()
                    .unwrap()
                    .remove("primaryAccession");
            }
            "missing-entry-type" => {
                payload["results"][0]
                    .as_object_mut()
                    .unwrap()
                    .remove("entryType");
            }
            "unknown-entry-type" => payload["results"][0]["entryType"] = json!("UNKNOWN"),
            "zero-taxon" => payload["results"][0]["organism"]["taxonId"] = json!(0),
            "blank-entry-name" => payload["results"][0]["uniProtkbId"] = json!(""),
            "invalid-score" => payload["results"][0]["annotationScore"] = json!(9.0),
            "wrong-requested-taxon" => payload["results"][0]["organism"]["taxonId"] = json!(10090),
            _ => {
                let row = payload["results"][0].clone();
                payload["results"].as_array_mut().unwrap().push(row);
            }
        }
        let mut reply = transport("search", payload);
        if name == "duplicate-search-accession" {
            reply.pages[0]
                .headers
                .insert("x-total-results".into(), "2".into());
        }
        blocked(name, "search", spec("search"), reply, "none").await;
    }
}

#[tokio::test]
async fn pagination_headers_and_completeness_are_not_best_effort() {
    for name in [
        "truncated-search",
        "malformed-total-count",
        "rows-exceed-total",
        "missing-total-count",
    ] {
        let mut reply = transport("search", body("search"));
        match name {
            "truncated-search" => {
                reply.pages[0]
                    .headers
                    .insert("x-total-results".into(), "2".into());
            }
            "malformed-total-count" => {
                reply.pages[0]
                    .headers
                    .insert("x-total-results".into(), "invalid".into());
            }
            "rows-exceed-total" => {
                reply.pages[0]
                    .headers
                    .insert("x-total-results".into(), "0".into());
            }
            _ => {
                reply.pages[0].headers.remove("x-total-results");
            }
        }
        blocked(name, "search", spec("search"), reply, "none").await;
    }
}

fn paginated(name: &str) -> Reply {
    let mut reply = transport("search", body("search"));
    reply.pages[0]
        .headers
        .insert("x-total-results".into(), "2".into());
    reply.pages[0].headers.insert(
        "link".into(),
        "<https://rest.uniprot.org/uniprotkb/search?cursor=abc%2Bdef&size=1>; rel=\"next\"".into(),
    );
    reply.pages.push(Page {
        body: json!({"results":[entry("P05067")]}),
        status: 200,
        headers: BTreeMap::from([
            ("x-total-results".into(), "2".into()),
            ("x-uniprot-release".into(), "SYNTHETIC_RELEASE".into()),
        ]),
    });
    if name == "mixed-release-pages" {
        reply.pages[1]
            .headers
            .insert("x-uniprot-release".into(), "DIFFERENT_RELEASE".into());
    }
    if name == "duplicate-paged-entry" {
        reply.pages[1].body = body("search");
    }
    reply
}

#[tokio::test]
async fn pages_do_not_mix_release_or_duplicate_proteins() {
    for name in ["mixed-release-pages", "duplicate-paged-entry"] {
        blocked(name, "search", spec("search"), paginated(name), "none").await;
    }
}

#[tokio::test]
async fn cursor_decoding_and_exact_limit_do_not_change_request_identity() {
    for name in ["encoded-cursor", "exact-cap-no-extra-fetch"] {
        let mut config = spec("search");
        config["size"] = json!(1);
        if name == "exact-cap-no-extra-fetch" {
            config["max_results"] = json!(1);
        }
        let (result, trace) = execute(config.clone(), paginated(name), "none").await;
        let output = result.unwrap();
        if name == "encoded-cursor" {
            assert!(
                trace["requests"][1]["url"]
                    .as_str()
                    .unwrap()
                    .contains(if fixed() {
                        "cursor=abc%2Bdef"
                    } else {
                        "cursor=abc%252Bdef"
                    })
            );
        } else {
            assert_eq!(
                trace["requests"].as_array().unwrap().len(),
                if fixed() { 1 } else { 2 }
            );
        }
        save(
            name,
            json!({"fixed":fixed(),"kind":"search","config":config,"output":output,"trace":trace,"g0_granted":false}),
        );
    }
}

#[tokio::test]
async fn all_three_arrow_string_representations_have_the_same_mapping_contract() {
    for mode in ["utf8", "large", "view"] {
        let mut config = spec("idmap");
        config["id_column"] = json!("id");
        let (result, trace) =
            execute(config.clone(), transport("idmap", body("idmap")), mode).await;
        assert_eq!(result.is_ok(), fixed() || mode == "utf8");
        save(
            &format!("input-string-{mode}"),
            json!({"fixed":fixed(),"kind":"idmap","config":config,"accepted":result.is_ok(),"output":result.as_ref().ok(),"error":result.err(),"trace":trace,"g0_granted":false}),
        );
    }
}

#[tokio::test]
async fn completed_http_status_and_request_identity_are_verified() {
    for kind in ["search", "idmap"] {
        for name in ["http-202", "request-identity"] {
            let mut reply = transport(kind, body(kind));
            if name == "http-202" {
                reply.pages[0].status = 202;
            } else {
                reply.returned_request_mismatch = true;
            }
            blocked(&format!("{kind}-{name}"), kind, spec(kind), reply, "none").await;
        }
    }
    for name in ["pending-submission", "blank-job-id"] {
        let mut reply = transport("idmap", body("idmap"));
        if name == "pending-submission" {
            reply.post_status = 202;
        } else {
            reply.job_id = "".into();
        }
        blocked(name, "idmap", spec("idmap"), reply, "none").await;
    }
}

#[tokio::test]
async fn redirects_are_not_all_mapping_completion() {
    for status in [301, 302, 307, 308] {
        let mut reply = transport("idmap", body("idmap"));
        reply.status_status = status;
        blocked(
            &format!("status-{status}-not-finished"),
            "idmap",
            spec("idmap"),
            reply,
            "none",
        )
        .await;
    }
    for name in [
        "foreign-status-location",
        "missing-status-location",
        "wrong-status-job",
        "wrong-redirect-state",
    ] {
        let mut reply = transport("idmap", body("idmap"));
        match name {
            "foreign-status-location" => {
                reply.status_headers.insert(
                    "location".into(),
                    "https://example.invalid/idmapping/uniprotkb/results/synthetic-job".into(),
                );
            }
            "missing-status-location" => {
                reply.status_headers.clear();
            }
            "wrong-status-job" => {
                reply.status_headers.insert(
                    "location".into(),
                    "https://rest.uniprot.org/idmapping/uniprotkb/results/other-job".into(),
                );
            }
            _ => reply.status_body = json!({"jobStatus":"RUNNING"}),
        }
        blocked(name, "idmap", spec("idmap"), reply, "none").await;
    }
}

#[tokio::test]
async fn complete_outputs_and_one_to_many_mapping_remain_full_width() {
    for kind in ["search", "idmap"] {
        let mut payload = body(kind);
        let extra = if kind == "search" {
            entry("P05067")
        } else {
            json!({"from":"INS","to":entry("P05067")})
        };
        payload["results"].as_array_mut().unwrap().push(extra);
        let mut reply = transport(kind, payload);
        if kind == "search" {
            reply.pages[0]
                .headers
                .insert("x-total-results".into(), "2".into());
        }
        let (result, trace) = execute(spec(kind), reply, "none").await;
        let output = result.unwrap();
        assert_eq!(
            output["fields"].as_array().unwrap().len(),
            if kind == "search" { 12 } else { 8 }
        );
        assert_eq!(output["rows"].as_array().unwrap().len(), 2);
        save(
            &format!("{kind}-complete-output"),
            json!({"fixed":fixed(),"kind":kind,"output":output,"trace":trace,"g0_granted":false}),
        );
    }
}

#[tokio::test]
async fn official_source_only_database_is_rejected_as_mapping_destination() {
    let mut config = spec("idmap");
    config["to_db"] = json!("UniProtKB_AC-ID");
    let (result, trace) = execute(config, transport("idmap", body("idmap")), "none").await;
    assert!(result.is_err());
    assert!(trace["requests"].as_array().unwrap().is_empty());
    for target in ["UniProtKB", "UniProtKB-Swiss-Prot"] {
        let mut config = spec("idmap");
        config["to_db"] = json!(target);
        let (result, _) = execute(config, transport("idmap", body("idmap")), "none").await;
        assert_eq!(result.unwrap()["rows"].as_array().unwrap().len(), 1);
    }
}

#[tokio::test]
async fn official_reviewed_filter_matches_returned_entry_type_in_both_directions() {
    for reviewed in [true, false] {
        let mut config = spec("search");
        config["reviewed"] = json!(reviewed);
        let mut wrong = body("search");
        wrong["results"][0]["entryType"] = json!(if reviewed {
            "UniProtKB unreviewed (TrEMBL)"
        } else {
            "UniProtKB reviewed (Swiss-Prot)"
        });
        let (result, _) = execute(config.clone(), transport("search", wrong), "none").await;
        assert!(result.is_err());
        let mut valid = body("search");
        valid["results"][0]["entryType"] = json!(if reviewed {
            "UniProtKB reviewed (Swiss-Prot)"
        } else {
            "UniProtKB unreviewed (TrEMBL)"
        });
        let (result, _) = execute(config, transport("search", valid), "none").await;
        assert_eq!(result.unwrap()["rows"][0]["reviewed"], reviewed);
    }
}

#[tokio::test]
async fn official_swissprot_destination_does_not_accept_trembl_entries() {
    let mut config = spec("idmap");
    config["to_db"] = json!("UniProtKB-Swiss-Prot");
    let mut wrong = body("idmap");
    wrong["results"][0]["to"]["entryType"] = json!("UniProtKB unreviewed (TrEMBL)");
    let (result, _) = execute(config, transport("idmap", wrong.clone()), "none").await;
    assert!(result.is_err());
    let (result, _) = execute(spec("idmap"), transport("idmap", wrong), "none").await;
    assert_eq!(result.unwrap()["rows"].as_array().unwrap().len(), 1);
}
