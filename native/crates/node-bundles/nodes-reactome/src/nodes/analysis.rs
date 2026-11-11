//! `source_reactome_analysis` — over-representation analysis node.

use std::sync::Arc;

use arrow_array::{Array, Float64Array, RecordBatch, StringArray, UInt64Array};
use arrow_schema::{DataType, Field, Schema};
use async_trait::async_trait;
use datafusion::dataframe::DataFrame;
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;

use dag_core::dag::{DagError, DagNode, NodePorts, graph::PortOutputs};
use dag_core::registry::{NodeCtx, NodeFactory};

use super::pathways::str_array;
use crate::ReactomeClient;
use crate::types::AnalysisResult;

/// Spec for [`ReactomeAnalysisNode`].
#[derive(Debug, Clone, Default, JsonSchema, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ReactomeAnalysisSpec {
    /// Gene or protein identifiers to analyse, e.g. `["TP53", "BRCA1"]`.
    #[serde(default)]
    pub identifiers: Option<Vec<String>>,

    /// Project orthologs to human. Default `true`.
    #[serde(default)]
    pub project_to_human: Option<bool>,
}

#[derive(Clone)]
pub struct ReactomeAnalysisNode {
    meta: NodePorts,
    spec: ReactomeAnalysisSpec,
    client: Option<ReactomeClient>,
}

impl ReactomeAnalysisNode {
    pub fn with_client(spec: ReactomeAnalysisSpec, client: ReactomeClient) -> Self {
        Self {
            meta: port_layout(),
            spec,
            client: Some(client),
        }
    }
}

pub struct ReactomeAnalysisNodeFactory {}

fn port_layout() -> NodePorts {
    NodePorts::new().add_output_port(None)
}

impl NodeFactory for ReactomeAnalysisNodeFactory {
    fn kind(&self) -> &'static str {
        "source_reactome_analysis"
    }

    fn desc(&self) -> &'static str {
        "Submit gene identifiers for Reactome pathway over-representation analysis."
    }

    fn doc(&self) -> &'static str {
        "A source node that submits identifiers to the Reactome Analysis \
        Service and emits enriched pathways with p-values and FDR as a \
        DataFrame.\n\n\
        Output schema: `stable_id, pathway_name, entities_found, \
        entities_total, p_value, fdr`.\n\n\
        Sort by `fdr` ascending to find the most significant pathways; filter \
        by `fdr < 0.05` for significance."
    }

    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(ReactomeAnalysisSpec)
    }

    fn ports(&self) -> NodePorts {
        port_layout()
    }

    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let node_spec: ReactomeAnalysisSpec = serde_json::from_value(spec)?;
        Ok(Box::new(ReactomeAnalysisNode {
            meta: port_layout(),
            spec: node_spec,
            client: None,
        }))
    }
}

#[async_trait]
impl DagNode for ReactomeAnalysisNode {
    fn ports(&self) -> &NodePorts {
        &self.meta
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new((*self).clone())
    }

    fn kind(&self) -> &'static str {
        "source_reactome_analysis"
    }

    fn as_any(&self) -> &dyn std::any::Any {
        self
    }

    async fn execute(
        &mut self,
        ctx: &NodeCtx,
        inputs: &[dag_core::dag::NodeInput],
        _reporter: &dag_core::dag::node_event::NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        if !inputs.is_empty() {
            return Err(DagError::Schedule(
                "Reactome source accepts zero DAG inputs".into(),
            ));
        }
        let ids = self.spec.identifiers.clone().ok_or_else(|| {
            DagError::Schedule("source_reactome_analysis: `identifiers` list is required".into())
        })?;
        if ids.is_empty() {
            return Err(DagError::Schedule(
                "source_reactome_analysis: `identifiers` cannot be empty".into(),
            ));
        }

        let ids = crate::qualify::identifiers(&ids)
            .map_err(|error| DagError::Schedule(error.to_string()))?;
        let client = self.client.clone().unwrap_or_else(ReactomeClient::new);
        let result = client
            .analyse_identifiers(&ids, self.spec.project_to_human.unwrap_or(true))
            .await
            .map_err(|e| DagError::Schedule(format!("Reactome analysis failed: {e}")))?;
        crate::qualify::analysis(&result, self.spec.project_to_human.unwrap_or(true))
            .map_err(|error| DagError::Schedule(error.to_string()))?;

        let session = ctx.session();
        let batch = build_analysis_batch(&result)?;
        let df = session.read_batch(batch).map_err(|e| {
            DagError::Schedule(format!("failed to read Reactome analysis batch: {e}"))
        })?;
        let mut res: PortOutputs = PortOutputs::new();
        res.insert(0, df);
        Ok(res)
    }
}

pub fn build_analysis_batch(result: &AnalysisResult) -> Result<RecordBatch, DagError> {
    let schema = Arc::new(Schema::new(vec![
        Field::new("stable_id", DataType::Utf8, true),
        Field::new("pathway_name", DataType::Utf8, true),
        Field::new("entities_found", DataType::UInt64, true),
        Field::new("entities_total", DataType::UInt64, true),
        Field::new("p_value", DataType::Float64, true),
        Field::new("fdr", DataType::Float64, true),
    ]));

    let rows = &result.pathways;
    RecordBatch::try_new(
        schema,
        vec![
            str_array(rows.iter().map(|p| Some(p.stable_id.clone())).collect()),
            str_array(rows.iter().map(|p| Some(p.name.clone())).collect()),
            Arc::new(UInt64Array::from(
                rows.iter().map(|p| p.entities.found).collect::<Vec<_>>(),
            )),
            Arc::new(UInt64Array::from(
                rows.iter().map(|p| p.entities.total).collect::<Vec<_>>(),
            )),
            Arc::new(Float64Array::from(
                rows.iter().map(|p| p.entities.p_value).collect::<Vec<_>>(),
            )),
            Arc::new(Float64Array::from(
                rows.iter().map(|p| p.entities.fdr).collect::<Vec<_>>(),
            )),
        ],
    )
    .map_err(|e| DagError::Schedule(format!("failed to build Reactome analysis batch: {e}")))
}
