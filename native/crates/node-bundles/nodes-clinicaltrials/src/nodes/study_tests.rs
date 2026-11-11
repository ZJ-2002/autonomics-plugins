// Synthetic fixture identifiers; no provider records were downloaded.
use super::*;
use crate::client::{CapturedResponse, ResponseTransport};
use serde_json::json;

#[test]
fn invalid_unicode_and_ascii_requests_never_panic() {
    for value in [
        "éé1234567",
        "骨髓12345",
        "NCT123",
        "NCT0000000x",
        "NCT00000000/path",
        "",
    ] {
        assert!(crate::client::normalize_nct_id(value).is_err());
    }
}

#[test]
fn date_precision_and_actual_estimated_qualifiers_remain_distinct() {
    for date in ["2026", "2026-10", "2026-10-09"] {
        for qualifier in ["ACTUAL", "ESTIMATED"] {
            let value: crate::types::DateValue =
                serde_json::from_value(json!({"date":date,"type":qualifier})).unwrap();
            assert_eq!(value.date.as_deref(), Some(date));
            assert_eq!(value.value_type.as_deref(), Some(qualifier));
        }
    }
}

#[test]
fn absent_and_zero_enrollment_are_not_collapsed() {
    let absent: crate::types::EnrollmentInfo =
        serde_json::from_value(json!({"type":"ESTIMATED"})).unwrap();
    let zero: crate::types::EnrollmentInfo =
        serde_json::from_value(json!({"count":0,"type":"ACTUAL"})).unwrap();
    assert_eq!(absent.count, None);
    assert_eq!(zero.count, Some(0));
    assert!(serde_json::from_value::<crate::types::EnrollmentInfo>(json!({"count":-1})).is_err());
}

#[test]
fn sparse_interventions_are_not_fabricated_or_given_wrong_type() {
    let study: Study=serde_json::from_value(json!({"protocolSection":{"identificationModule":{"nctId":"NCT00000000"},
        "armsInterventionsModule":{"interventions":[{"type":"DRUG","name":"Synthetic;name"},{"type":"OTHER"},{"name":"Unnamed category"},{}]}}})).unwrap();
    let batch = record_batch(&study).unwrap();
    let array = batch
        .column(13)
        .as_any()
        .downcast_ref::<StringArray>()
        .unwrap();
    assert_eq!(array.value(0), "DRUG:Synthetic;name;OTHER;Unnamed category");
    assert_eq!(batch.num_columns(), 16);
}

#[test]
fn conflicting_legacy_and_official_aliases_do_not_choose_a_winner() {
    assert!(
        serde_json::from_value::<crate::types::Intervention>(
            json!({"type":"DRUG","interventionType":"OTHER"})
        )
        .is_err()
    );
    assert!(
        serde_json::from_value::<crate::types::DateValue>(
            json!({"type":"ACTUAL","valueType":"ESTIMATED"})
        )
        .is_err()
    );
}

#[derive(Debug)]
struct ErrorBody;

#[async_trait]
impl ResponseTransport for ErrorBody {
    async fn response(&self, url: &str) -> crate::error::Result<CapturedResponse> {
        Ok(CapturedResponse {
            url: url.into(),
            response_url: url.into(),
            headers: std::collections::BTreeMap::from([(
                "content-type".into(),
                "application/json".into(),
            )]),
            status: 200,
            body: "{\"message\":\"Synthetic qualification failure\"}".into(),
        })
    }
}

#[tokio::test]
async fn rejected_received_response_still_has_complete_observation() {
    let client = ClinicalTrialsClient::new().with_transport(Arc::new(ErrorBody));
    assert!(client.study("NCT00000000").await.is_err());
    let captured = client.captured_responses();
    assert_eq!(captured.len(), 1);
    assert_eq!(
        captured[0].body,
        "{\"message\":\"Synthetic qualification failure\"}"
    );
    assert_eq!(captured[0].status, 200);
}
