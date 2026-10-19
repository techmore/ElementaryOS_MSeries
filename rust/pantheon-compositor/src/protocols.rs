pub mod pantheon_desktop_shell_v1 {
    pub mod server {
        use smithay::reexports::wayland_server;
        use wayland_server::protocol::*;

        pub mod __interfaces {
            use wayland_server::protocol::__interfaces::*;
            wayland_scanner::generate_interfaces!("protocol/pantheon-desktop-shell-v1.xml");
        }

        use self::__interfaces::*;
        wayland_scanner::generate_server_code!("protocol/pantheon-desktop-shell-v1.xml");
    }
}
