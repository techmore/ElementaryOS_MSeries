use msdk::runtime::{FailureKind, ServiceFailure, negotiate_service};

#[test]
fn incompatible_extensions_are_typed_and_recoverable() {
    assert!(negotiate_service(1, "example.read", "/update/Refresh", 7).is_ok());
    let failure = negotiate_service(2, "example.read", "/update/Refresh", 7).unwrap_err();
    assert_eq!(failure.kind, FailureKind::VersionMismatch);
    let diagnostic = failure.diagnostic();
    assert_eq!(diagnostic["source"], "/update/Refresh");
    assert_eq!(diagnostic["expected_version"], 1);
    assert_eq!(diagnostic["actual_version"], 2);
    assert!(failure.to_string().contains("retry"));
}

#[test]
fn diagnostic_and_debug_never_serialize_private_backend_details() {
    let secret = "password=synthetic-secret /private/customer/path confidential output";
    let failure =
        ServiceFailure::new(FailureKind::ProcessFailed, "process.run", "/update/Run", 2).with_detail(secret.into());
    assert_eq!(failure.detail(), Some(secret));
    for public in [failure.diagnostic().to_string(), format!("{failure:?}"), failure.to_string()] {
        assert!(!public.contains("synthetic-secret") && !public.contains("/private/customer"));
    }
}

#[test]
fn runtime_discovery_and_explanations_match_actual_limits_and_failures() {
    let discovery = msdk::agent::describe("runtime").unwrap();
    assert_eq!(discovery["extension_api_version"], 1);
    assert_eq!(discovery["process"]["default_combined_output_bytes"], msdk::process::Limits::default().output_bytes);
    assert_eq!(discovery["process"]["streaming"], false);
    for kind in FailureKind::ALL {
        assert_eq!(msdk::agent::explain(kind.code()), Some(kind.message()));
    }
}
