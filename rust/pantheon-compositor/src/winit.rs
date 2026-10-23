use std::{cell::RefCell, rc::Rc, time::Duration};

use smithay::{
    backend::{
        renderer::{damage::OutputDamageTracker, gles::GlesRenderer},
        winit::{self, WinitEvent},
    },
    output::{Mode, Output, PhysicalProperties, Subpixel},
    reexports::calloop::{EventLoop, channel},
    utils::{Rectangle, Transform},
};

use crate::PantheonCompositor;
use crate::cursor::{render_desktop_elements, render_lock_surface_elements};
use crate::display_config::{
    OutputModeSnapshot, OutputSnapshot, load_saved_monitor_configurations, transform_to_dbus,
};

pub fn init_winit(
    event_loop: &mut EventLoop<PantheonCompositor>,
    state: &mut PantheonCompositor,
) -> Result<(), Box<dyn std::error::Error>> {
    let (backend, winit) = winit::init()?;
    let backend = Rc::new(RefCell::new(backend));
    init_dmabuf(&backend, state);

    let mode = Mode {
        size: backend.borrow().window_size(),
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
    let saved = load_saved_monitor_configurations().remove("winit");
    let x = saved.as_ref().map_or(0, |saved| saved.x);
    let y = saved.as_ref().map_or(0, |saved| saved.y);
    let scale = saved.as_ref().map_or(1.0, |saved| saved.scale);
    // The nested Winit target's framebuffer is vertically flipped relative to
    // Smithay's logical output coordinates. Cancel that here; native DRM uses
    // the connector transform reported by the kernel instead.
    let transform = match saved.as_ref().map_or(6, |saved| saved.transform) {
        0 => Transform::Normal,
        1 => Transform::_90,
        2 => Transform::_180,
        3 => Transform::_270,
        4 => Transform::Flipped,
        5 => Transform::Flipped90,
        6 => Transform::Flipped180,
        _ => Transform::Flipped270,
    };
    output.change_current_state(
        Some(mode),
        Some(transform),
        Some(smithay::output::Scale::Fractional(scale)),
        Some((x, y).into()),
    );
    output.set_preferred(mode);

    state.space.map_output(&output, (x, y));
    state.primary_output_name = Some(output.name());
    state.display_config.update(OutputSnapshot {
        connector: "winit".into(),
        vendor: "Smithay".into(),
        product: "Winit".into(),
        serial: "Nested".into(),
        width: mode.size.w,
        height: mode.size.h,
        refresh_millihz: mode.refresh,
        modes: vec![OutputModeSnapshot {
            width: mode.size.w,
            height: mode.size.h,
            refresh_millihz: mode.refresh,
            preferred: true,
        }],
        scale: output.current_scale().fractional_scale(),
        transform: transform_to_dbus(output.current_transform()),
        x: output.current_location().x,
        y: output.current_location().y,
        primary: true,
        enabled: true,
    });

    let mut damage_tracker = OutputDamageTracker::from_output(&output);

    let event_backend = backend.clone();
    event_loop
        .handle()
        .insert_source(winit, move |event, _, state| {
            let mut backend = event_backend.borrow_mut();
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
                        modes: vec![OutputModeSnapshot {
                            width: mode.size.w,
                            height: mode.size.h,
                            refresh_millihz: mode.refresh,
                            preferred: true,
                        }],
                        scale: output.current_scale().fractional_scale(),
                        transform: transform_to_dbus(output.current_transform()),
                        x: output.current_location().x,
                        y: output.current_location().y,
                        primary: true,
                        enabled: true,
                    });
                }
                WinitEvent::Input(event) => {
                    state.process_input_event(event);
                    backend.window().request_redraw();
                }
                WinitEvent::Redraw => {
                    tracing::trace!("rendering nested compositor frame");
                    state.update_fractional_scale_preferences();
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
                            let elements =
                                render_desktop_elements(renderer, state, &output).unwrap();
                            damage_tracker
                                .render_output(
                                    renderer,
                                    &mut framebuffer,
                                    0,
                                    &elements,
                                    [0.1, 0.1, 0.1, 1.0],
                                )
                                .unwrap();
                        }
                    }
                    backend.submit(Some(&[damage])).unwrap();

                    if state.session_locked {
                        state.confirm_lock_output_frame(&output.name());
                    }

                    state.send_lock_surface_frames(&output, state.start_time.elapsed());
                    state.gesture_frame_windows().iter().for_each(|window| {
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
                }
                WinitEvent::CloseRequested => {
                    state.loop_signal.stop();
                }
                _ => (),
            };
        })?;

    let (redraw_sender, redraw_receiver) = channel::channel();
    state.winit_redraw_sender = Some(redraw_sender);
    let redraw_backend = backend.clone();
    event_loop
        .handle()
        .insert_source(redraw_receiver, move |event, _, _state| {
            if matches!(event, channel::Event::Msg(())) {
                redraw_backend.borrow().window().request_redraw();
            }
        })?;
    backend.borrow().window().request_redraw();

    Ok(())
}

/// Advertise `zwp_linux_dmabuf_v1` (v4 feedback) so GTK/Mesa clients can use
/// the GPU instead of falling back to wl_shm and software rendering. Feedback
/// needs the renderer's render node; without it no global is created.
fn init_dmabuf(
    backend: &Rc<RefCell<winit::WinitGraphicsBackend<GlesRenderer>>>,
    state: &mut PantheonCompositor,
) {
    use smithay::backend::{egl::EGLDevice, renderer::ImportDma};
    use smithay::wayland::dmabuf::DmabufFeedbackBuilder;

    let (node, formats) = {
        let mut guard = backend.borrow_mut();
        let renderer = guard.renderer();
        let node = EGLDevice::device_for_display(renderer.egl_context().display())
            .and_then(|device| device.try_get_render_node());
        (node, renderer.dmabuf_formats())
    };
    let Ok(Some(node)) = node else {
        tracing::warn!("nested renderer has no render node; linux-dmabuf not advertised");
        return;
    };
    if formats.iter().next().is_none() {
        tracing::warn!("nested renderer exposes no dmabuf formats; linux-dmabuf not advertised");
        return;
    }
    let feedback = match DmabufFeedbackBuilder::new(node.dev_id(), formats).build() {
        Ok(feedback) => feedback,
        Err(error) => {
            tracing::warn!(%error, "could not build dmabuf feedback; linux-dmabuf not advertised");
            return;
        }
    };
    let importer = backend.clone();
    state.dmabuf_importer = Some(Box::new(move |dmabuf| {
        importer
            .try_borrow_mut()
            .is_ok_and(|mut backend| backend.renderer().import_dmabuf(dmabuf, None).is_ok())
    }));
    let dh = state.display_handle.clone();
    state
        .dmabuf_state
        .create_global_with_default_feedback::<PantheonCompositor>(&dh, &feedback);
    tracing::info!("advertising linux-dmabuf v4 on the nested renderer");
}
