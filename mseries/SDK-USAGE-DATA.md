# Usage observation semantics (candidate)

`msdk::usage` supplies initial Rust data semantics for a future reusable usage
monitor. It does not provide collectors, authentication, a serialization
protocol, a status-area host, or native presentation. Those are still required
before the full status module can be claimed complete.

`Scope` separates provider, source and optional account. A provider aggregate
has no account; a remote server has its own opaque source identity. Callers
must supply opaque keys rather than credentials or private paths. Debug output
omits those keys, but callers must still keep sensitive data out of their own
logs and UI.

`Quota` requires explicit used/remaining basis points in 0–10,000 and a source
observation timestamp. Its conversion preserves the distinction between used
and remaining; a reset at or before the current time marks a fresh window
expired. Unknown observations must remain absent rather than being constructed
as zero. `State` distinguishes loading, empty, unknown, fresh, stale,
unavailable, failed, unsupported and expired; the caller owns transitions and
must not present stale or expired data as current.

`Tokens::total` adds known input and output with overflow checking; missing
components stay unknown. Cached input and reasoning are subsets and are not
added again. `subsets_valid` detects contradictions where a known subset
exceeds its known parent. These helpers do not merge observations, establish
provider coverage, deduplicate overlapping local/server data, or infer source
semantics. Adapters must provide those guarantees from documented contracts.

The in-memory `Snapshot` includes explicit complete/partial/unknown coverage
and groups observations by distinct scope. `validate()` rejects empty identity
keys, duplicate scopes or window keys, a fresh observation without a source
timestamp, and contradictory known token subsets. A window has its own quota
observation time; it need not equal the containing observation's timestamp.
Validation is explicit: callers must invoke it before presenting a snapshot.
This versioned Rust structure is not a versioned wire protocol and cannot by
itself prove that the collector actually covered all configured accounts.

Each observation carries a human-readable provider label and, for account
scope, an account label separate from opaque identity keys. `selected` is
presentation context and does not filter other accounts. `Snapshot::groups()`
validates first, then preserves first-seen provider/source and account order;
provider aggregates remain separate from account observations. It does not
merge overlapping sources or implement native widgets. Provider labels must
agree within each provider/source group. Labels may contain private information;
consumers must not log them indiscriminately.

`msdk_gtk::usage::render` is an initial read-only GTK presentation of a
validated snapshot, grouping provider/source labels, separate account rows and
quota windows. It marks stale and expired observations and does not collect or
refresh data. Callers supply a human-readable source label separately from the
opaque source key. This initial widget has not been visually reviewed against
CodexBar and does not implement status-area placement, popup interactions,
refresh, provider marks, localization, or focus/scroll preservation. It is not
an accepted implementation of the complete status-area specification.

`msdk_gtk::usage::UsagePanel` is a candidate bounded read-only viewport. Its
`update` builds and validates replacement content before changing the displayed
snapshot, then restores the prior numeric vertical scroll offset after layout,
clamped for shorter content. It does not preserve a semantic row anchor, focus
in interactive children, or provide refresh, subscriptions or host placement.
The caller must apply context freshness and stop its own reads.
