//! User idle time for gnome-settings-daemon and gnome-session.
//!
//! gsd-power dims and blanks the screen, and gnome-session tracks presence,
//! through Mutter's `org.gnome.Mutter.IdleMonitor` (found with an
//! ObjectManager at `/org/gnome/Mutter/IdleMonitor`, object `.../Core`).
//! Without it the screen never blanks on its own.
//!
//! The compositor thread only stores the time of the last input event in an
//! atomic. It messages the D-Bus thread when input arrives after at least a
//! second without any, or while a "user active" watch is waiting, so steady
//! typing or pointer motion costs one atomic store per event. The D-Bus
//! thread sleeps until the next watch deadline or message: no polling.
//!
//! An idle inhibitor (zwp_idle_inhibit_v1, e.g. a playing video) holds idle
//! time at zero, as Mutter does; it ending does not count as user activity.

use std::{
    collections::BTreeMap,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicU64, Ordering},
        mpsc,
    },
    thread,
    time::{Duration, Instant},
};

use zbus::{blocking::Connection, interface};

const BUS_NAME: &str = "org.gnome.Mutter.IdleMonitor";
const MANAGER_PATH: &str = "/org/gnome/Mutter/IdleMonitor";
const CORE_PATH: &str = "/org/gnome/Mutter/IdleMonitor/Core";
const INTERFACE: &str = "org.gnome.Mutter.IdleMonitor";
/// Input after this long without any input is reported to the D-Bus thread.
const REPORT_AFTER_MS: u64 = 1_000;
/// Defensive cap: watches of a client that died without removing them leak.
const MAX_WATCHES: usize = 512;

/// Pure watch bookkeeping, with Mutter's semantics: an idle watch fires once
/// each time idle time reaches its interval and re-arms on activity; a user
/// active watch fires once on the next activity and is then removed.
#[derive(Debug, Default)]
pub struct Watches {
    next_id: u32,
    idle: BTreeMap<u32, IdleWatch>,
    user_active: Vec<u32>,
}

#[derive(Debug)]
struct IdleWatch {
    interval_ms: u64,
    fired: bool,
}

impl Watches {
    fn allocate(&mut self) -> Option<u32> {
        if self.idle.len() + self.user_active.len() >= MAX_WATCHES {
            return None;
        }
        self.next_id = self.next_id.wrapping_add(1).max(1);
        Some(self.next_id)
    }

    /// Add an idle watch. A watch whose interval has already passed fires on
    /// the next `due` call, as in Mutter.
    pub fn add_idle(&mut self, interval_ms: u64) -> Option<u32> {
        let id = self.allocate()?;
        self.idle.insert(
            id,
            IdleWatch {
                interval_ms: interval_ms.max(1),
                fired: false,
            },
        );
        Some(id)
    }

    pub fn add_user_active(&mut self) -> Option<u32> {
        let id = self.allocate()?;
        self.user_active.push(id);
        Some(id)
    }

    pub fn remove(&mut self, id: u32) -> bool {
        let before = self.idle.len() + self.user_active.len();
        self.idle.remove(&id);
        self.user_active.retain(|watch| *watch != id);
        before != self.idle.len() + self.user_active.len()
    }

    pub fn wants_activity(&self) -> bool {
        !self.user_active.is_empty()
    }

    /// The user did something: fire and drop user-active watches, re-arm idle ones.
    pub fn on_activity(&mut self) -> Vec<u32> {
        for watch in self.idle.values_mut() {
            watch.fired = false;
        }
        std::mem::take(&mut self.user_active)
    }

    /// Idle watches whose interval `idle_ms` has reached; each fires once.
    pub fn due(&mut self, idle_ms: u64) -> Vec<u32> {
        self.idle
            .iter_mut()
            .filter(|(_, watch)| !watch.fired && watch.interval_ms <= idle_ms)
            .map(|(id, watch)| {
                watch.fired = true;
                *id
            })
            .collect()
    }

    /// Milliseconds until the next idle watch fires, given the current idle time.
    pub fn next_deadline_ms(&self, idle_ms: u64) -> Option<u64> {
        self.idle
            .values()
            .filter(|watch| !watch.fired)
            .map(|watch| watch.interval_ms.saturating_sub(idle_ms))
            .min()
    }
}

/// Activity clock shared by the compositor thread and the D-Bus thread.
#[derive(Debug)]
struct Shared {
    base: Instant,
    /// Milliseconds since `base` of the last input event.
    last_activity_ms: AtomicU64,
    /// Milliseconds since `base` at which the last inhibitor went away.
    inhibit_ended_ms: AtomicU64,
    inhibited: AtomicBool,
    /// A user-active watch is waiting, so every input event must be reported.
    wants_activity: AtomicBool,
}

impl Shared {
    fn now_ms(&self) -> u64 {
        self.base.elapsed().as_millis() as u64
    }

    /// Idle time as clients see it: zero while inhibited, and counted from the
    /// later of the last input and the end of the last inhibition.
    fn idle_ms(&self) -> u64 {
        if self.inhibited.load(Ordering::Acquire) {
            return 0;
        }
        let since = self
            .last_activity_ms
            .load(Ordering::Acquire)
            .max(self.inhibit_ended_ms.load(Ordering::Acquire));
        self.now_ms().saturating_sub(since)
    }
}

enum Event {
    Activity,
    InhibitChanged,
    WatchesChanged,
}

/// The compositor thread's handle to the idle monitor service.
#[derive(Clone)]
pub struct IdleMonitorHandle {
    shared: Arc<Shared>,
    events: mpsc::Sender<Event>,
}

impl IdleMonitorHandle {
    pub fn start() -> Self {
        let shared = Arc::new(Shared {
            base: Instant::now(),
            last_activity_ms: AtomicU64::new(0),
            inhibit_ended_ms: AtomicU64::new(0),
            inhibited: AtomicBool::new(false),
            wants_activity: AtomicBool::new(false),
        });
        let (events, receiver) = mpsc::channel();
        let service_shared = shared.clone();
        let service_events = events.clone();
        if let Err(error) = thread::Builder::new()
            .name("pantheon-idle-monitor-dbus".into())
            .spawn(move || serve(service_shared, service_events, receiver))
        {
            tracing::warn!(%error, "cannot start the idle monitor D-Bus thread");
        }
        Self { shared, events }
    }

    /// Record user input. Cheap enough to call for every input event.
    pub fn activity(&self) {
        let now = self.shared.now_ms();
        let previous = self.shared.last_activity_ms.swap(now, Ordering::AcqRel);
        if now.saturating_sub(previous) >= REPORT_AFTER_MS
            || self.shared.wants_activity.load(Ordering::Acquire)
        {
            let _ = self.events.send(Event::Activity);
        }
    }

    /// Current idle time in milliseconds (zero while an inhibitor is active).
    pub fn idle_ms(&self) -> u64 {
        self.shared.idle_ms()
    }

    pub fn set_inhibited(&self, inhibited: bool) {
        let was = self.shared.inhibited.swap(inhibited, Ordering::AcqRel);
        if was == inhibited {
            return;
        }
        if !inhibited {
            self.shared
                .inhibit_ended_ms
                .store(self.shared.now_ms(), Ordering::Release);
        }
        let _ = self.events.send(Event::InhibitChanged);
    }
}

struct IdleMonitorServer {
    shared: Arc<Shared>,
    watches: Arc<Mutex<Watches>>,
    events: mpsc::Sender<Event>,
}

impl IdleMonitorServer {
    fn changed(&self) {
        let _ = self.events.send(Event::WatchesChanged);
    }

    fn watches(&self) -> zbus::fdo::Result<std::sync::MutexGuard<'_, Watches>> {
        self.watches
            .lock()
            .map_err(|_| zbus::fdo::Error::Failed("idle monitor state is unavailable".into()))
    }
}

#[interface(name = "org.gnome.Mutter.IdleMonitor")]
impl IdleMonitorServer {
    fn get_idletime(&self) -> u64 {
        self.shared.idle_ms()
    }

    fn add_idle_watch(&self, interval: u64) -> zbus::fdo::Result<u32> {
        let id = self
            .watches()?
            .add_idle(interval)
            .ok_or_else(|| zbus::fdo::Error::LimitsExceeded("too many idle watches".into()))?;
        self.changed();
        Ok(id)
    }

    fn add_user_active_watch(&self) -> zbus::fdo::Result<u32> {
        let id = self
            .watches()?
            .add_user_active()
            .ok_or_else(|| zbus::fdo::Error::LimitsExceeded("too many idle watches".into()))?;
        self.shared.wants_activity.store(true, Ordering::Release);
        self.changed();
        Ok(id)
    }

    fn remove_watch(&self, id: u32) -> zbus::fdo::Result<()> {
        self.watches()?.remove(id);
        self.changed();
        Ok(())
    }

    fn reset_idletime(&self) {
        self.shared
            .last_activity_ms
            .store(self.shared.now_ms(), Ordering::Release);
        let _ = self.events.send(Event::Activity);
    }

    #[zbus(signal)]
    async fn watch_fired(
        emitter: &zbus::object_server::SignalEmitter<'_>,
        id: u32,
    ) -> zbus::Result<()>;
}

fn serve(shared: Arc<Shared>, events: mpsc::Sender<Event>, receiver: mpsc::Receiver<Event>) {
    let connection = match Connection::session() {
        Ok(connection) => connection,
        Err(error) => {
            tracing::warn!(%error, "cannot connect to the session bus; idle monitor is disabled");
            return;
        }
    };
    let watches = Arc::new(Mutex::new(Watches::default()));
    let server = IdleMonitorServer {
        shared: shared.clone(),
        watches: watches.clone(),
        events,
    };
    let registered = connection
        .object_server()
        .at(MANAGER_PATH, zbus::fdo::ObjectManager)
        .and_then(|_| connection.object_server().at(CORE_PATH, server));
    if let Err(error) = registered {
        tracing::warn!(%error, "cannot register the Mutter idle monitor interface");
        return;
    }
    if let Err(error) = connection.request_name(BUS_NAME) {
        tracing::warn!(%error, "cannot own the Mutter idle monitor name");
        return;
    }
    tracing::info!("serving Mutter idle monitor watches");

    let fire = |ids: Vec<u32>| {
        for id in ids {
            if let Err(error) =
                connection.emit_signal(None::<&str>, CORE_PATH, INTERFACE, "WatchFired", &(id,))
            {
                tracing::warn!(%error, id, "could not emit idle WatchFired");
            }
        }
    };

    loop {
        let timeout = {
            let watches = watches.lock().expect("idle watches lock poisoned");
            if shared.inhibited.load(Ordering::Acquire) {
                None
            } else {
                watches
                    .next_deadline_ms(shared.idle_ms())
                    .map(Duration::from_millis)
            }
        };
        let event = match timeout {
            Some(timeout) => match receiver.recv_timeout(timeout) {
                Ok(event) => Some(event),
                Err(mpsc::RecvTimeoutError::Timeout) => None,
                Err(mpsc::RecvTimeoutError::Disconnected) => return,
            },
            None => match receiver.recv() {
                Ok(event) => Some(event),
                Err(_) => return,
            },
        };
        let mut guard = watches.lock().expect("idle watches lock poisoned");
        let mut fired = Vec::new();
        if matches!(event, Some(Event::Activity)) {
            fired.extend(guard.on_activity());
        }
        // An inhibitor ending restarts the idle count; it is not user activity,
        // so it re-arms idle watches without firing user-active ones.
        if matches!(event, Some(Event::InhibitChanged)) && !shared.inhibited.load(Ordering::Acquire)
        {
            for watch in guard.idle.values_mut() {
                watch.fired = false;
            }
        }
        if !shared.inhibited.load(Ordering::Acquire) {
            fired.extend(guard.due(shared.idle_ms()));
        }
        shared
            .wants_activity
            .store(guard.wants_activity(), Ordering::Release);
        drop(guard);
        fire(fired);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn idle_watch_fires_once_and_rearms_on_activity() {
        let mut watches = Watches::default();
        let id = watches.add_idle(900_000).unwrap();
        assert_eq!(watches.next_deadline_ms(0), Some(900_000));
        assert!(watches.due(899_999).is_empty());
        assert_eq!(watches.due(900_000), vec![id]);
        assert!(
            watches.due(950_000).is_empty(),
            "fires once per idle period"
        );
        assert_eq!(watches.next_deadline_ms(950_000), None);
        assert!(watches.on_activity().is_empty());
        assert_eq!(watches.next_deadline_ms(0), Some(900_000));
    }

    #[test]
    fn user_active_watch_fires_once_then_disappears() {
        let mut watches = Watches::default();
        let idle = watches.add_idle(10).unwrap();
        let active = watches.add_user_active().unwrap();
        assert!(watches.wants_activity());
        assert_ne!(idle, active);
        assert_eq!(watches.on_activity(), vec![active]);
        assert!(!watches.wants_activity());
        assert!(watches.on_activity().is_empty());
    }

    #[test]
    fn removed_watches_never_fire() {
        let mut watches = Watches::default();
        let a = watches.add_idle(5).unwrap();
        let b = watches.add_idle(10).unwrap();
        assert!(watches.remove(a));
        assert!(!watches.remove(a));
        assert_eq!(watches.due(20), vec![b]);
    }

    #[test]
    fn watch_count_is_capped() {
        let mut watches = Watches::default();
        for _ in 0..MAX_WATCHES {
            assert!(watches.add_idle(1).is_some());
        }
        assert!(watches.add_user_active().is_none());
    }

    #[test]
    fn inhibition_holds_idle_time_at_zero_and_restarts_it() {
        let shared = Shared {
            base: Instant::now() - Duration::from_secs(100),
            last_activity_ms: AtomicU64::new(0),
            inhibit_ended_ms: AtomicU64::new(0),
            inhibited: AtomicBool::new(true),
            wants_activity: AtomicBool::new(false),
        };
        assert_eq!(shared.idle_ms(), 0);
        shared.inhibited.store(false, Ordering::Release);
        assert!(shared.idle_ms() >= 100_000);
        shared
            .inhibit_ended_ms
            .store(shared.now_ms(), Ordering::Release);
        assert!(shared.idle_ms() < 1_000);
    }
}
