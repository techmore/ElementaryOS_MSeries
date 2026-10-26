# SDK service and process contract

Status: implemented candidate contract for SDK 0.1.0; whole-SDK v1 qualification
remains tracked in SDK-COMPLETION.md. Inspect `msdk describe runtime` for the
implemented version, limits and failure codes. `msdk explain CODE` gives the
recovery message for runtime failures as well as checker diagnostics.

## Typed service extensions

An app supplies `msdk_gtk::host::Services` to `Host::open_with`. The primary entry
point is `invoke(ServiceCall) -> Result<bool, ServiceFailure>`. A request carries
the declared service name, arguments and an owned `ServiceReply`:

- Return `Ok(true)` once the request is owned, including asynchronous work. Keep
  its reply in that owned task and call `reply.success(payload)` or
  `reply.fail(failure)` on completion.
- Return `Ok(false)` only before doing any work. This permits another runtime
  adapter to handle the operation. `Err(failure)` is an owned failure and never
  falls through to a real system action.
- Registered service return payloads are validated before delivery. Wrong
  text/bool/none shapes become `service-malformed-data`, without logging the
  offending value. Declare all supported APIs through a service manifest.
- The first terminal reply wins, even across cloned replies and worker threads.
  Contradictory duplicate completion is ignored. Replies do not retain GTK.
- The Host assigns immutable service/call-source/operation identity to typed
  replies and errors. Rules calls use their `/update/Message` JSON pointer;
  custom Rust logic uses `/logic`. Operation IDs are host-local diagnostics,
  not account identity or a substitute for context/race checks.
- `Services::stop` must retire the provider's own subscriptions, timers, workers
  and pending requests. Its empty default is appropriate only when there is no
  ongoing work. Closing an accepted window stops host-owned work; a vetoed close
  keeps the Host usable. Late events cannot mutate a disposed Host.

`Services::api_version()` defaults to the existing extension interface version 1.
The Host checks it before call/feed dispatch and refuses incompatible versions.
This is the SDK extension contract, **not** a declaration that an OS daemon,
D-Bus interface, T3 server or provider API uses version 1. Each real backend must
publish and negotiate its own supported protocol/version and authority boundary.
Those backend and T3 qualifications remain open.

Existing `call`, `call_checked` and `start_feed` implementations remain compatibility
entry points. New service adapters should use `invoke`/`ServiceReply`. Legacy
raw event senders retain their own payload-validation and completion obligations;
compatibility does not qualify an old adapter automatically. Generic context
switch cancellation and app-specific adapter migration remain open gates.

## Errors and privacy

`msdk::runtime::ServiceFailure` carries a `FailureKind`, service, source context,
operation ID and optional numeric version information. Categories distinguish
unavailable, incompatible, denied, invalid input, malformed data, I/O, failed
process, timeout, output limit, cancellation and busy conditions.

`diagnostic()` emits `msdk.runtime.diagnostic.v1`. Its fields contain source
identifiers, numeric identity and a static recovery message. Command arguments,
stdout/stderr, private backend payloads and credentials are excluded. Debug and
Display use the same safe metadata/message policy. `with_detail`/`detail()` are
an explicit private-UI channel; never copy that detail to public logs/receipts.
A registered error callback receives the recoverable UI message; without one,
the Host shows its error banner. The app must provide useful Retry/Cancel states.

The fixture provider uses this same typed route. A missing reply is an explicit
unavailable error and cannot execute a real fallback. A malformed fixture reply
is rejected. Fixture tracing records the service identifier, not its arguments.

## Owned process work

The GUI-independent Rust API is `msdk::process::{spawn, Limits}`. Hold the returned
`Process` for the lifetime of the operation. `cancel()` or dropping an unfinished
handle requests cancellation of its dedicated process group. The worker reaps
its leader before completion. Group signals finish before the leader is reaped,
with cancellation serialized, so PID reuse cannot target a later process.

Implemented on Linux and macOS; unsupported platforms return a typed unavailable
failure. `/bin/sh -c` runs trusted app-authored task commands with null stdin and
nonblocking stdout/stderr pipes. Defaults are:

| Limit | Behavior |
| --- | --- |
| 120 seconds | Monotonic deadline; timeout stops the owned group |
| 1 MiB combined stdout/stderr | Exceeding the byte budget stops the group |
| 4 concurrent Host jobs | Further calls receive a recoverable busy error |
| Rust `Limits` override | Nonzero timeout/output; output cannot exceed 16 MiB |

`process.run` uses those defaults and delivers completed stdout to its `then`
message. Nonzero exit is a typed failure with stderr available as private detail.
Timeout/output-limit/cancellation are distinct from success. Inherited pipes do
not keep the worker waiting after the leader exits; same-group descendants are
retired. The Host clears owned handles on disposal.

This is task-command ownership, not a sandbox or supervisor for privileged,
daemonized, detached-session or OS-wide transactions. Use an explicit OS-owned
service adapter for those lifecycles; do not route a long-running update
transaction through a short task timeout. Streaming stdout/progress, retained
partial output and the updater reference-app contract remain unfinished. Do not
advertise them as implemented by this completed-output API.

## Verification

Core real-process checks cover output/nonzero exit, timeout, combined byte limit,
flood output, inherited pipes, drop cancellation, leader reaping and same-group
child cleanup, invalid limits and invalid command arguments. Diagnostic tests
cover privacy, version mismatch, actual default-limit discovery and explanations.

The native private-session test uses the actual Host dispatch, worker threads
and GTK state: incompatible provider is not invoked; supported version recovers;
unavailable service, malformed async reply and permission denial enter recovery;
valid typed replies recover; duplicate completion is ignored; missing fixture
reply cannot create a marker through fallback; accepted close kills a real owned
command. Run with a fresh Xvfb/D-Bus session and synthetic XDG state:

```sh
MSDK_PRIVATE_TEST_BUS=1 XDG_DATA_HOME=/tmp/msdk-runtime-state GSK_RENDERER=cairo \
  xvfb-run -a dbus-run-session -- cargo test --manifest-path SDK/Cargo.toml \
  -p msdk-gtk --test lifecycle --test runtime -- --test-threads=1
```

Use the isolated workspace from `mseries/sdk-tests/prepare.py`. Retain source,
locks, commands, results and failures separately from owner/physical-host
acceptance. These tests do not close the remaining SDK completion gates.
