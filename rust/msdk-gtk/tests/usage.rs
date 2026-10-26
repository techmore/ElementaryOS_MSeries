//! Run under a private D-Bus session and Xvfb.
use gtk::prelude::*;
use msdk::usage::{
    Coverage, Observation, Quota, QuotaUnit, Scope, Snapshot, Source, State, Window,
};

fn labels(widget: &gtk::Widget, output: &mut Vec<String>) {
    if let Some(label) = widget.downcast_ref::<gtk::Label>() {
        output.push(label.text().to_string());
    }
    let mut child = widget.first_child();
    while let Some(current) = child {
        labels(&current, output);
        child = current.next_sibling();
    }
}

#[test]
fn usage_rows_preserve_accounts_and_do_not_show_expired_quota_as_live() {
    assert_eq!(std::env::var("MSDK_PRIVATE_TEST_BUS").as_deref(), Ok("1"));
    gtk::init().unwrap();
    let first = Observation {
        scope: Scope {
            provider: "claude".into(),
            source: Source::LocalClient,
            account: Some("a".into()),
        },
        provider_label: "Claude".into(),
        source_label: "This device".into(),
        account_label: Some("Work".into()),
        selected: true,
        state: State::Fresh,
        observed_at: Some(100),
        windows: vec![Window {
            key: "week".into(),
            label: "7 day".into(),
            quota: Some(Quota::new(2500, QuotaUnit::Used, 100, Some(200)).unwrap()),
        }],
        tokens: None,
    };
    let second = Observation {
        scope: Scope {
            account: Some("b".into()),
            ..first.scope.clone()
        },
        account_label: Some("Personal".into()),
        selected: false,
        state: State::Unknown,
        windows: vec![Window {
            key: "week".into(),
            label: "7 day".into(),
            quota: None,
        }],
        ..first.clone()
    };
    let snapshot = Snapshot {
        coverage: Coverage::Partial,
        observations: vec![first, second],
    };
    let root = msdk_gtk::usage::render(&snapshot, 200).unwrap();
    let mut text = Vec::new();
    labels(root.upcast_ref(), &mut text);
    for expected in [
        "Claude",
        "This device",
        "Work · Selected",
        "Personal",
        "7 day: Expired — refresh required",
        "7 day: Unknown",
        "Usage coverage is partial",
    ] {
        assert!(
            text.iter().any(|value| value == expected),
            "missing {expected}: {text:?}"
        );
    }
    assert!(
        !text.iter().any(|value| value.contains("75%")),
        "expired quota cannot appear current"
    );
    let stale = Observation {
        state: State::Stale,
        windows: vec![Window {
            key: "week".into(),
            label: "7 day".into(),
            quota: Some(Quota::new(2500, QuotaUnit::Used, 100, None).unwrap()),
        }],
        ..snapshot.observations[1].clone()
    };
    let stale_view = msdk_gtk::usage::render(
        &Snapshot {
            coverage: Coverage::Complete,
            observations: vec![stale],
        },
        200,
    )
    .unwrap();
    let mut stale_text = Vec::new();
    labels(stale_view.upcast_ref(), &mut stale_text);
    assert_eq!(
        stale_text
            .iter()
            .filter(|value| value.as_str() == "Stale")
            .count(),
        1
    );
    assert!(
        stale_text
            .iter()
            .any(|value| value == "7 day: 75% remaining")
    );
    assert!(stale_text.iter().any(|value| value == "Reset unknown"));
}
