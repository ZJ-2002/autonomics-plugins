//! Native DAG adapters for the independently usable client SDK.

pub use gwascatalog_sdk::*;
pub mod nodes;

pub use nodes::associations::{AssociationsNodeFactory, StudyAssociationsNodeFactory};
pub use nodes::download::DownloadNodeFactory;
pub use nodes::efo_traits::EfoTraitsNodeFactory;
pub use nodes::search::SearchNodeFactory;
pub use nodes::snps::SnpsNodeFactory;
pub use nodes::studies::StudiesNodeFactory;
pub use nodes::summary_associations::SummaryAssociationsNodeFactory;
pub use nodes::unpublished::UnpublishedNodeFactory;

pub use nodes::register_nodes;
