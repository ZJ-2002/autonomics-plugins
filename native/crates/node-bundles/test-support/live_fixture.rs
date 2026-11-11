//! Live inputs stay in an explicitly supplied private JSON fixture.
#![allow(dead_code)]

pub struct LiveFixture(serde_json::Value);

impl LiveFixture {
    pub fn load(provider: &str) -> Result<Self, Box<dyn std::error::Error + Send + Sync>> {
        let path = std::env::var("AUTONOMICS_NATIVE_LIVE_FIXTURE")?;
        let document: serde_json::Value = serde_json::from_slice(&std::fs::read(path)?)?;
        let values = document.get(provider).filter(|v| v.is_object())
            .ok_or_else(|| std::io::Error::other(format!("missing live fixture section: {provider}")))?;
        Ok(Self(values.clone()))
    }

    pub fn text(&self, key: &str) -> &str {
        self.0.get(key).and_then(serde_json::Value::as_str)
            .filter(|v| !v.is_empty())
            .unwrap_or_else(|| panic!("missing nonempty live fixture string: {key}"))
    }

    pub fn number<T: TryFrom<u64>>(&self, key: &str) -> T {
        self.0.get(key).and_then(serde_json::Value::as_u64)
            .and_then(|v| T::try_from(v).ok())
            .unwrap_or_else(|| panic!("missing representable live fixture integer: {key}"))
    }
}
