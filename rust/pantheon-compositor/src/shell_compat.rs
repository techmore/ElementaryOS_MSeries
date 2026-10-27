use std::{
    collections::HashMap,
    ffi::OsString,
    process::Command,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    thread,
    time::{Duration, Instant},
};

use smithay::input::keyboard::{Keysym, ModifiersState, xkb};
use smithay::reexports::calloop::channel::Sender;
use zbus::{blocking::Connection, interface, object_server::SignalEmitter, zvariant::OwnedValue};

const BUS_NAME: &str = "org.gnome.Shell";
const OBJECT_PATH: &str = "/org/gnome/Shell";
const INTERFACE: &str = "org.gnome.Shell";
const SCREENSAVER_BUS_NAME: &str = "org.gnome.ScreenSaver";
const SCREENSAVER_OBJECT_PATH: &str = "/org/gnome/ScreenSaver";
const SCREENSAVER_INTERFACE: &str = "org.gnome.ScreenSaver";

#[derive(Clone)]
enum ShellEvent {
    /// A grabbed key was pressed; delivered only to the connection that grabbed it.
    AcceleratorActivated {
        id: u32,
        owner: String,
    },
    ActiveChanged(bool),
    /// Start the configured locker, as `org.gnome.ScreenSaver.Lock` does.
    Lock,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
struct AcceleratorModifiers {
    ctrl: bool,
    alt: bool,
    shift: bool,
    logo: bool,
}

#[derive(Clone, Copy, Debug)]
pub(crate) struct ParsedAccelerator {
    keysym: Keysym,
    modifiers: AcceleratorModifiers,
}

#[derive(Clone, Debug)]
pub(crate) struct ShellOsd {
    pub icon: Option<String>,
    pub level: Option<f64>,
    pub max_level: Option<f64>,
    pub connector: Option<String>,
    pub monitor: Option<u32>,
    expires_at: Instant,
}

impl ShellOsd {
    pub fn visible(&self) -> bool {
        Instant::now() < self.expires_at
    }
}

#[derive(Clone, Debug)]
struct KeyBinding {
    id: u32,
    /// Unique bus name of the connection that grabbed the key.
    owner: String,
    accelerator: ParsedAccelerator,
}

/// Every `GrabAccelerator` grab, tied to the D-Bus connection that made it.
///
/// A grab belongs to its connection: when that connection leaves the bus (a crash, a restart
/// during testing) its grabs go with it, as in GNOME Shell. Without that, a restarted
/// `gsd-media-keys` found its own volume keys still held by its dead predecessor, every
/// `GrabAccelerators` call came back 0 and the keys stayed dead until the next login.
#[derive(Default)]
struct GrabTable {
    bindings: Vec<KeyBinding>,
    next_id: u32,
}

impl GrabTable {
    /// Grab `accelerator` for `owner`; 0 means it is held by a different live connection.
    /// A connection grabbing a key it already holds gets a fresh id and the old one stops
    /// working, so a client that re-grabs before it releases cannot lock itself out.
    fn grab(&mut self, owner: &str, accelerator: ParsedAccelerator) -> u32 {
        if let Some(held) = self
            .bindings
            .iter()
            .find(|binding| same_accelerator(binding.accelerator, accelerator))
        {
            if held.owner != owner {
                tracing::warn!(holder = %held.owner, requester = %owner, "accelerator already grabbed by another connection");
                return 0;
            }
            self.bindings
                .retain(|binding| !same_accelerator(binding.accelerator, accelerator));
        }

        let id = self.next_id.max(1);
        self.next_id = id.wrapping_add(1).max(1);
        self.bindings.push(KeyBinding {
            id,
            owner: owner.to_owned(),
            accelerator,
        });
        id
    }

    /// Release the grabs `owner` holds among `actions`; other connections' grabs are untouched.
    fn release(&mut self, owner: &str, actions: &[u32]) -> usize {
        let initial_len = self.bindings.len();
        self.bindings
            .retain(|binding| !(binding.owner == owner && actions.contains(&binding.id)));
        initial_len - self.bindings.len()
    }

    /// Drop everything `owner` grabbed, once it has left the bus.
    fn drop_owner(&mut self, owner: &str) -> usize {
        let initial_len = self.bindings.len();
        self.bindings.retain(|binding| binding.owner != owner);
        initial_len - self.bindings.len()
    }

    fn matching(&self, keysym: Keysym, modifiers: &ModifiersState) -> Vec<(u32, String)> {
        self.bindings
            .iter()
            .filter(|binding| matches_accelerator(binding.accelerator, keysym, modifiers))
            .map(|binding| (binding.id, binding.owner.clone()))
            .collect()
    }
}

#[derive(Clone)]
pub struct ShellCompatHandle {
    bindings: Arc<Mutex<GrabTable>>,
    events: mpsc::Sender<ShellEvent>,
    active: Arc<AtomicBool>,
    active_since: Arc<Mutex<Option<Instant>>>,
    osd: Arc<Mutex<Option<ShellOsd>>>,
}

impl ShellCompatHandle {
    pub fn start(wayland_display: OsString, redraw_sender: Sender<()>) -> Self {
        let bindings = Arc::new(Mutex::new(GrabTable::default()));
        let (events, receiver) = mpsc::channel();
        let active = Arc::new(AtomicBool::new(false));
        let active_since = Arc::new(Mutex::new(None));
        let service_bindings = bindings.clone();
        let service_active = active.clone();
        let service_active_since = active_since.clone();
        let osd = Arc::new(Mutex::new(None));
        let service_osd = osd.clone();
        let (ready, names_owned) = mpsc::channel();
        let (osd_expiry, expiry_receiver) = mpsc::channel();
        let expiry_redraw_sender = redraw_sender.clone();
        thread::Builder::new()
            .name("pantheon-osd-expiry".into())
            .spawn(move || run_osd_expiry(expiry_receiver, expiry_redraw_sender))
            .expect("failed to start OSD expiry worker");
        thread::Builder::new()
            .name("pantheon-shell-dbus".into())
            .spawn(move || {
                serve_shell_compat(ShellCompatContext {
                    bindings: service_bindings,
                    active: service_active,
                    active_since: service_active_since,
                    osd: service_osd,
                    redraw_sender,
                    osd_expiry,
                    wayland_display,
                    receiver,
                    ready,
                })
            })
            .expect("failed to start shell compatibility D-Bus thread");
        // The session is announced ready only once org.gnome.Shell exists, so gsd-media-keys
        // never starts before the name it grabs the volume keys from.
        if names_owned.recv_timeout(Duration::from_secs(5)).is_err() {
            tracing::warn!(
                "Shell compatibility names were not owned in time; continuing without waiting"
            );
        }
        Self {
            bindings,
            events,
            active,
            active_since,
            osd,
        }
    }

    pub(crate) fn active_osd(&self) -> Option<ShellOsd> {
        let mut osd = self.osd.lock().expect("OSD state lock poisoned");
        if osd.as_ref().is_some_and(ShellOsd::visible) {
            osd.clone()
        } else {
            *osd = None;
            None
        }
    }

    pub fn activate_key(&self, keysym: Keysym, modifiers: &ModifiersState) -> bool {
        let matched = self
            .bindings
            .lock()
            .expect("keybinding lock poisoned")
            .matching(keysym, modifiers);

        if matched.is_empty() {
            return false;
        }
        for (id, owner) in matched {
            let _ = self
                .events
                .send(ShellEvent::AcceleratorActivated { id, owner });
        }
        true
    }

    /// Lock the session with the configured locker (idle lock).
    pub fn request_lock(&self) {
        let _ = self.events.send(ShellEvent::Lock);
    }

    pub fn set_locked(&self, locked: bool) {
        let previous = self.active.swap(locked, Ordering::AcqRel);
        if previous == locked {
            return;
        }
        *self.active_since.lock().expect("lock timer poisoned") = locked.then(Instant::now);
        let _ = self.events.send(ShellEvent::ActiveChanged(locked));
    }
}

struct ShellKeyGrabber {
    bindings: Arc<Mutex<GrabTable>>,
    osd: Arc<Mutex<Option<ShellOsd>>>,
    redraw_sender: Sender<()>,
    osd_expiry: mpsc::Sender<Instant>,
}

#[derive(Clone)]
struct ScreenSaverCompat {
    wayland_display: OsString,
    lock_command: OsString,
    active: Arc<AtomicBool>,
    active_since: Arc<Mutex<Option<Instant>>>,
    lock_running: Arc<Mutex<bool>>,
}

#[interface(name = "org.gnome.Shell")]
impl ShellKeyGrabber {
    fn grab_accelerator(
        &self,
        #[zbus(header)] header: zbus::message::Header<'_>,
        accelerator: String,
        _mode_flags: u32,
        grab_flags: u32,
    ) -> u32 {
        self.grab_one(&sender_of(&header), &accelerator, grab_flags)
    }

    fn grab_accelerators(
        &self,
        #[zbus(header)] header: zbus::message::Header<'_>,
        accelerators: Vec<(String, u32, u32)>,
    ) -> Vec<u32> {
        let sender = sender_of(&header);
        accelerators
            .into_iter()
            .map(|(accelerator, _mode_flags, grab_flags)| {
                self.grab_one(&sender, &accelerator, grab_flags)
            })
            .collect()
    }

    fn ungrab_accelerator(
        &self,
        #[zbus(header)] header: zbus::message::Header<'_>,
        action: u32,
    ) -> bool {
        self.remove_bindings(&sender_of(&header), &[action]) > 0
    }

    fn ungrab_accelerators(
        &self,
        #[zbus(header)] header: zbus::message::Header<'_>,
        actions: Vec<u32>,
    ) -> bool {
        let removed = self.remove_bindings(&sender_of(&header), &actions);
        removed == actions.len()
    }

    fn show_osd(&self, parameters: HashMap<String, OwnedValue>) {
        let value = |key: &str| parameters.get(key);
        let icon = value("icon")
            .and_then(|value| value.try_clone().ok())
            .and_then(|value| String::try_from(value).ok());
        let connector = value("connector")
            .and_then(|value| value.try_clone().ok())
            .and_then(|value| String::try_from(value).ok());
        let level = value("level").and_then(|value| f64::try_from(value).ok());
        let max_level = value("maxLevel").and_then(|value| f64::try_from(value).ok());
        let monitor = value("monitor")
            .and_then(|value| i32::try_from(value).ok())
            .and_then(|value| u32::try_from(value).ok());
        *self.osd.lock().expect("OSD state lock poisoned") = Some(ShellOsd {
            icon,
            level,
            max_level,
            connector,
            monitor,
            expires_at: Instant::now() + Duration::from_millis(1400),
        });
        let _ = self.redraw_sender.send(());
        let _ = self
            .osd_expiry
            .send(Instant::now() + Duration::from_millis(1450));
    }

    #[zbus(signal)]
    async fn accelerator_activated(
        emitter: &SignalEmitter<'_>,
        action: u32,
        parameters_dict: HashMap<String, OwnedValue>,
    ) -> zbus::Result<()>;
}

impl ShellKeyGrabber {
    fn grab_one(&self, owner: &str, accelerator: &str, grab_flags: u32) -> u32 {
        let Some(parsed) = parse_accelerator(accelerator, grab_flags) else {
            tracing::warn!(%accelerator, %owner, "cannot parse grabbed accelerator");
            return 0;
        };
        self.bindings
            .lock()
            .expect("keybinding lock poisoned")
            .grab(owner, parsed)
    }

    fn remove_bindings(&self, owner: &str, actions: &[u32]) -> usize {
        self.bindings
            .lock()
            .expect("keybinding lock poisoned")
            .release(owner, actions)
    }
}

/// The unique bus name of the caller; empty only for a message with no sender, which the bus
/// never delivers.
fn sender_of(header: &zbus::message::Header<'_>) -> String {
    header
        .sender()
        .map(|sender| sender.to_string())
        .unwrap_or_default()
}

/// Release the grabs of every connection that leaves the bus.
fn release_grabs_of_departed_clients(connection: &Connection, bindings: Arc<Mutex<GrabTable>>) {
    let proxy = match zbus::blocking::fdo::DBusProxy::new(connection) {
        Ok(proxy) => proxy,
        Err(error) => {
            tracing::warn!(%error, "cannot watch bus clients; grabs of departed clients will linger");
            return;
        }
    };
    let signals = match proxy.receive_name_owner_changed() {
        Ok(signals) => signals,
        Err(error) => {
            tracing::warn!(%error, "cannot watch bus clients; grabs of departed clients will linger");
            return;
        }
    };
    for signal in signals {
        let Ok(args) = signal.args() else { continue };
        let name = args.name().to_string();
        if !name.starts_with(':') || args.new_owner().is_some() {
            continue;
        }
        let released = bindings
            .lock()
            .expect("keybinding lock poisoned")
            .drop_owner(&name);
        if released > 0 {
            tracing::info!(owner = %name, released, "released key grabs of a client that left the bus");
        }
    }
}

#[interface(name = "org.gnome.ScreenSaver")]
impl ScreenSaverCompat {
    fn lock(&self) -> zbus::fdo::Result<()> {
        if self.active.load(Ordering::Acquire) {
            return Ok(());
        }

        let mut running = self.lock_running.lock().expect("lock child poisoned");
        if *running {
            return Ok(());
        }

        let mut process = Command::new(&self.lock_command)
            .env("WAYLAND_DISPLAY", &self.wayland_display)
            .spawn()
            .map_err(|error| zbus::fdo::Error::Failed(error.to_string()))?;
        *running = true;
        // A blocking waiter reaps the locker the moment it exits, so the
        // D-Bus thread never has to poll for it.
        let flag = self.lock_running.clone();
        let spawned = thread::Builder::new()
            .name("pantheon-locker-reaper".into())
            .spawn(move || {
                if let Err(error) = process.wait() {
                    tracing::warn!(%error, "could not reap the session locker");
                }
                *flag.lock().expect("lock child poisoned") = false;
            });
        if let Err(error) = spawned {
            *running = false;
            return Err(zbus::fdo::Error::Failed(error.to_string()));
        }
        Ok(())
    }

    fn get_active(&self) -> bool {
        self.active.load(Ordering::Acquire)
    }

    fn set_active(&self, active: bool) -> zbus::fdo::Result<()> {
        if active {
            self.lock()?;
        }
        // A caller cannot unlock the session through this legacy API; the
        // authenticated session-lock client owns unlock_and_destroy.
        Ok(())
    }

    fn get_active_time(&self) -> u32 {
        self.active_since
            .lock()
            .expect("lock timer poisoned")
            .map(|since| since.elapsed().as_secs().min(u32::MAX as u64) as u32)
            .unwrap_or(0)
    }

    #[zbus(signal)]
    async fn active_changed(emitter: &SignalEmitter<'_>, new_value: bool) -> zbus::Result<()>;
}

struct ShellCompatContext {
    bindings: Arc<Mutex<GrabTable>>,
    active: Arc<AtomicBool>,
    active_since: Arc<Mutex<Option<Instant>>>,
    osd: Arc<Mutex<Option<ShellOsd>>>,
    redraw_sender: Sender<()>,
    osd_expiry: mpsc::Sender<Instant>,
    wayland_display: OsString,
    receiver: mpsc::Receiver<ShellEvent>,
    /// Signalled once the Shell and ScreenSaver names are owned.
    ready: mpsc::Sender<()>,
}

fn serve_shell_compat(context: ShellCompatContext) {
    let ShellCompatContext {
        bindings,
        active,
        active_since,
        osd,
        redraw_sender,
        osd_expiry,
        wayland_display,
        receiver,
        ready,
    } = context;
    let connection = match Connection::session() {
        Ok(connection) => connection,
        Err(error) => {
            tracing::warn!(%error, "cannot connect to the session bus; Shell keybindings are disabled");
            return;
        }
    };

    if let Err(error) = connection.object_server().at(
        OBJECT_PATH,
        ShellKeyGrabber {
            bindings: bindings.clone(),
            osd,
            redraw_sender,
            osd_expiry,
        },
    ) {
        tracing::warn!(%error, "cannot register the Shell keybinding compatibility interface");
        return;
    }
    if let Err(error) = connection.request_name(BUS_NAME) {
        tracing::warn!(%error, "cannot own the Shell keybinding compatibility name");
        return;
    }

    let lock_command = lock_command(
        std::env::var_os("PANTHEON_LOCK_COMMAND"),
        std::path::Path::new(STYLED_LOCKER).is_file(),
    );
    let lock_running = Arc::new(Mutex::new(false));
    let screensaver = ScreenSaverCompat {
        wayland_display,
        lock_command,
        active,
        active_since,
        lock_running,
    };
    let idle_locker = screensaver.clone();
    if let Err(error) = connection
        .object_server()
        .at(SCREENSAVER_OBJECT_PATH, screensaver)
    {
        tracing::warn!(%error, "cannot register the ScreenSaver compatibility interface");
        return;
    }
    if let Err(error) = connection.request_name(SCREENSAVER_BUS_NAME) {
        tracing::warn!(%error, "cannot own the ScreenSaver compatibility name");
        return;
    }

    let watcher_connection = connection.clone();
    if let Err(error) = thread::Builder::new()
        .name("pantheon-shell-grabs".into())
        .spawn(move || release_grabs_of_departed_clients(&watcher_connection, bindings))
    {
        tracing::warn!(%error, "cannot start the key grab watcher");
    }

    tracing::info!("serving Shell accelerator and ScreenSaver compatibility interfaces");
    let _ = ready.send(());
    loop {
        match receiver.recv() {
            Ok(ShellEvent::AcceleratorActivated { id, owner }) => {
                let parameters = HashMap::<String, OwnedValue>::new();
                if let Err(error) = connection.emit_signal(
                    Some(owner.as_str()),
                    OBJECT_PATH,
                    INTERFACE,
                    "AcceleratorActivated",
                    &(id, parameters),
                ) {
                    tracing::warn!(%error, "could not emit AcceleratorActivated");
                }
            }
            Ok(ShellEvent::Lock) => {
                if let Err(error) = idle_locker.lock() {
                    tracing::warn!(%error, "could not start the session locker");
                }
            }
            Ok(ShellEvent::ActiveChanged(active)) => {
                if let Err(error) = connection.emit_signal(
                    None::<&str>,
                    SCREENSAVER_OBJECT_PATH,
                    SCREENSAVER_INTERFACE,
                    "ActiveChanged",
                    &(active,),
                ) {
                    tracing::warn!(%error, "could not emit ScreenSaver ActiveChanged");
                }
            }
            Err(_) => return,
        }
    }
}

/// The elementary-styled gtklock wrapper shipped with the session package.
const STYLED_LOCKER: &str = "/usr/bin/pantheon-lock";

/// `PANTHEON_LOCK_COMMAND` wins; otherwise the styled wrapper when it is
/// installed, else stock gtklock.
fn lock_command(configured: Option<OsString>, styled_installed: bool) -> OsString {
    configured
        .filter(|command| !command.is_empty())
        .unwrap_or_else(|| {
            OsString::from(if styled_installed {
                STYLED_LOCKER
            } else {
                "gtklock"
            })
        })
}

fn run_osd_expiry(receiver: mpsc::Receiver<Instant>, redraw_sender: Sender<()>) {
    loop {
        let mut deadline = match receiver.recv() {
            Ok(deadline) => deadline,
            Err(_) => return,
        };
        loop {
            let wait = deadline.saturating_duration_since(Instant::now());
            match receiver.recv_timeout(wait) {
                Ok(next_deadline) => deadline = next_deadline,
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    let _ = redraw_sender.send(());
                    break;
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => return,
            }
        }
    }
}

pub(crate) fn parse_accelerator(value: &str, _grab_flags: u32) -> Option<ParsedAccelerator> {
    let mut remaining = value.trim();
    let mut modifiers = AcceleratorModifiers::default();
    while remaining.starts_with('<') {
        let end = remaining.find('>')?;
        let modifier = remaining[1..end].to_ascii_lowercase();
        match modifier.as_str() {
            "control" | "ctrl" | "primary" => modifiers.ctrl = true,
            "alt" | "mod1" => modifiers.alt = true,
            "shift" => modifiers.shift = true,
            "super" | "meta" | "logo" | "mod4" => modifiers.logo = true,
            _ => return None,
        }
        remaining = &remaining[end + 1..];
    }

    let key_name = remaining.trim_start_matches('+');
    if key_name.is_empty() {
        return None;
    }
    let keysym = xkb::keysym_from_name(key_name, xkb::KEYSYM_CASE_INSENSITIVE);
    if keysym == xkb::keysyms::KEY_NoSymbol.into() {
        return None;
    }
    Some(ParsedAccelerator { keysym, modifiers })
}

pub(crate) fn matches_accelerator(
    accelerator: ParsedAccelerator,
    keysym: Keysym,
    modifiers: &ModifiersState,
) -> bool {
    let expected = accelerator.keysym.raw();
    let actual = keysym.raw();
    let expected_char = char::from_u32(expected);
    let actual_char = char::from_u32(actual);
    let ascii_letter = expected_char.is_some_and(|key| key.is_ascii_alphabetic())
        && actual_char.is_some_and(|key| key.is_ascii_alphabetic());
    let keys_match = if ascii_letter {
        expected_char
            .unwrap()
            .eq_ignore_ascii_case(&actual_char.unwrap())
    } else {
        expected == actual
    };
    let shift_matches = accelerator.modifiers.shift == modifiers.shift
        || (ascii_letter && !accelerator.modifiers.shift);

    keys_match
        && accelerator.modifiers.ctrl == modifiers.ctrl
        && accelerator.modifiers.alt == modifiers.alt
        && accelerator.modifiers.logo == modifiers.logo
        && shift_matches
}

fn same_accelerator(left: ParsedAccelerator, right: ParsedAccelerator) -> bool {
    left.keysym == right.keysym && left.modifiers == right.modifiers
}

#[cfg(test)]
mod lock_command_tests {
    use super::{STYLED_LOCKER, lock_command};
    use std::ffi::OsString;

    #[test]
    fn styled_locker_is_the_default_when_installed() {
        assert_eq!(lock_command(None, true), OsString::from(STYLED_LOCKER));
        assert_eq!(lock_command(None, false), OsString::from("gtklock"));
        assert_eq!(
            lock_command(Some(OsString::from("swaylock")), true),
            OsString::from("swaylock")
        );
        assert_eq!(
            lock_command(Some(OsString::new()), true),
            OsString::from(STYLED_LOCKER)
        );
    }
}

#[cfg(test)]
mod grab_table_tests {
    use super::{GrabTable, parse_accelerator};

    const GSD: &str = ":1.20";
    const GSD_RESTARTED: &str = ":1.95";
    const OTHER: &str = ":1.31";

    fn key(name: &str) -> super::ParsedAccelerator {
        parse_accelerator(name, 0).expect("test accelerator parses")
    }

    #[test]
    fn restarted_client_regrabs_keys_its_predecessor_held() {
        let mut table = GrabTable::default();
        assert_ne!(table.grab(GSD, key("XF86AudioRaiseVolume")), 0);
        assert_ne!(table.grab(GSD, key("XF86AudioMute")), 0);

        // The restarted client is refused while the dead one's grabs linger ...
        assert_eq!(table.grab(GSD_RESTARTED, key("XF86AudioRaiseVolume")), 0);
        // ... and succeeds once the bus reports the old connection gone.
        assert_eq!(table.drop_owner(GSD), 2);
        assert_ne!(table.grab(GSD_RESTARTED, key("XF86AudioRaiseVolume")), 0);
    }

    #[test]
    fn a_live_clients_key_is_not_stolen() {
        let mut table = GrabTable::default();
        let held = table.grab(GSD, key("XF86AudioMute"));
        assert_ne!(held, 0);
        assert_eq!(table.grab(OTHER, key("XF86AudioMute")), 0);
        assert_eq!(table.release(OTHER, &[held]), 0);
        assert_eq!(table.release(GSD, &[held]), 1);
    }

    #[test]
    fn regrab_before_release_keeps_the_key() {
        let mut table = GrabTable::default();
        let old = table.grab(GSD, key("XF86AudioLowerVolume"));
        let new = table.grab(GSD, key("XF86AudioLowerVolume"));
        assert_ne!(new, 0);
        assert_ne!(new, old);
        // gsd then releases the id it replaced: the fresh grab must survive.
        assert_eq!(table.release(GSD, &[old]), 0);
        assert_eq!(table.bindings.len(), 1);
        assert_eq!(table.bindings[0].id, new);
    }

    #[test]
    fn ids_are_never_zero_and_survive_wraparound() {
        let mut table = GrabTable {
            next_id: u32::MAX,
            ..GrabTable::default()
        };
        let first = table.grab(GSD, key("XF86AudioMute"));
        let second = table.grab(GSD, key("XF86AudioPlay"));
        assert_eq!(first, u32::MAX);
        assert_eq!(second, 1);
    }
}
