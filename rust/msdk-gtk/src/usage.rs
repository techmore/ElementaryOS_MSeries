//! Candidate reusable usage rows. Host placement, refresh, authentication,
//! focus/dismissal and provider collectors belong to separate adapters.
use gtk::prelude::*;
use msdk::usage::{Coverage, Observation, Snapshot, SnapshotError, State};

fn label(text: &str) -> gtk::Label {
    let label = gtk::Label::new(Some(text));
    label.set_xalign(0.0);
    label.set_wrap(true);
    label
}

fn state_text(state: State) -> &'static str {
    match state {
        State::Loading => "Loading",
        State::Empty => "No usage",
        State::Unknown => "Unknown",
        State::Fresh => "Current",
        State::Stale => "Stale",
        State::Unavailable => "Unavailable",
        State::Failed => "Refresh failed",
        State::Unsupported => "Unsupported",
        State::Expired => "Expired — refresh required",
    }
}

fn append_observation(parent: &gtk::Box, observation: &Observation, now: i64) {
    let heading = observation
        .account_label
        .as_deref()
        .unwrap_or("Provider total");
    let title = if observation.selected {
        format!("{heading} · Selected")
    } else {
        heading.to_string()
    };
    let row = gtk::Box::new(gtk::Orientation::VERTICAL, 3);
    row.append(&label(&title));
    row.append(&label(state_text(observation.state)));
    for window in &observation.windows {
        let value = match window.quota {
            Some(quota)
                if matches!(
                    quota.state_at(observation.state, now),
                    State::Fresh | State::Stale
                ) =>
            {
                let basis = quota.remaining_basis_points();
                let freshness = if observation.state == State::Stale {
                    " · Stale"
                } else {
                    ""
                };
                let reset = quota
                    .reset_at()
                    .and_then(|at| gtk::glib::DateTime::from_unix_local(at).ok())
                    .and_then(|at| at.format("%x %X").ok())
                    .map(|at| format!(" · Resets {at}"))
                    .unwrap_or_else(|| " · Reset unknown".into());
                format!(
                    "{}: {}.{:02}% remaining{reset}{freshness}",
                    window.label,
                    basis / 100,
                    basis % 100
                )
            }
            Some(quota) => format!(
                "{}: {}",
                window.label,
                state_text(quota.state_at(observation.state, now))
            ),
            None => format!("{}: Unknown", window.label),
        };
        row.append(&label(&value));
    }
    if let Some(tokens) = observation.tokens {
        let value = match (observation.state, tokens.total()) {
            (State::Fresh, Some(total)) => format!("Tokens: {total}"),
            (State::Stale, Some(total)) => format!("Tokens: {total} · Stale"),
            (_, Some(_)) => format!("Tokens: {}", state_text(observation.state)),
            (_, None) => "Tokens: Unknown".into(),
        };
        row.append(&label(&value));
    }
    parent.append(&row);
}

/// Build a fresh, read-only view from a validated snapshot. The caller owns
/// updates and must preserve focus/scroll when embedding it in an interactive
/// host. This function neither starts polling nor performs account actions.
pub fn render(snapshot: &Snapshot, now: i64) -> Result<gtk::Box, SnapshotError> {
    let groups = snapshot.groups()?;
    let root = gtk::Box::new(gtk::Orientation::VERTICAL, 12);
    if groups.is_empty() {
        root.append(&label(match snapshot.coverage {
            Coverage::Complete => "No usage available",
            Coverage::Partial => "Usage coverage is partial",
            Coverage::Unknown => "Usage coverage is unknown",
        }));
    }
    for group in groups {
        let card = gtk::Box::new(gtk::Orientation::VERTICAL, 6);
        card.add_css_class("card");
        let heading = label(group.label);
        heading.add_css_class("heading");
        card.append(&heading);
        card.append(&label(group.source_label));
        if let Some(aggregate) = group.aggregate {
            append_observation(&card, aggregate, now);
        }
        for account in group.accounts {
            append_observation(&card, account, now);
        }
        root.append(&card);
    }
    if !matches!(snapshot.coverage, Coverage::Complete) && !snapshot.observations.is_empty() {
        root.append(&label(match snapshot.coverage {
            Coverage::Partial => "Usage coverage is partial",
            _ => "Usage coverage is unknown",
        }));
    }
    Ok(root)
}
