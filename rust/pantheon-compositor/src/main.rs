#![allow(irrefutable_let_patterns)]

mod cursor;
mod cursor_theme;
mod display_config;
#[cfg(feature = "native-drm")]
mod edid;
mod gala_compat;
mod gesture_animation;
#[cfg(feature = "gesture-probe")]
mod gesture_probe;
mod gestures;
mod grabs;
mod handlers;
#[cfg(feature = "native-drm")]
mod hotplug;
mod input;
#[cfg(feature = "native-drm")]
mod kms_props;
#[cfg(feature = "native-drm")]
mod link_status;
#[cfg(feature = "native-drm")]
pub mod native;
mod overview;
mod pantheon_shell;
mod protocols;
mod shell_compat;
mod state;
mod tiling;
mod touchpad;
mod wakeups;
mod wallpaper;
mod winit;
mod workspace;
mod xwayland;

use smithay::reexports::{calloop::EventLoop, wayland_server::Display};
pub use state::PantheonCompositor;
use std::{
    io,
    os::{linux::net::SocketAddrExt, unix::net::UnixDatagram},
    path::Path,
};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    init_logging();

    let (backend, notify_systemd, command) = parse_arguments()?;
    let mut event_loop: EventLoop<PantheonCompositor> = EventLoop::try_new()?;
    let display: Display<PantheonCompositor> = Display::new()?;
    let mut state = match backend {
        BackendChoice::Nested => {
            if std::env::var_os("WAYLAND_DISPLAY").is_none()
                && std::env::var_os("DISPLAY").is_none()
            {
                return Err("nested backend requires an existing Wayland or X11 session".into());
            }
            let mut state = PantheonCompositor::new(&mut event_loop, display, "winit")?;
            crate::winit::init_winit(&mut event_loop, &mut state)?;
            state
        }
        BackendChoice::Native => {
            #[cfg(feature = "native-drm")]
            {
                use smithay::backend::session::{Session, libseat::LibSeatSession};
                let (session, notifier) = LibSeatSession::new()?;
                let seat_name = session.seat();
                let mut state = PantheonCompositor::new(&mut event_loop, display, &seat_name)?;
                crate::native::NativeBackend::start(
                    &mut event_loop,
                    &mut state,
                    session,
                    notifier,
                )?;
                state
            }
            #[cfg(not(feature = "native-drm"))]
            {
                return Err("native backend requires a build with --features native-drm".into());
            }
        }
    };

    #[cfg(feature = "gesture-probe")]
    if matches!(backend, BackendChoice::Nested) {
        crate::gesture_probe::install(&mut event_loop)?;
    }

    crate::xwayland::start(
        &mut event_loop,
        &mut state,
        matches!(backend, BackendChoice::Native),
    )?;
    state.pending_command = command;
    state.notify_systemd_when_ready = notify_systemd;

    // Launch requested clients against the compositor socket selected above.
    unsafe { std::env::set_var("WAYLAND_DISPLAY", &state.socket_name) };

    // The Gala-compat snapshot is republished after every dispatch, which
    // is when any state it mirrors can have changed (no polling timer).
    event_loop.run(None, &mut state, |state| state.publish_gala_snapshot())?;
    if let Some(error) = state.fatal_error.take() {
        return Err(io::Error::other(error).into());
    }
    Ok(())
}

fn init_logging() {
    if let Ok(env_filter) = tracing_subscriber::EnvFilter::try_from_default_env() {
        tracing_subscriber::fmt().with_env_filter(env_filter).init();
    } else {
        tracing_subscriber::fmt().init();
    }
}

/// Tell a systemd user service that the compositor has initialized its
/// Wayland socket and selected backend. Native startup only reaches this point
/// after the renderer and connected KMS outputs have been initialized.
pub(crate) fn notify_systemd_ready() -> io::Result<()> {
    let socket = std::env::var_os("NOTIFY_SOCKET")
        .ok_or_else(|| io::Error::other("--notify-systemd requires NOTIFY_SOCKET"))?;
    let encoded_socket = socket.as_encoded_bytes();
    let address = if let Some(abstract_name) = encoded_socket.strip_prefix(b"@") {
        std::os::unix::net::SocketAddr::from_abstract_name(abstract_name)?
    } else {
        std::os::unix::net::SocketAddr::from_pathname(Path::new(&socket))?
    };

    let notification = UnixDatagram::unbound()?;
    notification.connect_addr(&address)?;
    notification.send(b"READY=1\nSTATUS=Wayland socket and compositor backend initialized")?;
    Ok(())
}

#[derive(Clone, Copy)]
enum BackendChoice {
    Nested,
    Native,
}

type RunCommand = (String, Vec<String>);
type ParsedArguments = (BackendChoice, bool, Option<RunCommand>);

fn parse_arguments() -> Result<ParsedArguments, Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let mut backend = BackendChoice::Nested;
    let mut notify_systemd = false;
    let mut command = None;
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--backend" => {
                backend = match args.next().as_deref() {
                    Some("nested") => BackendChoice::Nested,
                    Some("native") => BackendChoice::Native,
                    _ => return Err("--backend requires either nested or native".into()),
                };
            }
            "--run" => {
                let program = args.next().ok_or("--run requires a program")?;
                command = Some((program, args.collect()));
                break;
            }
            "--notify-systemd" => notify_systemd = true,
            _ => return Err(
                "usage: pantheon-compositor [--backend nested|native] [--notify-systemd] [--run PROGRAM [ARGS...]]".into(),
            ),
        }
    }
    Ok((backend, notify_systemd, command))
}
