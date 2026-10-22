//! Cursor-based older-thread history from the T3 orchestration HTTP API.

use super::{auth, http, model::TurnItem};
use serde::Deserialize;
use serde_json::Value;

#[derive(Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct ProjectedTurnItem {
    pub position: u64,
    pub source_thread_id: String,
    pub source_item_id: String,
    pub item: TurnItem,
}

#[derive(Deserialize, Debug)]
#[serde(rename_all = "camelCase")]
pub struct ThreadHistoryPage {
    pub snapshot_sequence: u64,
    pub items: Vec<ProjectedTurnItem>,
    pub next_cursor: Option<String>,
    pub has_more_history: bool,
}

fn error_message(body: &str) -> String {
    serde_json::from_str::<Value>(body)
        .ok()
        .and_then(|value| {
            value
                .get("message")
                .and_then(Value::as_str)
                .or_else(|| value.get("reason").and_then(Value::as_str))
                .map(str::to_string)
        })
        .unwrap_or_else(|| "The T3 server could not load earlier history.".to_string())
}

pub async fn fetch_page(cred: &auth::Credential, thread_id: &str, cursor: &str) -> Result<ThreadHistoryPage, String> {
    let query = http::form(&[("cursor", cursor)]);
    let url = format!(
        "{}/api/orchestration/threads/{}/history?{}",
        cred.server.trim_end_matches('/'),
        http::path_segment(thread_id),
        query
    );
    let authorization = format!("Bearer {}", cred.access_token);
    let protocol = auth::PROTOCOL_VERSION.to_string();
    let response = http::request(
        "GET",
        &url,
        &[
            ("Authorization", &authorization),
            ("Accept", "application/json"),
            ("x-t3-orchestration-protocol", &protocol),
        ],
        None,
    )
    .await
    .map_err(|error| error.to_string())?;
    if !(200..300).contains(&response.status) {
        return Err(format!("{} (HTTP {})", error_message(&response.body), response.status));
    }
    serde_json::from_str(&response.body).map_err(|error| format!("Invalid T3 history response: {error}"))
}
