//! `mseries-remote-hostd`: the desktop-side daemon.
//!
//! * `mseries-remote-hostd` runs the daemon (D-Bus name `io.elementary.mseries.Remote`).
//! * `mseries-remote-hostd ctl <cmd>` is the scriptable owner interface.
//! * `mseries-remote-hostd check` prints a readiness report and exits.

use std::path::PathBuf;
use std::sync::Arc;

use clap::{Parser, Subcommand};
use remote_core::audit::{AuditSink, FileAudit, MemoryAudit};
use remote_core::clock::SystemClock;
use remote_core::consent::Policy;
use remote_hostd::backend::{Backend, TestBackend};
use remote_hostd::config::Config;
use remote_hostd::controller::{rtc_from_config, Controller};
use remote_hostd::web::run_listener_manager;

#[derive(Parser)]
#[command(version, about = "M-Series remote desktop host daemon (WebRTC)")]
struct Cli {
    #[arg(long, global = true)]
    config: Option<PathBuf>,
    /// Override the backend: `mutter` or `test`.
    #[arg(long)]
    backend: Option<String>,
    /// Override the listen address, e.g. 127.0.0.1:8484.
    #[arg(long)]
    listen: Option<String>,
    /// Start with sharing enabled (otherwise it starts off, by design).
    #[arg(long)]
    enable: bool,
    /// Run without the D-Bus interface (headless demos; consent requests then time out and deny).
    #[arg(long)]
    no_dbus: bool,
    /// With --no-dbus: print an invite link at start-up.
    #[arg(long)]
    print_invite: bool,
    #[command(subcommand)]
    command: Option<Cmd>,
}

#[derive(Subcommand)]
enum Cmd {
    /// Report what this machine can do.
    Check,
    /// Talk to a running daemon over D-Bus.
    Ctl {
        #[command(subcommand)]
        op: Ctl,
    },
}

#[derive(Subcommand)]
enum Ctl {
    Status,
    Enable,
    Disable,
    /// Print an invite link (add --control to let the owner grant control).
    Invite {
        #[arg(long)]
        control: bool,
    },
    Approve {
        request_id: String,
        /// Also allow remote control (view-only otherwise).
        #[arg(long)]
        control: bool,
    },
    Deny {
        request_id: String,
    },
    /// Turn control on or off for the live session.
    Control {
        state: OnOff,
    },
    Stop,
}

#[derive(Clone, clap::ValueEnum)]
enum OnOff {
    On,
    Off,
}

fn load_config(cli: &Cli) -> Config {
    let path = cli.config.clone().unwrap_or_else(Config::default_path);
    let mut cfg = Config::load(&path).unwrap_or_else(|e| {
        eprintln!("config error: {e}");
        std::process::exit(2);
    });
    if let Some(b) = &cli.backend {
        cfg.backend = b.clone();
    }
    if let Some(l) = &cli.listen {
        cfg.listen = l.clone();
    }
    if cli.enable {
        cfg.enable_at_start = true;
    }
    if let Err(e) = cfg.validate() {
        eprintln!("config error: {e}");
        std::process::exit(2);
    }
    cfg
}

fn make_backend(cfg: &Config) -> Result<Arc<dyn Backend>, String> {
    match cfg.backend.as_str() {
        "test" => Ok(Arc::new(TestBackend::default())),
        #[cfg(feature = "mutter")]
        "mutter" => Ok(Arc::new(remote_hostd::backend::mutter::MutterBackend::new())),
        other => Err(format!("backend {other:?} is not built into this binary")),
    }
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "info".into()),
        )
        .init();
    let cli = Cli::parse();

    match &cli.command {
        Some(Cmd::Check) => return check(&load_config(&cli)).await,
        #[cfg(feature = "dbus")]
        Some(Cmd::Ctl { op }) => return ctl(op).await,
        #[cfg(not(feature = "dbus"))]
        Some(Cmd::Ctl { .. }) => {
            eprintln!("built without D-Bus support");
            std::process::exit(2);
        }
        None => {}
    }

    let cfg = load_config(&cli);
    let backend = make_backend(&cfg).unwrap_or_else(|e| {
        eprintln!("{e}");
        std::process::exit(2);
    });
    let audit: Box<dyn AuditSink> = {
        let path = cfg
            .audit_log
            .clone()
            .unwrap_or_else(Config::default_audit_path);
        match FileAudit::open(&path) {
            Ok(a) => Box::new(a),
            Err(e) => {
                tracing::warn!(
                    "audit log {} unavailable ({e}); keeping it in memory only",
                    path.display()
                );
                Box::new(MemoryAudit::default())
            }
        }
    };
    let rtc = rtc_from_config(&cfg);
    let ctl = Controller::new(
        cfg.clone(),
        rtc,
        backend,
        Arc::new(SystemClock),
        audit,
        Policy::default(),
    );
    ctl.spawn_ticker();
    tokio::spawn(run_listener_manager(ctl.clone()));

    #[cfg(feature = "dbus")]
    let _bus = if cli.no_dbus {
        None
    } else {
        match remote_hostd::dbus::serve(ctl.clone()).await {
            Ok(c) => Some(c),
            Err(e) => {
                eprintln!(
                    "cannot own {} on the session bus: {e}",
                    remote_hostd::dbus::BUS_NAME
                );
                std::process::exit(1);
            }
        }
    };
    #[cfg(not(feature = "dbus"))]
    let _ = cli.no_dbus;

    if cfg.enable_at_start {
        ctl.set_enabled(true).await;
    }
    if cli.print_invite {
        // Wait for the listener, then print one view-only link.
        for _ in 0..50 {
            if ctl.status().listen.is_some() {
                break;
            }
            tokio::time::sleep(std::time::Duration::from_millis(100)).await;
        }
        match ctl.create_invite(false) {
            Ok(info) => {
                for l in info.links {
                    println!("{}\t{}", l.label, l.url);
                }
            }
            Err(e) => eprintln!("cannot create an invite: {e}"),
        }
    }

    let _ = tokio::signal::ctrl_c().await;
    ctl.set_enabled(false).await;
}

async fn check(cfg: &Config) {
    println!(
        "config: backend={} listen={} fps={} bitrate={}kbps",
        cfg.backend, cfg.listen, cfg.fps, cfg.bitrate_kbps
    );
    let hosts = remote_hostd::invite::candidate_hosts(&cfg.advertise);
    if hosts.is_empty() {
        println!("network: no non-loopback IPv4 address found");
    }
    for (label, host) in hosts {
        println!("network: {label} {host}");
    }
    let gst = std::process::Command::new("gst-launch-1.0")
        .arg("--version")
        .output();
    println!(
        "gstreamer: {}",
        if gst.map(|o| o.status.success()).unwrap_or(false) {
            "found"
        } else {
            "MISSING (needed for screen capture)"
        }
    );
    #[cfg(feature = "mutter")]
    if cfg.backend == "mutter" {
        match remote_hostd::backend::mutter::MutterBackend::probe() {
            Ok(()) => println!("compositor: org.gnome.Mutter.RemoteDesktop available"),
            Err(e) => println!("compositor: NOT available ({e})"),
        }
    }
}

#[cfg(feature = "dbus")]
async fn ctl(op: &Ctl) {
    use remote_hostd::dbus::RemoteProxy;
    let conn = zbus::Connection::session().await.unwrap_or_else(|e| {
        eprintln!("no session bus: {e}");
        std::process::exit(1);
    });
    let proxy = RemoteProxy::new(&conn).await.unwrap_or_else(|e| {
        eprintln!("{e}");
        std::process::exit(1);
    });
    let res: zbus::Result<()> = async {
        match op {
            Ctl::Status => println!("{}", proxy.get_status().await?),
            Ctl::Enable => proxy.set_enabled(true).await?,
            Ctl::Disable => proxy.set_enabled(false).await?,
            Ctl::Invite { control } => println!("{}", proxy.create_invite(*control).await?),
            Ctl::Approve {
                request_id,
                control,
            } => proxy.decide(request_id, true, *control).await?,
            Ctl::Deny { request_id } => proxy.decide(request_id, false, false).await?,
            Ctl::Control { state } => proxy.set_control(matches!(state, OnOff::On)).await?,
            Ctl::Stop => proxy.stop().await?,
        }
        Ok(())
    }
    .await;
    if let Err(e) = res {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
