use super::*;
use dag_core::dag::node_event::NodeReporter;
use kegg::client::{CapturedResponse, ResponseTransport};
use serde_json::{Value, json};
use std::sync::Mutex;

#[derive(Debug)]
struct Responses(Mutex<Vec<String>>);

#[async_trait]
impl ResponseTransport for Responses {
    async fn response(&self, url: &str) -> kegg::error::Result<CapturedResponse> {
        Ok(CapturedResponse {
            url: url.into(),
            status: 200,
            response_url: url.into(),
            headers: std::collections::BTreeMap::from([(
                "content-type".into(),
                if url.ends_with("/json") {
                    "application/json".into()
                } else {
                    "text/plain".into()
                },
            )]),
            body: self.0.lock().unwrap().remove(0),
        })
    }
}

fn fixed() -> bool {
    true
}

fn save(name: &str, value: Value) {
    let Some(root) = std::env::var_os("KEGG_COUNTER_DIR") else {
        return;
    };
    let root = std::path::PathBuf::from(root);
    std::fs::write(
        root.join(format!("{name}.json")),
        serde_json::to_vec_pretty(&value).unwrap(),
    )
    .unwrap();
}

fn spec() -> Value {
    json!({"organism":"hsa","include_pathway_names":false})
}

fn hierarchy() -> Value {
    json!({"name":"br08901","children":[{"name":"Metabolism","children":[{"name":"Carbohydrate metabolism","children":[{"name":"00010 Synthetic pathway"}]}]}]})
}

fn context() -> NodeCtx {
    NodeCtx::new(SessionContext::new().runtime_env(), None)
}

fn input(ctx: &NodeCtx, values: Vec<Option<&str>>, port: u8) -> NodeInput {
    let batch = RecordBatch::try_new(
        Arc::new(Schema::new(vec![Field::new("gene", DataType::Utf8, true)])),
        vec![Arc::new(StringArray::from(values))],
    )
    .unwrap();
    NodeInput::new_dataframe(port, ctx.session().read_batch(batch).unwrap())
}

async fn run(
    config: Value,
    responses: Vec<String>,
    inputs: Vec<NodeInput>,
    ctx: &NodeCtx,
) -> Result<PortOutputs, DagError> {
    let client = KeggClient::with_rate_limit(3)
        .unwrap()
        .with_transport(Arc::new(Responses(Mutex::new(responses))));
    let mut node =
        KeggGenePathwaysNode::with_client(serde_json::from_value(config).unwrap(), client);
    node.execute(ctx, &inputs, &NodeReporter::noop()).await
}

async fn rejected(name: &str, config: Value, raw: Vec<String>, inputs: Vec<NodeInput>) {
    let result = run(config.clone(), raw.clone(), inputs, &context()).await;
    assert_eq!(result.is_ok(), !fixed(), "{name}: {result:?}");
    save(
        name,
        json!({"fixed":fixed(),"accepted":result.is_ok(),"spec":config,"responses":raw,"error":result.err().map(|error|error.to_string())}),
    );
}

#[test]
fn unknown_controls_are_not_silently_ignored() {
    let accepted =
        serde_json::from_value::<KeggGenePathwaysSpec>(json!({"organism":"hsa","official":true}))
            .is_ok();
    assert_eq!(accepted, !fixed());
    save(
        "unknown-controls",
        json!({"fixed":fixed(),"accepted":accepted}),
    );
}

#[tokio::test]
async fn input_count_and_port_are_not_ignored() {
    let ctx = context();
    let mut config = spec();
    config["gene_column"] = json!("gene");
    for (name, inputs) in [
        (
            "extra-input",
            vec![
                input(&ctx, vec![Some("10458")], 0),
                input(&ctx, vec![Some("10458")], 0),
            ],
        ),
        ("wrong-port", vec![input(&ctx, vec![Some("10458")], 1)]),
    ] {
        rejected(
            name,
            config.clone(),
            vec!["hsa:10458\tpath:hsa00010\n".into()],
            inputs,
        )
        .await;
    }
}

#[tokio::test]
async fn null_or_blank_selected_identity_is_not_discarded() {
    let ctx = context();
    let mut config = spec();
    config["gene_column"] = json!("gene");
    for (name, value) in [("null-selection", None), ("blank-selection", Some(" "))] {
        rejected(
            name,
            config.clone(),
            vec!["hsa:10458\tpath:hsa00010\n".into()],
            vec![input(&ctx, vec![Some("10458"), value], 0)],
        )
        .await;
    }
}

#[tokio::test]
async fn unused_selection_control_does_not_query_all_genes() {
    let mut config = spec();
    config["gene_column"] = json!("gene");
    rejected(
        "unconnected-selection",
        config,
        vec!["hsa:10458\tpath:hsa00010\n".into()],
        vec![],
    )
    .await;
}

#[tokio::test]
async fn oversized_rate_is_not_accepted_for_frozen_source() {
    let mut config = spec();
    config["requests_per_second"] = json!(100);
    rejected(
        "excess-rate",
        config,
        vec!["hsa:10458\tpath:hsa00010\n".into()],
        vec![],
    )
    .await;
}

#[tokio::test]
async fn organism_is_one_atomic_code_not_an_operation() {
    let mut config = spec();
    config["organism"] = json!("hsa/other");
    rejected(
        "organism-operation",
        config,
        vec!["hsa:10458\tpath:hsa00010\n".into()],
        vec![],
    )
    .await;
}

#[tokio::test]
async fn malformed_pairs_do_not_become_successful_annotations() {
    for (name, raw) in [
        ("missing-tab", "hsa:10458\n"),
        ("extra-tab", "hsa:10458\tpath:hsa00010\tignored\n"),
        ("empty-source", "\tpath:hsa00010\n"),
        ("empty-target", "hsa:10458\t\n"),
    ] {
        rejected(name, spec(), vec![raw.into()], vec![]).await;
    }
}

#[tokio::test]
async fn species_and_pathway_namespace_are_not_guessed() {
    for (name, raw) in [
        ("foreign-gene", "mmu:10458\tpath:hsa00010\n"),
        ("foreign-pathway", "hsa:10458\tpath:mmu00010\n"),
        ("wrong-target-namespace", "hsa:10458\tko:K00010\n"),
        ("bad-pathway-width", "hsa:10458\tpath:hsa10\n"),
    ] {
        rejected(name, spec(), vec![raw.into()], vec![]).await;
    }
}

#[tokio::test]
async fn false_hierarchy_success_is_not_nameless_metadata() {
    let mut config = spec();
    config["include_pathway_names"] = json!(true);
    for (name, body) in [
        ("empty-hierarchy", json!({})),
        ("wrong-hierarchy", json!({"name":"br99999","children":[]})),
        (
            "missing-pathway-metadata",
            json!({"name":"br08901","children":[]}),
        ),
    ] {
        rejected(
            name,
            config.clone(),
            vec!["hsa:10458\tpath:hsa00010\n".into(), body.to_string()],
            vec![],
        )
        .await;
    }
}

#[tokio::test]
async fn conflicting_names_do_not_choose_first_match() {
    let mut config = spec();
    config["include_pathway_names"] = json!(true);
    let value = json!({"name":"br08901","children":[{"name":"Metabolism","children":[{"name":"00010 First synthetic"},{"name":"00010 Conflicting synthetic"}]}]});
    rejected(
        "conflicting-hierarchy-name",
        config,
        vec!["hsa:10458\tpath:hsa00010\n".into(), value.to_string()],
        vec![],
    )
    .await;
}

#[tokio::test]
async fn multiple_classes_are_not_silently_reduced_to_first() {
    let mut config = spec();
    config["include_pathway_names"] = json!(true);
    let value = json!({"name":"br08901","children":[{"name":"B category","children":[{"name":"00010 Synthetic pathway"}]},{"name":"A category","children":[{"name":"00010 Synthetic pathway"}]}]});
    let output = run(
        config,
        vec!["hsa:10458\tpath:hsa00010\n".into(), value.to_string()],
        vec![],
        &context(),
    )
    .await
    .unwrap();
    let batches = output
        .dataframe(1)
        .unwrap()
        .clone()
        .collect()
        .await
        .unwrap();
    let actual = batches[0]
        .column(3)
        .as_any()
        .downcast_ref::<StringArray>()
        .unwrap()
        .value(0)
        .to_owned();
    assert_eq!(
        actual,
        if fixed() {
            "A category;B category"
        } else {
            "B category"
        }
    );
    save("multiple-classes", json!({"fixed":fixed(),"actual":actual}));
}

#[tokio::test]
async fn bare_selection_is_independent_of_output_prefix_style() {
    let ctx = context();
    let mut config = spec();
    config["gene_column"] = json!("gene");
    config["strip_gene_prefix"] = json!(false);
    let output = run(
        config,
        vec!["hsa:10458\tpath:hsa00010\n".into()],
        vec![input(&ctx, vec![Some("10458")], 0)],
        &ctx,
    )
    .await
    .unwrap();
    let batches = output
        .dataframe(0)
        .unwrap()
        .clone()
        .collect()
        .await
        .unwrap();
    let rows = batches.iter().map(RecordBatch::num_rows).sum::<usize>();
    assert_eq!(rows, if fixed() { 1 } else { 0 });
    save(
        "bare-selection-prefix-style",
        json!({"fixed":fixed(),"rows":rows}),
    );
}

#[tokio::test]
async fn official_clients_do_not_each_get_an_independent_rate_budget() {
    let first = KeggClient::with_rate_limit(3)
        .unwrap()
        .with_transport(Arc::new(Responses(Mutex::new(vec![
            "hsa:10458\tpath:hsa00010\n".into(),
        ]))));
    let second = KeggClient::with_rate_limit(3)
        .unwrap()
        .with_transport(Arc::new(Responses(Mutex::new(vec![
            "hsa:10458\tpath:hsa00010\n".into(),
        ]))));
    first.link("pathway", "hsa").await.unwrap();
    let start = std::time::Instant::now();
    second.link("pathway", "hsa").await.unwrap();
    let elapsed = start.elapsed().as_millis();
    assert_eq!(elapsed >= 250, fixed());
    save(
        "shared-official-rate",
        json!({"fixed":fixed(),"second_client_wait_ms":elapsed,"native_HTTP_success":false}),
    );
}
