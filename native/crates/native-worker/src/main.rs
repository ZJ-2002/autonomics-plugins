//! Independently built native package control and invocation entries.
use std::sync::Arc;
use dag_core::{NodeCtx, NodeRegistry};
use native_node_runtime::server::{CompiledPackage, serve_control, serve_invocation};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let entry = std::env::args().nth(1);
    if !matches!(entry.as_deref(), Some("--native-node-control" | "--native-node-invoke")) {
        return Err("expected a versioned native package entry".into());
    }
    let compiled = CompiledPackage {
        name: "autonomics-native-nodes",
        source_revision: env!("AUTONOMICS_NATIVE_SOURCE_REVISION"),
        dependency_lock_sha256: env!("AUTONOMICS_NATIVE_LOCK_SHA256"),
        interface_sha256: env!("AUTONOMICS_NATIVE_INTERFACE_SHA256"),
    };
    // Metadata is resolved against actual factories. Execution gets a separate
    // invocation context carrying the admitted host services and data bundles.
    let runtime = Arc::new(datafusion::execution::runtime_env::RuntimeEnv::default());
    let mut registry = NodeRegistry::new(NodeCtx::new(runtime, None));
    registry.register_plugin(&nodes_causal::Plugin);
    registry.register_plugin(&nodes_dl::Plugin);
    registry.register_plugin(&nodes_epi::Plugin);
    registry.register_plugin(&nodes_genetics::Plugin);
    registry.register_plugin(&nodes_hypothesize::Plugin);
    registry.register_plugin(&nodes_io::Plugin::new());
    registry.register_plugin(&nodes_lcmm::Plugin);
    registry.register_plugin(&nodes_mice::Plugin);
    registry.register_plugin(&nodes_ml::Plugin);
    registry.register_plugin(&nodes_opengwas::Plugin);
    registry.register_plugin(&nodes_power::Plugin);
    registry.register_plugin(&nodes_rd::Plugin);
    registry.register_plugin(&nodes_regression::Plugin);
    registry.register_plugin(&nodes_sql::Plugin);
    registry.register_plugin(&nodes_survey::Plugin);
    registry.register_plugin(&nodes_survival::Plugin);
    registry.register_plugin(&nodes_writing::Plugin);
    registry.assert_no_conflicts()?;
    if entry.as_deref() == Some("--native-node-invoke") {
        serve_invocation(&compiled, |invocation, services| async move {
            let kind = invocation.address.rsplit('/').next().unwrap_or("");
            if !matches!(invocation.operation, native_node_protocol::invocation::Operation::Describe)
                && matches!(kind, "bib_save" | "literature_fulltext" | "source_literature" | "source_literature_fetch") {
                let capabilities = match services.call("host.capabilities", serde_json::Value::Null).await
                    .and_then(|value| serde_json::from_value::<Vec<String>>(value).map_err(|error| error.to_string())) {
                    Ok(capabilities) => capabilities,
                    Err(error) => return native_node_protocol::invocation::Outcome::Error(format!("host capability discovery: {error}")),
                };
                if capabilities.iter().any(|capability| capability == "library") {
                    match bib_base::native_service::connect(services.clone()).await {
                        Ok(library) => nodes_bib_base::nodes::set_shared_library(library),
                        Err(error) => return native_node_protocol::invocation::Outcome::Error(format!("resident bibliography: {error}")),
                    }
                } else if matches!(kind, "bib_save" | "literature_fulltext") {
                    return native_node_protocol::invocation::Outcome::Error("resident bibliography capability is unavailable".into());
                }
            }
            native_node_dag::server::execute(&registry, invocation, services).await
        }).await?;
        return Ok(());
    }
    serve_control(&compiled, |request| async move {
        match dag_core::native_protocol::control_request(&registry, request) {
            Ok(response) => response,
            Err(error) => native_node_protocol::Response::Error {
                code: "invalid_node_description".into(), message: error.to_string(),
            },
        }
    }).await?;
    Ok(())
}
