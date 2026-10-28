//! Headless viewer session: pair over the signalling socket, negotiate WebRTC
//! and count what arrives. Used by `tm-remote-viewer` and for support diagnostics.

use std::time::{Duration, Instant};

use futures::{SinkExt, StreamExt};
use remote_core::backoff::Backoff;
use remote_core::capture::Frame;
use remote_core::protocol::{ClientMsg, HostEvent, InputEvent, ServerMsg, PROTOCOL_VERSION};
use remote_rtc::viewer::ViewerPeer;
use remote_rtc::RtcConfig;
use tokio_tungstenite::tungstenite::Message;
use tokio_tungstenite::{connect_async, MaybeTlsStream, WebSocketStream};

pub type Ws = WebSocketStream<MaybeTlsStream<tokio::net::TcpStream>>;

#[derive(Debug, thiserror::Error)]
pub enum ClientError {
    #[error("{0}")]
    Msg(String),
}

fn err(e: impl ToString) -> ClientError {
    ClientError::Msg(e.to_string())
}

/// Parse `http://host:port/#i=TOKEN` into (`ws://host:port/ws`, token).
pub fn parse_link(link: &str) -> Result<(String, String), ClientError> {
    let rest = link
        .strip_prefix("http://")
        .ok_or_else(|| err("expected an http:// link"))?;
    let (hostport, frag) = rest
        .split_once("/#i=")
        .ok_or_else(|| err("link has no #i= invite"))?;
    if hostport.is_empty() || frag.is_empty() {
        return Err(err("malformed link"));
    }
    Ok((format!("ws://{hostport}/ws"), frag.to_string()))
}

pub async fn send(ws: &mut Ws, m: &ClientMsg) -> Result<(), ClientError> {
    ws.send(Message::Text(serde_json::to_string(m).map_err(err)?.into()))
        .await
        .map_err(err)
}

pub async fn recv(ws: &mut Ws, timeout: Duration) -> Result<ServerMsg, ClientError> {
    loop {
        match tokio::time::timeout(timeout, ws.next())
            .await
            .map_err(|_| err("timed out waiting for the host"))?
        {
            Some(Ok(Message::Text(t))) => return serde_json::from_str(&t).map_err(err),
            Some(Ok(Message::Close(_))) | None => {
                return Err(err("the host closed the connection"))
            }
            Some(Ok(_)) => continue,
            Some(Err(e)) => return Err(err(e)),
        }
    }
}

#[derive(Debug, Default, Clone)]
pub struct Report {
    pub frames: u64,
    pub first_frame_ms: Option<u128>,
    pub seconds: f64,
    pub control_granted: bool,
    pub width: u32,
    pub height: u32,
    pub rejected: Vec<String>,
    pub ended: Option<String>,
}

pub struct Options {
    pub duration: Duration,
    pub device: String,
    pub wait_for_owner: Duration,
    pub send_input: bool,
    pub rtc: RtcConfig,
}

enum Fail {
    /// The host said no, or the link is bad: do not retry.
    Fatal(ClientError),
    /// Network trouble: retry with backoff, resuming the session.
    Retry(ClientError),
}

fn retry(e: impl ToString) -> Fail {
    Fail::Retry(err(e))
}

/// Pair with `link`, stream for `opts.duration`, and report. Reconnects with
/// the shared backoff schedule if the connection drops mid-way.
pub async fn run(link: &str, opts: Options) -> Result<Report, ClientError> {
    let (url, invite) = parse_link(link)?;
    let mut report = Report::default();
    let mut started = Instant::now();
    let backoff = Backoff::default();
    let mut resume: Option<String> = None;
    let mut attempt = 0u32;
    loop {
        match once(
            &url,
            &invite,
            &mut resume,
            &opts,
            &mut report,
            &mut started,
            &mut attempt,
        )
        .await
        {
            Ok(()) => {
                report.seconds = started.elapsed().as_secs_f64();
                return Ok(report);
            }
            Err(Fail::Fatal(e)) => return Err(e),
            Err(Fail::Retry(e)) => match backoff.delay(attempt, 0.5) {
                Some(d) if started.elapsed() < opts.duration => {
                    eprintln!("{e}; retrying in {d:?}");
                    attempt += 1;
                    tokio::time::sleep(d).await;
                }
                _ => return Err(e),
            },
        }
    }
}

async fn once(
    url: &str,
    invite: &str,
    resume: &mut Option<String>,
    opts: &Options,
    report: &mut Report,
    started: &mut Instant,
    attempt: &mut u32,
) -> Result<(), Fail> {
    let (mut ws, _) = connect_async(url).await.map_err(retry)?;
    let hello = ClientMsg::Hello {
        version: PROTOCOL_VERSION,
        device: opts.device.clone(),
        invite: if resume.is_none() {
            Some(invite.to_string())
        } else {
            None
        },
        resume: resume.clone(),
    };
    send(&mut ws, &hello).await.map_err(Fail::Retry)?;
    let (resume_token, control) = loop {
        match recv(&mut ws, opts.wait_for_owner)
            .await
            .map_err(Fail::Retry)?
        {
            ServerMsg::Pending { expires_in_s, .. } => {
                eprintln!("waiting for the owner to approve ({expires_in_s}s)…")
            }
            ServerMsg::Granted {
                resume_token,
                control,
                ..
            } => break (resume_token, control),
            ServerMsg::Denied { reason } => {
                return Err(Fail::Fatal(err(format!("denied: {reason}"))))
            }
            ServerMsg::Error { code, message } => {
                return Err(Fail::Fatal(err(format!("{code}: {message}"))))
            }
            ServerMsg::Ended { reason } => {
                return Err(Fail::Fatal(err(format!("ended: {reason}"))))
            }
            _ => {}
        }
    };
    if resume.is_none() {
        // The clock measures streaming, not how long the owner took to answer.
        *started = Instant::now();
    }
    *resume = Some(resume_token);
    report.control_granted = control;

    let mut viewer = ViewerPeer::new(&opts.rtc).await.map_err(retry)?;
    let offer = viewer.create_offer().await.map_err(retry)?;
    send(&mut ws, &ClientMsg::Offer { sdp: offer })
        .await
        .map_err(Fail::Retry)?;
    let answer = loop {
        match recv(&mut ws, Duration::from_secs(15))
            .await
            .map_err(Fail::Retry)?
        {
            ServerMsg::Answer { sdp } => break sdp,
            ServerMsg::Error { code, message } => {
                return Err(Fail::Fatal(err(format!("{code}: {message}"))))
            }
            _ => {}
        }
    };
    viewer.set_answer(answer).await.map_err(retry)?;
    viewer
        .wait_connected(Duration::from_secs(15))
        .await
        .map_err(retry)?;
    *attempt = 0;

    let mut sent_input = false;
    let result = 'stream: loop {
        if started.elapsed() >= opts.duration {
            break 'stream Ok(());
        }
        if let Some(f) = viewer.next_frame(Duration::from_millis(250)).await {
            note_frame(report, &f, *started);
        }
        while let Some(ev) = viewer.next_event(Duration::from_millis(1)).await {
            match ev {
                HostEvent::Rejected { reason } => report.rejected.push(reason),
                HostEvent::Mode { control } => report.control_granted = control,
                HostEvent::Ended { reason } => {
                    report.ended = Some(reason);
                    break 'stream Ok(());
                }
                HostEvent::Pong { .. } => {}
            }
        }
        if opts.send_input && !sent_input && report.frames > 5 {
            sent_input = true;
            let _ = viewer
                .send_input(&InputEvent::Move { dx: 1.0, dy: 1.0 })
                .await;
        }
        if matches!(
            viewer.link_state(),
            remote_rtc::LinkState::Failed | remote_rtc::LinkState::Closed
        ) {
            break 'stream Err(retry("connection lost"));
        }
    };
    viewer.close().await;
    if result.is_ok() {
        let _ = send(&mut ws, &ClientMsg::Bye).await;
    }
    result
}

fn note_frame(report: &mut Report, f: &Frame, started: Instant) {
    report.frames += 1;
    report.width = f.width;
    report.height = f.height;
    report
        .first_frame_ms
        .get_or_insert(started.elapsed().as_millis());
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_invite_links() {
        let (ws, tok) = parse_link("http://100.64.0.9:8484/#i=abc_DEF-123").unwrap();
        assert_eq!(ws, "ws://100.64.0.9:8484/ws");
        assert_eq!(tok, "abc_DEF-123");
        assert!(parse_link("https://x/#i=a").is_err());
        assert!(parse_link("http://x:1/").is_err());
    }
}
