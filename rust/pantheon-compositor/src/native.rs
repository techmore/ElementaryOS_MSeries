//! Native M-series renderer setup.
//!
//! The renderer is selected independently of the KMS output device. On the
//! M1 Pro, the Asahi render node can render client content while the Apple DRM
//! device owns the physical connectors. Output allocation and scanout are
//! attached by the native output backend built on top of this manager.

use std::collections::{HashMap, HashSet};
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
    display_config::{
        OutputModeSnapshot, OutputSnapshot, load_saved_monitor_configurations, transform_to_dbus,
    },
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

fn output_mode_snapshots(
    modes: &[smithay::reexports::drm::control::Mode],
) -> Vec<OutputModeSnapshot> {
    let mut snapshots = modes
        .iter()
        .map(|drm_mode| {
            let mode = Mode::from(*drm_mode);
            OutputModeSnapshot {
                width: mode.size.w,
                height: mode.size.h,
                refresh_millihz: mode.refresh,
                preferred: drm_mode.mode_type().contains(ModeTypeFlags::PREFERRED),
            }
        })
        .collect::<Vec<_>>();
    if !snapshots.iter().any(|mode| mode.preferred)
        && let Some(first) = snapshots.first_mut()
    {
        first.preferred = true;
    }
    snapshots
}

pub struct NativeRenderer {
    pub render_node: DrmNode,
    pub render_gbm: GbmDevice<DrmDeviceFd>,
    pub gpus: NativeGpuManager,
}

pub struct NativeKmsOutput {
    pub connector: connector::Handle,
    pub crtc: smithay::reexports::drm::control::crtc::Handle,
    pub modes: Vec<smithay::reexports::drm::control::Mode>,
    pub output: Output,
    pub drm_output: NativeDrmOutput,
    pub global_id: smithay::reexports::wayland_server::backend::GlobalId,
    pub frame_pending: bool,
}

pub struct NativeKmsDevice {
    pub node: DrmNode,
    pub manager: NativeOutputManager,
    pub outputs: Vec<NativeKmsOutput>,
    disabled_connectors: HashSet<connector::Handle>,
    disconnected_disabled_connectors: HashSet<connector::Handle>,
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
    fn render_elements_for_output<'a>(
        &self,
        gpu_renderer: &mut NativeMultiRenderer<'a>,
        state: &PantheonCompositor,
        replacement: Option<(smithay::reexports::drm::control::crtc::Handle, &Output)>,
    ) -> Result<
        DrmOutputRenderElements<
            NativeMultiRenderer<'a>,
            CursorRenderElement<NativeMultiRenderer<'a>>,
        >,
        String,
    > {
        let mut render_elements = DrmOutputRenderElements::new();
        for output in &self.outputs {
            let render_output = replacement
                .filter(|(crtc, _)| *crtc == output.crtc)
                .map(|(_, output)| output)
                .unwrap_or(&output.output);
            let elements = if state.session_locked {
                render_lock_surface_elements(gpu_renderer, state, render_output)
            } else {
                let space_elements = smithay::desktop::space::space_render_elements(
                    gpu_renderer,
                    [&state.space],
                    render_output,
                    render_output.current_scale().fractional_scale() as f32,
                )
                .map_err(|error| format!("could not prepare output frame: {error:?}"))?;
                let cursor_elements = render_cursor_elements(gpu_renderer, state, render_output);
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
            render_elements.add_output(&output.crtc, [0.1, 0.1, 0.1, 1.0].into(), elements);
        }
        Ok(render_elements)
    }

    fn reassign_crtc_connector(
        &mut self,
        renderer: &mut NativeRenderer,
        state: &mut PantheonCompositor,
        old_name: &str,
        connector_info: &connector::Info,
        mode: smithay::reexports::drm::control::Mode,
    ) -> Result<(), String> {
        let Some(index) = self
            .outputs
            .iter()
            .position(|output| output.output.name() == old_name)
        else {
            return Err(format!("output {old_name} is no longer active"));
        };
        let old_output = self.outputs[index].output.clone();
        let old_connector = self.outputs[index].connector;
        let old_drm_mode = old_output
            .current_mode()
            .and_then(|current| {
                self.outputs[index]
                    .modes
                    .iter()
                    .find(|mode| Mode::from(**mode) == current)
                    .copied()
            })
            .ok_or_else(|| format!("{old_name} has no current DRM mode to restore"))?;
        let crtc = self.outputs[index].crtc;
        let location = old_output.current_location();
        let scale = old_output.current_scale();
        let transform = old_output.current_transform();
        let name = format!(
            "{}-{}",
            connector_info.interface().as_str(),
            connector_info.interface_id()
        );
        let (physical_width, physical_height) = connector_info.size().unwrap_or((0, 0));
        let output = Output::new(
            name.clone(),
            PhysicalProperties {
                size: (physical_width as i32, physical_height as i32).into(),
                subpixel: connector_info.subpixel().into(),
                make: "Apple".into(),
                model: name.clone(),
                serial_number: "Unknown".into(),
            },
        );
        let available_modes = connector_info.modes().to_vec();
        let preferred = available_modes
            .iter()
            .find(|candidate| candidate.mode_type().contains(ModeTypeFlags::PREFERRED))
            .copied()
            .unwrap_or(mode);
        output.set_preferred(Mode::from(preferred));
        for available_mode in &available_modes {
            output.add_mode(Mode::from(*available_mode));
        }
        output.change_current_state(
            Some(Mode::from(mode)),
            Some(transform),
            Some(scale),
            Some(location),
        );

        state.space.map_output(&output, location);
        let connectors = [connector_info.handle()];
        let connector_result = self.outputs[index]
            .drm_output
            .with_compositor(|compositor| {
                compositor.set_output_mode_source((&output).into());
                compositor.set_connectors(&connectors)
            });
        if let Err(error) = connector_result {
            self.outputs[index]
                .drm_output
                .with_compositor(|compositor| {
                    compositor.set_output_mode_source((&old_output).into());
                });
            state.space.unmap_output(&output);
            return Err(format!("DRM rejected connector reassignment: {error:?}"));
        }

        let result = (|| {
            let mut gpu_renderer = renderer
                .gpus
                .single_renderer(&renderer.render_node)
                .map_err(|error| format!("could not activate display renderer: {error:?}"))?;
            let render_elements =
                self.render_elements_for_output(&mut gpu_renderer, state, Some((crtc, &output)))?;
            self.outputs[index]
                .drm_output
                .use_mode(mode, &mut gpu_renderer, &render_elements)
                .map_err(|error| format!("could not commit connector reassignment: {error:?}"))
        })();

        if let Err(error) = result {
            let connectors = [old_connector];
            self.outputs[index]
                .drm_output
                .with_compositor(|compositor| {
                    compositor.set_output_mode_source((&old_output).into());
                    compositor.set_connectors(&connectors)
                })
                .map_err(|rollback| {
                    state.space.unmap_output(&output);
                    format!("{error}; could not restore previous connector: {rollback:?}")
                })?;
            let mut gpu_renderer = renderer
                .gpus
                .single_renderer(&renderer.render_node)
                .map_err(|rollback| {
                    state.space.unmap_output(&output);
                    format!("{error}; could not activate renderer for rollback: {rollback:?}")
                })?;
            let old_elements = self.render_elements_for_output(
                &mut gpu_renderer,
                state,
                Some((crtc, &old_output)),
            )?;
            self.outputs[index]
                .drm_output
                .use_mode(old_drm_mode, &mut gpu_renderer, &old_elements)
                .map_err(|rollback| {
                    state.space.unmap_output(&output);
                    format!("{error}; previous output rollback failed: {rollback:?}")
                })?;
            state.space.unmap_output(&output);
            return Err(error);
        }

        state
            .display_handle
            .disable_global::<PantheonCompositor>(self.outputs[index].global_id.clone());
        self.pending_global_removals
            .push((self.outputs[index].global_id.clone(), Instant::now()));
        state.space.unmap_output(&old_output);
        state.forget_output_during_lock(old_name);
        state.track_output_for_lock(&output);
        let global_id = output.create_global::<PantheonCompositor>(&state.display_handle);
        self.outputs[index].connector = connector_info.handle();
        self.outputs[index].modes = available_modes;
        self.outputs[index].output = output;
        self.outputs[index].global_id = global_id;
        self.outputs[index].frame_pending = false;
        self.disabled_connectors.insert(old_connector);
        self.disabled_connectors.remove(&connector_info.handle());
        Ok(())
    }

    pub fn set_enabled_outputs(
        &mut self,
        renderer: &mut NativeRenderer,
        state: &mut PantheonCompositor,
        enabled: &HashSet<String>,
        requested_mode_ids: &HashMap<String, String>,
    ) -> Result<(), String> {
        if enabled.is_empty() {
            return Err("at least one output must remain enabled".into());
        }
        let resources = self
            .manager
            .device_mut()
            .resource_handles()
            .map_err(|error| error.to_string())?;
        let mut name_to_connector = HashMap::new();
        for handle in resources.connectors() {
            let info = self
                .manager
                .device_mut()
                .get_connector(*handle, false)
                .map_err(|error| error.to_string())?;
            if info.state() == connector::State::Connected {
                let name = format!("{}-{}", info.interface().as_str(), info.interface_id());
                name_to_connector.insert(name, info.handle());
            }
        }
        for name in enabled {
            if !name_to_connector.contains_key(name) {
                return Err(format!("monitor {name} is no longer connected"));
            }
        }
        let current = self
            .outputs
            .iter()
            .map(|output| output.output.name())
            .collect::<HashSet<_>>();
        if current.is_empty() {
            return Err("native backend has no active output to anchor the transition".into());
        }

        for (name, connector) in &name_to_connector {
            if !enabled.contains(name) && !current.contains(name) {
                self.disabled_connectors.insert(*connector);
            }
        }

        for name in enabled {
            let connector = name_to_connector
                .get(name)
                .ok_or_else(|| format!("monitor {name} is no longer connected"))?;
            self.disabled_connectors.remove(connector);
        }
        self.refresh_connectors(renderer, state)
            .map_err(|error| format!("could not enable requested monitor: {error}"))?;
        let active_names = self
            .outputs
            .iter()
            .map(|output| output.output.name())
            .collect::<HashSet<_>>();
        let mut missing = enabled
            .difference(&active_names)
            .cloned()
            .collect::<Vec<_>>();
        missing.sort();
        for target_name in missing {
            let target_handle = name_to_connector[&target_name];
            let info = self
                .manager
                .device_mut()
                .get_connector(target_handle, false)
                .map_err(|error| error.to_string())?;
            let encoder = info
                .current_encoder()
                .and_then(|handle| self.manager.device_mut().get_encoder(handle).ok())
                .or_else(|| {
                    info.encoders()
                        .iter()
                        .find_map(|handle| self.manager.device_mut().get_encoder(*handle).ok())
                })
                .ok_or_else(|| format!("monitor {target_name} has no usable encoder"))?;
            let compatible_crtcs = resources.filter_crtcs(encoder.possible_crtcs());
            let old_name = self
                .outputs
                .iter()
                .find(|output| {
                    !enabled.contains(&output.output.name())
                        && compatible_crtcs.contains(&output.crtc)
                })
                .map(|output| output.output.name())
                .ok_or_else(|| {
                    format!("no compatible active CRTC can be reassigned to {target_name}")
                })?;
            let mode = info
                .modes()
                .iter()
                .find(|mode| {
                    requested_mode_ids.get(&target_name).is_some_and(|mode_id| {
                        let mode = Mode::from(**mode);
                        format!(
                            "{}x{}@{:.3}",
                            mode.size.w,
                            mode.size.h,
                            f64::from(mode.refresh) / 1000.0
                        ) == *mode_id
                    })
                })
                .or_else(|| {
                    info.modes()
                        .iter()
                        .find(|mode| mode.mode_type().contains(ModeTypeFlags::PREFERRED))
                })
                .copied()
                .or_else(|| info.modes().first().copied())
                .ok_or_else(|| format!("monitor {target_name} has no modes"))?;
            self.reassign_crtc_connector(renderer, state, &old_name, &info, mode)?;
        }
        let mut active = self
            .outputs
            .iter()
            .map(|output| output.output.name())
            .collect::<HashSet<_>>();
        if !enabled.is_subset(&active) {
            for name in enabled.difference(&active) {
                if let Some(connector) = name_to_connector.get(name) {
                    self.disabled_connectors.insert(*connector);
                }
            }
            return Err("native backend could not activate every requested output; the prior output remains active".into());
        }
        let disabling = self
            .outputs
            .iter()
            .filter(|output| !enabled.contains(&output.output.name()))
            .map(|output| output.connector)
            .collect::<Vec<_>>();
        for connector in disabling {
            let Some(index) = self
                .outputs
                .iter()
                .position(|output| output.connector == connector)
            else {
                continue;
            };
            let output = self.outputs.remove(index);
            state
                .display_handle
                .disable_global::<PantheonCompositor>(output.global_id.clone());
            self.pending_global_removals
                .push((output.global_id.clone(), Instant::now()));
            state.space.unmap_output(&output.output);
            state.forget_output_during_lock(&output.output.name());
            self.disabled_connectors.insert(output.connector);
            tracing::info!(output = %output.output.name(), "disabled DRM output by monitor configuration");
            drop(output);
        }
        active = self
            .outputs
            .iter()
            .map(|output| output.output.name())
            .collect();
        if &active != enabled {
            return Err("native backend could not activate the requested output set".into());
        }
        Ok(())
    }

    /// Apply output modes as one transaction. Smithay coordinates the shared
    /// DRM device while retaining rendered content for every CRTC; if a mode
    /// fails, previously switched outputs are restored before returning.
    pub fn apply_modes(
        &mut self,
        renderer: &mut NativeRenderer,
        state: &PantheonCompositor,
        requested: &HashMap<String, Mode>,
    ) -> Result<(), String> {
        let mut gpu_renderer = renderer
            .gpus
            .single_renderer(&renderer.render_node)
            .map_err(|error| format!("could not activate the display renderer: {error:?}"))?;
        let mut render_elements = DrmOutputRenderElements::<
            NativeMultiRenderer<'_>,
            CursorRenderElement<NativeMultiRenderer<'_>>,
        >::new();
        for output in &self.outputs {
            let elements = if state.session_locked {
                render_lock_surface_elements(&mut gpu_renderer, state, &output.output)
            } else {
                let space_elements = smithay::desktop::space::space_render_elements(
                    &mut gpu_renderer,
                    [&state.space],
                    &output.output,
                    output.output.current_scale().fractional_scale() as f32,
                )
                .map_err(|error| format!("could not prepare current output contents: {error:?}"))?;
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
            render_elements.add_output(&output.crtc, [0.1, 0.1, 0.1, 1.0].into(), elements);
        }

        let mut changes = Vec::new();
        for output in &self.outputs {
            let Some(mode) = requested.get(&output.output.name()) else {
                return Err(format!("no requested mode for {}", output.output.name()));
            };
            let target = output
                .modes
                .iter()
                .find(|drm_mode| Mode::from(**drm_mode) == *mode)
                .copied()
                .ok_or_else(|| {
                    format!(
                        "requested mode is not supported by {}",
                        output.output.name()
                    )
                })?;
            let current = output.output.current_mode().ok_or_else(|| {
                format!("{} has no current mode to restore", output.output.name())
            })?;
            let original = output
                .modes
                .iter()
                .find(|drm_mode| Mode::from(**drm_mode) == current)
                .copied()
                .ok_or_else(|| {
                    format!(
                        "current mode is missing from {}'s DRM inventory",
                        output.output.name()
                    )
                })?;
            if target != original {
                changes.push((output.crtc, target, original));
            }
        }

        let mut applied = Vec::new();
        for (crtc, target, original) in changes {
            let result = {
                let mut manager = self.manager.lock();
                manager.use_mode(&crtc, target, &mut gpu_renderer, &render_elements)
            };
            if let Err(error) = result {
                let mut rollback_errors = Vec::new();
                for (rollback_crtc, rollback_mode) in applied.into_iter().rev() {
                    let rollback_result = {
                        let mut manager = self.manager.lock();
                        manager.use_mode(
                            &rollback_crtc,
                            rollback_mode,
                            &mut gpu_renderer,
                            &render_elements,
                        )
                    };
                    if let Err(rollback_error) = rollback_result {
                        rollback_errors.push(format!("{rollback_error:?}"));
                    }
                }
                if rollback_errors.is_empty() {
                    return Err(format!("DRM rejected a requested display mode: {error:?}"));
                }
                return Err(format!(
                    "DRM rejected a display mode ({error:?}) and rollback also failed: {}",
                    rollback_errors.join("; ")
                ));
            }
            applied.push((crtc, original));
        }
        Ok(())
    }

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
        state.update_fractional_scale_preferences();
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
                    output.output.current_scale().fractional_scale() as f32,
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
        // Keep the user's current layout for outputs that remain connected.
        // Repacking every connector from x=0 here would silently erase a
        // configured vertical or offset arrangement on any hotplug.
        let existing_locations = self
            .outputs
            .iter()
            .filter_map(|output| {
                state
                    .space
                    .output_geometry(&output.output)
                    .map(|geometry| (output.output.name(), geometry.loc))
            })
            .collect::<HashMap<_, _>>();
        let disconnected = self
            .outputs
            .iter()
            .filter(|output| !connected_handles.contains(&output.connector))
            .map(|output| output.connector)
            .collect::<Vec<_>>();
        for connector in self.disabled_connectors.iter().copied() {
            if !connected_handles.contains(&connector)
                && let Ok(info) = self.manager.device_mut().get_connector(connector, false)
            {
                let name = format!("{}-{}", info.interface().as_str(), info.interface_id());
                state.display_config.remove(name);
                self.disconnected_disabled_connectors.insert(connector);
            }
        }
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
            if self.disabled_connectors.contains(&info.handle()) {
                if self.disconnected_disabled_connectors.remove(&info.handle())
                    && let Some(mode) = info
                        .modes()
                        .iter()
                        .find(|mode| mode.mode_type().contains(ModeTypeFlags::PREFERRED))
                        .copied()
                        .or_else(|| info.modes().first().copied())
                {
                    let mode = Mode::from(mode);
                    let name = format!("{}-{}", info.interface().as_str(), info.interface_id());
                    state.display_config.update(OutputSnapshot {
                        connector: name.clone(),
                        vendor: "Apple".into(),
                        product: name,
                        serial: "Unknown".into(),
                        width: mode.size.w,
                        height: mode.size.h,
                        refresh_millihz: mode.refresh,
                        modes: output_mode_snapshots(info.modes()),
                        scale: 1.0,
                        transform: 0,
                        x: 0,
                        y: 0,
                        primary: false,
                        enabled: false,
                    });
                }
                continue;
            }
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
            let available_modes = info.modes().to_vec();
            let preferred_mode = available_modes
                .iter()
                .find(|candidate| candidate.mode_type().contains(ModeTypeFlags::PREFERRED))
                .copied()
                .map(Mode::from)
                .unwrap_or(mode);
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
            output.set_preferred(preferred_mode);
            for available_mode in &available_modes {
                output.add_mode(Mode::from(*available_mode));
            }
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
                modes: available_modes,
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
            let primary_output_name = state
                .primary_output_name
                .as_ref()
                .filter(|name| {
                    self.outputs
                        .iter()
                        .any(|output| &output.output.name() == *name)
                })
                .cloned()
                .or_else(|| {
                    self.outputs
                        .iter()
                        .find(|output| output.output.name().starts_with("eDP-"))
                        .map(|output| output.output.name())
                })
                .or_else(|| self.outputs.first().map(|output| output.output.name()));
            state.primary_output_name = primary_output_name.clone();
            let mut next_x = state
                .space
                .outputs()
                .filter_map(|output| state.space.output_geometry(output))
                .map(|geometry| geometry.loc.x + geometry.size.w)
                .max()
                .unwrap_or(0);
            for output in &self.outputs {
                let name = output.output.name();
                let location = existing_locations.get(&name).copied().unwrap_or_else(|| {
                    let location = (next_x, 0).into();
                    if let Some(mode) = output.output.current_mode() {
                        let scale = output.output.current_scale().fractional_scale() as f64;
                        next_x += (mode.size.w as f64 / scale).round() as i32;
                    }
                    location
                });
                output
                    .output
                    .change_current_state(None, None, None, Some(location));
                state.space.map_output(&output.output, location);
                state.track_output_for_lock(&output.output);
                if let Some(mode) = output.output.current_mode() {
                    let scale = output.output.current_scale().fractional_scale() as f64;
                    let scale = if scale.is_finite() && scale > 0.0 {
                        scale
                    } else {
                        1.0
                    };
                    state.display_config.update(OutputSnapshot {
                        connector: name.clone(),
                        vendor: "Apple".into(),
                        product: name,
                        serial: "Unknown".into(),
                        width: mode.size.w,
                        height: mode.size.h,
                        refresh_millihz: mode.refresh,
                        modes: output_mode_snapshots(&output.modes),
                        scale,
                        transform: 0,
                        x: location.x,
                        y: location.y,
                        primary: primary_output_name.as_deref()
                            == Some(output.output.name().as_str()),
                        enabled: true,
                    });
                }
            }

            let output_geometries = state
                .space
                .outputs()
                .filter_map(|output| state.space.output_geometry(output))
                .collect::<Vec<_>>();
            let fallback = state
                .primary_output()
                .and_then(|output| state.space.output_geometry(&output))
                .or_else(|| output_geometries.first().copied());
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

            state.last_work_areas.clear();
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
        let saved_configurations = load_saved_monitor_configurations();

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
        let mut disabled_connectors = HashSet::new();
        let mut claimed_crtcs = HashSet::new();
        for connector in discovered {
            let name = format!(
                "{}-{}",
                connector.interface().as_str(),
                connector.interface_id()
            );
            if let Some(saved) = saved_configurations
                .get(&name)
                .filter(|configuration| !configuration.enabled)
            {
                let preferred = connector
                    .modes()
                    .iter()
                    .find(|mode| mode.mode_type().contains(ModeTypeFlags::PREFERRED))
                    .copied()
                    .unwrap_or(connector.modes()[0]);
                let selected = connector
                    .modes()
                    .iter()
                    .find(|mode| {
                        let mode = Mode::from(**mode);
                        format!(
                            "{}x{}@{:.3}",
                            mode.size.w,
                            mode.size.h,
                            f64::from(mode.refresh) / 1000.0
                        ) == saved.mode
                    })
                    .copied()
                    .unwrap_or(preferred);
                let mode = Mode::from(selected);
                state.display_config.update(OutputSnapshot {
                    connector: name.clone(),
                    vendor: "Apple".into(),
                    product: name,
                    serial: "Unknown".into(),
                    width: mode.size.w,
                    height: mode.size.h,
                    refresh_millihz: mode.refresh,
                    modes: output_mode_snapshots(connector.modes()),
                    scale: saved.scale,
                    transform: saved.transform,
                    x: saved.x,
                    y: saved.y,
                    primary: false,
                    enabled: false,
                });
                disabled_connectors.insert(connector.handle());
                continue;
            }
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
            let preferred_mode = connector
                .modes()
                .iter()
                .find(|mode| mode.mode_type().contains(ModeTypeFlags::PREFERRED))
                .copied()
                .unwrap_or(connector.modes()[0]);
            let mode = saved_configurations
                .get(&name)
                .and_then(|saved| {
                    connector.modes().iter().find(|mode| {
                        let mode = Mode::from(**mode);
                        format!(
                            "{}x{}@{:.3}",
                            mode.size.w,
                            mode.size.h,
                            f64::from(mode.refresh) / 1000.0
                        ) == saved.mode
                    })
                })
                .copied()
                .unwrap_or(preferred_mode);
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
        let mut next_x = 0;
        for selected in connected {
            let mode = Mode::from(selected.mode);
            let available_modes = selected.connector.modes().to_vec();
            let mode_snapshots = output_mode_snapshots(&available_modes);
            let name = format!(
                "{}-{}",
                selected.connector.interface().as_str(),
                selected.connector.interface_id()
            );
            let saved = saved_configurations.get(&name);
            let x = saved.map_or(next_x, |saved| saved.x);
            let y = saved.map_or(0, |saved| saved.y);
            let scale = saved.map_or(1.0, |saved| saved.scale);
            let primary = saved.map_or(outputs.is_empty(), |saved| saved.primary);
            let transform = match saved.map_or(0, |saved| saved.transform) {
                1 => smithay::utils::Transform::_90,
                2 => smithay::utils::Transform::_180,
                3 => smithay::utils::Transform::_270,
                4 => smithay::utils::Transform::Flipped,
                5 => smithay::utils::Transform::Flipped90,
                6 => smithay::utils::Transform::Flipped180,
                7 => smithay::utils::Transform::Flipped270,
                _ => smithay::utils::Transform::Normal,
            };
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
            let preferred_mode = available_modes
                .iter()
                .find(|candidate| candidate.mode_type().contains(ModeTypeFlags::PREFERRED))
                .copied()
                .map(Mode::from)
                .unwrap_or(mode);
            output.set_preferred(preferred_mode);
            for available_mode in &available_modes {
                output.add_mode(Mode::from(*available_mode));
            }
            output.change_current_state(
                Some(mode),
                Some(transform),
                Some(smithay::output::Scale::Fractional(scale)),
                Some((x, y).into()),
            );

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
            state.space.map_output(&output, (x, y));
            if primary {
                state.primary_output_name = Some(name.clone());
            }
            state.display_config.update(OutputSnapshot {
                connector: name.clone(),
                vendor: "Apple".into(),
                product: name,
                serial: "Unknown".into(),
                width: mode.size.w,
                height: mode.size.h,
                refresh_millihz: mode.refresh,
                modes: mode_snapshots,
                scale,
                transform: transform_to_dbus(transform),
                x,
                y,
                primary,
                enabled: true,
            });
            next_x = next_x.max(x + (mode.size.w as f64 / scale).round() as i32);
            outputs.push(NativeKmsOutput {
                connector: selected.connector.handle(),
                crtc: selected.crtc,
                modes: available_modes,
                output,
                drm_output,
                global_id,
                frame_pending: false,
            });
        }
        if outputs.is_empty() {
            return Err("could not initialize any connected KMS output".into());
        }
        if state.primary_output_name.is_none() {
            state.primary_output_name = outputs.first().map(|output| output.output.name());
        }

        Ok(Self {
            node,
            manager,
            outputs,
            disabled_connectors,
            disconnected_disabled_connectors: HashSet::new(),
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
