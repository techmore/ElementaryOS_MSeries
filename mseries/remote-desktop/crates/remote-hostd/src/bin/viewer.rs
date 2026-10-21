//! `tm-remote-viewer <invite-link>`: headless viewer for support diagnostics
//! and automated smoke tests. Prints one JSON line when done.

use std::time::Duration;

use clap::Parser;
use remote_hostd::client::{run, Options};
use remote_rtc::RtcConfig;

#[derive(Parser)]
#[command(version, about = "Headless viewer for the M-Series remote desktop")]
struct Args {
    /// Invite link shown on the computer, e.g. http://100.64.0.9:8484/#i=...
    link: String,
    /// Seconds to stream before disconnecting.
    #[arg(long, default_value_t = 5)]
    seconds: u64,
    /// Seconds to wait for the owner to tap Allow.
    #[arg(long, default_value_t = 90)]
    wait: u64,
    #[arg(long, default_value = "tm-remote-viewer")]
    device: String,
    /// Send one pointer nudge once video is flowing (only acts if control was granted).
    #[arg(long)]
    send_input: bool,
    /// Bind the media socket to loopback only (same-machine tests).
    #[arg(long)]
    loopback: bool,
}

#[tokio::main]
async fn main() {
    let a = Args::parse();
    let rtc = if a.loopback { RtcConfig::loopback() } else { RtcConfig::default() };
    let opts = Options {
        duration: Duration::from_secs(a.seconds),
        device: a.device,
        wait_for_owner: Duration::from_secs(a.wait),
        send_input: a.send_input,
        rtc,
    };
    match run(&a.link, opts).await {
        Ok(r) => {
            println!(
                "{}",
                serde_json::json!({
                    "ok": true, "frames": r.frames, "seconds": r.seconds, "width": r.width, "height": r.height,
                    "first_frame_ms": r.first_frame_ms, "control": r.control_granted, "rejected": r.rejected, "ended": r.ended,
                })
            );
        }
        Err(e) => {
            println!("{}", serde_json::json!({ "ok": false, "error": e.to_string() }));
            std::process::exit(1);
        }
    }
}
