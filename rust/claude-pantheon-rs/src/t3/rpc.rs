//! Effect RPC over the WebSocket, JSON serialization (`RpcSerialization.layerJson`): one JSON envelope
//! per text frame. Client → server: `Request`, `Ack`, `Interrupt`, `Ping`. Server → client: `Chunk`,
//! `Exit`, `Defect`, `Pong`, `ClientProtocolError`. A unary call is a Request answered by one Exit; a
//! subscription is a Request answered by Chunks (each acknowledged) and a final Exit.

use super::ws::{Frame, WebSocket};
use futures_channel::{mpsc, oneshot};
use gtk::glib;
use serde::Deserialize;
use serde_json::{Value, json};
use std::cell::{Cell, RefCell};
use std::collections::HashMap;
use std::rc::Rc;
use std::time::{Duration, Instant};

const PING_INTERVAL: Duration = Duration::from_secs(5);
const PING_TIMEOUT: Duration = Duration::from_secs(15);

#[derive(Debug, Clone)]
pub enum RpcError {
    /// The server failed the request with this error value (`_tag`, `message`, …).
    Failed(Value),
    /// The connection died or the server reported a protocol defect.
    Transport(String),
    Interrupted,
}

impl RpcError {
    pub fn message(&self) -> String {
        match self {
            RpcError::Failed(v) => v
                .get("message")
                .and_then(Value::as_str)
                .map(str::to_string)
                .or_else(|| v.get("_tag").and_then(Value::as_str).map(str::to_string))
                .unwrap_or_else(|| v.to_string()),
            RpcError::Transport(s) => s.clone(),
            RpcError::Interrupted => "interrupted".into(),
        }
    }

    pub fn tag(&self) -> Option<&str> {
        match self {
            RpcError::Failed(v) => v.get("_tag").and_then(Value::as_str),
            _ => None,
        }
    }
}

impl std::fmt::Display for RpcError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message())
    }
}

/// Server → client envelope, decoded loosely so unknown tags are skipped rather than fatal.
#[derive(Deserialize, Default)]
#[serde(default)]
pub struct Incoming {
    #[serde(rename = "_tag")]
    pub tag: String,
    #[serde(rename = "requestId")]
    pub request_id: Option<Value>,
    pub values: Option<Vec<Value>>,
    pub exit: Option<Exit>,
    pub defect: Option<Value>,
    pub error: Option<Value>,
}

#[derive(Deserialize, Default)]
#[serde(default)]
pub struct Exit {
    #[serde(rename = "_tag")]
    pub tag: String,
    pub value: Option<Value>,
    pub cause: Option<Vec<Value>>,
}

impl Exit {
    /// The request's outcome as the client sees it.
    pub fn into_result(self) -> Result<Value, RpcError> {
        if self.tag == "Success" {
            return Ok(self.value.unwrap_or(Value::Null));
        }
        let cause = self.cause.unwrap_or_default();
        for c in &cause {
            match c.get("_tag").and_then(Value::as_str) {
                Some("Fail") => return Err(RpcError::Failed(c.get("error").cloned().unwrap_or(Value::Null))),
                Some("Die") => {
                    return Err(RpcError::Transport(format!(
                        "server defect: {}",
                        c.get("defect").unwrap_or(&Value::Null)
                    )));
                }
                Some("Interrupt") => return Err(RpcError::Interrupted),
                _ => {}
            }
        }
        Err(RpcError::Transport("request failed without a cause".into()))
    }
}

enum Pending {
    Unary(oneshot::Sender<Result<Value, RpcError>>),
    Stream(mpsc::UnboundedSender<Result<Value, RpcError>>),
}

enum OutgoingFrame {
    Text(String),
    Ping,
    Pong(Vec<u8>),
    Close,
}

struct Inner {
    ws: Rc<WebSocket>,
    next_id: Cell<u64>,
    pending: RefCell<HashMap<String, Pending>>,
    outgoing: mpsc::UnboundedSender<OutgoingFrame>,
    last_received: Cell<Instant>,
    closed: Cell<bool>,
    on_close: RefCell<Vec<CloseHook>>,
}

type CloseHook = Box<dyn Fn(String)>;

/// A connected RPC client. Clone freely; all clones share one socket.
#[derive(Clone)]
pub struct Rpc {
    inner: Rc<Inner>,
}

impl Rpc {
    /// Wraps an upgraded socket and starts the reader, writer and keep-alive tasks on the main loop.
    pub fn start(ws: Rc<WebSocket>) -> Rpc {
        Self::start_with_ping_timing(ws, PING_INTERVAL, PING_TIMEOUT)
    }

    fn start_with_ping_timing(ws: Rc<WebSocket>, ping_interval: Duration, ping_timeout: Duration) -> Rpc {
        let (out_tx, mut out_rx) = mpsc::unbounded::<OutgoingFrame>();
        let inner = Rc::new(Inner {
            ws: ws.clone(),
            next_id: Cell::new(1),
            pending: RefCell::new(HashMap::new()),
            outgoing: out_tx,
            last_received: Cell::new(Instant::now()),
            closed: Cell::new(false),
            on_close: RefCell::new(Vec::new()),
        });
        let rpc = Rpc { inner };

        // Writer: a single task serializes frames, so concurrent requests never interleave bytes.
        let w = rpc.clone();
        glib::spawn_future_local(async move {
            use futures_util::StreamExt;
            while let Some(frame) = out_rx.next().await {
                let result = match frame {
                    OutgoingFrame::Text(text) => w.inner.ws.send_text(&text).await,
                    OutgoingFrame::Ping => w.inner.ws.send_ping().await,
                    OutgoingFrame::Pong(payload) => w.inner.ws.send_pong(&payload).await,
                    OutgoingFrame::Close => {
                        let _ = w.inner.ws.send_close().await;
                        break;
                    }
                };
                if let Err(e) = result {
                    w.fail_all(format!("send failed: {e}"));
                    break;
                }
            }
        });

        // Reader.
        let r = rpc.clone();
        glib::spawn_future_local(async move {
            loop {
                if r.inner.closed.get() {
                    break;
                }
                match r.inner.ws.next().await {
                    Ok(frame) => {
                        r.inner.last_received.set(Instant::now());
                        match frame {
                            Frame::Text(text) => r.dispatch(&text),
                            Frame::Ping(payload) => {
                                let _ = r.inner.outgoing.unbounded_send(OutgoingFrame::Pong(payload));
                            }
                            Frame::Pong(_) | Frame::Binary(_) => {}
                            Frame::Close(code) => {
                                r.fail_all(format!("server closed the connection ({})", code.unwrap_or(0)));
                            }
                        }
                    }
                    Err(e) => {
                        r.fail_all(format!("connection lost: {e}"));
                    }
                }
            }
        });

        // Match T3's client-runtime socket health check. Any incoming frame is activity; the
        // timeout detects half-open Wi-Fi/relay links without treating long-running streams as idle.
        let k = rpc.clone();
        glib::spawn_future_local(async move {
            loop {
                glib::timeout_future(ping_interval).await;
                if k.inner.closed.get() {
                    break;
                }
                if heartbeat_expired(k.inner.last_received.get(), Instant::now(), ping_timeout) {
                    k.fail_all(format!("server stopped responding for {} seconds", ping_timeout.as_secs()));
                    break;
                }
                if k.inner.outgoing.unbounded_send(OutgoingFrame::Ping).is_err() {
                    k.fail_all("could not queue the WebSocket heartbeat".into());
                    break;
                }
            }
        });
        rpc
    }

    pub fn is_closed(&self) -> bool {
        self.inner.closed.get()
    }

    /// Runs `f` once with the reason when the connection ends.
    pub fn on_close(&self, f: impl Fn(String) + 'static) {
        self.inner.on_close.borrow_mut().push(Box::new(f));
    }

    fn send_json(&self, v: &Value) {
        if std::env::var_os("CLAUDE_PANTHEON_DEBUG").is_some() {
            let t = v.to_string();
            let tag = v.get("tag").and_then(Value::as_str).unwrap_or("");
            if matches!(
                tag,
                "provider.auth.start"
                    | "provider.auth.respond"
                    | "provider.auth.complete"
                    | "provider.chatgpt.import-profile"
                    | "server.updateSettings"
            ) {
                eprintln!("rpc -> {tag} <payload redacted; {} bytes>", t.len());
            } else {
                let preview: String = t.chars().take(160).collect();
                eprintln!("rpc -> {preview}");
            }
        }
        let _ = self.inner.outgoing.unbounded_send(OutgoingFrame::Text(v.to_string()));
    }

    fn new_id(&self) -> String {
        let id = self.inner.next_id.get();
        self.inner.next_id.set(id + 1);
        id.to_string()
    }

    fn request_envelope(&self, id: &str, tag: &str, payload: Value) -> Value {
        json!({"_tag": "Request", "id": id, "tag": tag, "payload": payload, "headers": []})
    }

    /// One request, one answer.
    pub async fn call(&self, tag: &str, payload: Value) -> Result<Value, RpcError> {
        debug_assert!(super::contracts::is_known(tag), "RPC tag {tag} is not in the vendored contracts");
        if self.inner.closed.get() {
            return Err(RpcError::Transport("not connected".into()));
        }
        let id = self.new_id();
        let (tx, rx) = oneshot::channel();
        self.inner.pending.borrow_mut().insert(id.clone(), Pending::Unary(tx));
        self.send_json(&self.request_envelope(&id, tag, payload));
        rx.await.unwrap_or_else(|_| Err(RpcError::Transport("connection closed".into())))
    }

    /// A streaming request: values arrive on the receiver until the server's Exit (Ok end) or an error.
    pub fn subscribe(&self, tag: &str, payload: Value) -> (String, mpsc::UnboundedReceiver<Result<Value, RpcError>>) {
        debug_assert!(super::contracts::is_known(tag), "RPC tag {tag} is not in the vendored contracts");
        let id = self.new_id();
        let (tx, rx) = mpsc::unbounded();
        if self.inner.closed.get() {
            let _ = tx.unbounded_send(Err(RpcError::Transport("not connected".into())));
            return (id, rx);
        }
        self.inner.pending.borrow_mut().insert(id.clone(), Pending::Stream(tx));
        self.send_json(&self.request_envelope(&id, tag, payload));
        (id, rx)
    }

    /// Ends a subscription (or an in-flight call) on the server.
    pub fn interrupt(&self, id: &str) {
        if self.inner.pending.borrow_mut().remove(id).is_some() {
            self.send_json(&json!({"_tag": "Interrupt", "requestId": id}));
        }
    }

    pub async fn close(&self) {
        self.inner.closed.set(true);
        let _ = self.inner.outgoing.unbounded_send(OutgoingFrame::Close);
    }

    fn dispatch(&self, text: &str) {
        if std::env::var_os("CLAUDE_PANTHEON_DEBUG").is_some() {
            // Stream chunks can contain terminal sign-in output. Keep debug mode useful without
            // writing provider prompts, callback URLs or credentials to the terminal.
            eprintln!("rpc <- {} bytes", text.len());
        }
        let Ok(msg) = serde_json::from_str::<Incoming>(text) else { return };
        match msg.tag.as_str() {
            "Chunk" => {
                let Some(id) = id_text(&msg.request_id) else { return };
                let values = msg.values.unwrap_or_default();
                let pending = self.inner.pending.borrow();
                if let Some(Pending::Stream(tx)) = pending.get(&id) {
                    for v in values {
                        let _ = tx.unbounded_send(Ok(v));
                    }
                }
                drop(pending);
                self.send_json(&json!({"_tag": "Ack", "requestId": id}));
            }
            "Exit" => {
                let Some(id) = id_text(&msg.request_id) else { return };
                let result = msg.exit.map(Exit::into_result).unwrap_or(Ok(Value::Null));
                let entry = self.inner.pending.borrow_mut().remove(&id);
                match entry {
                    Some(Pending::Unary(tx)) => {
                        let _ = tx.send(result);
                    }
                    Some(Pending::Stream(tx)) => {
                        if let Err(e) = result {
                            let _ = tx.unbounded_send(Err(e));
                        }
                        // dropping tx ends the stream
                    }
                    None => {}
                }
            }
            "Defect" => self.fail_all(format!("server defect: {}", msg.defect.unwrap_or(Value::Null))),
            "ClientProtocolError" => self.fail_all(format!("protocol error: {}", msg.error.unwrap_or(Value::Null))),
            _ => {} // Pong, server-originated Request
        }
    }

    fn fail_all(&self, reason: String) {
        if self.inner.closed.replace(true) {
            return;
        }
        let pending: Vec<Pending> = self.inner.pending.borrow_mut().drain().map(|(_, p)| p).collect();
        for p in pending {
            match p {
                Pending::Unary(tx) => {
                    let _ = tx.send(Err(RpcError::Transport(reason.clone())));
                }
                Pending::Stream(tx) => {
                    let _ = tx.unbounded_send(Err(RpcError::Transport(reason.clone())));
                }
            }
        }
        for f in self.inner.on_close.borrow().iter() {
            f(reason.clone());
        }
        let _ = self.inner.outgoing.unbounded_send(OutgoingFrame::Close);
    }
}

fn heartbeat_expired(last_received: Instant, now: Instant, timeout: Duration) -> bool {
    now.saturating_duration_since(last_received) >= timeout
}

fn id_text(v: &Option<Value>) -> Option<String> {
    match v {
        Some(Value::String(s)) => Some(s.clone()),
        Some(Value::Number(n)) => Some(n.to_string()),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn exits_decode() {
        let ok: Incoming =
            serde_json::from_str(r#"{"_tag":"Exit","requestId":"3","exit":{"_tag":"Success","value":{"x":1}}}"#)
                .unwrap();
        assert_eq!(ok.exit.unwrap().into_result().unwrap()["x"], 1);
        let fail: Incoming = serde_json::from_str(
            r#"{"_tag":"Exit","requestId":"4","exit":{"_tag":"Failure","cause":[{"_tag":"Fail","error":{"_tag":"EnvironmentAuthorizationError","message":"This connection requires orchestration:operate."}}]}}"#,
        )
        .unwrap();
        let err = fail.exit.unwrap().into_result().unwrap_err();
        assert_eq!(err.tag(), Some("EnvironmentAuthorizationError"));
        assert!(err.message().contains("orchestration:operate"));
        let chunk: Incoming =
            serde_json::from_str(r#"{"_tag":"Chunk","requestId":7,"values":[{"kind":"synchronized"}]}"#).unwrap();
        assert_eq!(id_text(&chunk.request_id).as_deref(), Some("7"));
        assert_eq!(chunk.values.unwrap().len(), 1);
    }

    #[test]
    fn heartbeat_expires_after_silence_and_resets_on_any_frame() {
        let last = Instant::now();
        assert!(!heartbeat_expired(last, last + PING_TIMEOUT - Duration::from_millis(1), PING_TIMEOUT));
        assert!(heartbeat_expired(last, last + PING_TIMEOUT, PING_TIMEOUT));
        let received = last + Duration::from_secs(14);
        assert!(!heartbeat_expired(received, last + PING_TIMEOUT, PING_TIMEOUT));
    }

    #[test]
    fn websocket_pings_detect_a_silent_peer_and_trigger_disconnect() {
        use std::io::{Read, Write};
        use std::net::TcpListener;
        use std::thread;

        fn server_accept(key: &str) -> String {
            let mut checksum = glib::Checksum::new(glib::ChecksumType::Sha1).unwrap();
            checksum.update(key.as_bytes());
            checksum.update(b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11");
            glib::base64_encode(&checksum.digest()).to_string()
        }

        fn accept_and_miss_later_pongs(listener: TcpListener) -> usize {
            let (mut stream, _) = listener.accept().unwrap();
            stream.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
            let mut request = Vec::new();
            let mut chunk = [0; 2048];
            while !request.windows(4).any(|window| window == b"\r\n\r\n") {
                let count = stream.read(&mut chunk).unwrap();
                assert!(count > 0, "client closed before the WebSocket upgrade");
                request.extend_from_slice(&chunk[..count]);
            }
            let request = String::from_utf8(request).unwrap();
            let key = request
                .lines()
                .find_map(|line| {
                    line.split_once(':').filter(|(name, _)| name.eq_ignore_ascii_case("Sec-WebSocket-Key"))
                })
                .map(|(_, value)| value.trim())
                .unwrap();
            let accept = server_accept(key);
            write!(
                stream,
                "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n"
            )
            .unwrap();

            let mut frames = Vec::new();
            let mut pings = 0;
            loop {
                let count = match stream.read(&mut chunk) {
                    Ok(0) => break,
                    Ok(count) => count,
                    Err(error)
                        if matches!(error.kind(), std::io::ErrorKind::WouldBlock | std::io::ErrorKind::TimedOut) =>
                    {
                        continue;
                    }
                    Err(error) => panic!("fake WebSocket read failed: {error}"),
                };
                frames.extend_from_slice(&chunk[..count]);
                while let Some((_, opcode, payload, used)) = super::super::ws::decode_frame(&frames).unwrap() {
                    frames.drain(..used);
                    match opcode {
                        9 => {
                            pings += 1;
                            if pings == 1 {
                                // One pong proves that receiving a frame resets the deadline.
                                stream.write_all(&[0x8a, payload.len() as u8]).unwrap();
                                stream.write_all(&payload).unwrap();
                            }
                        }
                        8 => return pings,
                        _ => {}
                    }
                }
            }
            pings
        }

        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let server = thread::spawn(move || accept_and_miss_later_pongs(listener));
        let (closed_tx, closed_rx) = std::sync::mpsc::channel();
        let context = gtk::glib::MainContext::new();
        let rpc = context.block_on(async {
            let ws = WebSocket::connect(&format!("ws://{address}/ws")).await.unwrap();
            let rpc = Rpc::start_with_ping_timing(ws, Duration::from_millis(20), Duration::from_millis(180));
            rpc.on_close(move |reason| {
                let _ = closed_tx.send(reason);
            });
            for _ in 0..100 {
                if rpc.is_closed() {
                    break;
                }
                glib::timeout_future(Duration::from_millis(10)).await;
            }
            assert!(rpc.is_closed(), "the missed pong must close the RPC session");
            rpc
        });
        let reason = closed_rx.recv_timeout(Duration::from_secs(1)).unwrap();
        assert!(reason.contains("server stopped responding"), "unexpected close reason: {reason}");
        assert!(server.join().unwrap() >= 2, "the heartbeat sent repeated WebSocket Ping frames");
        drop(rpc);
    }
}
