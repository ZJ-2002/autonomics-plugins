use std::sync::Arc;

use arrow_array::{Array, RecordBatch, StringArray, UInt64Array};
use arrow_schema::{DataType, Field, Schema};
use async_trait::async_trait;
use datafusion::dataframe::DataFrame;
use datafusion::prelude::SessionContext;
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;

use dag_core::dag::{DagError, DagNode, NodePorts, graph::PortOutputs};
use dag_core::registry::{NodeCtx, NodeFactory};

use crate::ClinicalTrialsClient;
use crate::types::Study;

#[derive(Debug, Clone, JsonSchema, Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
pub struct ClinicalTrialsStudySpec {
    /// NCT identifier.
    pub nct_id: String,
    #[serde(default)]
    pub audit_path: Option<String>,
}

#[derive(Clone)]
pub struct ClinicalTrialsStudyNode {
    meta: NodePorts,
    spec: ClinicalTrialsStudySpec,
    client: Option<ClinicalTrialsClient>,
}

pub struct ClinicalTrialsStudyNodeFactory;

fn port_layout() -> NodePorts {
    NodePorts::new().add_output_port(None)
}

impl NodeFactory for ClinicalTrialsStudyNodeFactory {
    fn kind(&self) -> &'static str {
        "source_clinicaltrials_study"
    }

    fn desc(&self) -> &'static str {
        "Fetch one ClinicalTrials.gov study as a table."
    }

    fn doc(&self) -> &'static str {
        "A zero-input source node that resolves one ClinicalTrials.gov study. Output columns: \
        nct_id, brief_title, official_title, overall_status, start_date, completion_date, \
        lead_sponsor, organization, study_type, phases, enrollment, conditions, keywords, \
        interventions, primary_outcomes, brief_summary. Optional audit_path stores received \
        UTF8 bodies and request identity before table construction; this sidecar is not an \
        output port, node completion, version freeze or clinical/scientific certification."
    }

    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(ClinicalTrialsStudySpec)
    }

    fn ports(&self) -> NodePorts {
        port_layout()
    }

    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec = serde_json::from_value::<ClinicalTrialsStudySpec>(spec)?;
        Ok(Box::new(ClinicalTrialsStudyNode {
            meta: port_layout(),
            spec,
            client: None,
        }))
    }
}

impl ClinicalTrialsStudyNode {
    pub fn with_client(spec: ClinicalTrialsStudySpec, client: ClinicalTrialsClient) -> Self {
        Self {
            meta: port_layout(),
            spec,
            client: Some(client),
        }
    }
}

#[async_trait]
impl DagNode for ClinicalTrialsStudyNode {
    fn ports(&self) -> &NodePorts {
        &self.meta
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new((*self).clone())
    }

    fn kind(&self) -> &'static str {
        "source_clinicaltrials_study"
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
                "ClinicalTrials source has no input ports".into(),
            ));
        }
        if let Some(path) = &self.spec.audit_path {
            crate::publication::validate_output_path(path)?;
        }
        let client = self.client.clone().unwrap_or_default().for_run();
        let lookup = client
            .study(&self.spec.nct_id)
            .await
            .map_err(|error| DagError::Schedule(format!("ClinicalTrials request failed: {error}")));
        crate::audit::save(ctx, &self.spec.audit_path, &client, serde_json::json!({"spec":self.spec,"lookup_error":lookup.as_ref().err().map(ToString::to_string)})).await?;
        let study = lookup?;
        let batch = record_batch(&study)
            .map_err(|error| DagError::Schedule(format!("ClinicalTrials batch failed: {error}")))?;
        let dataframe = ctx
            .session()
            .read_batch(batch)
            .map_err(|error| DagError::Schedule(error.to_string()))?;
        let mut output = PortOutputs::new();
        output.insert(0, dataframe);
        Ok(output)
    }
}

fn join(values: &[String], separator: &str) -> Option<String> {
    (!values.is_empty()).then(|| values.join(separator))
}

fn record_batch(study: &Study) -> Result<RecordBatch, arrow_schema::ArrowError> {
    let protocol = &study.protocol_section;
    let identification = &protocol.identification_module;
    let status = &protocol.status_module;
    let schema = Arc::new(Schema::new(vec![
        Field::new("nct_id", DataType::Utf8, true),
        Field::new("brief_title", DataType::Utf8, true),
        Field::new("official_title", DataType::Utf8, true),
        Field::new("overall_status", DataType::Utf8, true),
        Field::new("start_date", DataType::Utf8, true),
        Field::new("completion_date", DataType::Utf8, true),
        Field::new("lead_sponsor", DataType::Utf8, true),
        Field::new("organization", DataType::Utf8, true),
        Field::new("study_type", DataType::Utf8, true),
        Field::new("phases", DataType::Utf8, true),
        Field::new("enrollment", DataType::UInt64, true),
        Field::new("conditions", DataType::Utf8, true),
        Field::new("keywords", DataType::Utf8, true),
        Field::new("interventions", DataType::Utf8, true),
        Field::new("primary_outcomes", DataType::Utf8, true),
        Field::new("brief_summary", DataType::Utf8, true),
    ]));

    let interventions = protocol
        .arms_interventions_module
        .interventions
        .iter()
        .filter_map(|intervention| {
            match (
                intervention.intervention_type.as_deref(),
                intervention.name.as_deref(),
            ) {
                (Some(category), Some(name)) => Some(format!("{category}:{name}")),
                (Some(category), None) => Some(category.to_owned()),
                (None, Some(name)) => Some(name.to_owned()),
                (None, None) => None,
            }
        })
        .collect::<Vec<_>>();
    let primary_outcomes = protocol
        .outcomes_module
        .primary_outcomes
        .iter()
        .filter_map(|outcome| outcome.measure.clone())
        .collect::<Vec<_>>();
    let columns = vec![
        Arc::new(StringArray::from(vec![identification.nct_id.as_deref()])) as Arc<dyn Array>,
        Arc::new(StringArray::from(vec![
            identification.brief_title.as_deref(),
        ])),
        Arc::new(StringArray::from(vec![
            identification.official_title.as_deref(),
        ])),
        Arc::new(StringArray::from(vec![status.overall_status.as_deref()])),
        Arc::new(StringArray::from(vec![
            status
                .start_date_struct
                .as_ref()
                .and_then(|date| date.date.as_deref()),
        ])),
        Arc::new(StringArray::from(vec![
            status
                .completion_date_struct
                .as_ref()
                .and_then(|date| date.date.as_deref()),
        ])),
        Arc::new(StringArray::from(vec![
            protocol
                .sponsor_collaborators_module
                .lead_sponsor
                .as_ref()
                .and_then(|sponsor| sponsor.name.as_deref()),
        ])),
        Arc::new(StringArray::from(vec![
            identification
                .organization
                .as_ref()
                .and_then(|organization| organization.full_name.as_deref()),
        ])),
        Arc::new(StringArray::from(vec![
            protocol.design_module.study_type.as_deref(),
        ])),
        Arc::new(StringArray::from(vec![
            join(&protocol.design_module.phases, ";").as_deref(),
        ])),
        Arc::new(UInt64Array::from(vec![
            protocol
                .design_module
                .enrollment_info
                .as_ref()
                .and_then(|enrollment| enrollment.count),
        ])),
        Arc::new(StringArray::from(vec![
            join(&protocol.conditions_module.conditions, ";").as_deref(),
        ])),
        Arc::new(StringArray::from(vec![
            join(&protocol.conditions_module.keywords, ";").as_deref(),
        ])),
        Arc::new(StringArray::from(vec![
            join(&interventions, ";").as_deref(),
        ])),
        Arc::new(StringArray::from(vec![
            join(&primary_outcomes, ";").as_deref(),
        ])),
        Arc::new(StringArray::from(vec![
            protocol.description_module.brief_summary.as_deref(),
        ])),
    ];
    RecordBatch::try_new(schema, columns)
}

#[cfg(test)]
#[path = "study_tests.rs"]
mod proof_regressions;

#[cfg(test)]
#[path = "contract_tests.rs"]
mod proof_contracts;
