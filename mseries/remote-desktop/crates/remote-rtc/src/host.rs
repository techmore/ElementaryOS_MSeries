//! The desktop side: answer an offer, stream H.264, receive input.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use futures::FutureExt;
use remote_core::capture::FrameSource;
use remote_core::encode::H264Encoder;
use remote_core::protocol::{HostEvent, InputEvent, INPUT_CHANNEL_LABEL};
use rtc::media::Sample;
use rtc::media_stream::MediaStreamTrack;
use rtc::peer_connection::configuration::media_engine::MIME_TYPE_H264;
use rtc::rtp_transceiver::rtp_sender::{
    RTCRtpCodec, RTCRtpCodecParameters, RTCRtpCodingParameters, RTCRtpEncodingParameters, RtpCodecKind,
};
use tokio::sync::{mpsc, watch};
use webrtc::data_channel::{DataChannel, DataChannelEvent};
use webrtc::media_stream::track_local::static_sample::TrackLocalStaticSample;
use webrtc::media_stream::track_local::TrackLocal;
use webrtc::peer_connection::{
    register_default_interceptors, MediaEngine, PeerConnection, PeerConnectionBuilder,
    PeerConnectionEventHandler, RTCConfigurationBuilder, RTCIceGatheringState, RTCIceServer,
    RTCPeerConnectionState, RTCSessionDescription, Registry,
};
use webrtc::runtime::default_runtime;

use crate::{LinkState, RtcConfig, RtcError};

pub(crate) const H264_FMTP: &str = "level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f";
pub(crate) const H264_PT: u8 = 102;

pub(crate) fn h264_codec() -> RTCRtpCodecParameters {
    RTCRtpCodecParameters {
        rtp_codec: RTCRtpCodec {
            mime_type: MIME_TYPE_H264.to_owned(),
            clock_rate: 90_000,
            channels: 0,
            sdp_fmtp_line: H264_FMTP.to_owned(),
            rtcp_feedback: vec![],
        },
        payload_type: H264_PT,
        ..Default::default()
    }
}

pub(crate) fn ice_servers(cfg: &RtcConfig) -> Vec<RTCIceServer> {
    cfg.ice_servers
        .iter()
        .map(|s| RTCIceServer {
            urls: s.urls.clone(),
            username: s.username.clone(),
            credential: s.credential.clone(),
            ..Default::default()
        })
        .collect()
}

/// Callbacks into the daemon. Must not block.
#[derive(Clone)]
pub struct HostCallbacks {
    pub on_input: Arc<dyn Fn(InputEvent) + Send + Sync>,
    pub on_state: Arc<dyn Fn(LinkState) + Send + Sync>,
}

struct Handler {
    gather_done: watch::Sender<bool>,
    callbacks: HostCallbacks,
    channel_out: Arc<Mutex<Option<mpsc::UnboundedSender<HostEvent>>>>,
    mode: watch::Receiver<bool>,
    runtime: Arc<dyn webrtc::runtime::Runtime>,
}

#[async_trait::async_trait]
impl PeerConnectionEventHandler for Handler {
    async fn on_ice_gathering_state_change(&self, state: RTCIceGatheringState) {
        let _ = self.gather_done.send(state == RTCIceGatheringState::Complete);
    }

    async fn on_connection_state_change(&self, state: RTCPeerConnectionState) {
        let s = match state {
            RTCPeerConnectionState::Connected => LinkState::Connected,
            RTCPeerConnectionState::Disconnected => LinkState::Disconnected,
            RTCPeerConnectionState::Failed => LinkState::Failed,
            RTCPeerConnectionState::Closed => LinkState::Closed,
            _ => LinkState::Connecting,
        };
        (self.callbacks.on_state)(s);
    }

    async fn on_data_channel(&self, dc: Arc<dyn DataChannel>) {
        let label = dc.label().await.unwrap_or_default();
        if label != INPUT_CHANNEL_LABEL {
            tracing::warn!("ignoring unexpected data channel {label:?}");
            return;
        }
        let (tx, mut rx) = mpsc::unbounded_channel::<HostEvent>();
        *self.channel_out.lock().unwrap() = Some(tx);
        let on_input = self.callbacks.on_input.clone();
        let mut mode = self.mode.clone();
        self.runtime.spawn(Box::pin(async move {
            let mut open = false;
            loop {
                futures::select! {
                    event = dc.poll().fuse() => match event {
                        Some(DataChannelEvent::OnOpen) => {
                            open = true;
                            let control = *mode.borrow();
                            send_event(&dc, &HostEvent::Mode { control }).await;
                        }
                        Some(DataChannelEvent::OnMessage(msg)) => match InputEvent::parse(&msg.data) {
                            Ok(InputEvent::Ping { t }) => send_event(&dc, &HostEvent::Pong { t }).await,
                            Ok(ev) => on_input(ev),
                            Err(e) => {
                                tracing::debug!("bad input: {e}");
                                send_event(&dc, &HostEvent::Rejected { reason: "invalid".into() }).await;
                            }
                        },
                        Some(DataChannelEvent::OnClose) | None => break,
                        _ => {}
                    },
                    out = rx.recv().fuse() => match out {
                        Some(ev) => if open { send_event(&dc, &ev).await },
                        None => break,
                    },
                    changed = mode.changed().fuse() => {
                        if changed.is_err() { break; }
                        if open {
                            let control = *mode.borrow();
                            send_event(&dc, &HostEvent::Mode { control }).await;
                        }
                    }
                }
            }
        }));
    }
}

async fn send_event(dc: &Arc<dyn DataChannel>, ev: &HostEvent) {
    if let Ok(text) = serde_json::to_string(ev) {
        let _ = dc.send_text(&text).await;
    }
}

/// An established host-side connection.
pub struct HostPeer {
    pc: Box<dyn PeerConnection>,
    track: Arc<TrackLocalStaticSample>,
    ssrc: u32,
    payload_type: u8,
    channel_out: Arc<Mutex<Option<mpsc::UnboundedSender<HostEvent>>>>,
    mode_tx: watch::Sender<bool>,
    gather_rx: watch::Receiver<bool>,
    stop: Arc<AtomicBool>,
    force_key: Arc<AtomicBool>,
    gather_timeout: Duration,
}

pub struct VideoParams {
    pub fps: u32,
    pub bitrate_bps: u32,
    pub keyframe_interval_s: u32,
}

impl From<&RtcConfig> for VideoParams {
    fn from(c: &RtcConfig) -> Self {
        Self { fps: c.fps, bitrate_bps: c.bitrate_bps, keyframe_interval_s: c.keyframe_interval_s }
    }
}

impl HostPeer {
    /// Accept a viewer's offer. Returns the peer and the gathered answer SDP.
    pub async fn accept(
        offer_sdp: String,
        cfg: &RtcConfig,
        callbacks: HostCallbacks,
        control_initial: bool,
    ) -> Result<(Self, String), RtcError> {
        let runtime = default_runtime().ok_or_else(|| RtcError::WebRtc("no runtime".into()))?;
        let mut media = MediaEngine::default();
        media.register_codec(h264_codec(), RtpCodecKind::Video)?;
        let registry = register_default_interceptors(Registry::new(), &mut media)?;

        let (gather_tx, gather_rx) = watch::channel(false);
        let (mode_tx, mode_rx) = watch::channel(control_initial);
        let channel_out = Arc::new(Mutex::new(None));
        let handler = Arc::new(Handler {
            gather_done: gather_tx,
            callbacks,
            channel_out: channel_out.clone(),
            mode: mode_rx,
            runtime: runtime.clone(),
        });

        let pc = PeerConnectionBuilder::new()
            .with_configuration(RTCConfigurationBuilder::new().with_ice_servers(ice_servers(cfg)).build())
            .with_media_engine(media)
            .with_interceptor_registry(registry)
            .with_handler(handler)
            .with_runtime(runtime)
            .with_udp_addrs(cfg.udp_bind.clone())
            .build()
            .await?;
        let pc: Box<dyn PeerConnection> = Box::new(pc);

        pc.set_remote_description(RTCSessionDescription::offer(offer_sdp)?).await?;

        // The track must exist before the answer is created so it binds to the
        // viewer's recvonly video transceiver.
        let ssrc = rand::random::<u32>();
        let track = Arc::new(TrackLocalStaticSample::new(
            Instant::now(),
            MediaStreamTrack::new(
                "m-series-desktop".to_owned(),
                "desktop-video".to_owned(),
                "Desktop".to_owned(),
                RtpCodecKind::Video,
                vec![RTCRtpEncodingParameters {
                    rtp_coding_parameters: RTCRtpCodingParameters { ssrc: Some(ssrc), ..Default::default() },
                    codec: h264_codec().rtp_codec,
                    ..Default::default()
                }],
            ),
        )?);
        let sender = pc.add_track(track.clone() as Arc<dyn TrackLocal>).await?;

        let answer = pc.create_answer(None).await?;
        pc.set_local_description(answer).await?;
        let payload_type = sender
            .get_parameters()
            .await?
            .rtp_parameters
            .codecs
            .first()
            .map(|c| c.payload_type)
            .ok_or_else(|| RtcError::WebRtc("no H.264 negotiated; the viewer must offer H.264".into()))?;

        let peer = Self {
            pc,
            track,
            ssrc,
            payload_type,
            channel_out,
            mode_tx,
            gather_rx,
            stop: Arc::new(AtomicBool::new(false)),
            force_key: Arc::new(AtomicBool::new(true)),
            gather_timeout: Duration::from_millis(cfg.gather_timeout_ms),
        };
        let sdp = peer.gathered_local_sdp().await?;
        Ok((peer, sdp))
    }

    async fn gathered_local_sdp(&self) -> Result<String, RtcError> {
        let mut rx = self.gather_rx.clone();
        let _ = tokio::time::timeout(self.gather_timeout, rx.wait_for(|done| *done)).await;
        self.pc
            .local_description()
            .await
            .map(|d| d.sdp)
            .ok_or_else(|| RtcError::WebRtc("no local description".into()))
    }

    /// Viewer sent a new offer on the live connection (ICE restart after a
    /// network change). Returns the new answer.
    pub async fn renegotiate(&self, offer_sdp: String) -> Result<String, RtcError> {
        self.pc.set_remote_description(RTCSessionDescription::offer(offer_sdp)?).await?;
        let answer = self.pc.create_answer(None).await?;
        self.pc.set_local_description(answer).await?;
        self.force_key.store(true, Ordering::SeqCst);
        self.gathered_local_sdp().await
    }

    pub async fn add_remote_candidate(&self, candidate: webrtc::peer_connection::RTCIceCandidateInit) -> Result<(), RtcError> {
        Ok(self.pc.add_ice_candidate(candidate).await?)
    }

    /// Owner changed the permission mid-session; the viewer UI follows.
    pub fn set_control(&self, control: bool) {
        let _ = self.mode_tx.send(control);
    }

    /// Tell the viewer something over the data channel (`Rejected`, `Ended`).
    pub fn notify(&self, ev: HostEvent) {
        if let Some(tx) = self.channel_out.lock().unwrap().as_ref() {
            let _ = tx.send(ev);
        }
    }

    /// Ask the encoder for an IDR on the next frame.
    pub fn request_keyframe(&self) {
        self.force_key.store(true, Ordering::SeqCst);
    }

    /// Start streaming `source`. Capture + encode run on a dedicated thread;
    /// samples cross a 2-deep channel so a slow network drops frames (and
    /// forces an IDR) instead of growing latency.
    pub fn start_video(&self, mut source: Box<dyn FrameSource>, params: VideoParams) -> Result<(), RtcError> {
        let (w, h) = source.dimensions();
        let mut enc = H264Encoder::new(w, h, params.fps, params.bitrate_bps)
            .map_err(|e| RtcError::WebRtc(e.to_string()))?;
        let (tx, mut rx) = mpsc::channel::<(bytes::Bytes, Duration)>(2);
        let stop = self.stop.clone();
        let force_key = self.force_key.clone();
        let frame_interval = Duration::from_secs_f64(1.0 / params.fps.max(1) as f64);
        let key_every = (params.fps.max(1) * params.keyframe_interval_s.max(1)) as u64;

        std::thread::Builder::new()
            .name("remote-capture".into())
            .spawn(move || {
                let started = Instant::now();
                let mut n: u64 = 0;
                let mut last = Instant::now();
                while !stop.load(Ordering::Relaxed) {
                    // Pace: never run ahead of the target frame rate.
                    let due = started + frame_interval.mul_f64(n as f64);
                    let now = Instant::now();
                    if due > now {
                        std::thread::sleep(due - now);
                    }
                    let frame = match source.next_frame() {
                        Ok(f) => f,
                        Err(e) => {
                            tracing::info!("capture stopped: {e}");
                            break;
                        }
                    };
                    if force_key.swap(false, Ordering::SeqCst) || (n > 0 && n % key_every == 0) {
                        enc.force_keyframe();
                    }
                    n += 1;
                    let bits = match enc.encode(&frame) {
                        Ok(b) => b,
                        Err(e) => {
                            tracing::error!("encode failed: {e}");
                            break;
                        }
                    };
                    if bits.is_empty() {
                        continue;
                    }
                    let now = Instant::now();
                    let dur = now.duration_since(last).max(Duration::from_millis(1));
                    last = now;
                    if tx.try_send((bytes::Bytes::from(bits), dur)).is_err() {
                        if tx.is_closed() {
                            break;
                        }
                        // Network can't keep up: drop, and heal with an IDR.
                        force_key.store(true, Ordering::SeqCst);
                    }
                }
            })
            .map_err(|e| RtcError::WebRtc(e.to_string()))?;

        let track = self.track.clone();
        let (ssrc, pt) = (self.ssrc, self.payload_type);
        tokio::spawn(async move {
            while let Some((data, duration)) = rx.recv().await {
                let sample = Sample { data, duration, ..Sample::new(Instant::now()) };
                if let Err(e) = track.sample_writer(ssrc, pt).write_sample(&sample).await {
                    tracing::info!("video write ended: {e}");
                    break;
                }
            }
        });
        Ok(())
    }

    pub async fn close(&self) {
        self.stop.store(true, Ordering::SeqCst);
        let _ = self.pc.close().await;
    }
}

impl Drop for HostPeer {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
    }
}
