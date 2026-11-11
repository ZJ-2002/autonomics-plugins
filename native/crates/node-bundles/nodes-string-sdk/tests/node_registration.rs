use std::sync::Arc;

use dag_core::{NodePlugin, NodeRegistry};
use datafusion::execution::runtime_env::RuntimeEnv;
use nodes_string_sdk::nodes::Plugin;

#[test]
fn node_plugin_registers_and_builds_all_sources() {
    let runtime = RuntimeEnv::default();
    let mut registry = NodeRegistry::with_ingredients(Arc::new(runtime), None);
    registry.register_plugin(&Plugin);

    let fixture = Plugin.fixture_spec("source_string_id_map").unwrap();
    for kind in [
        "source_string_id_map",
        "source_string_network",
        "source_string_enrichment",
        "source_string_ppi_enrichment",
    ] {
        let node = registry
            .build_node(kind, fixture.clone())
            .unwrap_or_else(|error| panic!("failed to build {kind}: {error}"));
        assert_eq!(node.kind(), kind);
        assert_eq!(node.ports().output_ports().len(), 1);
    }
}
