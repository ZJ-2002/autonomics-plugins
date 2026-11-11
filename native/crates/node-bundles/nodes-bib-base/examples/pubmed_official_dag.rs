use std::path::Path;
use std::sync::Arc;

use dag_core::dag::DAG;
use dag_core::dag::runtime::{InputHashing, SchedulerConfig};
use dag_core::registry::{NodeCtx, NodeRegistry};
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    if std::env::vars().any(|(name, _)| name.starts_with("ENDPOINT_") || name == "EUTILS_API_KEY") {
        return Err(
            "official public-rate proof forbids endpoint overrides and NCBI credentials".into(),
        );
    }
    let filename = std::env::args().nth(1).ok_or("job.json required")?;
    let job: Value = serde_json::from_slice(&std::fs::read(filename)?)?;
    let root = Path::new(job["run_root"].as_str().ok_or("run_root required")?);
    let storage = vfs::OpendalFileStorage::new(root);
    let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(Arc::new(storage)));
    let mut registry = NodeRegistry::new(context.clone());
    registry.register(Box::new(
        nodes_bib_base::nodes::literature_fetch::LiteratureFetchNodeFactory {},
    ));
    registry.register(Box::new(
        nodes_bib_base::nodes::evidence_merge::EvidenceMergeNodeFactory {},
    ));
    registry.register(Box::new(
        nodes_bib_base::nodes::literature_search::LiteratureSearchNodeFactory {},
    ));
    registry.assert_no_conflicts()?;
    let mut dag = DAG::default();
    let (source_kind, source_spec) = if let Some(query) = job.get("query") {
        (
            "source_literature",
            json!({"query":query, "limit":1, "sources":["pubmed"],
            "path":"/evidence.json", "note":"Technical API example; no scientific qualification."}),
        )
    } else {
        (
            "source_literature_fetch",
            json!({"id_kind":job["id_kind"],
            "id_value":job["id_value"], "sources":["pubmed"], "path":"/evidence.json",
            "note":"Technical API example; no scientific qualification."}),
        )
    };
    for (identifier, kind, spec) in [
        ("source", source_kind, source_spec),
        ("merge", "evidence_merge", json!({"path":"/merged.json"})),
    ] {
        dag.add_node_with_spec(
            identifier.into(),
            registry.build_node(kind, spec.clone())?,
            kind.into(),
            spec,
        )?;
    }
    dag.add_edge("source", "merge", 0, 0)?;
    let report = dag
        .run(
            &SchedulerConfig {
                max_concurrency: 1,
                incremental: false,
                input_hashing: InputHashing::Content,
                compute_row_counts: false,
                memory_guard: None,
                ..SchedulerConfig::default()
            },
            &context,
            None,
        )
        .await?;
    std::fs::write(
        root.join("run-report.json"),
        serde_json::to_vec_pretty(&report)?,
    )?;
    std::fs::write(
        root.join("dag.json"),
        serde_json::to_vec_pretty(&dag.tui_snapshot())?,
    )?;
    if !report.ok {
        return Err("native PubMed DAG failed; report preserved".into());
    }
    Ok(())
}
