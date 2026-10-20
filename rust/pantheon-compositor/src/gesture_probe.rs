//! Opt-in nested-only input probe for deterministic headless render receipts.
//! Absent from normal builds; the socket must be inside the private runtime dir.
use crate::PantheonCompositor;
use smithay::{
    backend::input::InputTime,
    reexports::calloop::{EventLoop, Interest, Mode, PostAction, generic::Generic},
};
use std::{io, os::unix::net::UnixDatagram, path::PathBuf};

pub(crate) fn install(
    event_loop: &mut EventLoop<'static, PantheonCompositor>,
) -> Result<(), Box<dyn std::error::Error>> {
    let runtime =
        PathBuf::from(std::env::var_os("XDG_RUNTIME_DIR").ok_or("probe needs XDG_RUNTIME_DIR")?);
    let socket = UnixDatagram::bind(runtime.join("gesture-probe"))?;
    socket.set_nonblocking(true)?;
    event_loop.handle().insert_source(
        Generic::new(socket, Interest::READ, Mode::Level),
        |_, socket, state| {
            let mut buffer = [0_u8; 256];
            loop {
                let len = match socket.recv(&mut buffer) {
                    Ok(len) => len,
                    Err(error) if error.kind() == io::ErrorKind::WouldBlock => break,
                    Err(error) => return Err(error),
                };
                let Ok(command) = std::str::from_utf8(&buffer[..len]) else {
                    continue;
                };
                let fields = command.split_whitespace().collect::<Vec<_>>();
                match fields.as_slice() {
                    ["begin"] => state.gesture_swipe_begin(3, InputTime::now()),
                    ["update", x, y] => {
                        if let (Ok(x), Ok(y)) = (x.parse::<f64>(), y.parse::<f64>()) {
                            state.gesture_swipe_update((x, y).into(), InputTime::now());
                        }
                    }
                    ["end"] => state.gesture_swipe_end(false, InputTime::now()),
                    ["cancel"] => state.gesture_swipe_end(true, InputTime::now()),
                    ["reset"] => state.cancel_active_gesture(InputTime::now()),
                    ["workspace", index] => {
                        if let Ok(index) = index.parse::<i32>() {
                            let _ = state.activate_workspace(index);
                        }
                    }
                    ["move", index] => {
                        let window = state.space.elements().next_back().cloned();
                        if let (Some(window), Ok(index)) = (window, index.parse::<i32>()) {
                            let _ = state.move_window_to_workspace(window.id() as u64, index);
                        }
                    }
                    ["animations", enabled] => {
                        use gio::prelude::SettingsExt;
                        let settings = gio::Settings::new("org.gnome.desktop.interface");
                        let _ = settings.set_boolean("enable-animations", *enabled == "on");
                    }
                    ["status"] => tracing::info!(
                        workspace = state.workspace_manager.active(),
                        overview = state.overview_active(),
                        preview = state.gesture_animation.is_some(),
                        windows = state.space.elements().count(),
                        "gesture probe status"
                    ),
                    _ => {}
                }
            }
            state.request_native_redraw();
            Ok(PostAction::Continue)
        },
    )?;
    Ok(())
}
