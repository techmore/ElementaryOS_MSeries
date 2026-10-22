use claude_pantheon_rs::t3::model::UsageSummary;
use claude_pantheon_rs::usage::UsagePage;
use gtk::prelude::*;

fn labels(widget: &gtk::Widget, out: &mut Vec<String>) {
    if let Some(label) = widget.downcast_ref::<gtk::Label>() {
        out.push(label.text().to_string());
    }
    let mut child = widget.first_child();
    while let Some(current) = child {
        labels(&current, out);
        child = current.next_sibling();
    }
}

fn rendered_labels(summary: &UsageSummary) -> Vec<String> {
    let page = UsagePage::new();
    page.render(summary, &[]);
    let mut out = Vec::new();
    labels(page.widget().upcast_ref(), &mut out);
    out
}

#[test]
fn usage_shows_only_cache_metrics_returned_by_t3() {
    gtk::init().expect("GTK initializes under Xvfb");

    let absent: UsageSummary = serde_json::from_value(serde_json::json!({
        "buckets": [{
            "provider": "codex",
            "model": "fixture-model",
            "totals": {"uncachedInputTokens": 10, "outputTokens": 4},
            "costUsd": 0.01
        }]
    }))
    .unwrap();
    let absent_labels = rendered_labels(&absent);
    assert!(!absent_labels.iter().any(|text| text == "cache reads"));
    assert!(!absent_labels.iter().any(|text| text == "saved by caching"));
    assert!(!absent_labels.iter().any(|text| text.contains("cache read") || text.contains("cache write")));

    let reported_zero: UsageSummary = serde_json::from_value(serde_json::json!({
        "buckets": [{
            "provider": "claude",
            "model": "fixture-model",
            "totals": {"cachedInputTokens": 0, "cacheCreationTokens": 0},
            "cacheSavingsUsd": 0.0
        }]
    }))
    .unwrap();
    let zero_labels = rendered_labels(&reported_zero);
    assert!(zero_labels.iter().any(|text| text == "cache reads"));
    assert!(zero_labels.iter().any(|text| text == "saved by caching"));
    assert!(zero_labels.iter().any(|text| text.contains("cache write 0 · cache read 0")));
}
