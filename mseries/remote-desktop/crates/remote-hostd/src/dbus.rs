//! Session-bus control surface for the native UI (`io.elementary.mseries.Remote`).
//!
//! Every method here is an *owner* action: enabling sharing, minting an invite,
//! answering the consent prompt, changing permission, stopping. The network
//! listener never reaches this interface, and a sandboxed app cannot call it
//! unless the user granted it talk access to this bus name.

use std::sync::Arc;

use tokio::sync::broadcast::error::RecvError;
use zbus::object_server::SignalEmitter;

use crate::controller::{Controller, UiEvent};

pub const BUS_NAME: &str = "io.elementary.mseries.Remote";
pub const OBJECT_PATH: &str = "/io/elementary/mseries/Remote";
pub const INTERFACE: &str = "io.elementary.mseries.Remote1";

pub struct RemoteService {
    ctl: Arc<Controller>,
}

fn failed(e: impl ToString) -> zbus::fdo::Error {
    zbus::fdo::Error::Failed(e.to_string())
}

#[zbus::interface(name = "io.elementary.mseries.Remote1")]
impl RemoteService {
    /// JSON: `{enabled, listen, backend, phase, pending, session, grace_until_ms, invites_pending}`.
    async fn get_status(&self) -> String {
        serde_json::to_string(&self.ctl.status()).unwrap_or_default()
    }

    async fn set_enabled(&self, enabled: bool) {
        self.ctl.set_enabled(enabled).await;
    }

    /// JSON: `{links:[{label,url}], qr:[rows], expires_ms, control_offered}`.
    async fn create_invite(&self, allow_control: bool) -> zbus::fdo::Result<String> {
        let info = self.ctl.create_invite(allow_control).map_err(failed)?;
        serde_json::to_string(&info).map_err(failed)
    }

    async fn decide(&self, request_id: &str, allow: bool, control: bool) -> zbus::fdo::Result<()> {
        self.ctl
            .decide(request_id, allow, control)
            .await
            .map_err(failed)
    }

    async fn set_control(&self, control: bool) -> zbus::fdo::Result<()> {
        self.ctl.set_control(control).await.map_err(failed)
    }

    async fn stop(&self) {
        self.ctl.stop("the owner ended the session").await;
    }

    #[zbus(property)]
    async fn enabled(&self) -> bool {
        self.ctl.status().enabled
    }

    #[zbus(signal)]
    async fn status_changed(emitter: &SignalEmitter<'_>, status_json: &str) -> zbus::Result<()>;

    #[zbus(signal)]
    async fn consent_requested(emitter: &SignalEmitter<'_>, request_json: &str)
        -> zbus::Result<()>;
}

/// Claim the bus name and forward controller events as signals. Fails if
/// another instance already owns the name.
pub async fn serve(ctl: Arc<Controller>) -> zbus::Result<zbus::Connection> {
    let conn = zbus::connection::Builder::session()?
        .name(BUS_NAME)?
        .serve_at(OBJECT_PATH, RemoteService { ctl: ctl.clone() })?
        .build()
        .await?;
    let mut rx = ctl.subscribe();
    let emitter_conn = conn.clone();
    tokio::spawn(async move {
        let Ok(emitter) = SignalEmitter::new(&emitter_conn, OBJECT_PATH) else {
            return;
        };
        loop {
            match rx.recv().await {
                Ok(UiEvent::Status) => {
                    let json = serde_json::to_string(&ctl.status()).unwrap_or_default();
                    let _ = RemoteService::status_changed(&emitter, &json).await;
                }
                Ok(UiEvent::ConsentRequested(req)) => {
                    let json = serde_json::to_string(&req).unwrap_or_default();
                    let _ = RemoteService::consent_requested(&emitter, &json).await;
                }
                Err(RecvError::Lagged(_)) => continue,
                Err(RecvError::Closed) => break,
            }
        }
    });
    Ok(conn)
}

/// Thin client used by `mseries-remote-hostd ctl ...` and scripts.
#[zbus::proxy(
    interface = "io.elementary.mseries.Remote1",
    default_service = "io.elementary.mseries.Remote",
    default_path = "/io/elementary/mseries/Remote"
)]
pub trait Remote {
    fn get_status(&self) -> zbus::Result<String>;
    fn set_enabled(&self, enabled: bool) -> zbus::Result<()>;
    fn create_invite(&self, allow_control: bool) -> zbus::Result<String>;
    fn decide(&self, request_id: &str, allow: bool, control: bool) -> zbus::Result<()>;
    fn set_control(&self, control: bool) -> zbus::Result<()>;
    fn stop(&self) -> zbus::Result<()>;
}
