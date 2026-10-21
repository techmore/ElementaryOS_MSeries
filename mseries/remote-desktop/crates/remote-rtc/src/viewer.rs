//! Headless viewer: the phone browser's role, in Rust. Used by the loopback
//! tests and by `tm-remote-viewer` for support diagnostics.

use std::sync::{Arc, Mutex};
use std::time::Duration;

use futures::FutureExt;
use remote_core::capture::Frame;
use remote_core::encode::H264Decoder;
use remote_core::protocol::{HostEvent, InputEvent, INPUT_CHANNEL_LABEL};
use rtc::rtcp::payload_feedbacks::picture_loss_indication::PictureLossIndication;
use rtc::rtp::codec::h264::H264Packet;
use rtc::rtp::packetizer::Depacketizer;
use rtc::rtp_transceiver::rtp_sender::RtpCodecKind;
use rtc::rtp_transceiver::{RTCRtpTransceiverDirection, RTCRtpTransceiverInit};
use tokio::sync::{mpsc, watch};
use webrtc::data_channel::{DataChannel, DataChannelEvent};
use webrtc::media_stream::track_remote::{TrackRemote, TrackRemoteEvent};
use webrtc::peer_connection::{
    register_default_interceptors, MediaEngine, PeerConnection, PeerConnectionBuilder,
    PeerConnectionEventHandler, RTCConfigurationBuilder, RTCIceGatheringState, RTCPeerConnectionState,
    RTCSessionDescription, Registry,
};
use webrtc::runtime::default_runtime;

use crate::host::{h264_codec, ice_servers};
use crate::{LinkState, RtcConfig, RtcError};

struct Handler {
    gather_done: watch::Sender<bool>,
    state: watch::Sender<LinkState>,
    frames: mpsc::Sender<Frame>,
    runtime: Arc<dyn webrtc::runtime::Runtime>,
}

#[async_trait::async_trait]
impl PeerConnectionEventHandler for Handler {
    async fn on_ice_gathering_state_change(&self, state: RTCIceGatheringState) {
        let _ = self.gather_done.send(state == RTCIceGatheringState::Complete);
    }

    async fn on_connection_state_change(&self, state: RTCPeerConnectionState) {
        let _ = self.state.send(match state {
            RTCPeerConnectionState::Connected => LinkState::Connected,
            RTCPeerConnectionState::Disconnected => LinkState::Disconnected,
            RTCPeerConnectionState::Failed => LinkState::Failed,
            RTCPeerConnectionState::Closed => LinkState::Closed,
            _ => LinkState::Connecting,
        });
    }

    async fn on_track(&self, track: Arc<dyn TrackRemote>) {
        let frames = self.frames.clone();
        let media_ssrc = track.ssrcs().await.first().copied().unwrap_or(0);
        self.runtime.spawn(Box::pin(async move {
            let mut depacketizer = H264Packet::default();
            let mut decoder = match H264Decoder::new() {
                Ok(d) => d,
                Err(e) => {
                    tracing::error!("decoder: {e}");
                    return;
                }
            };
            let mut au: Vec<u8> = Vec::new();
            let mut pli = tokio::time::interval(Duration::from_secs(3));
            loop {
                futures::select! {
                    evt = track.poll().fuse() => match evt {
                        Some(TrackRemoteEvent::OnRtpPacket(packet)) => {
                            if let Ok(nals) = depacketizer.depacketize(&packet.payload) {
                                au.extend_from_slice(&nals);
                            }
                            if packet.header.marker && !au.is_empty() {
                                if let Ok(Some(frame)) = decoder.decode(&au) {
                                    let _ = frames.try_send(frame);
                                }
                                au.clear();
                            }
                        }
                        Some(_) => {}
                        None => break,
                    },
                    _ = pli.tick().fuse() => {
                        let _ = track
                            .write_rtcp(vec![Box::new(PictureLossIndication { sender_ssrc: 0, media_ssrc })])
                            .await;
                    }
                }
            }
        }));
    }
}

pub struct ViewerPeer {
    pc: Box<dyn PeerConnection>,
    dc: Arc<dyn DataChannel>,
    frames: mpsc::Receiver<Frame>,
    events: mpsc::UnboundedReceiver<HostEvent>,
    state: watch::Receiver<LinkState>,
    gather_rx: watch::Receiver<bool>,
    gather_timeout: Duration,
    opened: watch::Receiver<bool>,
}

impl ViewerPeer {
    pub async fn new(cfg: &RtcConfig) -> Result<Self, RtcError> {
        let runtime = default_runtime().ok_or_else(|| RtcError::WebRtc("no runtime".into()))?;
        let mut media = MediaEngine::default();
        media.register_codec(h264_codec(), RtpCodecKind::Video)?;
        let registry = register_default_interceptors(Registry::new(), &mut media)?;

        let (gather_tx, gather_rx) = watch::channel(false);
        let (state_tx, state_rx) = watch::channel(LinkState::Connecting);
        let (frames_tx, frames_rx) = mpsc::channel(8);
        let pc = PeerConnectionBuilder::new()
            .with_configuration(RTCConfigurationBuilder::new().with_ice_servers(ice_servers(cfg)).build())
            .with_media_engine(media)
            .with_interceptor_registry(registry)
            .with_handler(Arc::new(Handler {
                gather_done: gather_tx,
                state: state_tx,
                frames: frames_tx,
                runtime: runtime.clone(),
            }))
            .with_runtime(runtime.clone())
            .with_udp_addrs(cfg.udp_bind.clone())
            .build()
            .await?;
        let pc: Box<dyn PeerConnection> = Box::new(pc);

        pc.add_transceiver_from_kind(
            RtpCodecKind::Video,
            Some(RTCRtpTransceiverInit {
                direction: RTCRtpTransceiverDirection::Recvonly,
                streams: vec![],
                send_encodings: vec![],
            }),
        )
        .await?;
        let dc = pc.create_data_channel(INPUT_CHANNEL_LABEL, None).await?;

        let (ev_tx, ev_rx) = mpsc::unbounded_channel();
        let (open_tx, open_rx) = watch::channel(false);
        let dc2 = dc.clone();
        runtime.spawn(Box::pin(async move {
            while let Some(e) = dc2.poll().await {
                match e {
                    DataChannelEvent::OnOpen => {
                        let _ = open_tx.send(true);
                    }
                    DataChannelEvent::OnMessage(m) => {
                        if let Ok(ev) = serde_json::from_slice::<HostEvent>(&m.data) {
                            let _ = ev_tx.send(ev);
                        }
                    }
                    DataChannelEvent::OnClose => break,
                    _ => {}
                }
            }
        }));

        Ok(Self {
            pc,
            dc,
            frames: frames_rx,
            events: ev_rx,
            state: state_rx,
            gather_rx,
            gather_timeout: Duration::from_millis(cfg.gather_timeout_ms),
            opened: open_rx,
        })
    }

    async fn gathered(&self) -> Result<String, RtcError> {
        let mut rx = self.gather_rx.clone();
        let _ = tokio::time::timeout(self.gather_timeout, rx.wait_for(|d| *d)).await;
        self.pc
            .local_description()
            .await
            .map(|d| d.sdp)
            .ok_or_else(|| RtcError::WebRtc("no local description".into()))
    }

    pub async fn create_offer(&self) -> Result<String, RtcError> {
        let offer = self.pc.create_offer(None).await?;
        self.pc.set_local_description(offer).await?;
        self.gathered().await
    }

    /// ICE-restart offer for a changed network.
    pub async fn restart_ice_offer(&self) -> Result<String, RtcError> {
        self.pc.restart_ice().await?;
        self.create_offer().await
    }

    pub async fn set_answer(&self, sdp: String) -> Result<(), RtcError> {
        Ok(self.pc.set_remote_description(RTCSessionDescription::answer(sdp)?).await?)
    }

    pub async fn wait_connected(&mut self, timeout: Duration) -> Result<(), RtcError> {
        tokio::time::timeout(timeout, self.state.wait_for(|s| *s == LinkState::Connected))
            .await
            .map_err(|_| RtcError::Timeout("peer connection"))?
            .map_err(|_| RtcError::WebRtc("connection dropped".into()))?;
        tokio::time::timeout(timeout, self.opened.wait_for(|o| *o))
            .await
            .map_err(|_| RtcError::Timeout("input data channel"))?
            .map_err(|_| RtcError::WebRtc("data channel dropped".into()))?;
        Ok(())
    }

    pub fn link_state(&self) -> LinkState {
        *self.state.borrow()
    }

    pub async fn next_frame(&mut self, timeout: Duration) -> Option<Frame> {
        tokio::time::timeout(timeout, self.frames.recv()).await.ok().flatten()
    }

    pub async fn next_event(&mut self, timeout: Duration) -> Option<HostEvent> {
        tokio::time::timeout(timeout, self.events.recv()).await.ok().flatten()
    }

    pub async fn send_input(&self, ev: &InputEvent) -> Result<(), RtcError> {
        let text = serde_json::to_string(ev).map_err(|e| RtcError::Signal(e.to_string()))?;
        Ok(self.dc.send_text(&text).await?)
    }

    pub async fn close(&self) {
        let _ = self.pc.close().await;
    }
}

/// Shared slot used by tests that need a value out of a callback.
pub type Slot<T> = Arc<Mutex<Vec<T>>>;
