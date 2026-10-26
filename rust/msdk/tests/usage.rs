use msdk::usage::{Quota, QuotaUnit, Scope, Source, State, Tokens};
use std::collections::HashSet;

#[test]
fn used_and_remaining_are_explicit_and_expired_windows_are_not_fresh() {
    let used = Quota::new(2500, QuotaUnit::Used, 100, Some(200)).unwrap();
    let remaining = Quota::new(7500, QuotaUnit::Remaining, 100, Some(200)).unwrap();
    assert_eq!(used.used_basis_points(), remaining.used_basis_points());
    assert_eq!(used.remaining_basis_points(), 7500);
    assert_eq!(used.observed_at(), 100);
    assert_eq!(used.state_at(State::Fresh, 199), State::Fresh);
    assert_eq!(used.state_at(State::Fresh, 200), State::Expired);
    assert_eq!(used.state_at(State::Stale, 200), State::Stale);
    assert!(Quota::new(10001, QuotaUnit::Used, 0, None).is_none());
    assert_eq!(Quota::new(0, QuotaUnit::Used, 0, None).unwrap().used_basis_points(), 0);
}

#[test]
fn token_subsets_are_not_counted_twice_and_missing_is_not_zero() {
    let counts = Tokens { input: Some(40), output: Some(25), cached_input: Some(12), reasoning: Some(7) };
    assert_eq!(counts.total(), Some(65));
    assert!(counts.subsets_valid());
    assert!(!Tokens { reasoning: Some(26), ..counts }.subsets_valid());
    assert!(!Tokens { cached_input: Some(41), ..counts }.subsets_valid());
    assert_eq!(Tokens { output: None, ..counts }.total(), None);
    assert_eq!(Tokens { input: Some(u64::MAX), output: Some(1), ..counts }.total(), None);
}

#[test]
fn account_aggregate_and_remote_sources_have_distinct_identity() {
    let aggregate = Scope { provider: "codex".into(), source: Source::LocalClient, account: None };
    let first = Scope { account: Some("account-a".into()), ..aggregate.clone() };
    let second = Scope { account: Some("account-b".into()), ..aggregate.clone() };
    let remote = Scope { source: Source::Server("server-a".into()), ..first.clone() };
    assert!(!format!("{remote:?}").contains("server-a"));
    assert!(!format!("{remote:?}").contains("account-a"));
    assert_eq!([aggregate, first, second, remote].into_iter().collect::<HashSet<_>>().len(), 4);
}
