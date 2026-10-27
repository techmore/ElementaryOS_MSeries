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
        input::InputEvent,
        libinput::{LibinputInputBackend, LibinputSessionInterface},
        renderer::{
            gles::GlesRenderer,
            multigpu::{GpuManager, MultiRenderer, gbm::GbmGlesBackend},
        },
        session::{
            Event as SessionEvent, Session,
            libseat::{LibSeatSession, LibSeatSessionNotifier},
        },
        udev::{UdevBackend, UdevEvent, all_gpus},
    },
    output::{Mode, Output, PhysicalProperties},
    reexports::{
        calloop::{
            EventLoop, LoopHandle, channel,
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
    cursor::{CursorRenderElement, render_desktop_elements, render_lock_surface_elements},
    display_config::{
        OutputModeSnapshot, OutputSnapshot, load_saved_monitor_configurations, transform_to_dbus,
    },
    display_trace::{self, Operation, OutputTrace},
    edid::{self, Candidate},
    flip_retry,
    hotplug::{EventKind, HotplugScheduler, event_triggers_reconcile},
    kms_props::{connector_edid, named_property},
    link_status::{self, Action, LINK_STATUS_GOOD, ResetState},
    prewarm::{self, Gate},
};

/// Grace period before a disabled output global is removed from clients.
const GLOBAL_REMOVAL_DELAY: Duration = Duration::from_secs(2);

/// Surfaces not shown on the output that flipped (occluded, off-screen, or on
/// another monitor) still get a frame callback this often, so they keep
/// making progress without animating at the full refresh rate.
const HIDDEN_FRAME_CALLBACK_INTERVAL: Duration = Duration::from_secs(1);

pub type GbmRendererBackend = GbmGlesBackend<GlesRenderer, DrmDeviceFd>;
pub type NativeGpuManager = GpuManager<GbmRendererBackend>;
pub type NativeAllocator = GbmAllocator<DrmDeviceFd>;
pub type NativeExporter = GbmFramebufferExporter<DrmDeviceFd>;
pub type NativeOutputManager = DrmOutputManager<NativeAllocator, NativeExporter, (), DrmDeviceFd>;
pub type NativeDrmOutput = DrmOutput<NativeAllocator, NativeExporter, (), DrmDeviceFd>;
type NativeMultiRenderer<'a> = MultiRenderer<'a, 'a, GbmRendererBackend, GbmRendererBackend>;

/// The corner clip runs on the render device's GLES renderer and frame, which the multi-GPU
/// wrapper hands out; a frame copied to another GPU afterwards keeps the clipped pixels.
impl crate::corner_render::CornerRenderer for NativeMultiRenderer<'_> {
    fn corner_program(&mut self) -> Option<smithay::backend::renderer::gles::GlesTexProgram> {
        crate::corner_render::gles_corner_program(self.as_mut())
    }

    fn gles_frame<'a, 'b, 'c>(
        frame: &'c mut <Self as smithay::backend::renderer::RendererSuper>::Frame<'a, 'b>,
    ) -> &'c mut smithay::backend::renderer::gles::GlesFrame<'a, 'b>
    where
        'b: 'a,
        Self: 'a,
    {
        frame.as_mut()
    }
}
type HardwareNode = (DrmNode, GbmDevice<DrmDeviceFd>);

const OUTPUT_FORMATS: &[smithay::backend::allocator::Fourcc] = &[
    smithay::backend::allocator::Fourcc::Argb2101010,
    smithay::backend::allocator::Fourcc::Abgr8888,
    smithay::backend::allocator::Fourcc::Argb8888,
];

/// Identity published for a monitor: the Wayland `PhysicalProperties` make,
/// model and serial, and the vendor/product/serial the display-config service
/// reports (and the profile watcher matches on).
#[derive(Clone, Debug, PartialEq, Eq)]
struct OutputIdentity {
    vendor: String,
    product: String,
    serial: String,
}

impl OutputIdentity {
    /// What the backend used to publish for every monitor. Still used for the
    /// panel, which exposes no EDID, and when an EDID cannot be read or parsed.
    fn fallback(name: &str) -> Self {
        Self {
            vendor: "Apple".into(),
            product: name.into(),
            serial: "Unknown".into(),
        }
    }

    fn physical_properties(&self, connector_info: &connector::Info) -> PhysicalProperties {
        let (width, height) = connector_info.size().unwrap_or((0, 0));
        PhysicalProperties {
            size: (width as i32, height as i32).into(),
            subpixel: connector_info.subpixel().into(),
            make: self.vendor.clone(),
            model: self.product.clone(),
            serial_number: self.serial.clone(),
        }
    }
}

fn connector_identity<D: DrmControlDevice>(
    device: &D,
    connector: connector::Handle,
    name: &str,
) -> OutputIdentity {
    connector_edid(device, connector)
        .and_then(|(bytes, _)| edid::parse(&bytes))
        .map_or_else(
            || OutputIdentity::fallback(name),
            |parsed| OutputIdentity {
                vendor: parsed.vendor,
                product: parsed.product,
                serial: parsed.serial,
            },
        )
}

/// Drop stale duplicate routes and retain successfully parsed identities for
/// this scan only. Missing/malformed EDID is not cached, preserving the later
/// identity-read retry while a dock is settling. No cache crosses a reconcile.
fn remove_stale_duplicates<D: DrmControlDevice>(
    device: &D,
    connected: &mut Vec<connector::Info>,
) -> (
    Vec<connector::Handle>,
    HashMap<connector::Handle, OutputIdentity>,
) {
    let mut identities = HashMap::new();
    let candidates = connected
        .iter()
        .filter_map(|info| {
            let started = display_trace::enabled().then(Instant::now);
            let read = connector_edid(device, info.handle());
            if let Some(monotonic_us) = display_trace::stamp() {
                display_trace::lifecycle_event!(monotonic_us = monotonic_us as u64,
                    connector = ?info.handle(), stage = "edid_read", success = read.is_some(),
                    duration_us = started.map(|t| t.elapsed().as_micros() as u64).unwrap_or(0),
                    "existing duplicate-route EDID query completed");
            }
            let (edid, blob_id) = read?;
            if let Some(parsed) = edid::parse(&edid) {
                identities.insert(
                    info.handle(),
                    OutputIdentity {
                        vendor: parsed.vendor,
                        product: parsed.product,
                        serial: parsed.serial,
                    },
                );
            }
            Some(Candidate {
                key: info.handle(),
                edid,
                blob_id,
                interface_id: info.interface_id(),
            })
        })
        .collect::<Vec<_>>();
    let stale = edid::stale_duplicates(&candidates);
    connected.retain(|info| !stale.contains(&info.handle()));
    identities.retain(|handle, _| !stale.contains(handle));
    (stale, identities)
}

/// The mode an output is first brought up with: preferred, else the first.
fn preferred_drm_mode(info: &connector::Info) -> Option<smithay::reexports::drm::control::Mode> {
    info.modes()
        .iter()
        .find(|mode| mode.mode_type().contains(ModeTypeFlags::PREFERRED))
        .copied()
        .or_else(|| info.modes().first().copied())
}

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
    /// Default linux-dmabuf feedback (render node, sampling formats) and the
    /// formats it lists; `None` while linux-dmabuf is not advertised.
    dmabuf: Option<(
        smithay::wayland::dmabuf::DmabufFeedback,
        smithay::backend::allocator::format::FormatSet,
    )>,
}

pub struct NativeKmsOutput {
    pub connector: connector::Handle,
    pub crtc: smithay::reexports::drm::control::crtc::Handle,
    pub modes: Vec<smithay::reexports::drm::control::Mode>,
    pub output: Output,
    pub drm_output: NativeDrmOutput,
    pub global_id: smithay::reexports::wayland_server::backend::GlobalId,
    pub frame_pending: bool,
    trace: Option<OutputTrace>,
    /// Frame timing for the 30 s metrics window.
    stats: crate::metrics::output::OutputStats,
    /// linux-dmabuf feedback with this output's scanout tranche, sent only to
    /// surfaces presented zero-copy on one of its planes (built on first use).
    scanout_feedback: Option<smithay::wayland::dmabuf::DmabufFeedback>,
    /// The last render pass produced no damage, so no vblank will come to send
    /// frame callbacks; an estimated-vblank timer has to.
    needs_estimated_frame: bool,
    estimated_frame_armed: bool,
}

pub struct NativeKmsDevice {
    pub node: DrmNode,
    pub manager: NativeOutputManager,
    pub outputs: Vec<NativeKmsOutput>,
    disabled_connectors: HashSet<connector::Handle>,
    disconnected_disabled_connectors: HashSet<connector::Handle>,
    /// Connectors currently hidden because another connector carries the same
    /// monitor; used to log a change once instead of on every poll.
    suppressed_duplicates: HashSet<connector::Handle>,
    /// Per-connector memory for answering `link-status = Bad`.
    link_resets: HashMap<connector::Handle, Option<ResetState>>,
    trace_connectors: HashMap<connector::Handle, (connector::State, usize)>,
    trace_link_status: HashMap<connector::Handle, u64>,
    /// Early modesets on helper threads (`PANTHEON_PREWARM_MODESET=1`).
    prewarm: prewarm::Slots<connector::Handle, prewarm::Warmed>,
    /// CRTC each running or finished prewarm programmed.
    prewarm_crtcs: HashMap<connector::Handle, smithay::reexports::drm::control::crtc::Handle>,
    prewarm_sender: Option<channel::Sender<PrewarmDone>>,
    /// An output's page flip was refused with EBUSY in the last render pass.
    busy_retry: bool,
    /// Consecutive render passes that ended with a busy flip.
    busy_passes: u32,
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
    hotplug: HotplugScheduler,
    trace_pending_event: Option<(Instant, u32)>,
}

/// Result of one prewarm helper thread, delivered to the compositor loop.
pub struct PrewarmDone {
    connector: connector::Handle,
    result: Result<prewarm::Warmed, String>,
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
                render_desktop_elements(gpu_renderer, state, render_output)
                    .map_err(|error| format!("could not prepare output frame: {error:?}"))?
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
        let trace = Operation::begin("reassign_crtc_connector");
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
        let identity =
            connector_identity(self.manager.device_mut(), connector_info.handle(), &name);
        let output = Output::new(name.clone(), identity.physical_properties(connector_info));
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
        self.outputs[index].trace = trace.output();
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
        let trace = Operation::begin("set_enabled_outputs");
        if let Some(monotonic_us) = display_trace::stamp() {
            tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                generation = trace.generation, requested_count = enabled.len(), active_count = self.outputs.len(), requested_outputs = ?enabled,
                stage = "enable_disable_request", "requested output set");
        }
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
            if let Some(monotonic_us) = display_trace::stamp() {
                tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                    generation = trace.generation, output = %output.output.name(), stage = "disabled",
                    "output unmapped by explicit configuration");
            }
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
        let trace = Operation::begin("apply_modes");
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
                render_desktop_elements(&mut gpu_renderer, state, &output.output)
                    .map_err(|error| format!("could not prepare output contents: {error:?}"))?
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
            let started = display_trace::enabled().then(Instant::now);
            let result = {
                let mut manager = self.manager.lock();
                manager.use_mode(&crtc, target, &mut gpu_renderer, &render_elements)
            };
            if let Some(monotonic_us) = display_trace::stamp() {
                let mode = Mode::from(target);
                tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                    generation = trace.generation, ?crtc, stage = "use_mode", success = result.is_ok(),
                    width = mode.size.w, height = mode.size.h, refresh_millihz = mode.refresh,
                    duration_us = started.map(|t| t.elapsed().as_micros() as u64).unwrap_or(0),
                    "requested KMS mode commit returned");
            }
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
            if let Some(output) = self.outputs.iter_mut().find(|o| o.crtc == crtc) {
                output.trace = trace.output();
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
        crate::metrics::render_pass();
        if state.displays_off {
            return Ok(0);
        }
        if state.screenshot_requested.get() {
            let outputs = self
                .outputs
                .iter()
                .map(|output| output.output.clone())
                .collect::<Vec<_>>();
            let mut capture_renderer = renderer.gpus.single_renderer(&renderer.render_node)?;
            crate::screenshot_pixels::process_request(&mut capture_renderer, state, &outputs);
        }
        let dirty_at = state.dirty_since.get();
        let mut skipped_pending = false;
        let mut rendered = 0;
        let mut busy = false;
        for output in &mut self.outputs {
            if output.frame_pending {
                skipped_pending = true;
                continue;
            }
            let started = Instant::now();
            let mut gpu_renderer = renderer.gpus.single_renderer(&renderer.render_node)?;
            let elements = if state.session_locked {
                render_lock_surface_elements(&mut gpu_renderer, state, &output.output)
            } else {
                render_desktop_elements(&mut gpu_renderer, state, &output.output)?
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
            // Remember which output each surface is mostly shown on, so the
            // vblank only sends frame callbacks to surfaces on that output.
            update_primary_scanout_outputs(state, &output.output, &frame.states);
            if let Some((default_feedback, render_formats)) = &renderer.dmabuf {
                let scanout_feedback = output.scanout_feedback.get_or_insert_with(|| {
                    scanout_feedback(
                        &output.drm_output,
                        renderer.render_node,
                        self.node,
                        render_formats,
                    )
                    .unwrap_or_else(|| default_feedback.clone())
                });
                send_dmabuf_feedback(
                    state,
                    &output.output,
                    &frame.states,
                    default_feedback,
                    scanout_feedback,
                );
            }
            if frame.is_empty {
                output.stats.record_empty();
                output.needs_estimated_frame = true;
                continue;
            }
            match output.drm_output.queue_frame(()) {
                Ok(()) => {}
                Err(error) if flip_retry::is_busy(&error) => {
                    // The previous commit on this CRTC (the link-status retrain
                    // after mapping) has not finished. The damage tracker has
                    // already taken this frame, so redraw everything next pass.
                    output.drm_output.reset_buffers();
                    busy = true;
                    tracing::debug!(output = %output.output.name(), "page flip busy; retrying");
                    continue;
                }
                Err(error) => return Err(error.into()),
            }
            if let Some(trace) = &mut output.trace {
                trace.queued(&output.output.name());
            }
            output.stats.record_queued(
                state.monotonic_clock.now().into(),
                started.elapsed(),
                dirty_at,
            );
            output.frame_pending = true;
            output.needs_estimated_frame = false;
            rendered += 1;
        }
        // Content that was waiting on a busy output will be drawn next pass.
        if !skipped_pending && !busy {
            state.dirty_since.set(None);
        }
        self.busy_retry = busy;
        if busy {
            self.busy_passes += 1;
            if self.busy_passes > flip_retry::MAX_BUSY_PASSES {
                self.busy_passes = 0;
                return Err("page flip stayed busy for about a second".into());
            }
        } else {
            self.busy_passes = 0;
        }
        Ok(rendered)
    }

    /// Blank every output for power save: disable its CRTC and planes. No
    /// flip stays pending, so the watchdog sees nothing stuck.
    pub fn power_off(&mut self) {
        for output in &mut self.outputs {
            if let Err(error) = output
                .drm_output
                .with_compositor(|compositor| compositor.clear())
            {
                tracing::warn!(output = %output.output.name(), ?error, "could not blank output");
            }
            output.frame_pending = false;
            output.needs_estimated_frame = false;
        }
    }

    /// Leave power save. The cleared CRTC state differs from the pending one,
    /// so the next queued frame performs the modeset that turns it back on;
    /// reset the buffers so that frame is drawn in full.
    pub fn power_on(&mut self) {
        for output in &mut self.outputs {
            output.drm_output.reset_buffers();
        }
    }

    /// Whether the last render pass left an output waiting on a busy CRTC;
    /// reading it clears the flag.
    pub fn take_busy_retry(&mut self) -> bool {
        std::mem::take(&mut self.busy_retry)
    }

    pub fn frame_submitted(
        &mut self,
        crtc: smithay::reexports::drm::control::crtc::Handle,
        flip: Duration,
        sequence: Option<u32>,
    ) -> Result<Option<Output>, Box<dyn std::error::Error>> {
        let Some(output) = self.outputs.iter_mut().find(|output| output.crtc == crtc) else {
            return Ok(None);
        };
        output.drm_output.frame_submitted()?;
        if let Some(trace) = &mut output.trace {
            trace.submitted(&output.output.name());
        }
        let refresh = output
            .output
            .current_mode()
            .and_then(|mode| crate::metrics::output::refresh_period(mode.refresh));
        output.stats.record_flip(flip, sequence, refresh);
        output.frame_pending = false;
        Ok(Some(output.output.clone()))
    }

    /// Outputs whose queued flip has been pending for at least `threshold`.
    pub fn stuck_flips(&self, now: Duration, threshold: Duration) -> Vec<(String, Duration)> {
        self.outputs
            .iter()
            .filter(|output| output.frame_pending)
            .filter_map(|output| {
                let age = output.stats.in_flight_age(now)?;
                (age >= threshold).then(|| (output.output.name(), age))
            })
            .collect()
    }

    /// Take every output's frame stats for the metrics window.
    pub fn take_metrics(&mut self) -> Vec<(String, crate::metrics::output::OutputWindow)> {
        self.outputs
            .iter_mut()
            .filter_map(|output| {
                output
                    .stats
                    .take_window()
                    .map(|window| (output.output.name(), window))
            })
            .collect()
    }

    /// Outputs whose last pass was empty and have no estimated-vblank timer
    /// yet: mark them armed and return when each one's next vblank is due.
    fn arm_estimated_frames(
        &mut self,
        now: Duration,
    ) -> Vec<(smithay::reexports::drm::control::crtc::Handle, Duration)> {
        let mut due = Vec::new();
        for output in &mut self.outputs {
            if !output.needs_estimated_frame || output.estimated_frame_armed || output.frame_pending
            {
                continue;
            }
            let Some(refresh) = output
                .output
                .current_mode()
                .and_then(|mode| crate::metrics::output::refresh_period(mode.refresh))
            else {
                continue;
            };
            let at = crate::metrics::output::next_vblank_estimate(
                now,
                output.stats.last_flip_time(),
                refresh,
            );
            output.estimated_frame_armed = true;
            due.push((output.crtc, at.saturating_sub(now)));
        }
        due
    }

    /// The estimated vblank for an empty frame arrived: returns the output to
    /// send frame callbacks for, unless a real frame took over meanwhile.
    fn estimated_frame_due(
        &mut self,
        crtc: smithay::reexports::drm::control::crtc::Handle,
    ) -> Option<Output> {
        let output = self.outputs.iter_mut().find(|output| output.crtc == crtc)?;
        output.estimated_frame_armed = false;
        if !std::mem::take(&mut output.needs_estimated_frame) || output.frame_pending {
            return None;
        }
        output.stats.empty_frame_callbacks += 1;
        Some(output.output.clone())
    }

    /// Release the placeholder framebuffer left by a finished prewarm. Call
    /// only after the compositor's own commit replaced it on the plane.
    fn release_prewarm(&mut self, connector: connector::Handle) {
        self.prewarm_crtcs.remove(&connector);
        if let Some(warmed) = self.prewarm.take_warmed(connector) {
            prewarm::release(self.manager.device(), warmed);
        }
    }

    /// Plan an early modeset for a connector the reconcile is about to map:
    /// same encoder, CRTC and mode choice, plus the CRTC's primary plane.
    fn plan_prewarm(
        &self,
        resources: &smithay::reexports::drm::control::ResourceHandles,
        info: &connector::Info,
        claimed: &HashSet<smithay::reexports::drm::control::crtc::Handle>,
    ) -> Option<prewarm::Plan> {
        let device = self.manager.device();
        let encoder = info
            .current_encoder()
            .and_then(|handle| device.get_encoder(handle).ok())
            .or_else(|| {
                info.encoders()
                    .iter()
                    .find_map(|handle| device.get_encoder(*handle).ok())
            })?;
        let crtc = resources
            .filter_crtcs(encoder.possible_crtcs())
            .into_iter()
            .find(|crtc| !claimed.contains(crtc) && !self.crtc_reserved_by_other(*crtc, info))?;
        let mode = preferred_drm_mode(info)?;
        let (plane, format) = prewarm::primary_plane(device, resources, crtc)?;
        Some(prewarm::Plan {
            crtc,
            plane,
            mode,
            format,
        })
    }

    fn crtc_reserved_by_other(
        &self,
        crtc: smithay::reexports::drm::control::crtc::Handle,
        info: &connector::Info,
    ) -> bool {
        self.prewarm_crtcs
            .iter()
            .any(|(connector, reserved)| *connector != info.handle() && *reserved == crtc)
    }

    fn spawn_prewarm(&mut self, connector: connector::Handle, plan: prewarm::Plan) {
        let Some(sender) = self.prewarm_sender.clone() else {
            return;
        };
        // A duplicate of the DRM master fd: same file description, so the
        // helper thread may commit without owning the output manager.
        let fd = self.manager.device().device_fd().clone();
        self.prewarm.started(connector, Instant::now());
        self.prewarm_crtcs.insert(connector, plan.crtc);
        let spawned = std::thread::Builder::new()
            .name("drm-prewarm".into())
            .spawn(move || {
                let result = prewarm::run(&fd, connector, &plan, true)
                    .and_then(|warmed| warmed.ok_or_else(|| "no modeset committed".to_owned()));
                let _ = sender.send(PrewarmDone { connector, result });
            });
        if let Err(error) = spawned {
            tracing::warn!(%error, "could not start the DRM prewarm thread");
            self.prewarm.finished(connector, Err(()));
            self.prewarm_crtcs.remove(&connector);
        }
    }

    /// Start early modesets for newly connected external connectors. Called
    /// from the udev event, before the debounce even elapses.
    pub fn prewarm_new_outputs(&mut self) {
        if self.prewarm_sender.is_none() {
            return;
        }
        let Ok(resources) = self.manager.device_mut().resource_handles() else {
            return;
        };
        let mut connected = Vec::new();
        for handle in resources.connectors() {
            if let Ok(info) = self.manager.device_mut().get_connector(*handle, false)
                && info.state() == connector::State::Connected
            {
                connected.push(info);
            }
        }
        remove_stale_duplicates(self.manager.device_mut(), &mut connected);
        connected.retain(|info| {
            !info.modes().is_empty()
                && info.interface() != connector::Interface::EmbeddedDisplayPort
                && !self.disabled_connectors.contains(&info.handle())
                && !self
                    .outputs
                    .iter()
                    .any(|output| output.connector == info.handle())
        });
        connected.sort_by_key(|info| info.interface_id());
        let claimed = self
            .outputs
            .iter()
            .map(|output| output.crtc)
            .collect::<HashSet<_>>();
        let now = Instant::now();
        for info in connected {
            if self.prewarm.gate(info.handle(), now) != Gate::Plan {
                continue;
            }
            if let Some(plan) = self.plan_prewarm(&resources, &info, &claimed) {
                tracing::info!(connector = ?info.handle(), "prewarming modeset on a helper thread");
                self.spawn_prewarm(info.handle(), plan);
            }
        }
    }

    /// Answer `link-status = Bad` on mapped connectors by writing `Good` back.
    ///
    /// The DCP driver marks a link Bad when its pipeline lost the mode and
    /// relies on userspace to trigger a modeset; plane-only flips never do.
    /// Writing `Good` is a full modeset through the atomic core. Bounded by
    /// `link_status::decide` so a sink that never trains cannot cause a loop.
    /// Returns true when any connector was reset.
    fn reset_bad_link_status(&mut self, generation: u64) -> bool {
        let now = Instant::now();
        let mapped = self
            .outputs
            .iter()
            .map(|output| (output.connector, output.output.name()))
            .collect::<Vec<_>>();
        self.link_resets
            .retain(|handle, _| mapped.iter().any(|(mapped, _)| mapped == handle));
        self.trace_link_status
            .retain(|handle, _| mapped.iter().any(|(mapped, _)| mapped == handle));
        let mut reset_any = false;
        for (handle, name) in mapped {
            let device = self.manager.device_mut();
            let Some((property, value)) = named_property(device, handle, "link-status") else {
                continue;
            };
            if display_trace::enabled() && self.trace_link_status.get(&handle) != Some(&value) {
                self.trace_link_status.insert(handle, value);
                if let Some(monotonic_us) = display_trace::stamp() {
                    tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                        generation, output = %name, stage = "link_status", raw_link_status = value,
                        "existing link-status read changed");
                }
            }
            let memory = self.link_resets.entry(handle).or_default();
            if link_status::decide(memory, value, now) != Action::Reset {
                continue;
            }
            let attempt = memory.as_ref().map(ResetState::attempts).unwrap_or(0);
            let started = display_trace::enabled().then(Instant::now);
            let result = device.set_property(handle, property, LINK_STATUS_GOOD);
            if let Some(monotonic_us) = display_trace::stamp() {
                tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                    generation, output = %name, stage = "link_reset", attempt, success = result.is_ok(),
                    duration_us = started.map(|t| t.elapsed().as_micros() as u64).unwrap_or(0),
                    "bounded existing Bad-to-Good link reset attempt");
            }
            match result {
                Ok(()) => {
                    tracing::info!(output = %name, "link-status was Bad; reset to Good to retrain the link");
                    reset_any = true;
                    if let Some(output) = self.outputs.iter_mut().find(|o| o.connector == handle) {
                        output.trace = OutputTrace::new(generation);
                    }
                }
                Err(error) => {
                    tracing::warn!(output = %name, %error, "could not reset link-status to Good");
                }
            }
        }
        reset_any
    }

    /// Reconcile connected DRM connectors with the outputs published to the
    /// Wayland space. Smithay's DRM notifier reports page flips and failures
    /// only; connector changes arrive via the udev monitor (see
    /// `crate::hotplug`) with a slow safety poll as backstop.
    fn refresh_connectors(
        &mut self,
        renderer: &mut NativeRenderer,
        state: &mut PantheonCompositor,
    ) -> Result<bool, Box<dyn std::error::Error>> {
        let trace = Operation::begin("refresh_connectors");
        let resources = self.manager.device_mut().resource_handles()?;
        let mut all_connected = Vec::new();
        for handle in resources.connectors() {
            let info = self.manager.device_mut().get_connector(*handle, false)?;
            if display_trace::enabled() {
                let snapshot = (info.state(), info.modes().len());
                if self.trace_connectors.get(handle) != Some(&snapshot) {
                    self.trace_connectors.insert(*handle, snapshot);
                    if let Some(monotonic_us) = display_trace::stamp() {
                        tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                            generation = trace.generation, connector = ?handle,
                            state = ?info.state(), mode_count = info.modes().len(),
                            stage = "connector_transition", "connector state or mode count changed");
                    }
                }
            }
            if info.state() == connector::State::Connected {
                all_connected.push(info);
            }
        }
        if display_trace::enabled() {
            self.trace_connectors.retain(|handle, _| {
                let present = resources.connectors().contains(handle);
                if !present && let Some(monotonic_us) = display_trace::stamp() {
                    tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                        generation = trace.generation, connector = ?handle, stage = "connector_removed",
                        "connector absent from DRM resources");
                }
                present
            });
        }
        // After a dock moves to another Type-C PHY the driver can keep the old
        // DisplayPort connector reported as connected. Treat the stale copy as
        // disconnected so no phantom output is mapped between the real screens.
        let (stale, mut identities) =
            remove_stale_duplicates(self.manager.device_mut(), &mut all_connected);
        for handle in &stale {
            if self.suppressed_duplicates.insert(*handle) {
                tracing::warn!(
                    connector = ?handle,
                    "ignoring connector that duplicates another connected monitor's EDID (stale dock route)"
                );
            }
        }
        self.suppressed_duplicates
            .retain(|handle| stale.contains(handle));
        let mut connected = Vec::new();
        let mut connected_handles = HashSet::new();
        for info in all_connected {
            connected_handles.insert(info.handle());
            if !info.modes().is_empty() {
                connected.push(info);
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
        for warmed in self
            .prewarm
            .retain(|handle| connected_handles.contains(handle))
        {
            prewarm::release(self.manager.device(), warmed);
        }
        self.prewarm_crtcs
            .retain(|handle, _| connected_handles.contains(handle));
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
                if let Some(monotonic_us) = display_trace::stamp() {
                    tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                        generation = trace.generation, output = %output.output.name(), stage = "disconnected",
                        "output global disabled and output unmapped");
                }
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
                    let identity = identities.remove(&info.handle()).unwrap_or_else(|| {
                        connector_identity(self.manager.device_mut(), info.handle(), &name)
                    });
                    state.display_config.update(OutputSnapshot {
                        connector: name,
                        vendor: identity.vendor,
                        product: identity.product,
                        serial: identity.serial,
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

            // With the prewarm flag on, the DCP modeset runs on a helper thread
            // and this connector is mapped on the reconcile its completion
            // triggers; any failure falls through to the inline path below.
            if self.prewarm_sender.is_some()
                && info.interface() != connector::Interface::EmbeddedDisplayPort
            {
                match self.prewarm.gate(info.handle(), Instant::now()) {
                    Gate::Wait => continue,
                    Gate::Plan => {
                        if let Some(plan) = self.plan_prewarm(&resources, &info, &claimed_crtcs) {
                            self.spawn_prewarm(info.handle(), plan);
                            continue;
                        }
                    }
                    Gate::Ready | Gate::Inline => {}
                }
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
            let warmed_crtc = self
                .prewarm_crtcs
                .get(&info.handle())
                .copied()
                .filter(|crtc| {
                    !claimed_crtcs.contains(crtc) && self.prewarm.warmed(info.handle()).is_some()
                });
            let Some(crtc) = warmed_crtc.or_else(|| {
                resources
                    .filter_crtcs(encoder.possible_crtcs())
                    .into_iter()
                    .find(|crtc| {
                        !claimed_crtcs.contains(crtc) && !self.crtc_reserved_by_other(*crtc, &info)
                    })
            }) else {
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
            let identity = identities.remove(&info.handle()).unwrap_or_else(|| {
                connector_identity(self.manager.device_mut(), info.handle(), &name)
            });
            let output = Output::new(name.clone(), identity.physical_properties(&info));
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
            let output_trace = trace.output();
            let initialize_started = display_trace::enabled().then(Instant::now);
            let initialized = self.manager.lock().initialize_output(
                crtc,
                drm_mode,
                &[info.handle()],
                &output,
                None,
                &mut gpu_renderer,
                &render_elements,
            );
            let drm_output = match initialized {
                Ok(output) => output,
                Err(error) => {
                    tracing::warn!(%name, ?error, "could not initialize newly connected KMS output");
                    self.release_prewarm(info.handle());
                    continue;
                }
            };
            self.release_prewarm(info.handle());

            if let Some(monotonic_us) = display_trace::stamp() {
                tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                    generation = trace.generation, output = %name, stage = "kms_initialized",
                    width = mode.size.w, height = mode.size.h, refresh_millihz = mode.refresh,
                    duration_us = initialize_started.map(|t| t.elapsed().as_micros() as u64).unwrap_or(0),
                    "new output KMS initialization completed");
            }
            let global_id = output.create_global::<PantheonCompositor>(&state.display_handle);
            self.outputs.push(NativeKmsOutput {
                connector: info.handle(),
                crtc,
                modes: available_modes,
                output,
                drm_output,
                global_id,
                frame_pending: false,
                trace: output_trace,
                stats: Default::default(),
                scanout_feedback: None,
                needs_estimated_frame: false,
                estimated_frame_armed: false,
            });
            claimed_crtcs.insert(crtc);
            changed = true;
            tracing::info!(%name, ?mode, "mapped newly connected DRM output");
        }

        if self.reset_bad_link_status(trace.generation) {
            state.request_native_redraw();
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
                        let scale = output.output.current_scale().fractional_scale();
                        next_x += (mode.size.w as f64 / scale).round() as i32;
                    }
                    location
                });
                output
                    .output
                    .change_current_state(None, None, None, Some(location));
                state.space.map_output(&output.output, location);
                if let Some(monotonic_us) = display_trace::stamp() {
                    tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                        generation = trace.generation, output = %name, stage = "space_mapped",
                        x = location.x, y = location.y, "output published to compositor space");
                }
                state.track_output_for_lock(&output.output);
                if let Some(mode) = output.output.current_mode() {
                    let scale = output.output.current_scale().fractional_scale();
                    let scale = if scale.is_finite() && scale > 0.0 {
                        scale
                    } else {
                        1.0
                    };
                    let physical = output.output.physical_properties();
                    state.display_config.update(OutputSnapshot {
                        connector: name,
                        vendor: physical.make,
                        product: physical.model,
                        serial: physical.serial_number,
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
                if now.duration_since(*disabled_at) >= GLOBAL_REMOVAL_DELAY {
                    state
                        .display_handle
                        .remove_global::<PantheonCompositor>(global.clone());
                    if let Some(monotonic_us) = display_trace::stamp() {
                        tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                            generation = trace.generation, stage = "global_retired",
                            disabled_for_us = now.duration_since(*disabled_at).as_micros() as u64,
                            "disabled output global removed after existing grace period");
                    }
                    false
                } else {
                    true
                }
            });

        if let Some(monotonic_us) = display_trace::stamp() {
            // A change is always worth INFO, even on a routine safety poll,
            // and so is the rest of this operation's trace.
            if changed {
                display_trace::end_quiet();
            }
            if !display_trace::quiet() {
                tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                    generation = trace.generation, stage = "reconcile_result", changed,
                    active_count = self.outputs.len(), retired_globals = self.pending_global_removals.len(),
                    "connector reconciliation completed");
            } else {
                tracing::debug!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                    generation = trace.generation, stage = "reconcile_result", changed,
                    active_count = self.outputs.len(), retired_globals = self.pending_global_removals.len(),
                    "connector reconciliation completed");
            }
        }
        Ok(changed)
    }

    /// Earliest pending Wayland global removal, if any.
    fn next_global_removal_deadline(&self) -> Option<Instant> {
        self.pending_global_removals
            .iter()
            .map(|(_, disabled_at)| *disabled_at + GLOBAL_REMOVAL_DELAY)
            .min()
    }

    fn open_output_device(
        session: &LibSeatSession,
        node: DrmNode,
        path: &Path,
        renderer: &mut NativeRenderer,
        state: &mut PantheonCompositor,
    ) -> Result<Self, Box<dyn std::error::Error>> {
        let trace = Operation::begin("open_output_device");
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
        let (stale_at_startup, mut identities) = remove_stale_duplicates(&drm, &mut discovered);
        if !stale_at_startup.is_empty() {
            tracing::warn!(
                connectors = ?stale_at_startup,
                "ignoring connectors that duplicate another connected monitor's EDID (stale dock route)"
            );
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
                let identity = identities
                    .remove(&connector.handle())
                    .unwrap_or_else(|| connector_identity(&drm, connector.handle(), &name));
                state.display_config.update(OutputSnapshot {
                    connector: name,
                    vendor: identity.vendor,
                    product: identity.product,
                    serial: identity.serial,
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
            let identity = identities
                .remove(&selected.connector.handle())
                .unwrap_or_else(|| {
                    connector_identity(manager.device(), selected.connector.handle(), &name)
                });
            let output = Output::new(
                name.clone(),
                identity.physical_properties(&selected.connector),
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

            let output_trace = trace.output();
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
                connector: name,
                vendor: identity.vendor,
                product: identity.product,
                serial: identity.serial,
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
                trace: output_trace,
                stats: Default::default(),
                scanout_feedback: None,
                needs_estimated_frame: false,
                estimated_frame_armed: false,
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
            suppressed_duplicates: stale_at_startup.into_iter().collect(),
            link_resets: HashMap::new(),
            trace_connectors: HashMap::new(),
            trace_link_status: HashMap::new(),
            prewarm: prewarm::Slots::default(),
            prewarm_crtcs: HashMap::new(),
            prewarm_sender: None,
            busy_retry: false,
            busy_passes: 0,
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
        let state_seat = session.seat();
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
                match &event {
                    InputEvent::DeviceAdded { device } => {
                        let mut device = device.clone();
                        crate::touchpad::apply(&state.peripheral_settings, &mut device);
                        state.input_devices.push(device);
                    }
                    InputEvent::DeviceRemoved { device } => {
                        state.cancel_active_gesture(smithay::backend::input::InputTime::now());
                        state.input_devices.retain(|known| known != device);
                    }
                    _ => {}
                }
                state.process_input_event(event);
                state.mark_dirty();
                state.request_native_redraw();
            })?;

        event_loop.handle().insert_source(
            session_notifier,
            move |event, _, state| match event {
                SessionEvent::PauseSession => {
                    let _trace = Operation::begin("session_pause");
                    state.cancel_active_gesture(smithay::backend::input::InputTime::now());
                    libinput_context.suspend();
                    if let Some(backend) = state.native_backend.as_mut() {
                        backend.kms.manager.pause();
                        backend.session_paused = true;
                    }
                    tracing::info!("native compositor session paused");
                }
                SessionEvent::ActivateSession => {
                    let _trace = Operation::begin("session_activate");
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
            .insert_source(drm_notifier, |event, metadata, state| match event {
                smithay::backend::drm::DrmEvent::VBlank(crtc) => {
                    crate::metrics::vblank();
                    // The kernel's flip timestamp (CLOCK_MONOTONIC on this
                    // driver); fall back to now for a realtime-only device.
                    let flip = match metadata.as_ref().map(|metadata| metadata.time) {
                        Some(smithay::backend::drm::DrmEventTime::Monotonic(time)) => time,
                        _ => state.monotonic_clock.now().into(),
                    };
                    let sequence = metadata.as_ref().map(|metadata| metadata.sequence);
                    let Some(backend) = state.native_backend.as_mut() else {
                        return;
                    };
                    let output = match backend.kms.frame_submitted(crtc, flip, sequence) {
                        Ok(Some(output)) => output,
                        Ok(None) => return,
                        Err(error) => {
                            tracing::error!(?error, "failed to complete native DRM frame");
                            state.stop_with_error(format!(
                                "native DRM frame completion failed: {error:?}"
                            ));
                            return;
                        }
                    };
                    state.confirm_lock_output_frame(&output.name());
                    send_frame_callbacks(state, &output);
                    state.space.refresh();
                    // After refresh, so a window that moved to another
                    // output gets that output's scale (no-op otherwise).
                    state.update_fractional_scale_preferences();
                    state.popups.cleanup();
                    let _ = state.display_handle.flush_clients();
                    state.request_native_redraw();
                }
                smithay::backend::drm::DrmEvent::Error(error) => {
                    tracing::error!(?error, "native DRM event source failed");
                    state.stop_with_error(format!("native DRM event source failed: {error:?}"));
                }
            })?;

        let (redraw_ping, redraw_source) = smithay::reexports::calloop::ping::make_ping()?;
        state.native_redraw_ping = Some(redraw_ping);
        state.native_backend = Some(Self {
            _session: session,
            renderer,
            kms,
            session_paused: false,
            hotplug: HotplugScheduler::new(Instant::now(), false),
            trace_pending_event: None,
        });
        let mut consecutive_render_failures = 0;
        let redraw_handle = event_loop.handle();
        event_loop
            .handle()
            .insert_source(redraw_source, move |(), _, state| {
                state.native_redraw_pending.set(false);
                let Some(mut backend) = state.native_backend.take() else {
                    return;
                };
                match backend.kms.render(&mut backend.renderer, state) {
                    Ok(_) => {
                        consecutive_render_failures = 0;
                        let now: Duration = state.monotonic_clock.now().into();
                        for (crtc, delay) in backend.kms.arm_estimated_frames(now) {
                            let timer = Timer::from_duration(delay);
                            let armed = redraw_handle.insert_source(timer, move |_, _, state| {
                                let output = state
                                    .native_backend
                                    .as_mut()
                                    .and_then(|backend| backend.kms.estimated_frame_due(crtc));
                                if let Some(output) = output {
                                    send_frame_callbacks(state, &output);
                                    let _ = state.display_handle.flush_clients();
                                }
                                TimeoutAction::Drop
                            });
                            if let Err(error) = armed {
                                tracing::warn!(?error, "could not arm the empty-frame callback timer");
                            }
                        }
                        if backend.kms.take_busy_retry() {
                            let retry = Timer::from_duration(flip_retry::RETRY_DELAY);
                            let _ = redraw_handle.insert_source(retry, |_, _, state| {
                                state.request_native_redraw();
                                TimeoutAction::Drop
                            });
                        }
                    }
                    Err(error) => {
                        consecutive_render_failures += 1;
                        tracing::error!(
                            ?error,
                            consecutive_render_failures,
                            "native output render failed"
                        );
                        if consecutive_render_failures >= 3 {
                            state.stop_with_error(format!(
                                "native output rendering failed {consecutive_render_failures} consecutive times: {error}"
                            ));
                        } else {
                            state.request_native_redraw();
                        }
                    }
                }
                state.native_backend = Some(backend);
            })?;

        // Hotplug is event driven: a udev `drm` monitor schedules a debounced
        // reconcile (plus one follow-up), and a slow safety poll covers a
        // missed event. Without a monitor the old 2 s poll is kept.
        let udev_backend = match UdevBackend::new(state_seat.as_str()) {
            Ok(backend) => Some(backend),
            Err(error) => {
                tracing::warn!(?error, "udev drm monitor unavailable; polling connectors");
                None
            }
        };
        let hotplug = HotplugScheduler::new(Instant::now(), udev_backend.is_some());
        let safety_interval = hotplug.safety_interval();
        if let Some(backend) = state.native_backend.as_mut() {
            backend.hotplug = hotplug;
        }
        let loop_handle = event_loop.handle();
        if prewarm::enabled() {
            tracing::info!("PANTHEON_PREWARM_MODESET=1: external modesets run on a helper thread");
            let (sender, receiver) = channel::channel::<PrewarmDone>();
            if let Some(backend) = state.native_backend.as_mut() {
                backend.kms.prewarm_sender = Some(sender);
            }
            let timer_handle = loop_handle.clone();
            loop_handle.insert_source(receiver, move |event, _, state| {
                let ChannelEvent::Msg(done) = event else {
                    return;
                };
                let Some(backend) = state.native_backend.as_mut() else {
                    return;
                };
                let kms = &mut backend.kms;
                match done.result {
                    Ok(warmed) => {
                        tracing::info!(connector = ?done.connector, "prewarmed modeset finished");
                        if let Some(orphan) = kms.prewarm.finished(done.connector, Ok(warmed)) {
                            prewarm::release(kms.manager.device(), orphan);
                        }
                    }
                    Err(error) => {
                        tracing::warn!(connector = ?done.connector, %error, "prewarm failed; mapping inline");
                        kms.prewarm.finished(done.connector, Err(()));
                        kms.prewarm_crtcs.remove(&done.connector);
                    }
                }
                arm_reconcile(&timer_handle, state);
            })?;
        }
        if let Some(udev_backend) = udev_backend {
            let timer_handle = loop_handle.clone();
            loop_handle.insert_source(udev_backend, move |event, _, state| {
                let (kind, device) = match event {
                    UdevEvent::Added { device_id, .. } => (EventKind::Added, device_id),
                    UdevEvent::Changed { device_id } => (EventKind::Changed, device_id),
                    UdevEvent::Removed { device_id } => (EventKind::Removed, device_id),
                };
                let Some(backend) = state.native_backend.as_mut() else {
                    return;
                };
                if !event_triggers_reconcile(kind, device, backend.kms.node.dev_id()) {
                    return;
                }
                let now = Instant::now();
                let deadline = backend.hotplug.on_event(now);
                if display_trace::enabled() {
                    let pending = backend.trace_pending_event.get_or_insert((now, 0));
                    pending.1 = pending.1.saturating_add(1);
                    if let Some(monotonic_us) = display_trace::stamp() {
                        tracing::info!(target: "pantheon_display_lifecycle", monotonic_us = monotonic_us as u64,
                            device, ?kind, stage = "udev_event", coalesced = deadline.is_none(),
                            burst_events = pending.1,
                            deadline_in_us = deadline.map(|t| t.saturating_duration_since(now).as_micros() as u64),
                            "relevant DRM uevent received");
                    }
                }
                if !backend.session_paused {
                    backend.kms.prewarm_new_outputs();
                }
                arm_deadline(&timer_handle, deadline);
            })?;
        }
        loop_handle.insert_source(Timer::from_duration(safety_interval), move |_, _, state| {
            match reconcile_tick(state).1 {
                Some(next_safety) => TimeoutAction::ToInstant(next_safety),
                None => TimeoutAction::ToDuration(safety_interval),
            }
        })?;
        advertise_dmabuf(state);
        state.request_native_redraw();
        Ok(())
    }
}

/// Record, for every surface drawn in this output's frame, whether this
/// output is now the one it is mostly shown on.
fn update_primary_scanout_outputs(
    state: &PantheonCompositor,
    output: &Output,
    render_states: &smithay::backend::renderer::element::RenderElementStates,
) {
    use smithay::desktop::utils::update_surface_primary_scanout_output;
    for window in state.gesture_frame_windows() {
        window.with_surfaces(|surface, states| {
            update_surface_primary_scanout_output(
                surface,
                output,
                states,
                None,
                render_states,
                smithay::backend::renderer::element::default_primary_scanout_output_compare,
            );
        });
    }
}

/// Frame callbacks after `output` presented (or would have, for an empty
/// frame): surfaces whose primary scanout output is `output` get one now;
/// surfaces shown nowhere get one at most every
/// `HIDDEN_FRAME_CALLBACK_INTERVAL`. If such a hidden surface is still
/// waiting, a sweep timer makes sure it is served even on an idle desktop.
fn send_frame_callbacks(state: &PantheonCompositor, output: &Output) {
    use smithay::wayland::compositor::SurfaceAttributes;
    let time = state.start_time.elapsed();
    // The lock screen is not a window: without this it draws one frame and
    // then never again (typing on it showed nothing).
    state.send_lock_surface_frames(output, time);
    if legacy_frame_callbacks() {
        for window in state.gesture_frame_windows() {
            window.send_frame(output, time, Some(Duration::ZERO), |_, _| {
                Some(output.clone())
            });
        }
        return;
    }
    let hidden_waiting = std::cell::Cell::new(false);
    let hidden_waiting = &hidden_waiting;
    for window in state.gesture_frame_windows() {
        window.send_frame(
            output,
            time,
            Some(HIDDEN_FRAME_CALLBACK_INTERVAL),
            |surface, states| {
                let primary =
                    smithay::desktop::utils::surface_primary_scanout_output(surface, states);
                if primary.is_none()
                    && !states
                        .cached_state
                        .get::<SurfaceAttributes>()
                        .current()
                        .frame_callbacks
                        .is_empty()
                {
                    hidden_waiting.set(true);
                }
                primary
            },
        );
    }
    if hidden_waiting.get() {
        arm_hidden_frame_sweep(state);
    }
}

/// `PANTHEON_FRAME_CALLBACKS=all` restores the old behaviour (every window
/// on every flip of every output), as a no-rebuild fallback if targeted
/// callbacks ever stall a client.
fn legacy_frame_callbacks() -> bool {
    static LEGACY: std::sync::OnceLock<bool> = std::sync::OnceLock::new();
    *LEGACY.get_or_init(|| {
        let legacy = std::env::var("PANTHEON_FRAME_CALLBACKS").is_ok_and(|value| value == "all");
        if legacy {
            tracing::info!(
                "PANTHEON_FRAME_CALLBACKS=all: frame callbacks to every window on every flip"
            );
        }
        legacy
    })
}

/// Serve hidden surfaces' frame callbacks once per interval while any are
/// waiting; the timer drops itself when none are.
fn arm_hidden_frame_sweep(state: &PantheonCompositor) {
    if state.hidden_frame_sweep_armed.replace(true) {
        return;
    }
    let timer = Timer::from_duration(HIDDEN_FRAME_CALLBACK_INTERVAL);
    let armed = state.loop_handle.insert_source(timer, |_, _, state| {
        state.hidden_frame_sweep_armed.set(false);
        let outputs = state
            .native_backend
            .as_ref()
            .map(|backend| {
                backend
                    .kms
                    .outputs
                    .iter()
                    .map(|output| output.output.clone())
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();
        // Re-arms itself through send_frame_callbacks if anyone still waits.
        for output in &outputs {
            send_frame_callbacks(state, output);
        }
        let _ = state.display_handle.flush_clients();
        TimeoutAction::Drop
    });
    if let Err(error) = armed {
        state.hidden_frame_sweep_armed.set(false);
        tracing::warn!(
            ?error,
            "could not arm the hidden-surface frame callback timer"
        );
    }
}

/// Whether to advertise linux-dmabuf on the native backend: on by default
/// since 2026-10-21 (owner-approved trial); `PANTHEON_DISABLE_DMABUF=1` or
/// `PANTHEON_ENABLE_DMABUF=0` turns it off.
fn dmabuf_enabled(disable: Option<&str>, enable: Option<&str>) -> bool {
    disable != Some("1") && enable != Some("0")
}

/// `zwp_linux_dmabuf_v1` v4 for native clients, so Mesa picks the Asahi GPU
/// and Chromium/Electron/GTK render on it instead of in software over wl_shm.
/// The default feedback lists the render node's formats; each output also
/// builds a scanout feedback (see [`scanout_feedback`]).
fn advertise_dmabuf(state: &mut PantheonCompositor) {
    use smithay::backend::renderer::ImportDma;
    use smithay::wayland::dmabuf::DmabufFeedbackBuilder;

    if !dmabuf_enabled(
        std::env::var("PANTHEON_DISABLE_DMABUF").ok().as_deref(),
        std::env::var("PANTHEON_ENABLE_DMABUF").ok().as_deref(),
    ) {
        tracing::info!(
            "linux-dmabuf disabled by PANTHEON_DISABLE_DMABUF/PANTHEON_ENABLE_DMABUF; clients use wl_shm"
        );
        return;
    }
    let Some(backend) = state.native_backend.as_mut() else {
        return;
    };
    let node = backend.renderer.render_node;
    let formats = match backend.renderer.gpus.single_renderer(&node) {
        Ok(renderer) => renderer.dmabuf_formats(),
        Err(error) => {
            tracing::warn!(?error, "no renderer for linux-dmabuf; not advertised");
            return;
        }
    };
    let feedback = match DmabufFeedbackBuilder::new(node.dev_id(), formats.clone()).build() {
        Ok(feedback) => feedback,
        Err(error) => {
            tracing::warn!(%error, "could not build dmabuf feedback; linux-dmabuf not advertised");
            return;
        }
    };
    backend.renderer.dmabuf = Some((feedback.clone(), formats));
    let dh = state.display_handle.clone();
    state
        .dmabuf_state
        .create_global_with_default_feedback::<PantheonCompositor>(&dh, &feedback);
    tracing::info!("advertising linux-dmabuf v4 on the native renderer");
}

/// Feedback for a surface the display controller scans out directly: a
/// scanout tranche on the KMS device with the output's plane formats (limited
/// to ones the GPU can also sample, so composition stays a fallback), then
/// the normal render tranche. Only sent to surfaces presented zero-copy, so
/// ordinary windows are not steered to scanout-only layouts.
fn scanout_feedback(
    drm_output: &NativeDrmOutput,
    render_node: DrmNode,
    kms_node: DrmNode,
    render_formats: &smithay::backend::allocator::format::FormatSet,
) -> Option<smithay::wayland::dmabuf::DmabufFeedback> {
    use smithay::backend::allocator::format::FormatSet;
    use smithay::reexports::wayland_protocols::wp::linux_dmabuf::zv1::server::zwp_linux_dmabuf_feedback_v1::TrancheFlags;
    use smithay::wayland::dmabuf::DmabufFeedbackBuilder;

    let plane_formats = drm_output.with_compositor(|compositor| {
        let surface = compositor.surface();
        surface
            .plane_info()
            .formats
            .iter()
            .copied()
            .chain(
                surface
                    .planes()
                    .overlay
                    .iter()
                    .flat_map(|plane| plane.formats.iter().copied()),
            )
            .collect::<FormatSet>()
    });
    let scanout_formats = plane_formats
        .intersection(render_formats)
        .copied()
        .collect::<FormatSet>();
    DmabufFeedbackBuilder::new(render_node.dev_id(), render_formats.clone())
        .add_preference_tranche(
            kms_node.dev_id(),
            TrancheFlags::Scanout,
            scanout_formats,
            4u32..=6,
        )
        .build()
        .inspect_err(|error| tracing::warn!(%error, "could not build scanout dmabuf feedback"))
        .ok()
}

/// Send each surface drawn on `output` the feedback that fits how it was
/// presented (smithay only resends when it changes).
fn send_dmabuf_feedback(
    state: &PantheonCompositor,
    output: &Output,
    render_states: &smithay::backend::renderer::element::RenderElementStates,
    default_feedback: &smithay::wayland::dmabuf::DmabufFeedback,
    scanout_feedback: &smithay::wayland::dmabuf::DmabufFeedback,
) {
    use smithay::backend::renderer::element::utils::select_dmabuf_feedback;
    for window in state.gesture_frame_windows() {
        window.send_dmabuf_feedback(
            output,
            smithay::desktop::utils::surface_primary_scanout_output,
            |surface, _| {
                select_dmabuf_feedback(surface, render_states, default_feedback, scanout_feedback)
            },
        );
    }
}

/// Record a hotplug-relevant event and arm the one-shot reconcile timer the
/// scheduler asks for (none when an armed deadline already covers it).
fn arm_reconcile(handle: &LoopHandle<'_, PantheonCompositor>, state: &mut PantheonCompositor) {
    let Some(backend) = state.native_backend.as_mut() else {
        return;
    };
    let deadline = backend.hotplug.on_event(Instant::now());
    arm_deadline(handle, deadline);
}

/// Arm the reconcile timer for a deadline the scheduler already returned.
fn arm_deadline(handle: &LoopHandle<'_, PantheonCompositor>, deadline: Option<Instant>) {
    let Some(deadline) = deadline else {
        return;
    };
    let armed = handle.insert_source(Timer::from_deadline(deadline), |_, _, state| {
        reconcile_tick(state).0
    });
    if let Err(error) = armed {
        tracing::warn!(?error, "failed to arm hotplug reconcile timer");
    }
}

/// Run one scheduler tick. Returns the timer action for an event-driven
/// timer (drop when nothing is pending) and the next safety-poll instant.
fn reconcile_tick(state: &mut PantheonCompositor) -> (TimeoutAction, Option<Instant>) {
    let Some(mut backend) = state.native_backend.take() else {
        return (TimeoutAction::Drop, None);
    };
    let now = Instant::now();
    let removal = backend.kms.next_global_removal_deadline();
    let tick = backend.hotplug.tick(now, removal);
    // A safety poll with no pending event: trace it at DEBUG unless it finds
    // a change (the reconcile result is still logged at INFO then).
    let _quiet = display_trace::QuietScope::enter(
        tick.reconcile
            && tick.safety_due
            && !tick.event_due
            && !tick.followup_due
            && !tick.removal_due,
    );
    if tick.reconcile {
        if let Some(monotonic_us) = display_trace::stamp() {
            display_trace::lifecycle_event!(
                monotonic_us = monotonic_us as u64,
                stage = "scheduler_tick",
                event_due = tick.event_due,
                followup_due = tick.followup_due,
                removal_due = tick.removal_due,
                safety_due = tick.safety_due,
                session_paused = backend.session_paused,
                event_wait_us = backend
                    .trace_pending_event
                    .map(|(t, _)| t.elapsed().as_micros() as u64),
                burst_events = backend.trace_pending_event.map(|(_, n)| n).unwrap_or(0),
                "display scheduler reconcile decision"
            );
        }
        backend.trace_pending_event = None;
        if !backend.session_paused
            && let Err(error) = backend.kms.refresh_connectors(&mut backend.renderer, state)
        {
            tracing::warn!(?error, "failed to reconcile native DRM connectors");
        }
    }
    // Removals queued by this very reconcile may need a later wakeup.
    let removal = backend.kms.next_global_removal_deadline();
    let next_event = [tick.next_event_deadline, removal]
        .into_iter()
        .flatten()
        .min();
    let action = next_event.map_or(TimeoutAction::Drop, TimeoutAction::ToInstant);
    state.native_backend = Some(backend);
    (action, Some(tick.next_safety))
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
                        dmabuf: None,
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
    ) -> Result<Option<HardwareNode>, Box<dyn std::error::Error>> {
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

#[cfg(test)]
mod dmabuf_tests {
    use super::dmabuf_enabled;

    #[test]
    fn dmabuf_is_on_unless_switched_off() {
        assert!(dmabuf_enabled(None, None));
        assert!(dmabuf_enabled(None, Some("1")));
        assert!(dmabuf_enabled(Some("0"), None));
        assert!(!dmabuf_enabled(Some("1"), None));
        assert!(!dmabuf_enabled(None, Some("0")));
        assert!(!dmabuf_enabled(Some("1"), Some("1")));
    }
}
