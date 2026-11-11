use std::sync::Arc;

use arrow_array::Int64Array;
use async_trait::async_trait;
use dag_core::dag::graph::{DAG, PortOutputs};
use dag_core::dag::node_event::NodeReporter;
use dag_core::dag::runtime::{RuntimeStatus, SchedulerConfig};
use dag_core::dag::{DagError, DagNode, LocalTaskExecutor, NodeInput, NodePorts};
use dag_core::registry::NodeCtx;
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};

use crate::shared::{build_json_batch, extract_rows, json_to_output};

#[derive(Clone)]
struct ConversionProbe {
    ports: NodePorts,
    payload: Option<Value>,
    endpoint: &'static str,
    query: Option<&'static str>,
}

impl ConversionProbe {
    fn source(endpoint: &'static str, payload: Value) -> Self {
        Self {
            ports: NodePorts::new().add_output_port(None),
            payload: Some(payload),
            endpoint,
            query: None,
        }
    }

    fn sql(query: &'static str) -> Self {
        Self {
            ports: NodePorts::new().add_input_port(None).add_output_port(None),
            payload: None,
            endpoint: "SYNTHETIC_CONVERTER_TEST_NOT_HTTP",
            query: Some(query),
        }
    }
}

#[async_trait]
impl DagNode for ConversionProbe {
    fn ports(&self) -> &NodePorts {
        &self.ports
    }

    fn kind(&self) -> &'static str {
        "synthetic_opengwas_conversion_probe"
    }

    fn as_any(&self) -> &dyn std::any::Any {
        self
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(self.clone())
    }

    async fn execute(
        &mut self,
        context: &NodeCtx,
        inputs: &[NodeInput],
        _reporter: &NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        if let Some(payload) = &self.payload {
            return json_to_output(context, payload, self.endpoint).await;
        }
        let session = context.session();
        session.register_table("port_0", inputs[0].dataframe()?.clone().into_view())?;
        let batches = session.sql(self.query.unwrap()).await?.collect().await?;
        let mut output = PortOutputs::new();
        output.insert(0, session.read_batches(batches)?);
        Ok(output)
    }
}

#[test]
fn empty_json_arrays_have_no_fabricated_rows_or_fields() {
    for response in [
        json!([]),
        json!({"study": []}),
        json!({"study1": [], "study2": []}),
    ] {
        let batch = build_json_batch(&extract_rows(&response)).unwrap();
        assert_eq!((batch.num_rows(), batch.num_columns()), (0, 0));
    }
}

#[test]
fn empty_object_records_are_not_treated_as_empty_responses() {
    for response in [json!([{}]), json!([null]), json!(["rs1205"]), json!({})] {
        assert!(build_json_batch(&extract_rows(&response)).is_err());
    }
}

#[tokio::test]
async fn empty_conversion_dag_materializes_counts_and_keeps_ineligible_estimates_failed() {
    let context = NodeCtx::new(SessionContext::new().runtime_env(), None);
    let settings = SchedulerConfig {
        max_concurrency: 1,
        ..SchedulerConfig::default()
    };
    for endpoint in [
        "/associations",
        "/tophits",
        "/phewas",
        "/variants/rsid",
        "/variants/chrpos",
    ] {
        for (payload, query, source_ok, sql_ok) in [
            (
                json!([]),
                "SELECT count(*) AS records FROM port_0",
                true,
                true,
            ),
            (json!([]), "SELECT beta, pval FROM port_0", true, false),
            (
                json!([{}]),
                "SELECT count(*) AS records FROM port_0",
                false,
                false,
            ),
        ] {
            let mut dag = DAG::default();
            dag.set_task_executor(Arc::new(LocalTaskExecutor::with_workspace_root(
                std::env::temp_dir().join(format!("opengwas-empty-probe-{}", std::process::id())),
            )));
            dag.add_node(
                "source".into(),
                Box::new(ConversionProbe::source(endpoint, payload)),
            )
            .unwrap();
            dag.add_node("query".into(), Box::new(ConversionProbe::sql(query)))
                .unwrap();
            dag.add_node(
                "sink".into(),
                Box::new(ConversionProbe::sql("SELECT * FROM port_0")),
            )
            .unwrap();
            dag.add_edge("source", "query", 0, 0).unwrap();
            dag.add_edge("query", "sink", 0, 0).unwrap();
            let report = dag.run(&settings, &context, None).await.unwrap();
            assert_eq!(
                report.status("source"),
                Some(if source_ok {
                    RuntimeStatus::Success
                } else {
                    RuntimeStatus::Failed
                }),
                "{endpoint}"
            );
            assert_eq!(
                report.status("query"),
                Some(if sql_ok {
                    RuntimeStatus::Success
                } else if source_ok {
                    RuntimeStatus::Failed
                } else {
                    RuntimeStatus::Skipped
                }),
                "{endpoint}"
            );
            assert_eq!(
                report.status("sink"),
                Some(if sql_ok {
                    RuntimeStatus::Success
                } else {
                    RuntimeStatus::Skipped
                }),
                "{endpoint}"
            );
            assert_eq!(report.ok, sql_ok);
            if sql_ok {
                let batches = dag
                    .output("sink")
                    .unwrap()
                    .dataframe(0)
                    .unwrap()
                    .clone()
                    .collect()
                    .await
                    .unwrap();
                assert_eq!(
                    batches.iter().map(|batch| batch.num_rows()).sum::<usize>(),
                    1
                );
                let counts = batches[0]
                    .column(0)
                    .as_any()
                    .downcast_ref::<Int64Array>()
                    .unwrap();
                assert_eq!(counts.value(0), 0);
            } else {
                assert!(dag.output("sink").is_none());
            }
        }
    }
}
