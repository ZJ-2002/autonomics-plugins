//! `source_uniprot_search` — search UniProtKB and emit a DataFrame.

use std::sync::Arc;

use arrow_array::{Array, BooleanArray, Float64Array, RecordBatch, StringArray, UInt64Array};
use arrow_schema::{DataType, Field, Schema};
use async_trait::async_trait;
use datafusion::dataframe::DataFrame;
use datafusion::prelude::SessionContext;
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;

use dag_core::dag::{DagError, DagNode, NodePorts, graph::PortOutputs};
use dag_core::registry::{NodeCtx, NodeFactory};

use crate::UniProtClient;
use crate::query::Query;
use crate::types::{Entry, SearchRequest};

// ---------------------------------------------------------------------------
// Spec
// ---------------------------------------------------------------------------

/// Spec for [`UniprotSearchNode`].
#[derive(Debug, Clone, Default, JsonSchema, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct UniprotSearchSpec {
    /// Gene name(s), OR-ed within the clause. Example: `["BRCA1", "BRCA2"]`.
    #[serde(default)]
    pub gene: Option<Vec<String>>,

    /// Protein name fragment(s) to match, OR-ed. Example: `["insulin"]`.
    #[serde(default)]
    pub protein_name: Option<Vec<String>>,

    /// Organism name(s). Example: `["Homo sapiens"]`.
    #[serde(default)]
    pub organism: Option<Vec<String>>,

    /// NCBI taxon ID, e.g. 9606 (human), 10090 (mouse). Prefer this over
    /// `organism`.
    #[serde(default)]
    pub organism_id: Option<u64>,

    /// UniProt accessions to fetch, e.g. `["P01308", "P0DTC2"]`.
    #[serde(default)]
    pub accessions: Option<Vec<String>>,

    /// Controlled-vocabulary keyword(s), e.g. `["Glycoprotein"]`.
    #[serde(default)]
    pub keyword: Option<Vec<String>>,

    /// true = reviewed Swiss-Prot only; false = TrEMBL only. Omit for both.
    #[serde(default)]
    pub reviewed: Option<bool>,

    /// Raw UniProt query expression (expert mode), used only when no typed
    /// filter field is set. Example: `"length:[500 TO 1000] AND
    /// organism_id:9606"`.
    #[serde(default)]
    pub query: Option<String>,

    /// Entries per page (max 500). Default: 25.
    #[serde(default)]
    pub size: Option<u32>,

    /// Maximum total entries to fetch across pages. Default: same as `size`
    /// (single page). For whole-proteome downloads prefer
    /// `source_uniprot_stream` — the API discourages paged search for bulk.
    #[serde(default)]
    pub max_results: Option<usize>,

    /// Sort expression, e.g. `"accession asc"`. Default: relevance.
    #[serde(default)]
    pub sort: Option<String>,
}

/// Render the spec's typed filters into a query expression, falling back to
/// the raw `query` field.
fn query_from_spec(spec: &UniprotSearchSpec) -> Result<String, DagError> {
    let typed = spec.gene.is_some()
        || spec.protein_name.is_some()
        || spec.organism.is_some()
        || spec.organism_id.is_some()
        || spec.accessions.is_some()
        || spec.keyword.is_some()
        || spec.reviewed.is_some();
    if spec.query.is_some() && typed {
        return Err(DagError::Schedule(
            "UniProt raw query and typed filters are mutually exclusive".into(),
        ));
    }
    for values in [
        &spec.gene,
        &spec.protein_name,
        &spec.organism,
        &spec.accessions,
        &spec.keyword,
    ]
    .into_iter()
    .flatten()
    {
        if values.is_empty() {
            return Err(DagError::Schedule(
                "typed search filters cannot be empty lists".into(),
            ));
        }
        for value in values {
            crate::qualify::nonempty(value, "typed search term")
                .map_err(|error| DagError::Schedule(error.to_string()))?;
        }
    }
    if spec.organism_id == Some(0) {
        return Err(DagError::Schedule(
            "requested organism_id must be positive".into(),
        ));
    }
    if let Some(ref q) = spec.query {
        crate::qualify::nonempty(q, "raw search query")
            .map_err(|error| DagError::Schedule(error.to_string()))?;
        if !q.trim().is_empty() {
            return Ok(q.trim().to_owned());
        }
    }
    let mut q = Query::new();
    if let Some(ref v) = spec.gene {
        q = q.gene(v.iter().map(String::as_str));
    }
    if let Some(ref v) = spec.protein_name {
        q = q.protein_name(v.iter().map(String::as_str));
    }
    if let Some(ref v) = spec.organism {
        q = q.organism(v.iter().map(String::as_str));
    }
    if let Some(t) = spec.organism_id {
        q = q.organism_id(t);
    }
    if let Some(ref v) = spec.accessions {
        q = q.accessions(v.iter().map(String::as_str));
    }
    if let Some(ref v) = spec.keyword {
        q = q.keyword(v.iter().map(String::as_str));
    }
    if let Some(r) = spec.reviewed {
        q = q.reviewed(r);
    }
    q.build()
        .map_err(|e| DagError::Schedule(format!("source_uniprot_search: {e}")))
}

// ---------------------------------------------------------------------------
// Node + Factory
// ---------------------------------------------------------------------------

/// Source node emitting a UniProtKB entries table.
#[derive(Clone)]
pub struct UniprotSearchNode {
    meta: NodePorts,
    spec: UniprotSearchSpec,
    client: Option<UniProtClient>,
}

impl UniprotSearchNode {
    pub fn with_client(spec: UniprotSearchSpec, client: UniProtClient) -> Self {
        Self {
            meta: port_layout(),
            spec,
            client: Some(client),
        }
    }
}

pub struct UniprotSearchNodeFactory {}

fn port_layout() -> NodePorts {
    NodePorts::new().add_output_port(None)
}

impl NodeFactory for UniprotSearchNodeFactory {
    fn kind(&self) -> &'static str {
        "source_uniprot_search"
    }

    fn desc(&self) -> &'static str {
        "Search UniProtKB proteins and emit entries as a table."
    }

    fn doc(&self) -> &'static str {
        "A source node that queries the UniProt REST API `/uniprotkb/search` \
        endpoint and emits the results as a DataFrame. No input ports; one \
        output port.\n\n\
        Populate any subset of the typed filters (gene, protein_name, \
        organism, organism_id, accessions, keyword, reviewed) — they are \
        AND-ed together — or pass a raw `query` expression (expert mode).\n\n\
        Output schema: `accession, entry_name, reviewed, protein_name, \
        gene_names, organism_name, organism_common, taxon_id, length, \
        protein_existence, annotation_score, function`.\n\n\
        Set `max_results` > `size` to auto-paginate via cursor. Pipe into \
        `sql_node` or `dataframe_to_file` for downstream processing; use \
        `source_uniprot_stream` for bulk (proteome-scale) downloads."
    }

    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(UniprotSearchSpec)
    }

    fn ports(&self) -> NodePorts {
        port_layout()
    }

    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let node_spec: UniprotSearchSpec = serde_json::from_value(spec)?;
        Ok(Box::new(UniprotSearchNode {
            meta: port_layout(),
            spec: node_spec,
            client: None,
        }))
    }
}

#[async_trait]
impl DagNode for UniprotSearchNode {
    fn ports(&self) -> &NodePorts {
        &self.meta
    }

    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new((*self).clone())
    }

    fn kind(&self) -> &'static str {
        "source_uniprot_search"
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
                "UniProt search requires zero inputs".into(),
            ));
        }
        let size = self.spec.size.unwrap_or(25);
        let max_results = self.spec.max_results.unwrap_or(size as usize);
        if !(1..=500).contains(&size) || max_results == 0 {
            return Err(DagError::Schedule(
                "UniProt size must be 1..500 and max_results must be positive".into(),
            ));
        }

        let mut req = SearchRequest::new(query_from_spec(&self.spec)?).size(size);
        if let Some(ref sort) = self.spec.sort {
            req = req.sort(sort);
        }

        let client = self.client.clone().unwrap_or_else(UniProtClient::new);
        let entries = client
            .search_all(&req, max_results)
            .await
            .map_err(|e| DagError::Schedule(format!("UniProt request failed: {e}")))?;
        for entry in &entries {
            crate::qualify::entry(entry).map_err(|error| DagError::Schedule(error.to_string()))?;
            if self
                .spec
                .reviewed
                .is_some_and(|reviewed| reviewed != entry.is_reviewed())
            {
                return Err(DagError::Schedule(
                    "returned entry type differs from requested reviewed filter".into(),
                ));
            }
            if self
                .spec
                .organism_id
                .is_some_and(|taxon| taxon != entry.organism.taxon_id)
            {
                return Err(DagError::Schedule(
                    "returned taxon differs from requested organism_id".into(),
                ));
            }
        }

        let session = ctx.session();
        let batch = build_entries_batch(&entries)?;
        let df = session
            .read_batch(batch)
            .map_err(|e| DagError::Schedule(format!("failed to read UniProt batch: {e}")))?;
        let mut res: PortOutputs = PortOutputs::new();
        res.insert(0, df);
        Ok(res)
    }
}

// ---------------------------------------------------------------------------
// Arrow batch builder
// ---------------------------------------------------------------------------

fn build_entries_batch(rows: &[Entry]) -> Result<RecordBatch, DagError> {
    let accessions: Vec<Option<String>> = rows
        .iter()
        .map(|e| Some(e.primary_accession.clone()))
        .collect();
    let entry_names: Vec<Option<String>> =
        rows.iter().map(|e| Some(e.uni_protkb_id.clone())).collect();
    let reviewed: Vec<bool> = rows.iter().map(|e| e.is_reviewed()).collect();
    let protein_names: Vec<Option<String>> = rows
        .iter()
        .map(|e| e.protein_name().map(str::to_owned))
        .collect();
    let gene_names: Vec<Option<String>> = rows
        .iter()
        .map(|e| {
            let genes = e.gene_names();
            if genes.is_empty() {
                None
            } else {
                Some(genes.join(", "))
            }
        })
        .collect();
    let organism_names: Vec<Option<String>> = rows
        .iter()
        .map(|e| e.organism.scientific_name.clone())
        .collect();
    let organism_common: Vec<Option<String>> = rows
        .iter()
        .map(|e| e.organism.common_name.clone())
        .collect();
    let taxon_ids: Vec<Option<u64>> = rows.iter().map(|e| Some(e.organism.taxon_id)).collect();
    let lengths: Vec<Option<u64>> = rows.iter().map(|e| e.sequence.length).collect();
    let existences: Vec<Option<String>> =
        rows.iter().map(|e| e.protein_existence.clone()).collect();
    let scores: Vec<Option<f64>> = rows.iter().map(|e| e.annotation_score).collect();
    let functions: Vec<Option<String>> = rows.iter().map(|e| e.function_text()).collect();

    let schema = Arc::new(Schema::new(vec![
        Field::new("accession", DataType::Utf8, true),
        Field::new("entry_name", DataType::Utf8, true),
        Field::new("reviewed", DataType::Boolean, true),
        Field::new("protein_name", DataType::Utf8, true),
        Field::new("gene_names", DataType::Utf8, true),
        Field::new("organism_name", DataType::Utf8, true),
        Field::new("organism_common", DataType::Utf8, true),
        Field::new("taxon_id", DataType::UInt64, true),
        Field::new("length", DataType::UInt64, true),
        Field::new("protein_existence", DataType::Utf8, true),
        Field::new("annotation_score", DataType::Float64, true),
        Field::new("function", DataType::Utf8, true),
    ]));

    RecordBatch::try_new(
        schema,
        vec![
            str_array(accessions),
            str_array(entry_names),
            Arc::new(BooleanArray::from(reviewed)),
            str_array(protein_names),
            str_array(gene_names),
            str_array(organism_names),
            str_array(organism_common),
            Arc::new(UInt64Array::from(taxon_ids)),
            Arc::new(UInt64Array::from(lengths)),
            str_array(existences),
            Arc::new(Float64Array::from(scores)),
            str_array(functions),
        ],
    )
    .map_err(|e| DagError::Schedule(format!("failed to build UniProt entries batch: {e}")))
}

// ---------------------------------------------------------------------------
// Arrow helpers
// ---------------------------------------------------------------------------

fn str_array(rows: Vec<Option<String>>) -> Arc<dyn Array> {
    let refs: Vec<Option<&str>> = rows.iter().map(|o| o.as_deref()).collect();
    Arc::new(StringArray::from(refs))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn entry_fixture() -> Entry {
        serde_json::from_str(
            r#"{
              "entryType": "UniProtKB reviewed (Swiss-Prot)",
              "primaryAccession": "P01308",
              "uniProtkbId": "INS_HUMAN",
              "organism": {"scientificName": "Homo sapiens", "commonName": "Human", "taxonId": 9606},
              "proteinExistence": "1: Evidence at protein level",
              "annotationScore": 5.0,
              "proteinDescription": {"recommendedName": {"fullName": {"value": "Insulin"}}},
              "genes": [{"geneName": {"value": "INS"}}],
              "comments": [
                {"commentType": "FUNCTION", "texts": [{"value": "Insulin lowers blood glucose levels."}]}
              ],
              "sequence": {"value": "MALWMRLL", "length": 110}
            }"#,
        )
        .unwrap()
    }

    #[test]
    fn build_batch_from_entries() {
        let entries = vec![
            entry_fixture(),
            serde_json::from_str::<Entry>(
                r#"{"entryType": "UniProtKB unreviewed (TrEMBL)", "primaryAccession": "ABC123"}"#,
            )
            .unwrap(),
        ];

        let batch = build_entries_batch(&entries).unwrap();
        assert_eq!(batch.num_rows(), 2);
        assert_eq!(batch.num_columns(), 12);

        let accs = batch
            .column(0)
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap();
        assert_eq!(accs.value(0), "P01308");
        assert_eq!(accs.value(1), "ABC123");

        let reviewed = batch
            .column(2)
            .as_any()
            .downcast_ref::<BooleanArray>()
            .unwrap();
        assert!(reviewed.value(0));
        assert!(!reviewed.value(1));

        let genes = batch
            .column(4)
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap();
        assert_eq!(genes.value(0), "INS");
        assert!(genes.is_null(1));

        let taxon = batch
            .column(7)
            .as_any()
            .downcast_ref::<UInt64Array>()
            .unwrap();
        assert_eq!(taxon.value(0), 9606);
        assert_eq!(taxon.value(1), 0);

        let func = batch
            .column(11)
            .as_any()
            .downcast_ref::<StringArray>()
            .unwrap();
        assert_eq!(func.value(0), "Insulin lowers blood glucose levels.");
        assert!(func.is_null(1));
    }

    #[test]
    fn query_from_spec_rejects_mixed_modes() {
        let spec = UniprotSearchSpec {
            query: Some("length:[500 TO 1000]".into()),
            gene: Some(vec!["INS".into()]),
            ..Default::default()
        };
        assert!(query_from_spec(&spec).is_err());
    }

    #[test]
    fn query_from_spec_joins_filters() {
        let spec = UniprotSearchSpec {
            gene: Some(vec!["INS".into()]),
            organism_id: Some(9606),
            reviewed: Some(true),
            ..Default::default()
        };
        assert_eq!(
            query_from_spec(&spec).unwrap(),
            "gene:INS AND organism_id:9606 AND reviewed:true"
        );
    }

    #[test]
    fn query_from_spec_empty_errors() {
        let err = query_from_spec(&UniprotSearchSpec::default()).unwrap_err();
        assert!(matches!(err, DagError::Schedule(_)));
    }
}
