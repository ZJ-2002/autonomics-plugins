use arrow_array::{Array, StringArray};
use dag_core::dag::node_event::NodeReporter;
use dag_core::dag::{DagNode, NodeInput};
use dag_core::registry::{NodeCtx, NodeFactory};
use datafusion::prelude::SessionContext;

use nodes_scp::nodes::{
    ScpFilesNodeFactory, ScpSearchNodeFactory, ScpStudiesNodeFactory, ScpStudyNodeFactory,
};

#[path = "../../test-support/live_fixture.rs"]
mod live_fixture;

type TestResult<T = ()> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

fn node_ctx() -> NodeCtx {
    NodeCtx::new(SessionContext::new().runtime_env(), None)
}

async fn run(
    factory: &dyn NodeFactory,
    spec: serde_json::Value,
) -> TestResult<Vec<arrow_array::RecordBatch>> {
    let ctx = node_ctx();
    let mut node = factory.build(spec, NodeCtx::clone(&ctx))?;
    let inputs: &[NodeInput] = &[];
    let outputs = node.execute(&ctx, inputs, &NodeReporter::noop()).await?;
    let dataframe = outputs.dataframe(0).map_err(std::io::Error::other)?;
    Ok(dataframe.clone().collect().await?)
}

#[tokio::test]
#[ignore = "live Broad Single Cell Portal API test"]
async fn scp_query_nodes_emit_dataframes() -> TestResult {
    let fixture = live_fixture::LiveFixture::load("scp")?;
    let studies = run(
        &ScpStudiesNodeFactory,
        serde_json::json!({"query": fixture.text("query"), "max_results": 5}),
    )
    .await?;
    assert!(studies[0].num_rows() > 0);
    let accessions = studies[0]
        .column(0)
        .as_any()
        .downcast_ref::<StringArray>()
        .expect("accessions");
    assert!(accessions.iter().flatten().any(|value| value == fixture.text("accession")));

    let search = run(
        &ScpSearchNodeFactory,
        serde_json::json!({"terms": fixture.text("search_terms"), "search_type": "study", "page": 1}),
    )
    .await?;
    assert!(search[0].num_rows() > 0);
    assert_eq!(search[0].num_columns(), 14);

    let study = run(
        &ScpStudyNodeFactory,
        serde_json::json!({"accession": fixture.text("accession")}),
    )
    .await?;
    assert_eq!(study[0].num_rows(), 1);
    assert_eq!(study[0].num_columns(), 14);

    let files = run(
        &ScpFilesNodeFactory,
        serde_json::json!({"accession": fixture.text("accession"), "file_type": "Expression Matrix"}),
    )
    .await?;
    assert_eq!(files[0].num_rows(), 1);
    assert_eq!(files[0].num_columns(), 8);

    Ok(())
}
