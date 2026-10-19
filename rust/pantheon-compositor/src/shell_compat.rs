use std::{
    collections::HashMap,
    ffi::OsString,
    process::{Child, Command},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    thread,
    time::{Duration, Instant},
};

use smithay::input::keyboard::{Keysym, ModifiersState, xkb};
use zbus::{blocking::Connection, interface, object_server::SignalEmitter, zvariant::OwnedValue};

const BUS_NAME: &str = "org.gnome.Shell";
const OBJECT_PATH: &str = "/org/gnome/Shell";
const INTERFACE: &str = "org.gnome.Shell";
const SCREENSAVER_BUS_NAME: &str = "org.gnome.ScreenSaver";
const SCREENSAVER_OBJECT_PATH: &str = "/org/gnome/ScreenSaver";
const SCREENSAVER_INTERFACE: &str = "org.gnome.ScreenSaver";

#[derive(Clone, Copy)]
enum ShellEvent {
    AcceleratorActivated(u32),
    ActiveChanged(bool),
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

#[derive(Clone, Copy, Debug)]
struct KeyBinding {
    id: u32,
    accelerator: ParsedAccelerator,
}

#[derive(Clone)]
pub struct ShellCompatHandle {
    bindings: Arc<Mutex<Vec<KeyBinding>>>,
    events: mpsc::Sender<ShellEvent>,
    active: Arc<AtomicBool>,
    active_since: Arc<Mutex<Option<Instant>>>,
}

impl ShellCompatHandle {
    pub fn start(wayland_display: OsString) -> Self {
        let bindings = Arc::new(Mutex::new(Vec::new()));
        let (events, receiver) = mpsc::channel();
        let active = Arc::new(AtomicBool::new(false));
        let active_since = Arc::new(Mutex::new(None));
        let service_bindings = bindings.clone();
        let service_active = active.clone();
        let service_active_since = active_since.clone();
        thread::Builder::new()
            .name("pantheon-shell-dbus".into())
            .spawn(move || {
                serve_shell_compat(
                    service_bindings,
                    service_active,
                    service_active_since,
                    wayland_display,
                    receiver,
                )
            })
            .expect("failed to start shell compatibility D-Bus thread");
        Self {
            bindings,
            events,
            active,
            active_since,
        }
    }

    pub fn activate_key(&self, keysym: Keysym, modifiers: &ModifiersState) -> bool {
        let matched = {
            let bindings = self.bindings.lock().expect("keybinding lock poisoned");
            bindings
                .iter()
                .filter(|binding| matches_accelerator(binding.accelerator, keysym, modifiers))
                .map(|binding| binding.id)
                .collect::<Vec<_>>()
        };

        if matched.is_empty() {
            return false;
        }
        for id in matched {
            let _ = self.events.send(ShellEvent::AcceleratorActivated(id));
        }
        true
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
    bindings: Arc<Mutex<Vec<KeyBinding>>>,
    next_id: u32,
}

struct ScreenSaverCompat {
    wayland_display: OsString,
    lock_command: OsString,
    active: Arc<AtomicBool>,
    active_since: Arc<Mutex<Option<Instant>>>,
    lock_child: Arc<Mutex<Option<Child>>>,
}

#[interface(name = "org.gnome.Shell")]
impl ShellKeyGrabber {
    fn grab_accelerator(&mut self, accelerator: String, _mode_flags: u32, grab_flags: u32) -> u32 {
        self.grab_one(&accelerator, grab_flags)
    }

    fn grab_accelerators(&mut self, accelerators: Vec<(String, u32, u32)>) -> Vec<u32> {
        accelerators
            .into_iter()
            .map(|(accelerator, _mode_flags, grab_flags)| self.grab_one(&accelerator, grab_flags))
            .collect()
    }

    fn ungrab_accelerator(&mut self, action: u32) -> bool {
        self.remove_bindings(&[action]) > 0
    }

    fn ungrab_accelerators(&mut self, actions: Vec<u32>) -> bool {
        let removed = self.remove_bindings(&actions);
        removed == actions.len()
    }

    fn show_osd(&self, _parameters: HashMap<String, OwnedValue>) {}

    #[zbus(signal)]
    async fn accelerator_activated(
        emitter: &SignalEmitter<'_>,
        action: u32,
        parameters_dict: HashMap<String, OwnedValue>,
    ) -> zbus::Result<()>;
}

impl ShellKeyGrabber {
    fn grab_one(&mut self, accelerator: &str, grab_flags: u32) -> u32 {
        let Some(parsed) = parse_accelerator(accelerator, grab_flags) else {
            return 0;
        };
        let mut bindings = self.bindings.lock().expect("keybinding lock poisoned");
        if bindings
            .iter()
            .any(|binding| same_accelerator(binding.accelerator, parsed))
        {
            return 0;
        }

        let id = self.next_id;
        self.next_id = self.next_id.wrapping_add(1).max(1);
        bindings.push(KeyBinding {
            id,
            accelerator: parsed,
        });
        id
    }

    fn remove_bindings(&self, actions: &[u32]) -> usize {
        let mut bindings = self.bindings.lock().expect("keybinding lock poisoned");
        let initial_len = bindings.len();
        bindings.retain(|binding| !actions.contains(&binding.id));
        initial_len - bindings.len()
    }
}

#[interface(name = "org.gnome.ScreenSaver")]
impl ScreenSaverCompat {
    fn lock(&self) -> zbus::fdo::Result<()> {
        if self.active.load(Ordering::Acquire) {
            return Ok(());
        }

        let mut child = self.lock_child.lock().expect("lock child poisoned");
        if let Some(running) = child.as_mut() {
            match running.try_wait() {
                Ok(None) => return Ok(()),
                Ok(Some(_)) => *child = None,
                Err(error) => return Err(zbus::fdo::Error::Failed(error.to_string())),
            }
        }

        let process = Command::new(&self.lock_command)
            .env("WAYLAND_DISPLAY", &self.wayland_display)
            .spawn()
            .map_err(|error| zbus::fdo::Error::Failed(error.to_string()))?;
        *child = Some(process);
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

fn serve_shell_compat(
    bindings: Arc<Mutex<Vec<KeyBinding>>>,
    active: Arc<AtomicBool>,
    active_since: Arc<Mutex<Option<Instant>>>,
    wayland_display: OsString,
    receiver: mpsc::Receiver<ShellEvent>,
) {
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
            bindings,
            next_id: 1,
        },
    ) {
        tracing::warn!(%error, "cannot register the Shell keybinding compatibility interface");
        return;
    }
    if let Err(error) = connection.request_name(BUS_NAME) {
        tracing::warn!(%error, "cannot own the Shell keybinding compatibility name");
        return;
    }

    let lock_command =
        std::env::var_os("PANTHEON_LOCK_COMMAND").unwrap_or_else(|| OsString::from("gtklock"));
    let lock_child = Arc::new(Mutex::new(None));
    if let Err(error) = connection.object_server().at(
        SCREENSAVER_OBJECT_PATH,
        ScreenSaverCompat {
            wayland_display,
            lock_command,
            active,
            active_since,
            lock_child: lock_child.clone(),
        },
    ) {
        tracing::warn!(%error, "cannot register the ScreenSaver compatibility interface");
        return;
    }
    if let Err(error) = connection.request_name(SCREENSAVER_BUS_NAME) {
        tracing::warn!(%error, "cannot own the ScreenSaver compatibility name");
        return;
    }

    tracing::info!("serving Shell accelerator and ScreenSaver compatibility interfaces");
    loop {
        {
            let mut child = lock_child.lock().expect("lock child poisoned");
            if let Some(running) = child.as_mut() {
                match running.try_wait() {
                    Ok(Some(_)) => {
                        *child = None;
                    }
                    Ok(None) => {}
                    Err(error) => tracing::warn!(%error, "could not reap the session locker"),
                }
            }
        }
        match receiver.recv_timeout(Duration::from_millis(100)) {
            Ok(ShellEvent::AcceleratorActivated(action)) => {
                let parameters = HashMap::<String, OwnedValue>::new();
                if let Err(error) = connection.emit_signal(
                    None::<&str>,
                    OBJECT_PATH,
                    INTERFACE,
                    "AcceleratorActivated",
                    &(action, parameters),
                ) {
                    tracing::warn!(%error, "could not emit AcceleratorActivated");
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
            Err(mpsc::RecvTimeoutError::Timeout) => {}
            Err(mpsc::RecvTimeoutError::Disconnected) => return,
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
