use wayland_client::protocol::{wl_compositor, wl_registry, wl_surface};
use wayland_client::{Connection, Dispatch, Proxy, QueueHandle, globals::registry_queue_init};

mod protocols {
    include!("../protocols.rs");
}

use protocols::pantheon_desktop_shell_v1::client::{
    io_elementary_pantheon_panel_v1::{Anchor, HideMode, IoElementaryPantheonPanelV1},
    io_elementary_pantheon_shell_v1::IoElementaryPantheonShellV1,
};

struct Probe;

impl Dispatch<wl_registry::WlRegistry, wayland_client::globals::GlobalListContents> for Probe {
    fn event(
        _state: &mut Self,
        _registry: &wl_registry::WlRegistry,
        _event: wl_registry::Event,
        _data: &wayland_client::globals::GlobalListContents,
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
    }
}

wayland_client::delegate_noop!(Probe: ignore wl_compositor::WlCompositor);
wayland_client::delegate_noop!(Probe: ignore wl_surface::WlSurface);
wayland_client::delegate_noop!(Probe: ignore IoElementaryPantheonPanelV1);

impl Dispatch<IoElementaryPantheonShellV1, ()> for Probe {
    fn event(
        _state: &mut Self,
        _shell: &IoElementaryPantheonShellV1,
        _event: <IoElementaryPantheonShellV1 as wayland_client::Proxy>::Event,
        _data: &(),
        _conn: &Connection,
        _qh: &QueueHandle<Self>,
    ) {
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let connection = Connection::connect_to_env()?;
    let (globals, mut queue) = registry_queue_init::<Probe>(&connection)?;
    let qh = queue.handle();
    let compositor: wl_compositor::WlCompositor = globals.bind(&qh, 1..=6, ())?;
    let shell: IoElementaryPantheonShellV1 = globals.bind(&qh, 1..=2, ())?;

    let surface = compositor.create_surface(&qh, ());
    let panel = shell.get_panel(&surface, &qh, ());
    panel.set_anchor(Anchor::Top);
    panel.set_size(600, 32);
    panel.set_hide_mode(HideMode::Never);
    panel.set_offset(0);
    queue.roundtrip(&mut Probe)?;

    println!(
        "Pantheon shell v{} accepted get_panel and panel v{} accepted anchor, size, hide mode, and offset",
        shell.version(),
        panel.version()
    );
    panel.destroy();
    surface.destroy();
    connection.flush()?;
    Ok(())
}
