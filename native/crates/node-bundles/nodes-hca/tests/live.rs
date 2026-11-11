use arrow_array::{Array, StringArray, UInt64Array};
use dag_core::dag::node_event::NodeReporter;
use dag_core::dag::{DagNode, NodeInput};
use dag_core::registry::{NodeCtx, NodeFactory};
use datafusion::prelude::SessionContext;

use nodes_hca::nodes::{
    HcaFilesNodeFactory, HcaProjectNodeFactory, HcaProjectsNodeFactory, HcaSamplesNodeFactory,
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
#[ignore = "live Human Cell Atlas Azul API test"]
async fn hca_query_nodes_emit_dataframes() -> TestResult {
    let fixture = live_fixture::LiveFixture::load("hca")?;
    let project_id = fixture.text("project_id");

    let projects = run(
        &HcaProjectsNodeFactory,
        serde_json::json!({"query": fixture.text("query"), "max_results": 5}),
    )
    .await?;
    assert_eq!(projects.len(), 1);
    assert_eq!(projects[0].num_rows(), 1);
    let ids = projects[0]
        .column(0)
        .as_any()
        .downcast_ref::<StringArray>()
        .expect("project IDs");
    assert_eq!(ids.value(0), project_id);

    let project = run(
        &HcaProjectNodeFactory,
        serde_json::json!({"project_id": project_id}),
    )
    .await?;
    assert_eq!(project[0].num_rows(), 1);
    assert_eq!(project[0].num_columns(), 22);

    let files = run(
        &HcaFilesNodeFactory,
        serde_json::json!({"project_id": project_id, "file_format": "h5", "size": 10}),
    )
    .await?;
    assert_eq!(files[0].num_rows(), 1);
    let cell_counts = files[0]
        .column(13)
        .as_any()
        .downcast_ref::<UInt64Array>()
        .expect("matrix cell counts");
    assert!(cell_counts.is_null(0));

    let samples = run(
        &HcaSamplesNodeFactory,
        serde_json::json!({"project_id": project_id, "size": 10}),
    )
    .await?;
    assert_eq!(samples[0].num_rows(), fixture.number::<usize>("sample_rows"));
    assert_eq!(samples[0].num_columns(), 8);

    Ok(())
}
