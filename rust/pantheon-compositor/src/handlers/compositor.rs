use crate::{
    PantheonCompositor, grabs::resize_grab, metrics::client::BufferKind, pantheon_shell,
    state::ClientState,
};
use smithay::{
    backend::renderer::utils::on_commit_buffer_handler,
    reexports::wayland_server::{
        Client,
        protocol::{wl_buffer, wl_surface::WlSurface},
    },
    wayland::{
        buffer::BufferHandler,
        compositor::{
            BufferAssignment, CompositorClientState, CompositorHandler, CompositorState,
            SurfaceAttributes, get_parent, is_sync_subsurface, with_states,
        },
        shm::{ShmHandler, ShmState},
    },
    xwayland::XWaylandClientData,
};

use super::xdg_shell;

/// What this commit attached (buffer type), how much it damaged (buffer
/// pixels) and how many frame callbacks it asked for.
fn commit_summary(surface: &WlSurface) -> (BufferKind, u64, u64) {
    use smithay::backend::renderer::{BufferType, buffer_dimensions, buffer_type};
    use smithay::wayland::compositor::Damage;

    with_states(surface, |states| {
        let mut attributes = states.cached_state.get::<SurfaceAttributes>();
        let current = attributes.current();
        let frame_callbacks = current.frame_callbacks.len() as u64;
        let Some(BufferAssignment::NewBuffer(buffer)) = current.buffer.as_ref() else {
            return (BufferKind::None, 0, frame_callbacks);
        };
        let kind = match buffer_type(buffer) {
            Some(BufferType::Shm) => BufferKind::Shm,
            Some(BufferType::Dma) => BufferKind::Dmabuf,
            _ => BufferKind::Other,
        };
        let damage_px = buffer_dimensions(buffer).map_or(0, |size| {
            let scale = current.buffer_scale.max(1);
            crate::metrics::client::damage_area(
                current.damage.iter().map(|damage| match damage {
                    Damage::Buffer(rect) => (rect.loc.x, rect.loc.y, rect.size.w, rect.size.h),
                    Damage::Surface(rect) => (
                        rect.loc.x.saturating_mul(scale),
                        rect.loc.y.saturating_mul(scale),
                        rect.size.w.saturating_mul(scale),
                        rect.size.h.saturating_mul(scale),
                    ),
                }),
                size.w,
                size.h,
            )
        });
        (kind, damage_px, frame_callbacks)
    })
}

impl CompositorHandler for PantheonCompositor {
    fn compositor_state(&mut self) -> &mut CompositorState {
        &mut self.compositor_state
    }

    fn client_compositor_state<'a>(&self, client: &'a Client) -> &'a CompositorClientState {
        if let Some(state) = client.get_data::<ClientState>() {
            return &state.compositor_state;
        }
        if let Some(state) = client.get_data::<XWaylandClientData>() {
            return &state.compositor_state;
        }
        panic!("unknown Wayland client data type")
    }

    fn commit(&mut self, surface: &WlSurface) {
        self.mark_dirty();
        let (buffer, damage_px, frame_callbacks) = commit_summary(surface);
        if let Some(stats) = self.commit_stats_for(surface) {
            stats.commit(buffer, damage_px, frame_callbacks);
        }
        if self.is_panel_surface(surface) {
            self.note_panel_buffer_commit(surface, buffer != BufferKind::None);
        }
        on_commit_buffer_handler::<Self>(surface);
        if !is_sync_subsurface(surface) {
            let mut root = surface.clone();
            while let Some(parent) = get_parent(&root) {
                root = parent;
            }
            if let Some(window) = self
                .space
                .elements()
                .find(|w| w.toplevel().is_some_and(|top| top.wl_surface() == &root))
                .cloned()
                .or_else(|| {
                    self.workspace_manager
                        .windows()
                        .into_iter()
                        .map(|(window, _, _)| window)
                        .find(|window| {
                            window
                                .toplevel()
                                .is_some_and(|top| top.wl_surface() == &root)
                        })
                })
            {
                window.on_commit();
            }
        };

        xdg_shell::handle_commit(self, surface);
        pantheon_shell::handle_surface_commit(self, surface);
        resize_grab::handle_commit(&mut self.space, surface);
        self.request_native_redraw();
    }
}

impl BufferHandler for PantheonCompositor {
    fn buffer_destroyed(&mut self, _buffer: &wl_buffer::WlBuffer) {}
}

impl ShmHandler for PantheonCompositor {
    fn shm_state(&self) -> &ShmState {
        &self.shm_state
    }
}

impl smithay::wayland::dmabuf::DmabufHandler for PantheonCompositor {
    fn dmabuf_state(&mut self) -> &mut smithay::wayland::dmabuf::DmabufState {
        &mut self.dmabuf_state
    }

    fn dmabuf_imported(
        &mut self,
        _global: &smithay::wayland::dmabuf::DmabufGlobal,
        dmabuf: smithay::backend::allocator::dmabuf::Dmabuf,
        notifier: smithay::wayland::dmabuf::ImportNotifier,
    ) {
        #[cfg_attr(not(feature = "native-drm"), allow(unused_mut))]
        let mut imported = self
            .dmabuf_importer
            .as_mut()
            .is_some_and(|import| import(&dmabuf));
        #[cfg(feature = "native-drm")]
        if !imported && let Some(backend) = self.native_backend.as_mut() {
            use smithay::backend::renderer::ImportDma;
            let node = backend.renderer.render_node;
            imported = backend
                .renderer
                .gpus
                .single_renderer(&node)
                .is_ok_and(|mut renderer| renderer.import_dmabuf(&dmabuf, None).is_ok());
        }
        if imported {
            let _ = notifier.successful::<PantheonCompositor>();
        } else {
            notifier.failed();
        }
    }
}
