#![allow(irrefutable_let_patterns)]

mod cursor;
mod display_config;
mod grabs;
mod handlers;
mod input;
#[cfg(feature = "native-drm")]
pub mod native;
mod pantheon_shell;
mod protocols;
mod shell_compat;
mod state;
mod winit;

use smithay::reexports::{calloop::EventLoop, wayland_server::Display};
pub use state::PantheonCompositor;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    init_logging();

    let (backend, command) = parse_arguments()?;
    let mut event_loop: EventLoop<PantheonCompositor> = EventLoop::try_new()?;
    let display: Display<PantheonCompositor> = Display::new()?;
    let mut state = match backend {
        BackendChoice::Nested => {
            if std::env::var_os("WAYLAND_DISPLAY").is_none()
                && std::env::var_os("DISPLAY").is_none()
            {
                return Err("nested backend requires an existing Wayland or X11 session".into());
            }
            let mut state = PantheonCompositor::new(&mut event_loop, display, "winit");
            crate::winit::init_winit(&mut event_loop, &mut state)?;
            state
        }
        BackendChoice::Native => {
            #[cfg(feature = "native-drm")]
            {
                use smithay::backend::session::{Session, libseat::LibSeatSession};
                let (session, notifier) = LibSeatSession::new()?;
                let seat_name = session.seat();
                let mut state = PantheonCompositor::new(&mut event_loop, display, &seat_name);
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

    // Launch requested clients against the compositor socket selected above.
    unsafe { std::env::set_var("WAYLAND_DISPLAY", &state.socket_name) };

    if let Some((program, args)) = command {
        std::process::Command::new(program).args(args).spawn()?;
    }

    event_loop.run(None, &mut state, move |_| {})?;
    Ok(())
}

fn init_logging() {
    if let Ok(env_filter) = tracing_subscriber::EnvFilter::try_from_default_env() {
        tracing_subscriber::fmt().with_env_filter(env_filter).init();
    } else {
        tracing_subscriber::fmt().init();
    }
}

#[derive(Clone, Copy)]
enum BackendChoice {
    Nested,
    Native,
}

fn parse_arguments()
-> Result<(BackendChoice, Option<(String, Vec<String>)>), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let mut backend = BackendChoice::Nested;
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
            _ => return Err(
                "usage: pantheon-compositor [--backend nested|native] [--run PROGRAM [ARGS...]]"
                    .into(),
            ),
        }
    }
    Ok((backend, command))
}
