use std::time::Duration;

use smithay::{
    backend::{
        renderer::{damage::OutputDamageTracker, gles::GlesRenderer},
        winit::{self, WinitEvent},
    },
    output::{Mode, Output, PhysicalProperties, Subpixel},
    reexports::calloop::EventLoop,
    utils::{Rectangle, Transform},
};

use crate::PantheonCompositor;
use crate::cursor::{CursorRenderElement, render_cursor_elements, render_lock_surface_elements};
use crate::display_config::OutputSnapshot;

pub fn init_winit(
    event_loop: &mut EventLoop<PantheonCompositor>,
    state: &mut PantheonCompositor,
) -> Result<(), Box<dyn std::error::Error>> {
    let (mut backend, winit) = winit::init()?;

    let mode = Mode {
        size: backend.window_size(),
        refresh: 60_000,
    };

    let output = Output::new(
        "winit".to_string(),
        PhysicalProperties {
            size: (0, 0).into(),
            subpixel: Subpixel::Unknown,
            make: "Smithay".into(),
            model: "Winit".into(),
            serial_number: "Unknown".into(),
        },
    );
    let _global = output.create_global::<PantheonCompositor>(&state.display_handle);
    output.change_current_state(
        Some(mode),
        Some(Transform::Flipped180),
        None,
        Some((0, 0).into()),
    );
    output.set_preferred(mode);

    state.space.map_output(&output, (0, 0));
    state.display_config.update(OutputSnapshot {
        connector: "winit".into(),
        vendor: "Smithay".into(),
        product: "Winit".into(),
        serial: "Nested".into(),
        width: mode.size.w,
        height: mode.size.h,
        refresh_millihz: mode.refresh,
        scale: 1.0,
        x: 0,
        y: 0,
        primary: true,
    });

    let mut damage_tracker = OutputDamageTracker::from_output(&output);

    event_loop
        .handle()
        .insert_source(winit, move |event, _, state| {
            match event {
                WinitEvent::Resized { size, .. } => {
                    let mode = Mode {
                        size,
                        refresh: 60_000,
                    };
                    output.change_current_state(Some(mode), None, None, None);
                    let output_name = output.name();
                    if let Some(lock_surface) = state.lock_surfaces.get(&output_name) {
                        lock_surface.with_pending_state(|pending| {
                            pending.size = Some((size.w.max(0) as u32, size.h.max(0) as u32).into())
                        });
                        lock_surface.send_configure();
                    }
                    state.display_config.update(OutputSnapshot {
                        connector: "winit".into(),
                        vendor: "Smithay".into(),
                        product: "Winit".into(),
                        serial: "Nested".into(),
                        width: mode.size.w,
                        height: mode.size.h,
                        refresh_millihz: mode.refresh,
                        scale: 1.0,
                        x: 0,
                        y: 0,
                        primary: true,
                    });
                }
                WinitEvent::Input(event) => state.process_input_event(event),
                WinitEvent::Redraw => {
                    let size = backend.window_size();
                    let damage = Rectangle::from_size(size);

                    {
                        backend.window().set_cursor_visible(false);
                        let (renderer, mut framebuffer) = backend.bind().unwrap();
                        if state.session_locked {
                            let elements = render_lock_surface_elements(renderer, state, &output);
                            damage_tracker
                                .render_output(
                                    renderer,
                                    &mut framebuffer,
                                    0,
                                    &elements,
                                    [0.0, 0.0, 0.0, 1.0],
                                )
                                .unwrap();
                        } else {
                            let cursor_elements = render_cursor_elements(renderer, state, &output);
                            smithay::desktop::space::render_output::<
                                _,
                                CursorRenderElement<GlesRenderer>,
                                _,
                                _,
                            >(
                                &output,
                                renderer,
                                &mut framebuffer,
                                1.0,
                                0,
                                [&state.space],
                                &cursor_elements,
                                &mut damage_tracker,
                                [0.1, 0.1, 0.1, 1.0],
                            )
                            .unwrap();
                        }
                    }
                    backend.submit(Some(&[damage])).unwrap();

                    if state.session_locked {
                        state.confirm_lock_output_frame(&output.name());
                    }

                    state.space.elements().for_each(|window| {
                        window.send_frame(
                            &output,
                            state.start_time.elapsed(),
                            Some(Duration::ZERO),
                            |_, _| Some(output.clone()),
                        )
                    });

                    state.space.refresh();
                    state.popups.cleanup();
                    let _ = state.display_handle.flush_clients();

                    // Ask for redraw to schedule new frame.
                    backend.window().request_redraw();
                }
                WinitEvent::CloseRequested => {
                    state.loop_signal.stop();
                }
                _ => (),
            };
        })?;

    Ok(())
}
