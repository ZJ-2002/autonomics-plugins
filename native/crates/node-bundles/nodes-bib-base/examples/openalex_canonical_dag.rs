use std::path::Path;
use std::sync::Arc;

use dag_core::dag::DAG;
use dag_core::dag::runtime::{InputHashing, SchedulerConfig};
use dag_core::registry::{NodeCtx, NodeRegistry};
use datafusion::prelude::SessionContext;
use serde_json::{Value, json};

async fn execute(job: &Value) -> Result<bool, Box<dyn std::error::Error>> {
    for (name, _) in std::env::vars() {
        if name.starts_with("ENDPOINT_") {
            return Err("endpoint overrides forbidden for official proof".into());
        }
    }
    let root = Path::new(job["run_root"].as_str().ok_or("run_root required")?);
    let storage = vfs::OpendalFileStorage::new(root);
    let context = NodeCtx::new(SessionContext::new().runtime_env(), Some(Arc::new(storage)));
    let mut registry = NodeRegistry::new(context.clone());
    registry.register(Box::new(
        nodes_bib_base::nodes::literature_search::LiteratureSearchNodeFactory {},
    ));
    registry.register(Box::new(
        nodes_bib_base::nodes::evidence_merge::EvidenceMergeNodeFactory {},
    ));
    registry.assert_no_conflicts()?;
    let mut dag = DAG::default();
    let source_spec = json!({"query":job["query"], "sources":["openalex"],
        "limit":job["limit"], "path":"/evidence.json",
        "note":"Technical API example; no scientific qualification."});
    let merge_spec = json!({"path":"/merged.json"});
    for (identifier, kind, spec) in [
        ("source", "source_literature", source_spec),
        ("merge", "evidence_merge", merge_spec),
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
    Ok(report.ok)
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let filename = std::env::args().nth(1).ok_or("job.json required")?;
    let job: Value = serde_json::from_slice(&std::fs::read(filename)?)?;
    match execute(&job).await {
        Ok(true) => Ok(()),
        Ok(false) => Err("DAG failed; report preserved".into()),
        Err(error) => {
            let root = Path::new(job["run_root"].as_str().ok_or("run_root required")?);
            std::fs::write(
                root.join("runner-error.json"),
                serde_json::to_vec_pretty(&json!({"error":error.to_string(),"G0":false}))?,
            )?;
            Err(error)
        }
    }
}
