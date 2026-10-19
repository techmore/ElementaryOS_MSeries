//! Native M-series renderer setup.
//!
//! The renderer is selected independently of the KMS output device. On the
//! M1 Pro, the Asahi render node can render client content while the Apple DRM
//! device owns the physical connectors. Output allocation and scanout are
//! attached by the native output backend built on top of this manager.

use std::path::Path;

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
        renderer::{
            element::surface::WaylandSurfaceRenderElement,
            gles::GlesRenderer,
            multigpu::{GpuManager, MultiRenderer, gbm::GbmGlesBackend},
        },
        session::{Session, libseat::LibSeatSession},
        udev::all_gpus,
    },
    output::{Mode, Output, PhysicalProperties},
    reexports::{
        drm::control::{Device as DrmControlDevice, ModeTypeFlags, connector},
        rustix::fs::OFlags,
    },
    utils::DeviceFd,
};

use crate::{PantheonCompositor, display_config::OutputSnapshot};

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
    pub node: DrmNode,
    pub connector: connector::Handle,
    pub output: Output,
    pub manager: NativeOutputManager,
    pub drm_output: NativeDrmOutput,
    pub notifier: DrmDeviceNotifier,
}

struct ConnectedOutput {
    connector: connector::Info,
    crtc: smithay::reexports::drm::control::crtc::Handle,
    mode: smithay::reexports::drm::control::Mode,
}

impl NativeKmsOutput {
    /// Open the first usable KMS device on the active libseat and initialize
    /// its preferred connected connector with buffers rendered on `renderer`.
    /// This creates Smithay output state but does not queue or present a frame.
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
                Ok(output) => return Ok(output),
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
    ) -> Result<bool, Box<dyn std::error::Error>> {
        let mut gpu_renderer = renderer.gpus.single_renderer(&renderer.render_node)?;
        let elements = smithay::desktop::space::space_render_elements(
            &mut gpu_renderer,
            [&state.space],
            &self.output,
            1.0,
        )?;
        let frame = self.drm_output.render_frame(
            &mut gpu_renderer,
            &elements,
            [0.1, 0.1, 0.1, 1.0],
            FrameFlags::DEFAULT,
        )?;
        if frame.is_empty {
            return Ok(false);
        }
        self.drm_output.queue_frame(())?;
        Ok(true)
    }

    pub fn frame_submitted(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        self.drm_output.frame_submitted()?;
        Ok(())
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

        let mut connected = Vec::new();
        for handle in resources.connectors() {
            let connector = drm.get_connector(*handle, false)?;
            if connector.state() != connector::State::Connected || connector.modes().is_empty() {
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
                .next()
            else {
                continue;
            };
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

        connected.sort_by_key(|output| {
            output.connector.interface() != connector::Interface::EmbeddedDisplayPort
        });
        let selected = connected
            .into_iter()
            .next()
            .ok_or("KMS device has no connected connector with a compatible CRTC")?;

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
        output.change_current_state(Some(mode), None, None, Some((0, 0).into()));

        let render_elements = DrmOutputRenderElements::<
            NativeMultiRenderer<'_>,
            WaylandSurfaceRenderElement<NativeMultiRenderer<'_>>,
        >::default();
        let drm_output = manager.lock().initialize_output(
            selected.crtc,
            selected.mode,
            &[selected.connector.handle()],
            &output,
            None,
            &mut gpu_renderer,
            &render_elements,
        )?;

        output.create_global::<PantheonCompositor>(&state.display_handle);
        state.space.map_output(&output, (0, 0));
        state.display_config.update(OutputSnapshot {
            connector: name.clone(),
            vendor: "Apple".into(),
            product: name,
            serial: "Unknown".into(),
            width: mode.size.w,
            height: mode.size.h,
            refresh_millihz: mode.refresh,
            scale: 1.0,
            x: 0,
            y: 0,
            primary: true,
        });

        Ok(Self {
            node,
            connector: selected.connector.handle(),
            output,
            manager,
            drm_output,
            notifier,
        })
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
