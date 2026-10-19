#![allow(irrefutable_let_patterns)]

mod handlers;
mod grabs;
mod input;
mod pantheon_shell;
mod protocols;
mod state;
mod winit;

use smithay::reexports::{calloop::EventLoop, wayland_server::Display};
pub use state::PantheonCompositor;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    init_logging();

    if std::env::var_os("WAYLAND_DISPLAY").is_none() && std::env::var_os("DISPLAY").is_none() {
        return Err("nested prototype requires an existing Wayland or X11 session".into());
    }

    let command = parse_command()?;
    let mut event_loop: EventLoop<PantheonCompositor> = EventLoop::try_new()?;
    let display: Display<PantheonCompositor> = Display::new()?;
    let mut state = PantheonCompositor::new(&mut event_loop, display);

    // This prototype deliberately uses the nested winit backend. It does not
    // open DRM/KMS devices or replace the active desktop session.
    crate::winit::init_winit(&mut event_loop, &mut state)?;

    // The host backend is already initialized from the original environment.
    // Launch requested clients against the nested display only.
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

fn parse_command() -> Result<Option<(String, Vec<String>)>, Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    match args.next().as_deref() {
        None => Ok(None),
        Some("--run") => {
            let program = args.next().ok_or("--run requires a program")?;
            Ok(Some((program, args.collect())))
        }
        Some(_) => Err("usage: pantheon-compositor [--run PROGRAM [ARGS...]]".into()),
    }
}
