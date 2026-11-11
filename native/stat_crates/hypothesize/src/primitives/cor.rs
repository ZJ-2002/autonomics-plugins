//! Correlation tests — port of `stats::cor.test`.
//!
//! Pearson and asymptotic (`exact=FALSE`, `continuity=FALSE`) rank tests.
//! Spearman uses a t approximation; Kendall uses tie-corrected tau-b.

use serde_json::json;

use super::HypothesisTest;
use crate::{
    Alternative, HypoError, KEY_KIND, Result,
    dist::{normal_cdf, normal_sf, normal_two_sided_p},
    extras,
};

/// Correlation method selector.
#[derive(
    Clone, Copy, PartialEq, Eq, Debug, serde::Deserialize, serde::Serialize, schemars::JsonSchema,
)]
#[serde(rename_all = "lowercase")]
pub enum CorMethod {
    Pearson,
    Spearman,
    Kendall,
}

/// Test for association between paired samples.
///
/// Rank methods correspond to `cor.test(..., exact=FALSE, continuity=FALSE)`.
/// They do not implement R's default exact/AS89 branches.
pub fn cor_test(
    x: &[f64],
    y: &[f64],
    method: CorMethod,
    alt: Alternative,
) -> Result<HypothesisTest> {
    if x.len() != y.len() {
        return Err(HypoError::LengthMismatch {
            a: x.len(),
            b: y.len(),
        });
    }
    let n = x.len();
    if n < 3 {
        return Err(HypoError::InvalidInput(
            "correlation test requires ≥ 3 paired observations".into(),
        ));
    }
    if x.iter().chain(y).any(|value| !value.is_finite()) {
        return Err(HypoError::InvalidInput(
            "correlation inputs must be finite".into(),
        ));
    }
    match method {
        CorMethod::Pearson => pearson(x, y, n, alt),
        CorMethod::Spearman => spearman(x, y, n, alt),
        CorMethod::Kendall => kendall(x, y, n, alt),
    }
}

fn pearson(x: &[f64], y: &[f64], n: usize, alt: Alternative) -> Result<HypothesisTest> {
    let nf = n as f64;
    let mx = crate::extras_mean(x);
    let my = crate::extras_mean(y);
    let mut sxy = 0.0;
    let mut sxx = 0.0;
    let mut syy = 0.0;
    for i in 0..n {
        let dx = x[i] - mx;
        let dy = y[i] - my;
        sxy += dx * dy;
        sxx += dx * dx;
        syy += dy * dy;
    }
    if sxx == 0.0 || syy == 0.0 {
        return Err(HypoError::InvalidInput(
            "zero variance in at least one sample (constant values)".into(),
        ));
    }
    let r = (sxy / (sxx * syy).sqrt()).clamp(-1.0, 1.0);
    if !r.is_finite() {
        return Err(HypoError::InvalidInput("correlation is not finite".into()));
    }
    let df = nf - 2.0;
    let t = r * (df / (1.0 - r * r)).sqrt();
    let p = crate::primitives::t::p_value_t(t, df, alt);
    Ok(HypothesisTest::new(
        t,
        p,
        df,
        alt,
        "Pearson's product-moment correlation",
        extras([
            (KEY_KIND, json!("cor_test")),
            ("method", json!("pearson")),
            ("estimate", json!(r)),
            ("n", json!(n as u64)),
        ]),
    ))
}

fn spearman(x: &[f64], y: &[f64], n: usize, alt: Alternative) -> Result<HypothesisTest> {
    let rx = rank_average(x);
    let ry = rank_average(y);
    // Spearman is Pearson on ranks (with average ties).
    let result = pearson(&rx, &ry, n, alt)?;
    Ok(HypothesisTest::new(
        (n as f64).mul_add((n as f64).powi(2), -(n as f64))
            * (1.0 - result.extra_f64("estimate").unwrap())
            / 6.0,
        result.p_value,
        f64::NAN,
        result.alternative,
        "Spearman's rank correlation rho",
        {
            let mut e = result.extras.clone();
            e.insert(KEY_KIND.into(), json!("cor_test"));
            e.insert("method".into(), json!("spearman"));
            e.insert("exact".into(), json!(false));
            e.insert("continuity".into(), json!(false));
            e
        },
    ))
}

fn kendall(x: &[f64], y: &[f64], n: usize, alt: Alternative) -> Result<HypothesisTest> {
    let nf = n as f64;
    // Count concordant and discordant pairs.
    let mut concordant = 0_i64;
    let mut discordant = 0_i64;
    for i in 0..n {
        for j in (i + 1)..n {
            if x[j] == x[i] || y[j] == y[i] {
                continue;
            }
            if (x[j] > x[i]) == (y[j] > y[i]) {
                concordant += 1;
            } else {
                discordant += 1;
            }
        }
    }
    let x_ties = tie_sums(x);
    let y_ties = tie_sums(y);
    let total_pairs = nf * (nf - 1.0) / 2.0;
    let denominator = ((total_pairs - x_ties.0 / 2.0) * (total_pairs - y_ties.0 / 2.0)).sqrt();
    if denominator <= 0.0 {
        return Err(HypoError::InvalidInput(
            "Kendall correlation is not estimable for constant input".into(),
        ));
    }
    let signed_pairs = (concordant - discordant) as f64;
    let tau = signed_pairs / denominator;
    let variance = (nf * (nf - 1.0) * (2.0 * nf + 5.0) - x_ties.1 - y_ties.1) / 18.0
        + x_ties.0 * y_ties.0 / (2.0 * nf * (nf - 1.0))
        + x_ties.2 * y_ties.2 / (9.0 * nf * (nf - 1.0) * (nf - 2.0));
    if variance <= 0.0 || !variance.is_finite() {
        return Err(HypoError::InvalidInput(
            "Kendall null variance is not estimable".into(),
        ));
    }
    let z = signed_pairs / variance.sqrt();
    let p = match alt {
        Alternative::TwoSided => normal_two_sided_p(z),
        Alternative::Greater => normal_sf(z),
        Alternative::Less => normal_cdf(z),
    };
    Ok(HypothesisTest::new(
        z,
        p,
        f64::NAN,
        alt,
        "Kendall's rank correlation tau",
        extras([
            (KEY_KIND, json!("cor_test")),
            ("method", json!("kendall")),
            ("estimate", json!(tau)),
            ("n", json!(n as u64)),
            ("concordant", json!(concordant)),
            ("discordant", json!(discordant)),
            ("exact", json!(false)),
            ("continuity", json!(false)),
        ]),
    ))
}

fn tie_sums(values: &[f64]) -> (f64, f64, f64) {
    let mut sorted = values.to_vec();
    sorted.sort_by(|first, second| first.total_cmp(second));
    let mut pair_sum = 0.0;
    let mut variance_sum = 0.0;
    let mut triple_sum = 0.0;
    let mut start = 0;
    while start < sorted.len() {
        let mut end = start + 1;
        while end < sorted.len() && sorted[end] == sorted[start] {
            end += 1;
        }
        let size = (end - start) as f64;
        pair_sum += size * (size - 1.0);
        variance_sum += size * (size - 1.0) * (2.0 * size + 5.0);
        triple_sum += size * (size - 1.0) * (size - 2.0);
        start = end;
    }
    (pair_sum, variance_sum, triple_sum)
}

/// Assign average ranks (R `rank(ties.method = "average")`).
fn rank_average(v: &[f64]) -> Vec<f64> {
    let n = v.len();
    let mut idx: Vec<usize> = (0..n).collect();
    idx.sort_by(|&a, &b| v[a].partial_cmp(&v[b]).unwrap_or(std::cmp::Ordering::Equal));
    let mut ranks = vec![0.0_f64; n];
    let mut i = 0;
    while i < n {
        let mut j = i + 1;
        while j < n && v[idx[j]] == v[idx[i]] {
            j += 1;
        }
        // Tied positions i..j get the average of ranks i+1..j.
        let avg = ((i + 1 + j) as f64) / 2.0; // average of (i+1, i+2, ..., j) = (i+1+j)/2
        for k in i..j {
            ranks[idx[k]] = avg;
        }
        i = j;
    }
    ranks
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pearson_perfect_positive() {
        let x: Vec<f64> = (1..=10).map(|i| i as f64).collect();
        let y: Vec<f64> = x.iter().map(|&v| 2.0 * v + 1.0).collect();
        let t = cor_test(&x, &y, CorMethod::Pearson, Alternative::TwoSided).unwrap();
        assert!((t.extra_f64("estimate").unwrap() - 1.0).abs() < 1e-12);
        // r=1 → t = +Inf → p ≈ 0
        assert!(t.p_value < 1e-10);
    }

    #[test]
    fn pearson_against_manual() {
        // x = 1..8, y = x + noise
        let x = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0];
        let y = vec![2.0, 4.0, 5.0, 7.0, 9.0, 11.0, 12.0, 15.0];
        let t = cor_test(&x, &y, CorMethod::Pearson, Alternative::TwoSided).unwrap();
        // Manual Pearson r ≈ 0.9958
        let r = t.extra_f64("estimate").unwrap();
        assert!((r - 0.9958).abs() < 0.001);
        assert_eq!(t.dof, 6.0);
    }

    #[test]
    fn spearman_matches_pearson_on_monotonic() {
        // For strictly monotonic data, Spearman r = 1.
        let x = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let y = vec![10.0, 20.0, 30.0, 40.0, 50.0];
        let t = cor_test(&x, &y, CorMethod::Spearman, Alternative::TwoSided).unwrap();
        assert!((t.extra_f64("estimate").unwrap() - 1.0).abs() < 1e-12);
    }

    #[test]
    fn kendall_basic() {
        // Strictly increasing → τ = 1
        let x = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let y = vec![10.0, 20.0, 30.0, 40.0, 50.0];
        let t = cor_test(&x, &y, CorMethod::Kendall, Alternative::TwoSided).unwrap();
        assert!((t.extra_f64("estimate").unwrap() - 1.0).abs() < 1e-12);
    }

    #[test]
    fn rank_metadata_and_kendall_ties_match_asymptotic_r() {
        let first = [1.0, 1.0, 2.0, 4.0, 4.0, 6.0];
        let second = [2.0, 3.0, 3.0, 1.0, 5.0, 5.0];
        let kendall = cor_test(&first, &second, CorMethod::Kendall, Alternative::TwoSided).unwrap();
        assert!((kendall.extra_f64("estimate").unwrap() - 5.0 / 13.0).abs() < 1e-12);
        assert_eq!(kendall.extras["concordant"].as_i64(), Some(8));
        assert_eq!(kendall.extras["discordant"].as_i64(), Some(3));
        assert!(kendall.dof.is_nan());
        let spearman =
            cor_test(&first, &second, CorMethod::Spearman, Alternative::TwoSided).unwrap();
        assert!((spearman.stat - 210.0 / 11.0).abs() < 1e-12);
        assert!(spearman.dof.is_nan());
        assert!(
            cor_test(
                &[1.0, f64::INFINITY, 3.0],
                &[1.0, 2.0, 4.0],
                CorMethod::Pearson,
                Alternative::TwoSided
            )
            .is_err()
        );
    }

    #[test]
    fn rejects_bad_inputs() {
        assert!(cor_test(&[1.0], &[1.0], CorMethod::Pearson, Alternative::TwoSided).is_err());
        assert!(
            cor_test(
                &[1.0, 2.0],
                &[1.0],
                CorMethod::Pearson,
                Alternative::TwoSided
            )
            .is_err()
        );
        // Constant data → zero variance
        assert!(
            cor_test(
                &[1.0, 1.0, 1.0],
                &[1.0, 2.0, 3.0],
                CorMethod::Pearson,
                Alternative::TwoSided
            )
            .is_err()
        );
    }

    #[test]
    fn rank_average_ties() {
        let v = vec![3.0, 1.0, 2.0, 1.0];
        let r = rank_average(&v);
        // Sorted: 1,1,2,3 → ranks 1.5,1.5,3,4 → back: 3→4, 1→1.5, 2→3, 1→1.5
        assert!((r[0] - 4.0).abs() < 1e-12);
        assert!((r[1] - 1.5).abs() < 1e-12);
        assert!((r[2] - 3.0).abs() < 1e-12);
        assert!((r[3] - 1.5).abs() < 1e-12);
    }
}
