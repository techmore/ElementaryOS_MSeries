//! Native M-series renderer setup.
//!
//! The renderer is selected independently of the KMS output device. On the
//! M1 Pro, the Asahi render node can render client content while the Apple DRM
//! device owns the physical connectors. Output allocation and scanout are
//! attached by the native output backend built on top of this manager.

use std::path::Path;

use smithay::{
    backend::{
        drm::{DrmDeviceFd, DrmNode, NodeType},
        egl::{EGLContext, EGLDevice, EGLDisplay, context::ContextPriority},
        renderer::{
            gles::GlesRenderer,
            multigpu::{GpuManager, gbm::GbmGlesBackend},
        },
        session::{Session, libseat::LibSeatSession},
        udev::all_gpus,
    },
    reexports::rustix::fs::OFlags,
    utils::DeviceFd,
};

pub type GbmRendererBackend = GbmGlesBackend<GlesRenderer, DrmDeviceFd>;
pub type NativeGpuManager = GpuManager<GbmRendererBackend>;

pub struct NativeRenderer {
    pub render_node: DrmNode,
    pub gpus: NativeGpuManager,
}

impl NativeRenderer {
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
                Ok(Some(render_node)) => return Ok(Self { render_node, gpus }),
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
    ) -> Result<Option<DrmNode>, Box<dyn std::error::Error>> {
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
        gpus.as_mut().add_node(render_node, gbm)?;
        Ok(Some(render_node))
    }
}
