//! Opt-in nested-only input probe for deterministic headless render receipts.
//! Absent from normal builds; the socket must be inside the private runtime dir.
use crate::PantheonCompositor;
use crate::placement::Direction;
use crate::snap_assist::AssistKey;
use crate::tiling::ModeRequest;
use smithay::{
    backend::input::{ButtonState, InputTime},
    input::pointer::{ButtonEvent, GrabStartData, MotionEvent},
    reexports::calloop::{EventLoop, Interest, Mode, PostAction, generic::Generic},
    utils::{Logical, Point, SERIAL_COUNTER},
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
                    ["snap", direction] => {
                        let direction = match *direction {
                            "left" => Some(Direction::Left),
                            "right" => Some(Direction::Right),
                            "up" => Some(Direction::Up),
                            "down" => Some(Direction::Down),
                            _ => None,
                        };
                        if let Some(direction) = direction {
                            state.snap_focused_window(direction);
                        }
                    }
                    ["mode", request] => {
                        let request = match *request {
                            "maximize" => Some(ModeRequest::Maximize),
                            "unmaximize" => Some(ModeRequest::Unmaximize),
                            "fullscreen" => Some(ModeRequest::Fullscreen),
                            "unfullscreen" => Some(ModeRequest::Unfullscreen),
                            _ => None,
                        };
                        if let (Some(request), Some(window)) = (request, state.focused_window()) {
                            state.set_window_mode(&window, request);
                        }
                    }
                    // Drag the focused window through the real move grab.
                    ["press", x, y] => {
                        if let (Ok(x), Ok(y)) = (x.parse::<f64>(), y.parse::<f64>()) {
                            probe_press(state, (x, y).into());
                        }
                    }
                    ["motion", x, y] => {
                        if let (Ok(x), Ok(y)) = (x.parse::<f64>(), y.parse::<f64>()) {
                            probe_motion(state, (x, y).into());
                        }
                    }
                    ["release"] => probe_button(state, ButtonState::Released),
                    // Focus the nth application window, in creation order.
                    ["focus", index] => {
                        if let Ok(index) = index.parse::<usize>() {
                            let mut windows = state
                                .space
                                .elements()
                                .filter(|window| {
                                    window.toplevel().is_none_or(|toplevel| {
                                        !state.is_panel_surface(toplevel.wl_surface())
                                    })
                                })
                                .cloned()
                                .collect::<Vec<_>>();
                            windows.sort_by_key(|window| window.id());
                            if let Some(window) = windows.get(index) {
                                state.raise_window(window, true);
                                state.focus_window_keyboard(window, SERIAL_COUNTER.next_serial());
                            }
                        }
                    }
                    ["assist", action] => {
                        let action = match *action {
                            "next" => Some(AssistKey::Next),
                            "prev" => Some(AssistKey::Previous),
                            "choose" => Some(AssistKey::Choose),
                            "dismiss" => Some(AssistKey::Dismiss),
                            _ => None,
                        };
                        if let Some(action) = action {
                            state.snap_assist_action(action);
                        }
                    }
                    ["assist-click", x, y] => {
                        if let (Ok(x), Ok(y)) = (x.parse::<f64>(), y.parse::<f64>()) {
                            let consumed = state.handle_snap_assist_click((x, y).into());
                            tracing::info!(consumed, "snap probe assist click");
                        }
                    }
                    ["assist-status"] => {
                        tracing::info!("snap probe assist {}", state.assist_summary());
                    }
                    // Press on the focused window's inner edge, as its border would.
                    ["split-press", x, y] => {
                        if let (Ok(x), Ok(y)) = (x.parse::<f64>(), y.parse::<f64>()) {
                            probe_split_press(state, (x, y).into());
                        }
                    }
                    ["placement"] => {
                        if let Some(window) = state.focused_window() {
                            let area = state
                                .primary_output_for(&window)
                                .and_then(|output| state.space.output_geometry(&output))
                                .map(|geometry| state.work_area_for_output(geometry))
                                .unwrap_or_default();
                            tracing::info!(
                                "snap probe {} area={},{},{},{} preview={}",
                                state.placement_summary(&window),
                                area.loc.x,
                                area.loc.y,
                                area.size.w,
                                area.size.h,
                                state.corner_snap_preview.is_some(),
                            );
                        }
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

const BTN_LEFT: u32 = 0x110;

fn probe_motion(state: &mut PantheonCompositor, location: Point<f64, Logical>) {
    let Some(pointer) = state.seat.get_pointer() else {
        return;
    };
    let event = MotionEvent {
        location,
        serial: SERIAL_COUNTER.next_serial(),
        time: InputTime::now(),
    };
    pointer.motion(state, None, &event);
    pointer.frame(state);
}

fn probe_button(state: &mut PantheonCompositor, button_state: ButtonState) {
    let Some(pointer) = state.seat.get_pointer() else {
        return;
    };
    let event = ButtonEvent {
        serial: SERIAL_COUNTER.next_serial(),
        time: InputTime::now(),
        button: BTN_LEFT,
        state: button_state,
    };
    pointer.button(state, &event);
    pointer.frame(state);
}

/// Press at `location` and start a move grab on the focused window, as a
/// title-bar drag (`xdg_toplevel.move`) would.
fn probe_press(state: &mut PantheonCompositor, location: Point<f64, Logical>) {
    probe_motion(state, location);
    probe_button(state, ButtonState::Pressed);
    let (Some(pointer), Some(window)) = (state.seat.get_pointer(), state.focused_window()) else {
        return;
    };
    let start_data = GrabStartData {
        focus: None,
        button: BTN_LEFT,
        location,
    };
    state.start_move_grab(&pointer, start_data, window, SERIAL_COUNTER.next_serial());
}

fn probe_split_press(state: &mut PantheonCompositor, location: Point<f64, Logical>) {
    probe_motion(state, location);
    probe_button(state, ButtonState::Pressed);
    let (Some(pointer), Some(window)) = (state.seat.get_pointer(), state.focused_window()) else {
        return;
    };
    let start_data = GrabStartData {
        focus: None,
        button: BTN_LEFT,
        location,
    };
    let edges = state.inner_edge_of(&window);
    let started = state.try_start_split_resize(
        &pointer,
        start_data,
        &window,
        edges,
        SERIAL_COUNTER.next_serial(),
    );
    tracing::info!(started, "snap probe split press");
}
