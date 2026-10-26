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
