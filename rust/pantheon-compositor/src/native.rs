//! Native M-series renderer setup.
//!
//! The renderer is selected independently of the KMS output device. On the
//! M1 Pro, the Asahi render node can render client content while the Apple DRM
//! device owns the physical connectors. Output allocation and scanout are
//! attached by the native output backend built on top of this manager.

use std::collections::HashSet;
use std::path::Path;
use std::time::{Duration, Instant};

use smithay::{
    backend::{
        allocator::gbm::{GbmAllocator, GbmBufferFlags, GbmDevice},
        drm::{
            DrmDevice, DrmDeviceFd, DrmDeviceNotifier, DrmNode, NodeType,
            compositor::FrameFlags,
            exporter::gbm::GbmFramebufferExporter,
            output::{DrmOutput, DrmOutputManager, DrmOutputRenderElements},
        },
    },
    backend::{
        egl::{EGLContext, EGLDevice, EGLDisplay, context::ContextPriority},
        libinput::{LibinputInputBackend, LibinputSessionInterface},
        renderer::{
            gles::GlesRenderer,
            multigpu::{GpuManager, MultiRenderer, gbm::GbmGlesBackend},
        },
        session::{
            Event as SessionEvent, Session,
            libseat::{LibSeatSession, LibSeatSessionNotifier},
        },
        udev::all_gpus,
    },
    output::{Mode, Output, PhysicalProperties},
    reexports::{
        calloop::{
            EventLoop, channel,
            channel::Event as ChannelEvent,
            timer::{TimeoutAction, Timer},
        },
        drm::control::{Device as DrmControlDevice, ModeTypeFlags, connector},
        input::Libinput,
        rustix::fs::OFlags,
    },
    utils::DeviceFd,
};

use crate::{
    PantheonCompositor,
    cursor::{CursorRenderElement, render_cursor_elements, render_lock_surface_elements},
    display_config::OutputSnapshot,
};

pub type GbmRendererBackend = GbmGlesBackend<GlesRenderer, DrmDeviceFd>;
pub type NativeGpuManager = GpuManager<GbmRendererBackend>;
pub type NativeAllocator = GbmAllocator<DrmDeviceFd>;
pub type NativeExporter = GbmFramebufferExporter<DrmDeviceFd>;
pub type NativeOutputManager = DrmOutputManager<NativeAllocator, NativeExporter, (), DrmDeviceFd>;
pub type NativeDrmOutput = DrmOutput<NativeAllocator, NativeExporter, (), DrmDeviceFd>;
type NativeMultiRenderer<'a> = MultiRenderer<'a, 'a, GbmRendererBackend, GbmRendererBackend>;

const OUTPUT_FORMATS: &[smithay::backend::allocator::Fourcc] = &[
    smithay::backend::allocator::Fourcc::Abgr2101010,
    smithay::backend::allocator::Fourcc::Argb2101010,
    smithay::backend::allocator::Fourcc::Abgr8888,
    smithay::backend::allocator::Fourcc::Argb8888,
];

pub struct NativeRenderer {
    pub render_node: DrmNode,
    pub render_gbm: GbmDevice<DrmDeviceFd>,
    pub gpus: NativeGpuManager,
}

pub struct NativeKmsOutput {
    pub connector: connector::Handle,
    pub crtc: smithay::reexports::drm::control::crtc::Handle,
    pub output: Output,
    pub drm_output: NativeDrmOutput,
    pub global_id: smithay::reexports::wayland_server::backend::GlobalId,
    pub frame_pending: bool,
}

pub struct NativeKmsDevice {
    pub node: DrmNode,
    pub manager: NativeOutputManager,
    pub outputs: Vec<NativeKmsOutput>,
    pub notifier: Option<DrmDeviceNotifier>,
    pending_global_removals: Vec<(
        smithay::reexports::wayland_server::backend::GlobalId,
        Instant,
    )>,
}

pub struct NativeBackend {
    pub _session: LibSeatSession,
    pub renderer: NativeRenderer,
    pub kms: NativeKmsDevice,
    session_paused: bool,
}

struct ConnectedOutput {
    connector: connector::Info,
    crtc: smithay::reexports::drm::control::crtc::Handle,
    mode: smithay::reexports::drm::control::Mode,
}

impl NativeKmsDevice {
    /// Open the first usable KMS device on the active libseat and initialize
    /// every connected connector with a compatible, unclaimed CRTC. Each
    /// output receives its own scanout surface while sharing the device,
    /// allocator, exporter and event source.
    pub fn initialize(
        session: &LibSeatSession,
        renderer: &mut NativeRenderer,
        state: &mut PantheonCompositor,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let mut last_error = None;
        for path in all_gpus(session.seat())? {
            let node = match DrmNode::from_path(&path) {
                Ok(node) if node.dev_id() != renderer.render_node.dev_id() => node,
                _ => continue,
            };
            match Self::open_output_device(session, node, &path, renderer, state) {
                Ok(kms) => return Ok(kms),
                Err(error) => last_error = Some(error),
            }
        }

        match last_error {
            Some(error) => Err(error),
            None => Err("no separate DRM KMS device was found on the active libseat".into()),
        }
    }

    /// Render the current Pantheon space to this output and queue damaged
    /// content for scanout. The matching KMS vblank must call
    /// `frame_submitted` before another frame is queued.
    pub fn render(
        &mut self,
        renderer: &mut NativeRenderer,
        state: &PantheonCompositor,
    ) -> Result<usize, Box<dyn std::error::Error>> {
        let mut rendered = 0;
        for output in &mut self.outputs {
            if output.frame_pending {
                continue;
            }
            let mut gpu_renderer = renderer.gpus.single_renderer(&renderer.render_node)?;
            let elements = if state.session_locked {
                render_lock_surface_elements(&mut gpu_renderer, state, &output.output)
            } else {
                let space_elements = smithay::desktop::space::space_render_elements(
                    &mut gpu_renderer,
                    [&state.space],
                    &output.output,
                    1.0,
                )?;
                let cursor_elements =
                    render_cursor_elements(&mut gpu_renderer, state, &output.output);
                let mut elements = space_elements
                    .into_iter()
                    .map(|element| match element {
                        smithay::desktop::space::SpaceRenderElements::Surface(surface) => {
                            CursorRenderElement::from(surface)
                        }
                        smithay::desktop::space::SpaceRenderElements::Element(element) => {
                            CursorRenderElement::from(element)
                        }
                        smithay::desktop::space::SpaceRenderElements::_GenericCatcher(_) => {
                            unreachable!("SpaceRenderElements generic catcher is never constructed")
                        }
                    })
                    .collect::<Vec<_>>();
                elements.extend(cursor_elements);
                elements
            };
            let frame = output.drm_output.render_frame(
                &mut gpu_renderer,
                &elements,
                if state.session_locked {
                    [0.0, 0.0, 0.0, 1.0]
                } else {
                    [0.1, 0.1, 0.1, 1.0]
                },
                FrameFlags::DEFAULT,
            )?;
            if frame.is_empty {
                continue;
            }
            output.drm_output.queue_frame(())?;
            output.frame_pending = true;
            rendered += 1;
        }
        Ok(rendered)
    }

    pub fn frame_submitted(
        &mut self,
        crtc: smithay::reexports::drm::control::crtc::Handle,
    ) -> Result<Option<Output>, Box<dyn std::error::Error>> {
        let Some(output) = self.outputs.iter_mut().find(|output| output.crtc == crtc) else {
            return Ok(None);
        };
        output.drm_output.frame_submitted()?;
        output.frame_pending = false;
        Ok(Some(output.output.clone()))
    }

    /// Reconcile connected DRM connectors with the outputs published to the
    /// Wayland space. Smithay's DRM notifier reports page flips and failures,
    /// so connector state is polled on a short timer instead of assuming a
    /// hotplug event will arrive through that source.
    fn refresh_connectors(
        &mut self,
        renderer: &mut NativeRenderer,
        state: &mut PantheonCompositor,
    ) -> Result<bool, Box<dyn std::error::Error>> {
        let resources = self.manager.device_mut().resource_handles()?;
        let mut connected = Vec::new();
        let mut connected_handles = HashSet::new();
        for handle in resources.connectors() {
            let info = self.manager.device_mut().get_connector(*handle, false)?;
            if info.state() == connector::State::Connected {
                connected_handles.insert(info.handle());
                if !info.modes().is_empty() {
                    connected.push(info);
                }
            }
        }
        connected.sort_by_key(|info| {
            (
                info.interface() != connector::Interface::EmbeddedDisplayPort,
                info.interface_id(),
            )
        });
        let disconnected = self
            .outputs
            .iter()
            .filter(|output| !connected_handles.contains(&output.connector))
            .map(|output| output.connector)
            .collect::<Vec<_>>();
        let mut changed = !disconnected.is_empty();
        if changed {
            for output in self
                .outputs
                .iter()
                .filter(|output| !connected_handles.contains(&output.connector))
            {
                state
                    .display_handle
                    .disable_global::<PantheonCompositor>(output.global_id.clone());
                self.pending_global_removals
                    .push((output.global_id.clone(), Instant::now()));
                state.space.unmap_output(&output.output);
                state.forget_output_during_lock(&output.output.name());
                state.display_config.remove(output.output.name());
                tracing::info!(output = %output.output.name(), "unmapped disconnected DRM output");
            }
            self.outputs
                .retain(|output| connected_handles.contains(&output.connector));
        }

        let mut claimed_crtcs = self
            .outputs
            .iter()
            .map(|output| output.crtc)
            .collect::<HashSet<_>>();
        for info in connected {
            if self
                .outputs
                .iter()
                .any(|output| output.connector == info.handle())
            {
                continue;
            }

            let encoder = info
                .current_encoder()
                .and_then(|handle| self.manager.device_mut().get_encoder(handle).ok())
                .or_else(|| {
                    info.encoders()
                        .iter()
                        .find_map(|handle| self.manager.device_mut().get_encoder(*handle).ok())
                });
            let Some(encoder) = encoder else {
                tracing::warn!(connector = ?info.handle(), "connected DRM connector has no usable encoder");
                continue;
            };
            let Some(crtc) = resources
                .filter_crtcs(encoder.possible_crtcs())
                .into_iter()
                .find(|crtc| !claimed_crtcs.contains(crtc))
            else {
                tracing::warn!(connector = ?info.handle(), "connected DRM connector has no unclaimed compatible CRTC");
                continue;
            };

            let drm_mode = info
                .modes()
                .iter()
                .find(|mode| mode.mode_type().contains(ModeTypeFlags::PREFERRED))
                .copied()
                .unwrap_or(info.modes()[0]);
            let mode = Mode::from(drm_mode);
            let name = format!("{}-{}", info.interface().as_str(), info.interface_id());
            let (physical_width, physical_height) = info.size().unwrap_or((0, 0));
            let output = Output::new(
                name.clone(),
                PhysicalProperties {
                    size: (physical_width as i32, physical_height as i32).into(),
                    subpixel: info.subpixel().into(),
                    make: "Apple".into(),
                    model: name.clone(),
                    serial_number: "Unknown".into(),
                },
            );
            output.set_preferred(mode);
            output.change_current_state(Some(mode), None, None, Some((0, 0).into()));

            let mut gpu_renderer = renderer.gpus.single_renderer(&renderer.render_node)?;
            let render_elements = DrmOutputRenderElements::<
                NativeMultiRenderer<'_>,
                CursorRenderElement<NativeMultiRenderer<'_>>,
            >::default();
            let drm_output = match self.manager.lock().initialize_output(
                crtc,
                drm_mode,
                &[info.handle()],
                &output,
                None,
                &mut gpu_renderer,
                &render_elements,
            ) {
                Ok(output) => output,
                Err(error) => {
                    tracing::warn!(%name, ?error, "could not initialize newly connected KMS output");
                    continue;
                }
            };

            let global_id = output.create_global::<PantheonCompositor>(&state.display_handle);
            self.outputs.push(NativeKmsOutput {
                connector: info.handle(),
                crtc,
                output,
                drm_output,
                global_id,
                frame_pending: false,
            });
            claimed_crtcs.insert(crtc);
            changed = true;
            tracing::info!(%name, ?mode, "mapped newly connected DRM output");
        }

        if changed {
            self.outputs.sort_by_key(|output| {
                (
                    !output.output.name().starts_with("eDP-"),
                    output.output.name(),
                )
            });
            let mut x = 0;
            for (index, output) in self.outputs.iter().enumerate() {
                state.space.map_output(&output.output, (x, 0));
                state.track_output_for_lock(&output.output);
                if let Some(mode) = output.output.current_mode() {
                    output
                        .output
                        .change_current_state(None, None, None, Some((x, 0).into()));
                    state.display_config.update(OutputSnapshot {
                        connector: output.output.name(),
                        vendor: "Apple".into(),
                        product: output.output.name(),
                        serial: "Unknown".into(),
                        width: mode.size.w,
                        height: mode.size.h,
                        refresh_millihz: mode.refresh,
                        scale: 1.0,
                        x,
                        y: 0,
                        primary: index == 0,
                    });
                    x += mode.size.w;
                }
            }

            let output_geometries = state
                .space
                .outputs()
                .filter_map(|output| state.space.output_geometry(output))
                .collect::<Vec<_>>();
            let fallback = output_geometries.first().copied();
            if let Some(fallback) = fallback {
                let windows = state.space.elements().cloned().collect::<Vec<_>>();
                for window in windows {
                    let Some(location) = state.space.element_location(&window) else {
                        continue;
                    };
                    let size = window.geometry().size;
                    let center_x = location.x + size.w / 2;
                    let center_y = location.y + size.h / 2;
                    let on_output = output_geometries.iter().any(|geometry| {
                        center_x >= geometry.loc.x
                            && center_x < geometry.loc.x + geometry.size.w
                            && center_y >= geometry.loc.y
                            && center_y < geometry.loc.y + geometry.size.h
                    });
                    if !on_output {
                        let max_x = fallback.loc.x + (fallback.size.w - size.w).max(0);
                        let max_y = fallback.loc.y + (fallback.size.h - size.h).max(0);
                        let x = (fallback.loc.x + (fallback.size.w - size.w) / 2)
                            .clamp(fallback.loc.x, max_x);
                        let y = (fallback.loc.y + (fallback.size.h - size.h) / 2)
                            .clamp(fallback.loc.y, max_y);
                        state.space.map_element(window, (x, y), false);
                    }
                }
            }

            state.last_work_area = None;
            let panels = state
                .space
                .elements()
                .filter_map(|window| {
                    let surface = window.toplevel()?.wl_surface();
                    state.is_panel_surface(surface).then(|| surface.clone())
                })
                .collect::<Vec<_>>();
            let has_mapped_panels = !panels.is_empty();
            for panel in panels {
                state.update_panel(&panel, |_| {});
            }
            if !has_mapped_panels && state.space.outputs().next().is_some() {
                state.reconfigure_managed_windows();
            }
            state.space.refresh();
            let _ = state.display_handle.flush_clients();
            state.request_native_redraw();
        }

        let now = Instant::now();
        self.pending_global_removals
            .retain(|(global, disabled_at)| {
                if now.duration_since(*disabled_at) >= Duration::from_secs(2) {
                    state
                        .display_handle
                        .remove_global::<PantheonCompositor>(global.clone());
                    false
                } else {
                    true
                }
            });

        Ok(changed)
    }

    fn open_output_device(
        session: &LibSeatSession,
        node: DrmNode,
        path: &Path,
        renderer: &mut NativeRenderer,
        state: &mut PantheonCompositor,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let mut session = session.clone();
        let fd = session.open(
            path,
            OFlags::RDWR | OFlags::CLOEXEC | OFlags::NOCTTY | OFlags::NONBLOCK,
        )?;
        let drm_fd = DrmDeviceFd::new(DeviceFd::from(fd));
        let (drm, notifier) = DrmDevice::new(drm_fd.clone(), true)?;
        let gbm = GbmDevice::new(drm_fd)?;
        let resources = drm.resource_handles()?;

        let mut discovered = Vec::new();
        for handle in resources.connectors() {
            let connector = drm.get_connector(*handle, false)?;
            if connector.state() != connector::State::Connected || connector.modes().is_empty() {
                continue;
            }
            discovered.push(connector);
        }
        discovered.sort_by_key(|connector| {
            (
                connector.interface() != connector::Interface::EmbeddedDisplayPort,
                connector.interface_id(),
            )
        });

        let mut connected = Vec::new();
        let mut claimed_crtcs = HashSet::new();
        for connector in discovered {
            let encoder = connector
                .current_encoder()
                .and_then(|handle| drm.get_encoder(handle).ok())
                .or_else(|| {
                    connector
                        .encoders()
                        .iter()
                        .find_map(|handle| drm.get_encoder(*handle).ok())
                });
            let Some(encoder) = encoder else { continue };
            let Some(crtc) = resources
                .filter_crtcs(encoder.possible_crtcs())
                .into_iter()
                .find(|crtc| !claimed_crtcs.contains(crtc))
            else {
                continue;
            };
            claimed_crtcs.insert(crtc);
            let mode = connector
                .modes()
                .iter()
                .find(|mode| mode.mode_type().contains(ModeTypeFlags::PREFERRED))
                .copied()
                .unwrap_or(connector.modes()[0]);
            connected.push(ConnectedOutput {
                connector,
                crtc,
                mode,
            });
        }

        if connected.is_empty() {
            return Err("KMS device has no connected connector with a compatible CRTC".into());
        }

        let output_allocator = renderer.output_allocator();
        let mut gpu_renderer = renderer.gpus.single_renderer(&renderer.render_node)?;
        let render_formats = gpu_renderer
            .as_mut()
            .egl_context()
            .dmabuf_render_formats()
            .iter()
            .copied()
            .collect::<Vec<_>>();
        if render_formats.is_empty() {
            return Err("hardware renderer exposes no DMA-BUF render formats".into());
        }

        let exporter = GbmFramebufferExporter::new(gbm.clone(), renderer.render_node.into());
        let mut manager = DrmOutputManager::new(
            drm,
            output_allocator,
            exporter,
            Some(gbm),
            OUTPUT_FORMATS.iter().copied(),
            render_formats,
        );

        let render_elements = DrmOutputRenderElements::<
            NativeMultiRenderer<'_>,
            CursorRenderElement<NativeMultiRenderer<'_>>,
        >::default();
        let mut outputs = Vec::with_capacity(connected.len());
        let mut x = 0;
        for selected in connected {
            let mode = Mode::from(selected.mode);
            let name = format!(
                "{}-{}",
                selected.connector.interface().as_str(),
                selected.connector.interface_id()
            );
            let (physical_width, physical_height) = selected.connector.size().unwrap_or((0, 0));
            let output = Output::new(
                name.clone(),
                PhysicalProperties {
                    size: (physical_width as i32, physical_height as i32).into(),
                    subpixel: selected.connector.subpixel().into(),
                    make: "Apple".into(),
                    model: name.clone(),
                    serial_number: "Unknown".into(),
                },
            );
            output.set_preferred(mode);
            output.change_current_state(Some(mode), None, None, Some((x, 0).into()));

            let drm_output = match manager.lock().initialize_output(
                selected.crtc,
                selected.mode,
                &[selected.connector.handle()],
                &output,
                None,
                &mut gpu_renderer,
                &render_elements,
            ) {
                Ok(output) => output,
                Err(error) => {
                    tracing::warn!(%name, ?error, "could not initialize connected KMS output");
                    continue;
                }
            };

            let global_id = output.create_global::<PantheonCompositor>(&state.display_handle);
            state.space.map_output(&output, (x, 0));
            state.display_config.update(OutputSnapshot {
                connector: name.clone(),
                vendor: "Apple".into(),
                product: name,
                serial: "Unknown".into(),
                width: mode.size.w,
                height: mode.size.h,
                refresh_millihz: mode.refresh,
                scale: 1.0,
                x,
                y: 0,
                primary: outputs.is_empty(),
            });
            x += mode.size.w;
            outputs.push(NativeKmsOutput {
                connector: selected.connector.handle(),
                crtc: selected.crtc,
                output,
                drm_output,
                global_id,
                frame_pending: false,
            });
        }
        if outputs.is_empty() {
            return Err("could not initialize any connected KMS output".into());
        }

        Ok(Self {
            node,
            manager,
            outputs,
            notifier: Some(notifier),
            pending_global_removals: Vec::new(),
        })
    }
}

impl NativeBackend {
    /// Initialize native input, renderer and the first KMS output, then register
    /// their event sources. This is called only for explicit `--backend native`
    /// startup; the default nested backend never opens a libseat session.
    pub fn start(
        event_loop: &mut EventLoop<PantheonCompositor>,
        state: &mut PantheonCompositor,
        session: LibSeatSession,
        session_notifier: LibSeatSessionNotifier,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let mut renderer = NativeRenderer::initialize(&session)?;
        let mut kms = NativeKmsDevice::initialize(&session, &mut renderer, state)?;
        let drm_notifier = kms.notifier.take().expect("DRM notifier is present");

        let mut libinput_context = Libinput::new_with_udev::<
            LibinputSessionInterface<LibSeatSession>,
        >(session.clone().into());
        libinput_context
            .udev_assign_seat(&session.seat())
            .map_err(|_| "libinput failed to assign the active seat")?;
        let libinput_backend = LibinputInputBackend::new(libinput_context.clone());
        event_loop
            .handle()
            .insert_source(libinput_backend, |event, _, state| {
                state.process_input_event(event);
                #[cfg(feature = "native-drm")]
                state.request_native_redraw();
            })?;

        event_loop.handle().insert_source(
            session_notifier,
            move |event, _, state| match event {
                SessionEvent::PauseSession => {
                    libinput_context.suspend();
                    if let Some(backend) = state.native_backend.as_mut() {
                        backend.kms.manager.pause();
                        backend.session_paused = true;
                    }
                    tracing::info!("native compositor session paused");
                }
                SessionEvent::ActivateSession => {
                    tracing::info!("native compositor session activated");
                    if let Err(error) = libinput_context.resume() {
                        tracing::error!(?error, "failed to resume libinput");
                    }
                    if let Some(backend) = state.native_backend.as_mut() {
                        backend.session_paused = true;
                        match backend.kms.manager.lock().activate(false) {
                            Ok(()) => backend.session_paused = false,
                            Err(error) => {
                                tracing::error!(?error, "failed to reactivate DRM output");
                            }
                        }
                    }
                    state.request_native_redraw();
                }
            },
        )?;

        event_loop
            .handle()
            .insert_source(drm_notifier, |event, _, state| match event {
                smithay::backend::drm::DrmEvent::VBlank(crtc) => {
                    let Some(backend) = state.native_backend.as_mut() else {
                        return;
                    };
                    let output = match backend.kms.frame_submitted(crtc) {
                        Ok(Some(output)) => output,
                        Ok(None) => return,
                        Err(error) => {
                            tracing::error!(?error, "failed to complete native DRM frame");
                            return;
                        }
                    };
                    state.confirm_lock_output_frame(&output.name());
                    state.space.elements().for_each(|window| {
                        window.send_frame(
                            &output,
                            state.start_time.elapsed(),
                            Some(Duration::ZERO),
                            |_, _| Some(output.clone()),
                        );
                    });
                    state.space.refresh();
                    state.popups.cleanup();
                    let _ = state.display_handle.flush_clients();
                    state.request_native_redraw();
                }
                smithay::backend::drm::DrmEvent::Error(error) => {
                    tracing::error!(?error, "native DRM event source failed");
                }
            })?;

        let (redraw_sender, redraw_receiver) = channel::channel();
        state.native_redraw_sender = Some(redraw_sender);
        state.native_backend = Some(Self {
            _session: session,
            renderer,
            kms,
            session_paused: false,
        });
        event_loop
            .handle()
            .insert_source(redraw_receiver, |event, _, state| {
                if !matches!(event, ChannelEvent::Msg(())) {
                    return;
                }
                let Some(mut backend) = state.native_backend.take() else {
                    return;
                };
                if let Err(error) = backend.kms.render(&mut backend.renderer, state) {
                    tracing::error!(?error, "native output render failed");
                }
                state.native_backend = Some(backend);
            })?;

        event_loop.handle().insert_source(
            Timer::from_duration(Duration::from_secs(2)),
            |_, _, state| {
                let Some(mut backend) = state.native_backend.take() else {
                    return TimeoutAction::ToDuration(Duration::from_secs(2));
                };
                if !backend.session_paused
                    && let Err(error) = backend.kms.refresh_connectors(&mut backend.renderer, state)
                {
                    tracing::warn!(?error, "failed to reconcile native DRM connectors");
                }
                state.native_backend = Some(backend);
                TimeoutAction::ToDuration(Duration::from_secs(2))
            },
        )?;
        state.request_native_redraw();
        Ok(())
    }
}

impl NativeRenderer {
    /// Allocate render buffers on the hardware GPU with scanout usage enabled.
    /// The Apple KMS framebuffer exporter can import these buffers for the
    /// display controller, which has no EGL renderer on the measured M1 Pro.
    pub fn output_allocator(&self) -> NativeAllocator {
        GbmAllocator::new(
            self.render_gbm.clone(),
            GbmBufferFlags::RENDERING | GbmBufferFlags::SCANOUT,
        )
    }

    /// Open the first hardware renderer on the active libseat and register it
    /// with Smithay's multi-GPU manager. A scanout-only GPU is intentionally
    /// not required to expose EGL.
    pub fn initialize(session: &LibSeatSession) -> Result<Self, Box<dyn std::error::Error>> {
        let gpu_paths = all_gpus(session.seat())?;
        if gpu_paths.is_empty() {
            return Err("libseat found no DRM GPU nodes".into());
        }

        let primary_path = smithay::backend::udev::primary_gpu(session.seat())
            .ok()
            .flatten();
        let mut paths = gpu_paths;
        if let Some(primary_path) = primary_path {
            if let Some(index) = paths.iter().position(|path| path == &primary_path) {
                paths.remove(index);
            }
            paths.insert(0, primary_path);
        }

        let mut gpus = GpuManager::new(GbmRendererBackend::with_factory(|display| {
            let context = EGLContext::new_with_priority(display, ContextPriority::High)?;
            let capabilities = unsafe { GlesRenderer::supported_capabilities(&context)? };
            Ok(unsafe { GlesRenderer::with_capabilities(context, capabilities)? })
        }))?;

        let mut last_error = None;
        for path in paths {
            match Self::add_hardware_node(session, &mut gpus, &path) {
                Ok(Some((render_node, render_gbm))) => {
                    return Ok(Self {
                        render_node,
                        render_gbm,
                        gpus,
                    });
                }
                Ok(None) => {}
                Err(error) => last_error = Some(error),
            }
        }

        match last_error {
            Some(error) => Err(error),
            None => Err("no hardware EGL renderer was found on the active libseat".into()),
        }
    }

    fn add_hardware_node(
        session: &LibSeatSession,
        gpus: &mut NativeGpuManager,
        path: &Path,
    ) -> Result<Option<(DrmNode, GbmDevice<DrmDeviceFd>)>, Box<dyn std::error::Error>> {
        let node = DrmNode::from_path(path)?;
        let mut session = session.clone();
        let fd = session.open(
            path,
            OFlags::RDWR | OFlags::CLOEXEC | OFlags::NOCTTY | OFlags::NONBLOCK,
        )?;
        let drm_fd = DrmDeviceFd::new(DeviceFd::from(fd));
        let gbm = smithay::backend::allocator::gbm::GbmDevice::new(drm_fd.clone())?;
        let display = unsafe { EGLDisplay::new(gbm.clone())? };
        let egl_device = EGLDevice::device_for_display(&display)?;

        if egl_device.is_software() {
            return Ok(None);
        }

        let render_node = egl_device
            .try_get_render_node()?
            .or_else(|| node.node_with_type(NodeType::Render).and_then(Result::ok))
            .unwrap_or(node);
        gpus.as_mut().add_node(render_node, gbm.clone())?;
        Ok(Some((render_node, gbm)))
    }
}
