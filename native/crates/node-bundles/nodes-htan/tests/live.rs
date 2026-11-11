use arrow_array::{Array, StringArray, UInt64Array};
use dag_core::dag::node_event::NodeReporter;
use dag_core::dag::{DagNode, NodeInput};
use dag_core::registry::{NodeCtx, NodeFactory};
use datafusion::prelude::SessionContext;

use nodes_htan::nodes::{HtanAtlasesNodeFactory, HtanDatasetsNodeFactory, HtanFilesNodeFactory};

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
#[ignore = "live HTAN Portal ClickHouse test"]
async fn htan_query_nodes_emit_dataframes() -> TestResult {
    let fixture = live_fixture::LiveFixture::load("htan")?;
    let atlases = run(&HtanAtlasesNodeFactory, serde_json::json!({})).await?;
    assert_eq!(atlases[0].num_rows(), fixture.number::<usize>("atlas_rows"));
    assert_eq!(atlases[0].num_columns(), 10);
    let ids = atlases[0]
        .column(0)
        .as_any()
        .downcast_ref::<StringArray>()
        .expect("atlas IDs");
    assert_eq!(ids.value(0), fixture.text("first_atlas"));

    let datasets = run(
        &HtanDatasetsNodeFactory,
        serde_json::json!({"atlas": fixture.text("atlas"), "max_results": 1000}),
    )
    .await?;
    assert!(datasets[0].num_rows() > 0);
    assert_eq!(datasets[0].num_columns(), 10);

    let files = run(
        &HtanFilesNodeFactory,
        serde_json::json!({
            "atlas": fixture.text("atlas"),
            "level": fixture.text("level"),
            "assay": fixture.text("assay"),
            "file_format": fixture.text("file_format"),
            "max_results": 5
        }),
    )
    .await?;
    assert_eq!(files[0].num_rows(), 5);
    assert_eq!(files[0].num_columns(), 14);
    let formats = files[0]
        .column(6)
        .as_any()
        .downcast_ref::<StringArray>()
        .expect("file formats");
    assert!(formats.iter().flatten().all(|value| value == fixture.text("file_format")));

    let selected_file_counts = atlases[0]
        .column(7)
        .as_any()
        .downcast_ref::<UInt64Array>()
        .expect("file rows");
    let selected_index = (0..ids.len())
        .find(|index| ids.value(*index) == fixture.text("atlas"))
        .expect("configured atlas");
    assert_eq!(selected_file_counts.value(selected_index), fixture.number::<u64>("file_count"));

    Ok(())
}
