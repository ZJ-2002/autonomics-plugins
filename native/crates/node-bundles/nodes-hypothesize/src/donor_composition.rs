//! Donor-level single-cell composition test.
//!
//! Cells are first aggregated to donor-by-cell-type counts. Each cell type is
//! then tested with a binomial logistic model (`cell count / donor total`
//! versus condition). This is a grouped-binomial likelihood, not a
//! donor-overdispersion or donor-permutation model.

use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use arrow_array::{Array, BooleanArray, Float64Array, RecordBatch, StringArray, UInt64Array};
use arrow_schema::{DataType, Field, Schema};
use async_trait::async_trait;
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;

use dag_core::node::{DagNode, NodeInput, NodePorts};
use dag_core::registry::{NodeCtx, NodeFactory};
use dag_core::{dag::DagError, dag::graph::PortOutputs};

use crate::common::{HypoNodeError, collect_input};

pub const DONOR_COMPOSITION_KIND: &str = "hypothesize.donor_composition_test";

fn default_min_donor_cells() -> u64 {
    10
}

fn default_correction() -> String {
    "BH".into()
}

fn default_min_donors_per_condition() -> u64 {
    1
}

#[derive(Debug, Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DonorCompositionSpec {
    pub donor_col: String,
    pub cell_type_col: String,
    pub condition_col: String,
    pub cell_id_col: Option<String>,
    pub reference: String,
    pub test: String,
    pub cell_types: Option<Vec<String>>,
    #[serde(default = "default_min_donor_cells")]
    pub min_donor_cells: u64,
    #[serde(default = "default_min_donors_per_condition")]
    pub min_donors_per_condition: u64,
    #[serde(default = "default_correction")]
    pub correction: String,
}

pub struct DonorCompositionNodeFactory;

#[derive(Clone)]
pub struct DonorCompositionNode {
    ports: NodePorts,
    spec: DonorCompositionSpec,
}

fn validate(spec: &DonorCompositionSpec) -> Result<(), String> {
    for (name, value) in [
        ("donor_col", &spec.donor_col),
        ("cell_type_col", &spec.cell_type_col),
        ("condition_col", &spec.condition_col),
        ("reference", &spec.reference),
        ("test", &spec.test),
    ] {
        if value.is_empty() || value.trim() != value {
            return Err(format!(
                "{name} cannot be empty or have surrounding whitespace"
            ));
        }
    }
    let mut columns = BTreeSet::new();
    for column in [&spec.donor_col, &spec.cell_type_col, &spec.condition_col]
        .into_iter()
        .chain(spec.cell_id_col.as_ref())
    {
        if column.is_empty() || column.trim() != column || !columns.insert(column) {
            return Err("input column bindings must be distinct and nonempty without surrounding whitespace".into());
        }
    }
    if let Some(cell_types) = &spec.cell_types {
        let mut seen = BTreeSet::new();
        if cell_types.is_empty()
            || cell_types
                .iter()
                .any(|value| value.is_empty() || value.trim() != value || !seen.insert(value))
        {
            return Err(
                "cell_types must be a nonempty unique frozen family without surrounding whitespace"
                    .into(),
            );
        }
    }
    if spec.reference == spec.test {
        return Err("reference and test conditions must differ".into());
    }
    if spec.min_donor_cells == 0 {
        return Err("min_donor_cells must be greater than zero".into());
    }
    if spec.min_donors_per_condition == 0 {
        return Err("min_donors_per_condition must be greater than zero".into());
    }
    hypothesize::AdjustMethod::parse(&spec.correction).map_err(|error| error.to_string())?;
    Ok(())
}

fn port_layout() -> NodePorts {
    NodePorts::new()
        .add_input_port(None)
        .add_output_port(None)
        .add_output_port(None)
}

impl NodeFactory for DonorCompositionNodeFactory {
    fn kind(&self) -> &'static str {
        DONOR_COMPOSITION_KIND
    }
    fn desc(&self) -> &'static str {
        "Tests aggregated donor cell-type counts with a two-condition grouped-binomial model."
    }
    fn doc(&self) -> &'static str {
        "Input is a cell-level table with distinct donor, cell-type, and condition columns, optionally a globally unique cell_id column. An explicit cell_types family preserves its order, absent tests, and multiplicity denominator; without it only observed types are tested. After the minimum-cell filter, each group must meet min_donors_per_condition (default 1). The model has only an intercept and two-condition slope, using its finite analytic MLE. Failed tests retain NULL statistics and explicit status, not dropped rows. Output 0 reports test-versus-reference log-odds, Wald z, p, family size, and group donor counts; output 1 retains all donor compositions and eligible_by_cell_count. This grouped-binomial model does not account for donor overdispersion, covariates, random effects or donor permutations and must not be represented as donor-robust inference."
    }
    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(DonorCompositionSpec)
    }
    fn ports(&self) -> NodePorts {
        port_layout()
    }
    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let spec: DonorCompositionSpec = serde_json::from_value(spec)?;
        validate(&spec).map_err(dag_core::registry::error::Error::Unknown)?;
        Ok(Box::new(DonorCompositionNode {
            ports: port_layout(),
            spec,
        }))
    }
}

#[derive(Clone)]
struct DonorCompositionNodeInner {
    meta: NodePorts,
    spec: DonorCompositionSpec,
}

impl DonorCompositionNode {
    fn inner(&self) -> DonorCompositionNodeInner {
        DonorCompositionNodeInner {
            meta: self.ports.clone(),
            spec: self.spec.clone(),
        }
    }
}

#[async_trait]
impl DagNode for DonorCompositionNode {
    fn ports(&self) -> &NodePorts {
        &self.ports
    }
    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(self.clone())
    }
    fn kind(&self) -> &'static str {
        DONOR_COMPOSITION_KIND
    }
    fn as_any(&self) -> &dyn std::any::Any {
        self
    }
    async fn execute(
        &mut self,
        ctx: &NodeCtx,
        inputs: &[NodeInput],
        reporter: &dag_core::dag::node_event::NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        self.inner().execute(ctx, inputs, reporter).await
    }
}

#[async_trait]
impl DagNode for DonorCompositionNodeInner {
    fn ports(&self) -> &NodePorts {
        &self.meta
    }
    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new(self.clone())
    }
    fn kind(&self) -> &'static str {
        DONOR_COMPOSITION_KIND
    }
    fn as_any(&self) -> &dyn std::any::Any {
        self
    }
    async fn execute(
        &mut self,
        ctx: &NodeCtx,
        inputs: &[NodeInput],
        _reporter: &dag_core::dag::node_event::NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        let batches = collect_input(inputs).await.map_err(DagError::from)?;
        let donors = extract_triple(&batches, &self.spec)?;
        let tests = fit_composition(&donors, &self.spec)?;
        let composition = composition_batch(&donors, &self.spec)
            .map_err(|e| DagError::from(HypoNodeError::Spec(e)))?;
        let test_batch = test_batch(&tests).map_err(|e| DagError::from(HypoNodeError::Spec(e)))?;
        let session = ctx.session();
        let composition_df = session
            .read_batch(composition)
            .map_err(|e| DagError::from(HypoNodeError::ReadBatch(e.to_string())))?;
        let test_df = session
            .read_batch(test_batch)
            .map_err(|e| DagError::from(HypoNodeError::ReadBatch(e.to_string())))?;
        let mut outputs = PortOutputs::new();
        outputs.insert(0, test_df);
        outputs.insert(1, composition_df);
        Ok(outputs)
    }
}

struct DonorTable {
    donors: BTreeMap<String, String>,
    totals: BTreeMap<String, u64>,
    counts: BTreeMap<(String, String), u64>,
    cell_types: BTreeSet<String>,
}

struct CompositionResult {
    cell_type: String,
    donors: u64,
    cells: u64,
    reference_proportion: Option<f64>,
    test_proportion: Option<f64>,
    log_odds_ratio: Option<f64>,
    standard_error: Option<f64>,
    z: Option<f64>,
    p_raw: Option<f64>,
    p_adj: Option<f64>,
    family_size: u64,
    reference_donors: u64,
    test_donors: u64,
    fit_status: &'static str,
}

fn string_column(batch: &RecordBatch, name: &str) -> Result<Vec<Option<String>>, HypoNodeError> {
    let values = batch
        .column_by_name(name)
        .and_then(|array| array.as_any().downcast_ref::<StringArray>())
        .ok_or_else(|| HypoNodeError::Column(name.to_string()))?;
    Ok((0..values.len())
        .map(|row| (!values.is_null(row)).then(|| values.value(row).to_string()))
        .collect())
}

fn extract_triple(
    batches: &[RecordBatch],
    spec: &DonorCompositionSpec,
) -> Result<DonorTable, HypoNodeError> {
    let mut table = DonorTable {
        donors: BTreeMap::new(),
        totals: BTreeMap::new(),
        counts: BTreeMap::new(),
        cell_types: BTreeSet::new(),
    };
    let mut cell_ids = BTreeSet::new();
    for batch in batches {
        let donors = string_column(batch, &spec.donor_col)?;
        let cell_types = string_column(batch, &spec.cell_type_col)?;
        let conditions = string_column(batch, &spec.condition_col)?;
        let identifiers = spec
            .cell_id_col
            .as_ref()
            .map(|column| string_column(batch, column))
            .transpose()?;
        if donors.len() != cell_types.len() || donors.len() != conditions.len() {
            return Err(HypoNodeError::Column("column length mismatch".into()));
        }
        for row in 0..batch.num_rows() {
            let donor = donors[row]
                .as_deref()
                .filter(|value| !value.is_empty() && value.trim() == *value);
            let cell_type = cell_types[row]
                .as_deref()
                .filter(|value| !value.is_empty() && value.trim() == *value);
            let condition = conditions[row]
                .as_deref()
                .filter(|value| !value.is_empty() && value.trim() == *value);
            let (Some(donor), Some(cell_type), Some(condition)) = (donor, cell_type, condition)
            else {
                return Err(HypoNodeError::Column(
                    "donor/cell_type/condition cannot be null, empty or have surrounding whitespace".into(),
                ));
            };
            if let Some(identifiers) = &identifiers {
                let identifier = identifiers[row]
                    .as_deref()
                    .filter(|value| !value.is_empty() && value.trim() == *value)
                    .ok_or_else(|| {
                        HypoNodeError::Column(
                            "cell_id cannot be null, empty or have surrounding whitespace".into(),
                        )
                    })?;
                if !cell_ids.insert(identifier.to_string()) {
                    return Err(HypoNodeError::Spec(format!(
                        "duplicate cell_id `{identifier}`"
                    )));
                }
            }
            if condition != spec.reference && condition != spec.test {
                return Err(HypoNodeError::Spec(format!(
                    "unexpected condition `{condition}`; expected {} or {}",
                    spec.reference, spec.test
                )));
            }
            match table.donors.get(donor) {
                Some(previous) if previous != condition => {
                    return Err(HypoNodeError::Spec(format!(
                        "donor `{donor}` maps to multiple conditions"
                    )));
                }
                _ => {}
            }
            table
                .donors
                .insert(donor.to_string(), condition.to_string());
            *table.totals.entry(donor.to_string()).or_default() += 1;
            *table
                .counts
                .entry((donor.to_string(), cell_type.to_string()))
                .or_default() += 1;
            table.cell_types.insert(cell_type.to_string());
        }
    }
    if let Some(cell_types) = &spec.cell_types {
        table.cell_types.extend(cell_types.iter().cloned());
    }
    if table.donors.len() < 2 {
        return Err(HypoNodeError::Insufficient(
            "at least two donors are required".into(),
        ));
    }
    if !table.donors.values().any(|v| v == &spec.reference)
        || !table.donors.values().any(|v| v == &spec.test)
    {
        return Err(HypoNodeError::Insufficient(
            "both reference and test donors are required".into(),
        ));
    }
    Ok(table)
}

fn fit_composition(
    table: &DonorTable,
    spec: &DonorCompositionSpec,
) -> Result<Vec<CompositionResult>, HypoNodeError> {
    let family = spec
        .cell_types
        .clone()
        .unwrap_or_else(|| table.cell_types.iter().cloned().collect());
    let mut results = Vec::new();
    for cell_type in &family {
        let mut observations = Vec::new();
        for (donor, condition) in &table.donors {
            let total = table.totals[donor];
            if total >= spec.min_donor_cells {
                let count = table
                    .counts
                    .get(&(donor.clone(), cell_type.clone()))
                    .copied()
                    .unwrap_or_default();
                observations.push((
                    if condition == &spec.test { 1.0 } else { 0.0 },
                    count as f64,
                    total as f64,
                ));
            }
        }
        let ref_values: Vec<_> = observations
            .iter()
            .filter(|(x, _, _)| *x == 0.0)
            .map(|(_, k, n)| k / n)
            .collect();
        let test_values: Vec<_> = observations
            .iter()
            .filter(|(x, _, _)| *x == 1.0)
            .map(|(_, k, n)| k / n)
            .collect();
        let mut result = CompositionResult {
            cell_type: cell_type.clone(),
            donors: observations.len() as u64,
            cells: observations.iter().map(|(_, k, _)| *k as u64).sum(),
            reference_proportion: (!ref_values.is_empty())
                .then(|| ref_values.iter().sum::<f64>() / ref_values.len() as f64),
            test_proportion: (!test_values.is_empty())
                .then(|| test_values.iter().sum::<f64>() / test_values.len() as f64),
            log_odds_ratio: None,
            standard_error: None,
            z: None,
            p_raw: None,
            p_adj: None,
            family_size: family.len() as u64,
            reference_donors: ref_values.len() as u64,
            test_donors: test_values.len() as u64,
            fit_status: "INSUFFICIENT_DONORS",
        };
        if result.reference_donors >= spec.min_donors_per_condition
            && result.test_donors >= spec.min_donors_per_condition
        {
            result.fit_status = "NON_FINITE_MLE";
            if let Some((log_odds_ratio, standard_error, statistic, probability)) =
                fit_binomial(&observations)
            {
                result.log_odds_ratio = Some(log_odds_ratio);
                result.standard_error = Some(standard_error);
                result.z = Some(statistic);
                result.p_raw = Some(probability);
                result.fit_status = "ESTIMABLE";
            }
        }
        results.push(result);
    }
    let pvalues = results
        .iter()
        .filter_map(|row| row.p_raw)
        .collect::<Vec<_>>();
    if !pvalues.is_empty() {
        let method = hypothesize::AdjustMethod::parse(&spec.correction)
            .map_err(|error| HypoNodeError::Spec(error.to_string()))?;
        let adjusted = hypothesize::p_adjust_raw(&pvalues, method, Some(family.len()))
            .map_err(|error| HypoNodeError::Test(error.to_string()))?;
        results
            .iter_mut()
            .filter(|row| row.p_raw.is_some())
            .zip(adjusted)
            .for_each(|(row, probability)| row.p_adj = Some(probability));
    }
    Ok(results)
}

fn fit_binomial(observations: &[(f64, f64, f64)]) -> Option<(f64, f64, f64, f64)> {
    let mut successes_by_group = [0.0, 0.0];
    let mut failures_by_group = [0.0, 0.0];
    for &(condition, successes, trials) in observations {
        if !condition.is_finite()
            || (condition != 0.0 && condition != 1.0)
            || !successes.is_finite()
            || !trials.is_finite()
            || trials <= 0.0
            || successes < 0.0
            || successes > trials
        {
            return None;
        }
        let group = if condition == 0.0 { 0 } else { 1 };
        successes_by_group[group] += successes;
        failures_by_group[group] += trials - successes;
    }
    if successes_by_group
        .iter()
        .chain(&failures_by_group)
        .any(|value| !value.is_finite() || *value <= 0.0)
    {
        return None;
    }
    let slope = (successes_by_group[1].ln() - failures_by_group[1].ln())
        - (successes_by_group[0].ln() - failures_by_group[0].ln());
    let variance = successes_by_group
        .iter()
        .chain(&failures_by_group)
        .map(|value| 1.0 / value)
        .sum::<f64>();
    let standard_error = variance.sqrt();
    let statistic = slope / standard_error;
    let probability = 2.0 * hypothesize::normal_cdf(-statistic.abs());
    if !slope.is_finite()
        || !standard_error.is_finite()
        || standard_error <= 0.0
        || !statistic.is_finite()
        || !probability.is_finite()
        || !(0.0..=1.0).contains(&probability)
    {
        return None;
    }
    Some((slope, standard_error, statistic, probability))
}

fn composition_batch(
    table: &DonorTable,
    spec: &DonorCompositionSpec,
) -> Result<RecordBatch, String> {
    let mut donors = Vec::new();
    let mut conditions = Vec::new();
    let mut cell_types = Vec::new();
    let mut counts = Vec::new();
    let mut totals = Vec::new();
    let mut proportions = Vec::new();
    let mut eligible = Vec::new();
    for donor in table.donors.keys() {
        for cell_type in &table.cell_types {
            let count = table
                .counts
                .get(&(donor.clone(), cell_type.clone()))
                .copied()
                .unwrap_or_default();
            let total = table.totals[donor];
            donors.push(donor.clone());
            conditions.push(table.donors[donor].clone());
            cell_types.push(cell_type.clone());
            counts.push(count);
            totals.push(total);
            proportions.push(count as f64 / total as f64);
            eligible.push(total >= spec.min_donor_cells);
        }
    }
    RecordBatch::try_new(
        Arc::new(Schema::new(vec![
            Field::new("donor_id", DataType::Utf8, false),
            Field::new("condition", DataType::Utf8, false),
            Field::new("cell_type", DataType::Utf8, false),
            Field::new("count", DataType::UInt64, false),
            Field::new("donor_total", DataType::UInt64, false),
            Field::new("proportion", DataType::Float64, false),
            Field::new("eligible_by_cell_count", DataType::Boolean, false),
        ])),
        vec![
            Arc::new(StringArray::from(donors)),
            Arc::new(StringArray::from(conditions)),
            Arc::new(StringArray::from(cell_types)),
            Arc::new(UInt64Array::from(counts)),
            Arc::new(UInt64Array::from(totals)),
            Arc::new(Float64Array::from(proportions)),
            Arc::new(BooleanArray::from(eligible)),
        ],
    )
    .map_err(|error| error.to_string())
}

fn test_batch(rows: &[CompositionResult]) -> Result<RecordBatch, String> {
    RecordBatch::try_new(
        Arc::new(Schema::new(vec![
            Field::new("cell_type", DataType::Utf8, false),
            Field::new("donors", DataType::UInt64, false),
            Field::new("cells", DataType::UInt64, false),
            Field::new("reference_proportion", DataType::Float64, true),
            Field::new("test_proportion", DataType::Float64, true),
            Field::new("log_odds_ratio", DataType::Float64, true),
            Field::new("standard_error", DataType::Float64, true),
            Field::new("z", DataType::Float64, true),
            Field::new("p_raw", DataType::Float64, true),
            Field::new("p_adj", DataType::Float64, true),
            Field::new("family_size", DataType::UInt64, false),
            Field::new("reference_donors", DataType::UInt64, false),
            Field::new("test_donors", DataType::UInt64, false),
            Field::new("fit_status", DataType::Utf8, false),
        ])),
        vec![
            Arc::new(StringArray::from(
                rows.iter()
                    .map(|row| row.cell_type.clone())
                    .collect::<Vec<_>>(),
            )),
            Arc::new(UInt64Array::from(
                rows.iter().map(|row| row.donors).collect::<Vec<_>>(),
            )),
            Arc::new(UInt64Array::from(
                rows.iter().map(|row| row.cells).collect::<Vec<_>>(),
            )),
            Arc::new(Float64Array::from(
                rows.iter()
                    .map(|row| row.reference_proportion)
                    .collect::<Vec<_>>(),
            )),
            Arc::new(Float64Array::from(
                rows.iter()
                    .map(|row| row.test_proportion)
                    .collect::<Vec<_>>(),
            )),
            Arc::new(Float64Array::from(
                rows.iter()
                    .map(|row| row.log_odds_ratio)
                    .collect::<Vec<_>>(),
            )),
            Arc::new(Float64Array::from(
                rows.iter()
                    .map(|row| row.standard_error)
                    .collect::<Vec<_>>(),
            )),
            Arc::new(Float64Array::from(
                rows.iter().map(|row| row.z).collect::<Vec<_>>(),
            )),
            Arc::new(Float64Array::from(
                rows.iter().map(|row| row.p_raw).collect::<Vec<_>>(),
            )),
            Arc::new(Float64Array::from(
                rows.iter().map(|row| row.p_adj).collect::<Vec<_>>(),
            )),
            Arc::new(UInt64Array::from(
                rows.iter().map(|row| row.family_size).collect::<Vec<_>>(),
            )),
            Arc::new(UInt64Array::from(
                rows.iter()
                    .map(|row| row.reference_donors)
                    .collect::<Vec<_>>(),
            )),
            Arc::new(UInt64Array::from(
                rows.iter().map(|row| row.test_donors).collect::<Vec<_>>(),
            )),
            Arc::new(StringArray::from(
                rows.iter().map(|row| row.fit_status).collect::<Vec<_>>(),
            )),
        ],
    )
    .map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn batch() -> RecordBatch {
        let mut donors = Vec::new();
        let mut conditions = Vec::new();
        let mut cell_types = Vec::new();
        for donor in 0..8 {
            let condition = if donor < 4 { "control" } else { "case" };
            for _ in 0..20 {
                donors.push(format!("d{donor}"));
                conditions.push(condition);
                // Cases enrich for T cells; controls enrich for B cells.
                let cell_type = if condition == "case" {
                    if donors.len() % 4 == 0 { "T" } else { "B" }
                } else if donors.len() % 4 == 0 {
                    "B"
                } else {
                    "T"
                };
                cell_types.push(cell_type);
            }
        }
        RecordBatch::try_new(
            Arc::new(Schema::new(vec![
                Field::new("donor_id", DataType::Utf8, false),
                Field::new("condition", DataType::Utf8, false),
                Field::new("cell_type", DataType::Utf8, false),
            ])),
            vec![
                Arc::new(StringArray::from(donors)),
                Arc::new(StringArray::from(conditions)),
                Arc::new(StringArray::from(cell_types)),
            ],
        )
        .unwrap()
    }

    #[tokio::test]
    async fn fits_donor_level_binomial_models() {
        let ctx = NodeCtx::new(
            datafusion::prelude::SessionContext::new().runtime_env(),
            None,
        );
        let mut node = DonorCompositionNodeFactory
            .build(
                serde_json::json!({
                    "donor_col": "donor_id",
                    "cell_type_col": "cell_type",
                    "condition_col": "condition",
                    "reference": "control",
                    "test": "case"
                }),
                ctx.clone(),
            )
            .unwrap();
        let dataframe = ctx.session().read_batch(batch()).unwrap();
        let outputs = node
            .execute(
                &ctx,
                &[NodeInput::new_dataframe(0, dataframe)],
                &dag_core::dag::node_event::NodeReporter::noop(),
            )
            .await
            .unwrap();
        let tests = outputs
            .get(&0)
            .unwrap()
            .as_dataframe()
            .unwrap()
            .clone()
            .collect()
            .await
            .unwrap();
        assert_eq!(tests.iter().map(RecordBatch::num_rows).sum::<usize>(), 2);
        let composition = outputs
            .get(&1)
            .unwrap()
            .as_dataframe()
            .unwrap()
            .clone()
            .collect()
            .await
            .unwrap();
        assert_eq!(
            composition.iter().map(RecordBatch::num_rows).sum::<usize>(),
            16
        );
    }
}
