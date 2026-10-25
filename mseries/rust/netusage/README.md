# Network-usage logger Rust candidate

This standalone daemon is a Rust candidate for
`mseries/netspeed/netusage/netusage.py`. It keeps the existing resolved monitor
and `ss -tinpHO` input contracts, process/host attribution, idle sampling,
15-second flushing, and the `usage_minute`, `usage_hour`, `dns_hour`, and `meta`
SQLite schema consumed by `panel-network.patch`.

The candidate is not installed or enabled. Keep the existing Python
`netusage.service` as the only active writer until a fixture-driven differential
suite, rollback rehearsal, package review, and device-session qualification
have been completed. Do not run both services together: they share one database
and would double count traffic.

## Build and current checks

```sh
cargo fmt --check
cargo test --locked
cargo clippy --locked --all-targets -- -D warnings
cargo build --release --locked
```

The candidate currently has focused unit tests for socket counter parsing,
loopback filtering, process names, DNS address/name handling, query accounting,
socket counter deltas, SQL quoting, a SQLite schema/flush round trip, and
restoring pending records after a failed database flush before a successful
retry. A same-fixture comparison
against the Python socket parser covers counters, missing counters, loopback,
unowned sockets and IPv6 peers. A second same-fixture comparison covers eleven
timestamped resolved events, including A/AAAA suppression, failures, ignored
names and answer addresses. Full daemon restart, SQLite failure/retry and
desktop-session differential cases remain before calling the port complete.

Intentional hardening: malformed resolved `question` containers are skipped
instead of terminating the DNS reader thread; Python and Rust share this rule,
and the malformed-container cases are included in the fixture suite.

Runtime requirements are `ss`, `resolvectl`, `timeout`, and the `sqlite3` CLI.
SQLite remains accessed through the CLI to avoid an unsafe FFI boundary. The
database location and retention windows match the Python service.

No intentional enhancements are included. Hardware and desktop-session
qualification has not been performed.
