//! The phone-facing listener: static web client + the signalling WebSocket.
//!
//! Nothing here is trusted: the page is static, `/ws` accepts only a bounded
//! `hello` carrying a single-use invite or a signed resume token, and the
//! owner's yes is required (and obtained out of band, over D-Bus) before a
//! single frame is sent.

use std::net::SocketAddr;
use std::sync::Arc;

use axum::extract::ws::{CloseFrame, Message, WebSocket, WebSocketUpgrade};
use axum::extract::{ConnectInfo, State};
use axum::http::{header, HeaderMap, HeaderValue, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::routing::get;
use axum::Router;
use futures::{SinkExt, StreamExt};
use remote_core::protocol::{ClientMsg, ServerMsg, MAX_SIGNAL_BYTES};
use tokio::net::TcpListener;
use tokio::sync::{mpsc, Semaphore};

use crate::controller::Controller;

const INDEX: &str = include_str!("../web/index.html");
const APP_JS: &str = include_str!("../web/app.js");
const STYLE: &str = include_str!("../web/style.css");
const MANIFEST: &str = include_str!("../web/manifest.webmanifest");
const ICON: &str = include_str!("../web/icon.svg");

/// Unauthenticated sockets are cheap but not free.
const MAX_SOCKETS: usize = 4;

#[derive(Clone)]
struct App {
    ctl: Arc<Controller>,
    sockets: Arc<Semaphore>,
}

const CSP: &str = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; \
media-src 'self' blob:; connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'";

fn asset(content_type: &'static str, body: &'static str) -> Response {
    let mut h = HeaderMap::new();
    h.insert(header::CONTENT_TYPE, HeaderValue::from_static(content_type));
    h.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    h.insert(
        header::CONTENT_SECURITY_POLICY,
        HeaderValue::from_static(CSP),
    );
    h.insert(
        header::X_CONTENT_TYPE_OPTIONS,
        HeaderValue::from_static("nosniff"),
    );
    h.insert(
        header::REFERRER_POLICY,
        HeaderValue::from_static("no-referrer"),
    );
    h.insert("x-frame-options", HeaderValue::from_static("DENY"));
    (StatusCode::OK, h, body).into_response()
}

pub fn router(ctl: Arc<Controller>) -> Router {
    let app = App {
        ctl,
        sockets: Arc::new(Semaphore::new(MAX_SOCKETS)),
    };
    Router::new()
        .route(
            "/",
            get(|| async { asset("text/html; charset=utf-8", INDEX) }),
        )
        .route(
            "/app.js",
            get(|| async { asset("text/javascript; charset=utf-8", APP_JS) }),
        )
        .route(
            "/style.css",
            get(|| async { asset("text/css; charset=utf-8", STYLE) }),
        )
        .route(
            "/manifest.webmanifest",
            get(|| async { asset("application/manifest+json", MANIFEST) }),
        )
        .route("/icon.svg", get(|| async { asset("image/svg+xml", ICON) }))
        .route("/ws", get(ws_handler))
        .with_state(app)
}

/// Same-origin only: a web page on another site must not be able to drive a
/// pairing socket from the owner's browser.
fn origin_ok(headers: &HeaderMap) -> bool {
    let Some(origin) = headers.get(header::ORIGIN) else {
        return true;
    };
    let host = headers.get(header::HOST).and_then(|h| h.to_str().ok());
    let origin = origin.to_str().ok();
    match (origin, host) {
        (Some(o), Some(h)) => {
            o.strip_prefix("http://")
                .or_else(|| o.strip_prefix("https://"))
                == Some(h)
        }
        _ => false,
    }
}

async fn ws_handler(
    State(app): State<App>,
    ConnectInfo(peer): ConnectInfo<SocketAddr>,
    headers: HeaderMap,
    ws: WebSocketUpgrade,
) -> Response {
    if !origin_ok(&headers) {
        return StatusCode::FORBIDDEN.into_response();
    }
    let Ok(permit) = app.sockets.clone().try_acquire_owned() else {
        return StatusCode::SERVICE_UNAVAILABLE.into_response();
    };
    ws.max_message_size(MAX_SIGNAL_BYTES)
        .max_frame_size(MAX_SIGNAL_BYTES)
        .on_upgrade(move |socket| async move {
            run_socket(app.ctl.clone(), socket, Some(peer)).await;
            drop(permit);
        })
}

fn is_terminal(msg: &ServerMsg) -> bool {
    matches!(
        msg,
        ServerMsg::Ended { .. } | ServerMsg::Denied { .. } | ServerMsg::Error { .. }
    )
}

async fn run_socket(ctl: Arc<Controller>, socket: WebSocket, remote: Option<SocketAddr>) {
    let (mut sink, mut stream) = socket.split();
    let (to_ctl, from_ws) = mpsc::channel::<ClientMsg>(16);
    let (to_ws, mut from_ctl) = mpsc::unbounded_channel::<ServerMsg>();

    let serve = tokio::spawn(ctl.serve_viewer(from_ws, to_ws.clone(), remote));

    let writer = tokio::spawn(async move {
        while let Some(msg) = from_ctl.recv().await {
            let terminal = is_terminal(&msg);
            let Ok(text) = serde_json::to_string(&msg) else {
                continue;
            };
            if sink.send(Message::Text(text.into())).await.is_err() {
                break;
            }
            if terminal {
                let _ = sink
                    .send(Message::Close(Some(CloseFrame {
                        code: 1000,
                        reason: "done".into(),
                    })))
                    .await;
                break;
            }
        }
        let _ = sink.close().await;
    });

    while let Some(Ok(frame)) = stream.next().await {
        match frame {
            Message::Text(t) => match ClientMsg::parse(&t) {
                Ok(msg) => {
                    if to_ctl.send(msg).await.is_err() {
                        break;
                    }
                }
                Err(e) => {
                    let _ = to_ws.send(ServerMsg::Error {
                        code: "bad_message".into(),
                        message: e.to_string(),
                    });
                    break;
                }
            },
            Message::Close(_) => break,
            Message::Ping(_) | Message::Pong(_) => {}
            Message::Binary(_) => {
                let _ = to_ws.send(ServerMsg::Error {
                    code: "bad_message".into(),
                    message: "text only".into(),
                });
                break;
            }
        }
    }
    drop(to_ctl);
    drop(to_ws);
    let _ = serve.await;
    let _ = writer.await;
}

/// Bind the listener while sharing is enabled; drop it (and every socket)
/// when it is turned off.
pub async fn run_listener_manager(ctl: Arc<Controller>) {
    let mut enabled = ctl.enabled_rx();
    loop {
        if !*enabled.borrow_and_update() {
            if enabled.changed().await.is_err() {
                return;
            }
            continue;
        }
        let addr: SocketAddr = match ctl.config().listen.parse() {
            Ok(a) => a,
            Err(_) => return,
        };
        let listener = match TcpListener::bind(addr).await {
            Ok(l) => l,
            Err(e) => {
                tracing::error!("cannot listen on {addr}: {e}");
                ctl.set_listen_addr(None);
                if enabled.changed().await.is_err() {
                    return;
                }
                continue;
            }
        };
        let local = listener.local_addr().ok();
        ctl.set_listen_addr(local);
        tracing::info!("remote desktop listening on {local:?}");
        let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
        let server = axum::serve(
            listener,
            router(ctl.clone()).into_make_service_with_connect_info::<SocketAddr>(),
        )
        .with_graceful_shutdown(async move {
            let _ = stop_rx.await;
        });
        let task = tokio::spawn(async move {
            let _ = server.await;
        });
        loop {
            if enabled.changed().await.is_err() {
                let _ = stop_tx.send(());
                return;
            }
            if !*enabled.borrow() {
                break;
            }
        }
        // Graceful shutdown waits for sockets; the controller already ended the session.
        let _ = stop_tx.send(());
        let abort = task.abort_handle();
        if tokio::time::timeout(std::time::Duration::from_secs(2), task)
            .await
            .is_err()
        {
            abort.abort();
        }
        ctl.set_listen_addr(None);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn h(origin: Option<&str>, host: &str) -> HeaderMap {
        let mut m = HeaderMap::new();
        if let Some(o) = origin {
            m.insert(header::ORIGIN, o.parse().unwrap());
        }
        m.insert(header::HOST, host.parse().unwrap());
        m
    }

    #[test]
    fn origin_must_match_host() {
        assert!(origin_ok(&h(None, "100.64.0.9:8484")));
        assert!(origin_ok(&h(
            Some("http://100.64.0.9:8484"),
            "100.64.0.9:8484"
        )));
        assert!(!origin_ok(&h(
            Some("http://evil.example"),
            "100.64.0.9:8484"
        )));
        assert!(!origin_ok(&h(Some("null"), "100.64.0.9:8484")));
    }
}
