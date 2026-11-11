//! `source_opengwas_ld_clump` — LD-clumped independent loci from
//! OpenGWAS `/ld/clump`.

use async_trait::async_trait;
use schemars::{JsonSchema, schema_for};
use serde::Deserialize;

use dag_core::dag::{DagError, graph::PortOutputs};
use dag_core::node::{DagNode, NodePorts};
use dag_core::registry::{NodeCtx, NodeFactory};

use opengwas::types::LdClumpRequest;

use crate::shared::{ld_clump_to_output, make_client, single_output_port};

const KIND_LD_CLUMP: &str = "source_opengwas_ld_clump";

fn default_clump_r2() -> f64 {
    0.001
}
fn default_clump_kb() -> i32 {
    5000
}
fn default_clump_pop() -> String {
    "EUR".to_string()
}

/// Spec for [`OpengwasLdClumpNode`].
#[derive(Debug, Clone, JsonSchema, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct OpengwasLdClumpSpec {
    /// rs IDs to clump.
    pub rsid: Vec<String>,
    /// P-values for each SNP (same length as `rsid`).
    pub pval: Vec<f64>,
    /// Significance threshold. Default `5e-8`.
    #[serde(default)]
    pub pthresh: Option<f64>,
    /// LD r² threshold for clumping. Default `0.001`.
    #[serde(default = "default_clump_r2")]
    pub r2: f64,
    /// Clumping window size in kb. Default `5000`.
    #[serde(default = "default_clump_kb")]
    pub kb: i32,
    /// Reference population: `EUR`, `SAS`, `EAS`, `AFR`, `AMR`, `legacy`. Default `EUR`.
    #[serde(default = "default_clump_pop")]
    pub pop: String,
}

impl OpengwasLdClumpSpec {
    fn request(&self) -> LdClumpRequest {
        LdClumpRequest {
            rsid: self.rsid.clone(),
            pval: self.pval.clone(),
            pthresh: self.pthresh,
            r2: Some(self.r2),
            kb: Some(self.kb),
            pop: Some(self.pop.clone()),
        }
    }
}

/// Source node: LD-clumped independent loci from OpenGWAS `/ld/clump`.
#[derive(Clone)]
pub struct OpengwasLdClumpNode {
    meta: NodePorts,
    spec: OpengwasLdClumpSpec,
}

pub struct OpengwasLdClumpNodeFactory;

impl NodeFactory for OpengwasLdClumpNodeFactory {
    fn kind(&self) -> &'static str {
        KIND_LD_CLUMP
    }
    fn desc(&self) -> &'static str {
        "Performs LD clumping via OpenGWAS /ld/clump and returns independent loci."
    }
    fn doc(&self) -> &'static str {
        "A source node that calls the OpenGWAS `/ld/clump` endpoint to clump a \
        set of SNPs (with associated p-values) into independent loci using 1000 \
        Genomes reference data.\n\n\
        The API returns retained rs IDs, not PLINK annotations. Output has `rsid, \
        pval`, preserving the submitted SNP order and original p-values. An empty \
        retained set yields a zero-row table with that schema.\n\n\
        Defaults match the REST API (kb=5000, pthresh=5e-8), not the different \
        ieugwasr::ld_clump_api defaults (kb=10000, clump_p=1). Freeze these \
        parameters explicitly when reproducing an R analysis."
    }
    fn spec_schema(&self) -> schemars::Schema {
        schema_for!(OpengwasLdClumpSpec)
    }
    fn ports(&self) -> NodePorts {
        single_output_port()
    }
    fn build(
        &self,
        spec: serde_json::Value,
        _node_ctx: NodeCtx,
    ) -> dag_core::registry::error::Result<Box<dyn DagNode>> {
        let s: OpengwasLdClumpSpec = serde_json::from_value(spec)?;
        s.request()
            .validate()
            .map_err(dag_core::registry::error::Error::Unknown)?;
        Ok(Box::new(OpengwasLdClumpNode {
            meta: single_output_port(),
            spec: s,
        }))
    }
}

#[async_trait]
impl DagNode for OpengwasLdClumpNode {
    fn ports(&self) -> &NodePorts {
        &self.meta
    }
    fn clone_box(&self) -> Box<dyn DagNode> {
        Box::new((*self).clone())
    }
    fn kind(&self) -> &'static str {
        KIND_LD_CLUMP
    }
    fn as_any(&self) -> &dyn std::any::Any {
        self
    }
    async fn execute(
        &mut self,
        node_ctx: &NodeCtx,
        _inputs: &[dag_core::dag::NodeInput],
        _reporter: &dag_core::dag::node_event::NodeReporter,
    ) -> Result<PortOutputs, DagError> {
        let client = make_client()?;
        let request = self.spec.request();
        let resp = client
            .ld_clump(&request)
            .await
            .map_err(|e| DagError::Schedule(format!("OpenGWAS /ld/clump failed: {e}")))?;
        ld_clump_to_output(node_ctx, &resp, &request).await
    }
}
