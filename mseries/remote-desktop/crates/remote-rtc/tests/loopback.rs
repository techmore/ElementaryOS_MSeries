//! Headless loopback: a Rust viewer and the host peer talk over real UDP on
//! 127.0.0.1 with real DTLS/SRTP/SCTP. No desktop, no GPU, no network.

use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use remote_core::capture::{FrameSource, TestPattern};
use remote_core::protocol::{Button, HostEvent, InputEvent};
use remote_rtc::host::{HostCallbacks, HostPeer, VideoParams};
use remote_rtc::viewer::ViewerPeer;
use remote_rtc::{LinkState, RtcConfig};

struct Rig {
    host: HostPeer,
    viewer: ViewerPeer,
    inputs: Arc<Mutex<Vec<InputEvent>>>,
    states: Arc<Mutex<Vec<LinkState>>>,
}

async fn connect(control: bool) -> Rig {
    let cfg = RtcConfig::loopback();
    let inputs = Arc::new(Mutex::new(Vec::new()));
    let states = Arc::new(Mutex::new(Vec::new()));
    let (i, s) = (inputs.clone(), states.clone());
    let callbacks = HostCallbacks {
        on_input: Arc::new(move |ev| i.lock().unwrap().push(ev)),
        on_state: Arc::new(move |st| s.lock().unwrap().push(st)),
    };
    let mut viewer = ViewerPeer::new(&cfg).await.unwrap();
    let offer = viewer.create_offer().await.unwrap();
    let (host, answer) = HostPeer::accept(offer, &cfg, callbacks, control).await.unwrap();
    viewer.set_answer(answer).await.unwrap();
    viewer.wait_connected(Duration::from_secs(10)).await.expect("connect");
    Rig { host, viewer, inputs, states }
}

fn pattern() -> Box<dyn FrameSource> {
    Box::new(TestPattern::new(640, 360))
}

fn params() -> VideoParams {
    VideoParams { fps: 30, bitrate_bps: 2_000_000, keyframe_interval_s: 2 }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn streams_decodable_ordered_video_and_round_trips_input() {
    let mut rig = connect(true).await;
    rig.host.start_video(pattern(), params()).unwrap();

    // Video: collect for 3 seconds, verify the counter strip in decoded frames.
    let started = Instant::now();
    let mut counters = Vec::new();
    while started.elapsed() < Duration::from_secs(3) {
        if let Some(f) = rig.viewer.next_frame(Duration::from_secs(2)).await {
            assert_eq!((f.width, f.height), (640, 360));
            counters.push(TestPattern::read_counter(&f));
        }
    }
    let elapsed = started.elapsed().as_secs_f64();
    assert!(counters.len() >= 45, "only {} frames decoded in {elapsed:.1}s", counters.len());
    assert!(counters.windows(2).all(|w| w[1] > w[0]), "frames out of order: {counters:?}");
    let span = counters.last().unwrap() - counters.first().unwrap() + 1;
    let delivered = counters.len() as f64 / span as f64;
    println!("loopback video: {} frames / {:.1}s, delivery {:.0}% of {} produced", counters.len(), elapsed, delivered * 100.0, span);
    assert!(delivered > 0.8, "lost too many frames: {delivered}");

    // Input: mode on open, then ping/pong and a click reaching the callback.
    let mut saw_mode = false;
    for _ in 0..5 {
        if let Some(HostEvent::Mode { control }) = rig.viewer.next_event(Duration::from_millis(500)).await {
            assert!(control);
            saw_mode = true;
            break;
        }
    }
    assert!(saw_mode, "host never announced its mode");
    rig.viewer.send_input(&InputEvent::Ping { t: 42 }).await.unwrap();
    rig.viewer.send_input(&InputEvent::Move { dx: 3.0, dy: -2.0 }).await.unwrap();
    rig.viewer.send_input(&InputEvent::Click { button: Button::Left }).await.unwrap();
    let mut pong = false;
    for _ in 0..5 {
        if let Some(HostEvent::Pong { t }) = rig.viewer.next_event(Duration::from_millis(500)).await {
            assert_eq!(t, 42);
            pong = true;
            break;
        }
    }
    assert!(pong, "no pong");
    tokio::time::sleep(Duration::from_millis(200)).await;
    let got = rig.inputs.lock().unwrap().clone();
    assert_eq!(got, vec![InputEvent::Move { dx: 3.0, dy: -2.0 }, InputEvent::Click { button: Button::Left }]);
    assert!(rig.states.lock().unwrap().contains(&LinkState::Connected));
    rig.host.close().await;
    rig.viewer.close().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn malformed_input_is_rejected_not_delivered() {
    let mut rig = connect(false).await;
    // Raw garbage through the same channel must not reach the callback.
    rig.viewer
        .send_input(&InputEvent::Move { dx: 1e12, dy: 0.0 })
        .await
        .unwrap();
    let mut rejected = false;
    for _ in 0..6 {
        if let Some(HostEvent::Rejected { .. }) = rig.viewer.next_event(Duration::from_millis(400)).await {
            rejected = true;
            break;
        }
    }
    assert!(rejected);
    assert!(rig.inputs.lock().unwrap().is_empty());
    rig.host.close().await;
    rig.viewer.close().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn video_survives_an_ice_restart() {
    let mut rig = connect(false).await;
    rig.host.start_video(pattern(), params()).unwrap();
    assert!(rig.viewer.next_frame(Duration::from_secs(5)).await.is_some());

    let offer = rig.viewer.restart_ice_offer().await.unwrap();
    let answer = rig.host.renegotiate(offer).await.unwrap();
    rig.viewer.set_answer(answer).await.unwrap();

    // Drain, then require fresh frames after the restart.
    tokio::time::sleep(Duration::from_millis(500)).await;
    let mut after = 0;
    let started = Instant::now();
    while started.elapsed() < Duration::from_secs(3) {
        if rig.viewer.next_frame(Duration::from_millis(500)).await.is_some() {
            after += 1;
        }
    }
    assert!(after >= 30, "only {after} frames after ICE restart");
    rig.host.close().await;
    rig.viewer.close().await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn mode_changes_reach_the_viewer_live() {
    let mut rig = connect(false).await;
    let mut first = None;
    for _ in 0..5 {
        if let Some(HostEvent::Mode { control }) = rig.viewer.next_event(Duration::from_millis(500)).await {
            first = Some(control);
            break;
        }
    }
    assert_eq!(first, Some(false));
    rig.host.set_control(true);
    let mut second = None;
    for _ in 0..5 {
        if let Some(HostEvent::Mode { control }) = rig.viewer.next_event(Duration::from_millis(500)).await {
            second = Some(control);
            break;
        }
    }
    assert_eq!(second, Some(true));
    rig.host.notify(HostEvent::Ended { reason: "test".into() });
    let mut ended = false;
    for _ in 0..5 {
        if let Some(HostEvent::Ended { .. }) = rig.viewer.next_event(Duration::from_millis(500)).await {
            ended = true;
            break;
        }
    }
    assert!(ended);
    rig.host.close().await;
    rig.viewer.close().await;
}
