//! Competing-risk risk-estimation metrics (`crrkit`) — the external-validation
//! scoring layer for cause-1 cumulative-incidence predictions.
//!
//! Metrics for evaluating cumulative-incidence predictions under competing
//! risks with inverse-probability-of-censoring weights.
//!
//! Provided here:
//!
//! * [`ipcw_brier`] — competing-risk IPCW Brier score, per-subject
//!   contributions, and censoring-weight diagnostics.
//! * [`ipcw_auc`] — time-dependent AUC whose controls include subjects dead
//!   of the competing cause, properly censoring-weighted (not a plain ROC);
//! * [`grouped_calibration`] / [`calibration_slope`] — competing-risk
//!   calibration against the IPCW-observed event probability;
//! * [`paired_brier_delta_bootstrap`] — patient-level paired bootstrap of
//!   `BS(M_ref) − BS(M_new)` re-estimating the censoring weights inside every
//!   resample.
//!
//! Status coding: 0 = censored, 1 = event of interest, 2 = competing event.
//! Times and horizon must use the same units.
//!
//! # Relationship to the rest of the workspace
//!
//! `stat_crates/cmprsk` fits the Fine–Gray models whose CIF predictions are
//! scored here; `stat_crates/dl::survival::brier_score` is a single-event
//! IPCW Brier that treats competing events as censoring and **must not** be
//! used for competing-risk endpoints — this crate is its replacement for
//! that purpose.

pub mod auc;
pub mod bootstrap;
pub mod brier;
pub mod calibration;
pub mod censoring;
pub mod error;

pub use auc::{IpcwAuc, ipcw_auc};
pub use bootstrap::{BootstrapOptions, PairedBootstrapDelta, paired_brier_delta_bootstrap};
pub use brier::{BrierOptions, IpcwBrier, ipcw_brier};
pub use calibration::{CalibrationGroup, CalibrationSlope, calibration_slope, grouped_calibration};
pub use censoring::ReverseKmCensoring;
pub use error::{CrrkitError, Result};
