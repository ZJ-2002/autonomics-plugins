use schemars::JsonSchema;
use serde::de::DeserializeOwned;
use serde_json::{Value, json};

fn properties<Specification: JsonSchema>() -> Value {
    serde_json::to_value(schemars::schema_for!(Specification)).unwrap()["properties"].clone()
}

#[test]
fn associations_exposes_all_official_optional_controls() {
    let schema = properties::<crate::associations::OpengwasAssociationsSpec>();
    for name in [
        "align_alleles",
        "palindromes",
        "maf_threshold",
        "commercial_approval_received",
    ] {
        assert!(
            schema.get(name).is_some(),
            "Official associations control {name} is absent"
        );
    }
}

#[test]
fn tophits_exposes_explicit_preclumped_and_commercial_controls() {
    let schema = properties::<crate::tophits::OpengwasTophitsSpec>();
    for name in ["preclumped", "commercial_approval_received"] {
        assert!(
            schema.get(name).is_some(),
            "Official tophits control {name} is absent"
        );
    }
}

#[test]
fn phewas_exposes_explicit_commercial_control() {
    let schema = properties::<crate::phewas::OpengwasPhewasSpec>();
    assert!(schema.get("commercial_approval_received").is_some());
}

fn rejects_unknown<Specification: DeserializeOwned>(mut input: Value) {
    input["misspelled_control"] = json!(1);
    assert!(serde_json::from_value::<Specification>(input).is_err());
}

#[test]
fn all_eight_source_specs_reject_unknown_control_fields() {
    rejects_unknown::<crate::associations::OpengwasAssociationsSpec>(
        json!({"variant":["rs1"],"id":["study"]}),
    );
    rejects_unknown::<crate::tophits::OpengwasTophitsSpec>(json!({"id":["study"]}));
    rejects_unknown::<crate::phewas::OpengwasPhewasSpec>(json!({"variant":["rs1"]}));
    rejects_unknown::<crate::gwasinfo::OpengwasGwasinfoSpec>(json!({"id":["study"]}));
    rejects_unknown::<crate::gwasinfo_search::OpengwasGwasinfoSearchSpec>(json!({"keyword":"toy"}));
    rejects_unknown::<crate::ld_clump::OpengwasLdClumpSpec>(json!({"rsid":["rs1"],"pval":[1e-8]}));
    rejects_unknown::<crate::variants_rsid::OpengwasVariantsRsidSpec>(json!({"rsid":["rs1"]}));
    rejects_unknown::<crate::variants_chrpos::OpengwasVariantsChrposSpec>(
        json!({"chrpos":["1:1"]}),
    );
}

#[test]
fn official_decimal_examples_preserve_ieee_bits() {
    for (text, expected) in [
        ("1.4171e-40", 1.4171e-40_f64),
        ("2.09411e-29", 2.09411e-29_f64),
        ("1.88018e-28", 1.88018e-28_f64),
        ("5.11446e-26", 5.11446e-26_f64),
    ] {
        assert_eq!(
            serde_json::from_str::<f64>(text).unwrap().to_bits(),
            expected.to_bits()
        );
    }
}

#[test]
fn associations_request_retains_explicit_zero_and_all_optional_controls() {
    let input = json!({"variant":["rs1"],"id":["study"],"align_alleles":0,
        "palindromes":0,"maf_threshold":0.2,"commercial_approval_received":0});
    let specification: crate::associations::OpengwasAssociationsSpec =
        serde_json::from_value(input.clone()).unwrap();
    let request = serde_json::to_value(specification.request()).unwrap();
    for name in [
        "align_alleles",
        "palindromes",
        "maf_threshold",
        "commercial_approval_received",
    ] {
        assert_eq!(request[name], input[name]);
    }
}

#[test]
fn tophits_request_preserves_explicit_server_selection_without_changing_defaults() {
    let specification: crate::tophits::OpengwasTophitsSpec = serde_json::from_value(
        json!({"id":["study"],"preclumped":0,"commercial_approval_received":0}),
    )
    .unwrap();
    let request = specification.request();
    assert_eq!(request.preclumped, Some(0));
    assert_eq!(request.commercial_approval_received, Some(0));
    assert_eq!(request.kb, Some(5000));
    assert_eq!(request.clump, Some(1));
}

#[test]
fn phewas_request_preserves_empty_index_and_explicit_control() {
    let specification: crate::phewas::OpengwasPhewasSpec = serde_json::from_value(
        json!({"variant":["rs1"],"index_list":[],"commercial_approval_received":0}),
    )
    .unwrap();
    let request = specification.request();
    assert_eq!(request.index_list, Some(Vec::new()));
    assert_eq!(request.commercial_approval_received, Some(0));
    assert_eq!(request.pval, Some(0.01));
}

#[test]
fn omitted_new_controls_remain_omitted() {
    let associations: crate::associations::OpengwasAssociationsSpec =
        serde_json::from_value(json!({"variant":["rs1"],"id":["study"]})).unwrap();
    let request = serde_json::to_value(associations.request()).unwrap();
    for name in [
        "align_alleles",
        "palindromes",
        "maf_threshold",
        "commercial_approval_received",
    ] {
        assert!(request.get(name).is_none());
    }
    let tophits: crate::tophits::OpengwasTophitsSpec =
        serde_json::from_value(json!({"id":["study"]})).unwrap();
    assert_eq!(tophits.request().preclumped, None);
    assert_eq!(tophits.request().commercial_approval_received, None);
}
