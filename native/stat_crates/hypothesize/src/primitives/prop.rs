//! Proportion tests — port of `stats::prop.test`.
//!
//! One-sample and two-sample tests for proportions using the Pearson
//! chi-squared statistic with optional Yates continuity correction.
//! One- and two-sample integer-count cases of R `prop.test`.

use serde_json::json;

use super::HypothesisTest;
use crate::{
    Alternative, HypoError, KEY_KIND, Result,
    dist::{chisq_sf, normal_cdf, normal_inv, normal_sf},
    extras,
};

/// One-sample proportion test: `H₀: p = p0`.
///
/// `correct = true` applies Yates' continuity correction (R default).
/// Defaults to a two-sided test and a 95% confidence interval.
pub fn prop_test_one(x: u32, n: u32, p0: f64, correct: bool) -> Result<HypothesisTest> {
    prop_test_one_with_options(x, n, p0, correct, Alternative::TwoSided, 0.95)
}

pub fn prop_test_one_with_options(
    x: u32,
    n: u32,
    p0: f64,
    correct: bool,
    alt: Alternative,
    conf_level: f64,
) -> Result<HypothesisTest> {
    validate_conf_level(conf_level)?;
    if n == 0 {
        return Err(HypoError::InvalidInput("n must be > 0".into()));
    }
    if x > n {
        return Err(HypoError::InvalidInput(format!("x ({x}) > n ({n})")));
    }
    if !(p0 > 0.0 && p0 < 1.0) {
        return Err(HypoError::InvalidInput(format!(
            "p0 must be in (0, 1), got {p0}"
        )));
    }
    let nf = n as f64;
    let xf = x as f64;
    let expected = nf * p0;
    let expected_complement = nf * (1.0 - p0);

    // χ² = (|O - E| - c)² / E + (|O' - E'| - c)² / E'
    // where c = 0.5 if correct else 0.
    let c = if correct {
        0.5_f64.min((xf - expected).abs())
    } else {
        0.0
    };
    let d1 = (xf - expected).abs() - c;
    let d2 = ((nf - xf) - expected_complement).abs() - c;
    let stat = d1 * d1 / expected + d2 * d2 / expected_complement;
    let dof = 1.0_f64;
    let phat = xf / nf;
    let p_value = proportion_p_value(stat, phat - p0, alt);
    let quantile = normal_inv(if alt == Alternative::TwoSided {
        (1.0 + conf_level) / 2.0
    } else {
        conf_level
    });
    let adjustment = quantile.powi(2) / (2.0 * nf);
    let upper_center = phat + c / nf;
    let lower_center = phat - c / nf;
    let upper = if upper_center >= 1.0 {
        1.0
    } else {
        (upper_center
            + adjustment
            + quantile
                * (upper_center * (1.0 - upper_center) / nf + adjustment / (2.0 * nf)).sqrt())
            / (1.0 + 2.0 * adjustment)
    };
    let lower = if lower_center <= 0.0 {
        0.0
    } else {
        (lower_center + adjustment
            - quantile
                * (lower_center * (1.0 - lower_center) / nf + adjustment / (2.0 * nf)).sqrt())
            / (1.0 + 2.0 * adjustment)
    };
    let (conf_low, conf_high) = match alt {
        Alternative::TwoSided => (lower.max(0.0), upper.min(1.0)),
        Alternative::Greater => (lower.max(0.0), 1.0),
        Alternative::Less => (0.0, upper.min(1.0)),
    };
    Ok(HypothesisTest::new(
        stat,
        p_value,
        dof,
        alt,
        if c > 0.0 {
            "1-sample proportions test with continuity correction"
        } else {
            "1-sample proportions test without continuity correction"
        },
        extras([
            (KEY_KIND, json!("prop_test")),
            ("estimate", json!(phat)),
            ("null_value", json!(p0)),
            ("x", json!(x)),
            ("n", json!(n)),
            ("corrected", json!(c > 0.0)),
            ("conf_low", json!(conf_low)),
            ("conf_high", json!(conf_high)),
            ("conf_level", json!(conf_level)),
        ]),
    ))
}

/// Two-sample proportion test: `H₀: p₁ − p₂ = 0`.
///
/// Uses the pooled estimate `p̂ = (x₁ + x₂) / (n₁ + n₂)` under H₀.
pub fn prop_test_two(x1: u32, n1: u32, x2: u32, n2: u32, correct: bool) -> Result<HypothesisTest> {
    prop_test_two_with_options(x1, n1, x2, n2, correct, Alternative::TwoSided, 0.95)
}

pub fn prop_test_two_with_options(
    x1: u32,
    n1: u32,
    x2: u32,
    n2: u32,
    correct: bool,
    alt: Alternative,
    conf_level: f64,
) -> Result<HypothesisTest> {
    validate_conf_level(conf_level)?;
    if n1 == 0 || n2 == 0 {
        return Err(HypoError::InvalidInput("n1 and n2 must be > 0".into()));
    }
    if x1 > n1 || x2 > n2 {
        return Err(HypoError::InvalidInput("counts exceed sample sizes".into()));
    }
    let (n1f, n2f) = (n1 as f64, n2 as f64);
    let (x1f, x2f) = (x1 as f64, x2 as f64);
    let p1 = x1f / n1f;
    let p2 = x2f / n2f;
    let p_pool = (x1f + x2f) / (n1f + n2f);
    if p_pool == 0.0 || p_pool == 1.0 {
        return Err(HypoError::InvalidInput(
            "pooled proportion has zero variance; test is not estimable".into(),
        ));
    }
    let difference = p1 - p2;
    let inverse_n_sum = 1.0 / n1f + 1.0 / n2f;
    let c = if correct {
        0.5_f64.min(difference.abs() / inverse_n_sum)
    } else {
        0.0
    };
    // Build the 2×2 table and compute Pearson χ² with continuity correction.
    // Rows: (success, failure), Columns: (group1, group2).
    let expected = [
        [n1f * p_pool, n2f * p_pool],
        [n1f * (1.0 - p_pool), n2f * (1.0 - p_pool)],
    ];
    let observed = [[x1f, x2f], [n1f - x1f, n2f - x2f]];
    let mut stat = 0.0_f64;
    for i in 0..2 {
        for j in 0..2 {
            let d = observed[i][j] - expected[i][j];
            // Yates correction applies to 2×2 tables only, on each cell.
            let d_corrected = d.abs() - c;
            stat += d_corrected * d_corrected / expected[i][j];
        }
    }
    let dof = 1.0_f64;
    let p_value = proportion_p_value(stat, difference, alt);
    let quantile = normal_inv(if alt == Alternative::TwoSided {
        (1.0 + conf_level) / 2.0
    } else {
        conf_level
    });
    let width =
        quantile * (p1 * (1.0 - p1) / n1f + p2 * (1.0 - p2) / n2f).sqrt() + c * inverse_n_sum;
    let (conf_low, conf_high) = match alt {
        Alternative::TwoSided => (
            (difference - width).max(-1.0),
            (difference + width).min(1.0),
        ),
        Alternative::Greater => ((difference - width).max(-1.0), 1.0),
        Alternative::Less => (-1.0, (difference + width).min(1.0)),
    };
    Ok(HypothesisTest::new(
        stat,
        p_value,
        dof,
        alt,
        if c > 0.0 {
            "2-sample test for equality of proportions with continuity correction"
        } else {
            "2-sample test for equality of proportions without continuity correction"
        },
        extras([
            (KEY_KIND, json!("prop_test")),
            ("estimate1", json!(p1)),
            ("estimate2", json!(p2)),
            ("estimate", json!(difference)),
            ("null_value", json!(0.0)),
            ("pooled", json!(p_pool)),
            ("x1", json!(x1)),
            ("n", json!(u64::from(n1) + u64::from(n2))),
            ("n1", json!(n1)),
            ("x2", json!(x2)),
            ("n2", json!(n2)),
            ("corrected", json!(c > 0.0)),
            ("conf_low", json!(conf_low)),
            ("conf_high", json!(conf_high)),
            ("conf_level", json!(conf_level)),
        ]),
    ))
}

fn validate_conf_level(conf_level: f64) -> Result<()> {
    if !conf_level.is_finite() || conf_level <= 0.0 || conf_level >= 1.0 {
        return Err(HypoError::InvalidInput(
            "conf_level must be in (0, 1)".into(),
        ));
    }
    Ok(())
}

fn proportion_p_value(statistic: f64, difference: f64, alt: Alternative) -> f64 {
    let signed_z = if difference == 0.0 {
        0.0
    } else {
        difference.signum() * statistic.sqrt()
    };
    match alt {
        Alternative::TwoSided => chisq_sf(statistic.max(0.0), 1.0),
        Alternative::Less => normal_cdf(signed_z),
        Alternative::Greater => normal_sf(signed_z),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_sample_basic() {
        // R: prop.test(50, 100, p=0.5, correct=TRUE)
        let t = prop_test_one(50, 100, 0.5, true).unwrap();
        assert_eq!(t.stat, 0.0);
        assert_eq!(t.p_value, 1.0);
        assert_eq!(t.extras["corrected"].as_bool(), Some(false));
        assert_eq!(t.dof, 1.0);
    }

    #[test]
    fn one_sample_against_r() {
        // R: prop.test(65, 100, p=0.5, correct=TRUE)
        // chi-squared ≈ 8.01, p ≈ 0.00465
        let t = prop_test_one(65, 100, 0.5, true).unwrap();
        // With continuity correction: (|15| - 0.5)²/50 + (|15| - 0.5)²/50
        // = 14.5² / 50 * 2 = 210.25/50 * 2 = 8.41
        assert!((t.stat - 8.41).abs() < 0.01);
        assert!((t.extra_f64("estimate").unwrap() - 0.65).abs() < 1e-12);
    }

    #[test]
    fn one_sample_no_correction() {
        let t_corr = prop_test_one(65, 100, 0.5, true).unwrap();
        let t_nc = prop_test_one(65, 100, 0.5, false).unwrap();
        // Without correction the statistic is larger.
        assert!(t_nc.stat > t_corr.stat);
        // Without correction: 15²/50 * 2 = 9.0
        assert!((t_nc.stat - 9.0).abs() < 1e-9);
    }

    #[test]
    fn two_sample_basic() {
        // R: prop.test(c(30, 40), c(100, 100), correct=TRUE)
        let t = prop_test_two(30, 100, 40, 100, true).unwrap();
        assert_eq!(t.dof, 1.0);
        assert!(t.stat > 0.0);
        // p should be moderate (not very significant)
        assert!(t.p_value > 0.05);
    }

    #[test]
    fn rejects_bad_inputs() {
        assert!(prop_test_one(5, 3, 0.5, true).is_err());
        assert!(prop_test_one(5, 0, 0.5, true).is_err());
        assert!(prop_test_one(5, 10, 0.0, true).is_err());
        assert!(prop_test_one(5, 10, 1.0, true).is_err());
        assert!(prop_test_two(5, 3, 4, 10, true).is_err());
        assert!(prop_test_two(5, 10, 4, 0, true).is_err());
        assert!(prop_test_two(0, 10, 0, 12, true).is_err());
        assert!(prop_test_two(10, 10, 12, 12, true).is_err());
        assert!(prop_test_one_with_options(5, 10, 0.5, true, Alternative::Less, f64::NAN).is_err());
    }

    #[test]
    fn continuity_is_capped_and_large_totals_do_not_overflow() {
        let near = prop_test_one(50, 101, 0.497, true).unwrap();
        assert!(near.stat < 1e-28);
        assert!((near.p_value - 1.0).abs() < 1e-12);
        let equal = prop_test_two(30, 100, 30, 100, true).unwrap();
        assert_eq!(equal.stat, 0.0);
        assert_eq!(equal.p_value, 1.0);
        let large = prop_test_two(1, u32::MAX, 2, u32::MAX, false).unwrap();
        assert_eq!(large.extras["n"].as_u64(), Some(2 * u64::from(u32::MAX)));
        assert!(large.p_value.is_finite());
    }
}
