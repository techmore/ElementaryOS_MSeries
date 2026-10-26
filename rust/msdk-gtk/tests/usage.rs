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

    let mut many = Vec::new();
    for (provider, display, count) in [
        ("codex", "Codex", 2),
        ("claude", "Claude", 2),
        ("grok", "Grok", 1),
        ("opencode", "OpenCode", 1),
    ] {
        for index in 0..count {
            let mut item = snapshot.observations[0].clone();
            item.scope.provider = provider.into();
            item.scope.account = Some(format!("fixture-{index}"));
            item.provider_label = display.into();
            item.account_label = Some(format!("{display} account {index}"));
            item.selected = index == 0;
            many.push(item);
        }
    }
    let view = msdk_gtk::usage::render(
        &Snapshot {
            coverage: Coverage::Partial,
            observations: many,
        },
        150,
    )
    .unwrap();
    let mut all_text = Vec::new();
    labels(view.upcast_ref(), &mut all_text);
    assert_eq!(
        all_text.first().map(String::as_str),
        Some("Providers: Codex · Claude · Grok · OpenCode")
    );
    assert_eq!(
        all_text.get(1).map(String::as_str),
        Some("Usage coverage is partial")
    );
    for expected in [
        "Codex account 1",
        "Claude account 1",
        "Grok account 0",
        "OpenCode account 0",
    ] {
        assert!(
            all_text
                .iter()
                .any(|value| value == expected || value == &format!("{expected} · Selected"))
        );
    }
    let scroll = gtk::ScrolledWindow::builder()
        .hscrollbar_policy(gtk::PolicyType::Never)
        .vscrollbar_policy(gtk::PolicyType::Automatic)
        .child(&view)
        .build();
    let window = gtk::Window::builder()
        .default_width(360)
        .default_height(300)
        .child(&scroll)
        .build();
    window.present();
    let context = gtk::glib::MainContext::default();
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(3);
    while scroll.vadjustment().upper() <= scroll.vadjustment().page_size()
        && std::time::Instant::now() < deadline
    {
        context.iteration(false);
        std::thread::sleep(std::time::Duration::from_millis(10));
    }
    let adjustment = scroll.vadjustment();
    assert!(
        adjustment.upper() > adjustment.page_size(),
        "long content must scroll"
    );
    adjustment.set_value(adjustment.upper() - adjustment.page_size());
    assert!(
        adjustment.value() > 0.0,
        "the last provider must be reachable by scrolling"
    );
    window.close();
}
