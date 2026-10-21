//! Orchestration: owns the consent machine, the live peer and the viewer's
//! signalling channel. Transport-agnostic so the same code serves the
//! WebSocket listener, the D-Bus interface and the tests.

use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex, Weak};
use std::time::Duration;

use remote_core::audit::AuditSink;
use remote_core::clock::Clock;
use remote_core::consent::{
    ConsentError, ConsentManager, Decision, Event, Grant, PendingRequest, Policy, Status,
};
use remote_core::input::{InputGate, Outcome};
use remote_core::protocol::{ClientMsg, HostEvent, ServerMsg};
use remote_rtc::host::{HostCallbacks, HostPeer, VideoParams};
use remote_rtc::{IceServer, LinkState, RtcConfig};
use serde::Serialize;
use tokio::sync::{broadcast, mpsc, oneshot, watch};

use crate::backend::Backend;
use crate::config::Config;
use crate::invite::{self, InviteInfo};

#[derive(Debug, Clone)]
pub enum UiEvent {
    /// Anything about the status changed; re-read [`Controller::status`].
    Status,
    /// A phone is asking to connect. The UI must show the consent prompt.
    ConsentRequested(PendingRequest),
}

#[derive(Debug, Clone, Serialize)]
pub struct UiStatus {
    pub enabled: bool,
    pub listen: Option<String>,
    pub backend: String,
    #[serde(flatten)]
    pub status: Status,
}

enum Decided {
    Granted(Grant),
    Denied(String),
}

struct LivePeer {
    peer: Arc<HostPeer>,
    gate: Arc<Mutex<InputGate>>,
    gen: u64,
}

struct Inner {
    consent: ConsentManager,
    waiters: HashMap<String, oneshot::Sender<Decided>>,
    peer: Option<LivePeer>,
    /// Bumped on every attach so a newer signalling socket supersedes an older one.
    gen: u64,
    viewer: Option<(u64, mpsc::UnboundedSender<ServerMsg>)>,
    resume_token: Option<String>,
    listen: Option<SocketAddr>,
}

pub struct Controller {
    inner: Mutex<Inner>,
    backend: Arc<dyn Backend>,
    cfg: Config,
    rtc: RtcConfig,
    clock: Arc<dyn Clock>,
    ui: broadcast::Sender<UiEvent>,
    enabled: watch::Sender<bool>,
}

pub fn rtc_from_config(cfg: &Config) -> RtcConfig {
    let mut ice_servers = Vec::new();
    if !cfg.stun.is_empty() {
        ice_servers.push(IceServer {
            urls: cfg.stun.clone(),
            username: String::new(),
            credential: String::new(),
        });
    }
    if let Some(t) = &cfg.turn {
        ice_servers.push(IceServer {
            urls: t.urls.clone(),
            username: t.username.clone(),
            credential: t.credential.clone(),
        });
    }
    RtcConfig {
        ice_servers,
        fps: cfg.fps,
        bitrate_bps: cfg.bitrate_kbps * 1000,
        keyframe_interval_s: cfg.keyframe_interval_s,
        ..RtcConfig::default()
    }
}

impl Controller {
    pub fn new(
        cfg: Config,
        rtc: RtcConfig,
        backend: Arc<dyn Backend>,
        clock: Arc<dyn Clock>,
        audit: Box<dyn AuditSink>,
        policy: Policy,
    ) -> Arc<Self> {
        let (ui, _) = broadcast::channel(64);
        let (enabled, _) = watch::channel(false);
        Arc::new(Self {
            inner: Mutex::new(Inner {
                consent: ConsentManager::new(policy, clock.clone(), audit),
                waiters: HashMap::new(),
                peer: None,
                gen: 0,
                viewer: None,
                resume_token: None,
                listen: None,
            }),
            backend,
            cfg,
            rtc,
            clock,
            ui,
            enabled,
        })
    }

    fn with<R>(&self, f: impl FnOnce(&mut Inner) -> R) -> R {
        f(&mut self.inner.lock().unwrap())
    }

    pub fn subscribe(&self) -> broadcast::Receiver<UiEvent> {
        self.ui.subscribe()
    }

    pub fn enabled_rx(&self) -> watch::Receiver<bool> {
        self.enabled.subscribe()
    }

    pub fn config(&self) -> &Config {
        &self.cfg
    }

    pub fn set_listen_addr(&self, addr: Option<SocketAddr>) {
        self.with(|i| i.listen = addr);
        let _ = self.ui.send(UiEvent::Status);
    }

    pub fn status(&self) -> UiStatus {
        let enabled = *self.enabled.borrow();
        let backend = self.backend.name().to_string();
        self.with(|i| UiStatus {
            enabled,
            listen: i.listen.map(|a| a.to_string()),
            backend,
            status: i.consent.status(),
        })
    }

    /// Turn sharing on or off. Off ends any session and revokes every invite.
    pub async fn set_enabled(self: &Arc<Self>, on: bool) {
        if !on {
            self.with(|i| {
                i.consent.end("sharing turned off");
                i.consent.cancel_invites();
            });
            self.pump().await;
        }
        self.enabled.send_replace(on);
        let _ = self.ui.send(UiEvent::Status);
    }

    pub fn create_invite(&self, allow_control: bool) -> Result<InviteInfo, String> {
        if !*self.enabled.borrow() {
            return Err("Sharing is off. Turn it on first.".into());
        }
        let port = self
            .with(|i| i.listen.map(|a| a.port()))
            .ok_or("The listener is not up yet.")?;
        let token = self
            .with(|i| i.consent.create_invite(allow_control))
            .map_err(|e| e.to_string())?;
        let hosts = invite::candidate_hosts(&self.cfg.advertise);
        let links = invite::build_links(&hosts, port, &token);
        let qr = links
            .first()
            .map(|l| invite::qr_rows(&l.url))
            .unwrap_or_default();
        let expires_ms = self.clock.now_ms() + self.with(|i| i.consent.policy().invite_ttl_ms);
        let _ = self.ui.send(UiEvent::Status);
        Ok(InviteInfo {
            links,
            qr,
            expires_ms,
            control_offered: allow_control,
        })
    }

    pub async fn decide(
        self: &Arc<Self>,
        request_id: &str,
        allow: bool,
        control: bool,
    ) -> Result<(), String> {
        let decision = if allow {
            Decision::Allow { control }
        } else {
            Decision::Deny
        };
        let result = self.with(|i| {
            let r = i.consent.decide(request_id, decision);
            if let Ok(Some(grant)) = &r {
                if let Some(w) = i.waiters.remove(request_id) {
                    let _ = w.send(Decided::Granted(grant.clone()));
                }
            }
            r
        });
        self.pump().await;
        result.map(|_| ()).map_err(|e| e.to_string())
    }

    pub async fn set_control(self: &Arc<Self>, control: bool) -> Result<(), String> {
        let r = self.with(|i| i.consent.set_control(control));
        self.pump().await;
        r.map_err(|e| e.to_string())
    }

    pub async fn stop(self: &Arc<Self>, reason: &str) {
        self.with(|i| i.consent.end(reason));
        self.pump().await;
    }

    /// Drive timers (consent timeout, grace, idle). Runs for the daemon's life.
    pub fn spawn_ticker(self: &Arc<Self>) {
        let me = Arc::downgrade(self);
        tokio::spawn(async move {
            let mut tick = tokio::time::interval(Duration::from_millis(500));
            loop {
                tick.tick().await;
                let Some(me) = me.upgrade() else { break };
                me.with(|i| i.consent.tick());
                me.pump().await;
            }
        });
    }

    /// Deliver the consent machine's pending effects.
    pub async fn pump(self: &Arc<Self>) {
        loop {
            let events = self.with(|i| i.consent.take_events());
            if events.is_empty() {
                break;
            }
            for ev in events {
                match ev {
                    Event::Requested(req) => {
                        let _ = self.ui.send(UiEvent::ConsentRequested(req));
                    }
                    Event::Denied { request_id, reason } => {
                        if let Some(w) = self.with(|i| i.waiters.remove(&request_id)) {
                            let _ = w.send(Decided::Denied(reason));
                        }
                    }
                    Event::Ended { reason, .. } => {
                        let (peer, viewer) = self.with(|i| {
                            i.resume_token = None;
                            (i.peer.take(), i.viewer.take())
                        });
                        if let Some(lp) = peer {
                            self.log_quality(&lp, &format!("session ended: {reason}"));
                            lp.peer.notify(HostEvent::Ended {
                                reason: reason.clone(),
                            });
                            // Give the data channel a moment to flush the notice.
                            tokio::time::sleep(Duration::from_millis(100)).await;
                            lp.peer.close().await;
                            lp.gate.lock().unwrap().release_all();
                        }
                        if let Some((_, tx)) = viewer {
                            let _ = tx.send(ServerMsg::Ended { reason });
                        }
                    }
                    Event::ModeChanged { control, .. } => {
                        if let Some(p) = self.with(|i| i.peer.as_ref().map(|p| p.peer.clone())) {
                            p.set_control(control);
                        }
                    }
                    Event::Granted(_) | Event::Attached { .. } | Event::Detached { .. } => {}
                }
            }
            let _ = self.ui.send(UiEvent::Status);
        }
        let _ = self.ui.send(UiEvent::Status);
    }

    /// One line per peer: how well the link did. Aggregates only; no content.
    fn log_quality(&self, lp: &LivePeer, why: &str) {
        let st = lp.peer.stats();
        let sent = st.frames_sent + st.frames_dropped;
        let drop_pct = if sent == 0 {
            0.0
        } else {
            st.frames_dropped as f64 * 100.0 / sent as f64
        };
        let kbps = if st.streamed_s > 0.5 {
            st.bytes_sent as f64 * 8.0 / 1000.0 / st.streamed_s
        } else {
            0.0
        };
        let detail = format!(
            "{why}; connect_ms={}; streamed_s={:.1}; frames={}; dropped={} ({drop_pct:.1}%); avg_kbps={kbps:.0}",
            st.connect_ms.map(|m| m.to_string()).unwrap_or_else(|| "none".into()),
            st.streamed_s,
            st.frames_sent,
            st.frames_dropped,
        );
        self.with(|i| i.consent.audit_note("link_quality", None, &detail));
    }

    fn callbacks(
        self: &Arc<Self>,
        gen: u64,
        gate: Arc<Mutex<InputGate>>,
        slot: Arc<Mutex<Weak<HostPeer>>>,
    ) -> HostCallbacks {
        let on_input = {
            let me = Arc::downgrade(self);
            let slot = slot.clone();
            Arc::new(move |ev: remote_core::protocol::InputEvent| {
                let Some(me) = me.upgrade() else { return };
                let control = me.with(|i| {
                    i.consent.note_activity();
                    i.consent.can_control()
                });
                let outcome = gate.lock().unwrap().handle(&ev, control, me.clock.now_ms());
                if let Outcome::Rejected(reason) = outcome {
                    if let Some(p) = slot.lock().unwrap().upgrade() {
                        p.notify(HostEvent::Rejected {
                            reason: reason.into(),
                        });
                    }
                }
            })
        };
        let on_state = {
            let me = Arc::downgrade(self);
            Arc::new(move |st: LinkState| {
                let Some(me) = me.upgrade() else { return };
                tokio::spawn(async move {
                    me.with(|i| {
                        // A superseded peer closing must not detach its successor.
                        if i.peer.as_ref().map(|p| p.gen) != Some(gen) {
                            return;
                        }
                        match st {
                            LinkState::Connected => {
                                if let Some(t) = i.resume_token.clone() {
                                    let _ = i.consent.attach(&t);
                                }
                            }
                            LinkState::Disconnected | LinkState::Failed | LinkState::Closed => {
                                i.consent.detach()
                            }
                            LinkState::Connecting => {}
                        }
                    });
                    me.pump().await;
                });
            })
        };
        HostCallbacks { on_input, on_state }
    }

    async fn handle_offer(
        self: &Arc<Self>,
        gen: u64,
        sdp: String,
        tx: &mpsc::UnboundedSender<ServerMsg>,
    ) {
        let existing = self.with(|i| {
            i.peer
                .as_ref()
                .filter(|p| p.gen == gen)
                .map(|p| p.peer.clone())
        });
        if let Some(peer) = existing {
            match peer.renegotiate(sdp).await {
                Ok(answer) => {
                    let _ = tx.send(ServerMsg::Answer { sdp: answer });
                }
                Err(e) => {
                    let _ = tx.send(ServerMsg::Error {
                        code: "renegotiate_failed".into(),
                        message: e.to_string(),
                    });
                }
            }
            return;
        }

        let backend = self.backend.clone();
        let (max_width, fps) = (self.cfg.max_width, self.cfg.fps);
        let streams = match tokio::task::spawn_blocking(move || backend.open(max_width, fps)).await
        {
            Ok(Ok(s)) => s,
            Ok(Err(e)) => {
                let _ = tx.send(ServerMsg::Error {
                    code: "capture_failed".into(),
                    message: e.to_string(),
                });
                return;
            }
            Err(e) => {
                let _ = tx.send(ServerMsg::Error {
                    code: "capture_failed".into(),
                    message: e.to_string(),
                });
                return;
            }
        };
        let gate = Arc::new(Mutex::new(InputGate::new(
            streams.input,
            self.clock.now_ms(),
        )));
        let slot = Arc::new(Mutex::new(Weak::new()));
        let control = self.with(|i| i.consent.can_control());
        let callbacks = self.callbacks(gen, gate.clone(), slot.clone());
        match HostPeer::accept(sdp, &self.rtc, callbacks, control).await {
            Ok((peer, answer)) => {
                let peer = Arc::new(peer);
                *slot.lock().unwrap() = Arc::downgrade(&peer);
                if let Err(e) = peer.start_video(streams.source, VideoParams::from(&self.rtc)) {
                    let _ = tx.send(ServerMsg::Error {
                        code: "encode_failed".into(),
                        message: e.to_string(),
                    });
                    peer.close().await;
                    return;
                }
                let old = self.with(|i| i.peer.replace(LivePeer { peer, gate, gen }));
                if let Some(old) = old {
                    self.log_quality(&old, "replaced by new connection");
                    old.peer.close().await;
                }
                let _ = tx.send(ServerMsg::Answer { sdp: answer });
            }
            Err(e) => {
                let _ = tx.send(ServerMsg::Error {
                    code: "offer_rejected".into(),
                    message: e.to_string(),
                });
            }
        }
    }

    /// Serve one viewer signalling connection until it ends.
    pub async fn serve_viewer(
        self: Arc<Self>,
        mut rx: mpsc::Receiver<ClientMsg>,
        tx: mpsc::UnboundedSender<ServerMsg>,
        remote: Option<std::net::SocketAddr>,
    ) {
        let err = |code: &str, message: &str| ServerMsg::Error {
            code: code.into(),
            message: message.into(),
        };

        let Ok(Some(ClientMsg::Hello {
            device,
            invite,
            resume,
            ..
        })) = tokio::time::timeout(Duration::from_secs(10), rx.recv()).await
        else {
            let _ = tx.send(err("hello_required", "Expected a hello message."));
            return;
        };
        let ip = remote
            .map(|a| a.ip().to_string())
            .unwrap_or_else(|| "unknown".into());
        self.with(|i| {
            i.consent.audit_note(
                "viewer_connected",
                Some(&device),
                &format!("ip={ip}; resume={}", resume.is_some()),
            )
        });
        if !*self.enabled.borrow() {
            let _ = tx.send(err("disabled", "Sharing is off on this computer."));
            return;
        }

        let grant = if let Some(invite) = invite {
            let (wtx, wrx) = oneshot::channel();
            let req = self.with(|i| {
                let r = i.consent.request(&invite, &device);
                if let Ok(req) = &r {
                    i.waiters.insert(req.id.clone(), wtx);
                }
                r
            });
            self.pump().await;
            let req = match req {
                Ok(r) => r,
                Err(ConsentError::Busy) => {
                    let _ = tx.send(err("busy", "Another device is connected or waiting."));
                    return;
                }
                Err(ConsentError::Auth(_)) => {
                    let _ = tx.send(err(
                        "invalid_invite",
                        "That link is invalid, used or expired.",
                    ));
                    return;
                }
                Err(e) => {
                    let _ = tx.send(err("rejected", &e.to_string()));
                    return;
                }
            };
            let wait_s = self.with(|i| i.consent.policy().consent_timeout_ms) / 1000;
            let _ = tx.send(ServerMsg::Pending {
                request_id: req.id.clone(),
                expires_in_s: wait_s,
            });
            match tokio::time::timeout(Duration::from_secs(wait_s + 5), wrx).await {
                Ok(Ok(Decided::Granted(g))) => g,
                Ok(Ok(Decided::Denied(reason))) => {
                    let _ = tx.send(ServerMsg::Denied { reason });
                    return;
                }
                _ => {
                    let _ = tx.send(ServerMsg::Denied {
                        reason: "Nobody answered in time.".into(),
                    });
                    return;
                }
            }
        } else if let Some(resume) = resume {
            let attached = self.with(|i| i.consent.attach(&resume));
            match attached {
                Ok(session) => {
                    let grace_ms = self.with(|i| i.consent.policy().grace_ms);
                    Grant {
                        session,
                        resume_token: resume,
                        grace_ms,
                    }
                }
                Err(_) => {
                    let _ = tx.send(err("resume_failed", "The session ended. Scan a new link."));
                    return;
                }
            }
        } else {
            let _ = tx.send(err("hello_required", "Expected an invite or resume token."));
            return;
        };

        // Attach (first time after a grant) and take over from any older socket.
        let gen = self.with(|i| {
            let _ = i.consent.attach(&grant.resume_token);
            i.resume_token = Some(grant.resume_token.clone());
            i.gen += 1;
            if let Some((_, old)) = i.viewer.replace((i.gen, tx.clone())) {
                let _ = old.send(ServerMsg::Error {
                    code: "replaced".into(),
                    message: "Another connection took over.".into(),
                });
            }
            i.gen
        });
        self.pump().await;
        let _ = tx.send(ServerMsg::Granted {
            session_id: grant.session.id.clone(),
            resume_token: grant.resume_token.clone(),
            control: grant.session.control,
            grace_s: grant.grace_ms / 1000,
            ice_servers: self
                .rtc
                .ice_servers
                .iter()
                .map(|s| remote_core::protocol::IceServerInfo {
                    urls: s.urls.clone(),
                    username: s.username.clone(),
                    credential: s.credential.clone(),
                })
                .collect(),
        });

        while let Some(msg) = rx.recv().await {
            // A newer socket may have superseded this one.
            if self.with(|i| i.viewer.as_ref().map(|v| v.0)) != Some(gen) {
                break;
            }
            match msg {
                ClientMsg::Offer { sdp } => self.handle_offer(gen, sdp, &tx).await,
                ClientMsg::Candidate {
                    candidate,
                    sdp_mid,
                    sdp_mline_index,
                } => {
                    if let Some(p) = self.with(|i| {
                        i.peer
                            .as_ref()
                            .filter(|p| p.gen == gen)
                            .map(|p| p.peer.clone())
                    }) {
                        let init = remote_rtc::RTCIceCandidateInit {
                            candidate,
                            sdp_mid,
                            sdp_mline_index,
                            username_fragment: None,
                            url: None,
                        };
                        if let Err(e) = p.add_remote_candidate(init).await {
                            tracing::debug!("candidate ignored: {e}");
                        }
                    }
                }
                ClientMsg::Bye => {
                    self.stop("the phone disconnected").await;
                    break;
                }
                ClientMsg::Hello { .. } => {
                    let _ = tx.send(err("unexpected", "Already connected."));
                }
            }
        }
        // Signalling socket closed. Media may continue; the peer's own state
        // callback decides when to start the grace period.
    }
}
