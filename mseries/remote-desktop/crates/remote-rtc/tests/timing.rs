use std::time::{Duration, Instant};
use remote_rtc::host::{HostCallbacks, HostPeer};
use remote_rtc::viewer::ViewerPeer;
use remote_rtc::RtcConfig;
use std::sync::Arc;

#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn setup_time() {
    let cfg = RtcConfig::loopback();
    let t0 = Instant::now();
    let mut viewer = ViewerPeer::new(&cfg).await.unwrap();
    println!("viewer new {:?}", t0.elapsed());
    let offer = viewer.create_offer().await.unwrap();
    println!("offer gathered {:?}", t0.elapsed());
    let cb = HostCallbacks { on_input: Arc::new(|_| {}), on_state: Arc::new(|_| {}) };
    let (_host, answer) = HostPeer::accept(offer, &cfg, cb, false).await.unwrap();
    println!("answer gathered {:?}", t0.elapsed());
    viewer.set_answer(answer).await.unwrap();
    viewer.wait_connected(Duration::from_secs(10)).await.unwrap();
    println!("connected {:?}", t0.elapsed());
}
