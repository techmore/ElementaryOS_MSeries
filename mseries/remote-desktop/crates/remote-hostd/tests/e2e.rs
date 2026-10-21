//! End-to-end through the real listener, signalling WebSocket, consent machine,
//! WebRTC and input gate, headless on 127.0.0.1 with the synthetic desktop.

use std::sync::Arc;
use std::time::Duration;

use futures::{SinkExt, StreamExt};
use remote_core::audit::MemoryAudit;
use remote_core::capture::TestPattern;
use remote_core::clock::SystemClock;
use remote_core::consent::{Phase, Policy};
use remote_core::protocol::{Button, ClientMsg, HostEvent, InputEvent, ServerMsg, PROTOCOL_VERSION};
use remote_hostd::backend::TestBackend;
use remote_hostd::config::Config;
use remote_hostd::controller::{Controller, UiEvent};
use remote_hostd::web::run_listener_manager;
use remote_rtc::viewer::ViewerPeer;
use remote_rtc::RtcConfig;
use tokio::net::TcpStream;
use tokio_tungstenite::tungstenite::client::IntoClientRequest;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::{connect_async, MaybeTlsStream, WebSocketStream};

type Ws = WebSocketStream<MaybeTlsStream<TcpStream>>;

struct Host {
    ctl: Arc<Controller>,
    backend: Arc<TestBackend>,
    audit: MemoryAudit,
    port: u16,
}

async fn host() -> Host {
    let cfg = Config { listen: "127.0.0.1:0".into(), backend: "test".into(), advertise: vec!["127.0.0.1".into()], ..Config::default() };
    let backend = Arc::new(TestBackend::default());
    let audit = MemoryAudit::default();
    let ctl = Controller::new(
        cfg,
        RtcConfig::loopback(),
        backend.clone(),
        Arc::new(SystemClock),
        Box::new(audit.clone()),
        Policy::default(),
    );
    ctl.spawn_ticker();
    tokio::spawn(run_listener_manager(ctl.clone()));
    ctl.set_enabled(true).await;
    let port = loop {
        if let Some(a) = ctl.status().listen {
            break a.rsplit(':').next().unwrap().parse().unwrap();
        }
        tokio::time::sleep(Duration::from_millis(20)).await;
    };
    Host { ctl, backend, audit, port }
}

fn token_of(url: &str) -> String {
    url.split("#i=").nth(1).unwrap().to_string()
}

async fn open(port: u16) -> Ws {
    connect_async(format!("ws://127.0.0.1:{port}/ws")).await.unwrap().0
}

async fn send(ws: &mut Ws, m: &ClientMsg) {
    ws.send(Message::Text(serde_json::to_string(m).unwrap().into())).await.unwrap();
}

async fn recv(ws: &mut Ws) -> ServerMsg {
    loop {
        match tokio::time::timeout(Duration::from_secs(10), ws.next()).await.expect("signalling timeout") {
            Some(Ok(Message::Text(t))) => return serde_json::from_str(&t).unwrap(),
            Some(Ok(Message::Close(_))) | None => panic!("socket closed"),
            Some(Ok(_)) => continue,
            Some(Err(e)) => panic!("socket error: {e}"),
        }
    }
}

fn hello_invite(token: &str) -> ClientMsg {
    ClientMsg::Hello { version: PROTOCOL_VERSION, device: "Test phone".into(), invite: Some(token.into()), resume: None }
}

fn hello_resume(token: &str) -> ClientMsg {
    ClientMsg::Hello { version: PROTOCOL_VERSION, device: "Test phone".into(), invite: None, resume: Some(token.into()) }
}

async fn next_consent(rx: &mut tokio::sync::broadcast::Receiver<UiEvent>) -> remote_core::consent::PendingRequest {
    loop {
        if let UiEvent::ConsentRequested(r) = tokio::time::timeout(Duration::from_secs(5), rx.recv()).await.unwrap().unwrap() {
            return r;
        }
    }
}

/// Offer over the socket, return a connected viewer.
async fn negotiate(ws: &mut Ws) -> ViewerPeer {
    let cfg = RtcConfig::loopback();
    let mut viewer = ViewerPeer::new(&cfg).await.unwrap();
    let offer = viewer.create_offer().await.unwrap();
    send(ws, &ClientMsg::Offer { sdp: offer }).await;
    let ServerMsg::Answer { sdp } = recv(ws).await else { panic!("expected answer") };
    viewer.set_answer(sdp).await.unwrap();
    viewer.wait_connected(Duration::from_secs(10)).await.unwrap();
    viewer
}

async fn expect_mode(v: &mut ViewerPeer, want: bool) {
    for _ in 0..10 {
        if let Some(HostEvent::Mode { control }) = v.next_event(Duration::from_millis(500)).await {
            if control == want {
                return;
            }
        }
    }
    panic!("never saw mode control={want}");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn full_session_consent_view_only_control_reconnect_and_stop() {
    let h = host().await;
    let mut ui = h.ctl.subscribe();

    // Nothing happens until the owner makes an invite and says yes.
    let invite = h.ctl.create_invite(true).unwrap();
    let token = token_of(&invite.links[0].url);
    assert!(!invite.qr.is_empty());

    let mut ws = open(h.port).await;
    send(&mut ws, &hello_invite(&token)).await;
    let ServerMsg::Pending { request_id, .. } = recv(&mut ws).await else { panic!("expected pending") };
    let req = next_consent(&mut ui).await;
    assert_eq!(req.id, request_id);
    assert_eq!(req.device, "Test phone");
    assert_eq!(h.ctl.status().status.phase, Phase::Pending);

    // Owner approves view-only.
    h.ctl.decide(&request_id, true, false).await.unwrap();
    let ServerMsg::Granted { resume_token, control, .. } = recv(&mut ws).await else { panic!("expected granted") };
    assert!(!control);

    let mut viewer = negotiate(&mut ws).await;
    let mut got_frame = false;
    for _ in 0..30 {
        if let Some(f) = viewer.next_frame(Duration::from_secs(1)).await {
            assert!(TestPattern::read_counter(&f) < 1000);
            got_frame = true;
            break;
        }
    }
    assert!(got_frame, "no video after approval");
    assert_eq!(h.ctl.status().status.phase, Phase::Active);

    // View-only: input is rejected and never reaches the platform layer.
    expect_mode(&mut viewer, false).await;
    viewer.send_input(&InputEvent::Click { button: Button::Left }).await.unwrap();
    let mut rejected = false;
    for _ in 0..10 {
        if let Some(HostEvent::Rejected { reason }) = viewer.next_event(Duration::from_millis(400)).await {
            assert_eq!(reason, "view_only");
            rejected = true;
            break;
        }
    }
    assert!(rejected);
    assert!(h.backend.sink.events.lock().unwrap().is_empty());

    // Owner upgrades to control: viewer is told, input now reaches the sink.
    h.ctl.set_control(true).await.unwrap();
    expect_mode(&mut viewer, true).await;
    viewer.send_input(&InputEvent::Move { dx: 5.0, dy: 5.0 }).await.unwrap();
    for _ in 0..20 {
        if !h.backend.sink.events.lock().unwrap().is_empty() {
            break;
        }
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    assert_eq!(h.backend.sink.events.lock().unwrap().clone(), vec![InputEvent::Move { dx: 5.0, dy: 5.0 }]);

    // A second device is turned away while a session is live.
    let spare = h.ctl.create_invite(false);
    assert!(spare.is_err(), "no invites while busy");

    // The phone drops (tab backgrounded): the session survives the grace period...
    viewer.close().await;
    drop(ws);
    let mut in_grace = false;
    for _ in 0..40 {
        if h.ctl.status().status.phase == Phase::Grace {
            in_grace = true;
            break;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    assert!(in_grace, "host never noticed the viewer was gone");

    // ...and resumes with the token, no second consent, control preserved.
    let mut ws2 = open(h.port).await;
    send(&mut ws2, &hello_resume(&resume_token)).await;
    let ServerMsg::Granted { control, .. } = recv(&mut ws2).await else { panic!("expected granted on resume") };
    assert!(control, "owner's control grant survives a reconnect");
    let mut viewer2 = negotiate(&mut ws2).await;
    assert!(viewer2.next_frame(Duration::from_secs(5)).await.is_some());
    assert_eq!(h.ctl.status().status.phase, Phase::Active);

    // Owner ends the session: both the data channel and the socket are told.
    h.ctl.stop("owner stopped").await;
    let ServerMsg::Ended { reason } = recv(&mut ws2).await else { panic!("expected ended") };
    assert_eq!(reason, "owner stopped");
    assert_eq!(h.ctl.status().status.phase, Phase::Idle);

    // The old resume token is dead.
    let mut ws3 = open(h.port).await;
    send(&mut ws3, &hello_resume(&resume_token)).await;
    assert!(matches!(recv(&mut ws3).await, ServerMsg::Error { code, .. } if code == "resume_failed"));

    // Audit trail covers the lifecycle and holds no secrets or typed text.
    let names = h.audit.names();
    for expected in ["invite_created", "consent_requested", "consent_granted", "mode_changed", "session_detached", "session_ended"] {
        assert!(names.iter().any(|n| n == expected), "missing audit event {expected}: {names:?}");
    }
    let dump = serde_json::to_string(&h.audit.events()).unwrap();
    assert!(!dump.contains(&token) && !dump.contains(&resume_token));
    viewer2.close().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn owner_can_deny_and_invites_are_single_use() {
    let h = host().await;
    let mut ui = h.ctl.subscribe();
    let token = token_of(&h.ctl.create_invite(false).unwrap().links[0].url);

    let mut ws = open(h.port).await;
    send(&mut ws, &hello_invite(&token)).await;
    let ServerMsg::Pending { .. } = recv(&mut ws).await else { panic!() };
    let req = next_consent(&mut ui).await;
    h.ctl.decide(&req.id, false, false).await.unwrap();
    assert!(matches!(recv(&mut ws).await, ServerMsg::Denied { .. }));
    assert_eq!(h.ctl.status().status.phase, Phase::Idle);

    // The invite was consumed by the request; reusing it fails.
    let mut ws2 = open(h.port).await;
    send(&mut ws2, &hello_invite(&token)).await;
    assert!(matches!(recv(&mut ws2).await, ServerMsg::Error { code, .. } if code == "invalid_invite"));

    // Garbage never gets past the door.
    let mut ws3 = open(h.port).await;
    send(&mut ws3, &hello_invite("AAAAAAAAAAAAAAAAAAAAAA")).await;
    assert!(matches!(recv(&mut ws3).await, ServerMsg::Error { code, .. } if code == "invalid_invite"));
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn view_only_invite_cannot_be_upgraded_and_busy_host_turns_others_away() {
    let h = host().await;
    let mut ui = h.ctl.subscribe();
    let token = token_of(&h.ctl.create_invite(false).unwrap().links[0].url);
    let mut ws = open(h.port).await;
    send(&mut ws, &hello_invite(&token)).await;
    let ServerMsg::Pending { request_id, .. } = recv(&mut ws).await else { panic!() };
    let _ = next_consent(&mut ui).await;
    assert!(h.ctl.decide(&request_id, true, true).await.is_err(), "control must be refused for a view-only invite");
    h.ctl.decide(&request_id, true, false).await.unwrap();
    assert!(matches!(recv(&mut ws).await, ServerMsg::Granted { control: false, .. }));
    assert!(h.ctl.set_control(true).await.is_err());

    // Someone with a stale-but-wrong link while busy.
    let mut other = open(h.port).await;
    send(&mut other, &hello_invite("BBBBBBBBBBBBBBBBBBBBBB")).await;
    assert!(matches!(recv(&mut other).await, ServerMsg::Error { code, .. } if code == "busy"));
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn disabling_sharing_ends_everything_and_closes_the_door() {
    let h = host().await;
    let mut ui = h.ctl.subscribe();
    let token = token_of(&h.ctl.create_invite(false).unwrap().links[0].url);
    let mut ws = open(h.port).await;
    send(&mut ws, &hello_invite(&token)).await;
    let ServerMsg::Pending { request_id, .. } = recv(&mut ws).await else { panic!() };
    let _ = next_consent(&mut ui).await;
    h.ctl.decide(&request_id, true, false).await.unwrap();
    let _ = recv(&mut ws).await;
    h.ctl.set_enabled(false).await;
    assert!(matches!(recv(&mut ws).await, ServerMsg::Ended { .. }));
    assert!(h.ctl.create_invite(false).is_err());
    // The listener goes away.
    let mut closed = false;
    for _ in 0..40 {
        if connect_async(format!("ws://127.0.0.1:{}/ws", h.port)).await.is_err() {
            closed = true;
            break;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    assert!(closed, "listener still accepting after sharing was turned off");
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn cross_origin_pages_and_bad_frames_are_refused() {
    let h = host().await;
    let mut req = format!("ws://127.0.0.1:{}/ws", h.port).into_client_request().unwrap();
    req.headers_mut().insert("origin", "http://evil.example".parse().unwrap());
    assert!(connect_async(req).await.is_err(), "cross-origin socket must be refused");

    let mut ws = open(h.port).await;
    ws.send(Message::Text("{\"type\":\"shell\",\"cmd\":\"id\"}".into())).await.unwrap();
    assert!(matches!(recv(&mut ws).await, ServerMsg::Error { code, .. } if code == "bad_message"));

    // Static client is served with a strict CSP.
    let body = reqwest_free_get(h.port, "/").await;
    assert!(body.contains("content-security-policy"));
    assert!(body.contains("<title>remote desktop</title>"));
}

/// Minimal HTTP/1.0 GET so the test needs no HTTP client crate.
async fn reqwest_free_get(port: u16, path: &str) -> String {
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    let mut s = TcpStream::connect(("127.0.0.1", port)).await.unwrap();
    s.write_all(format!("GET {path} HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n\r\n").as_bytes()).await.unwrap();
    let mut out = String::new();
    s.read_to_string(&mut out).await.unwrap();
    out.to_lowercase()
}
