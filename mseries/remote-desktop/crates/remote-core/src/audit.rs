//! Append-only audit trail. Records who/when/what-permission, never frame
//! content and never typed text (only event counts).

use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::Path;
use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};

use crate::clock::Millis;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AuditEvent {
    pub ts_ms: Millis,
    pub event: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub device: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub detail: Option<String>,
}

pub trait AuditSink: Send {
    fn record(&mut self, event: &AuditEvent);
}

/// In-memory sink; clone the handle to inspect events from a test.
#[derive(Clone, Default)]
pub struct MemoryAudit(Arc<Mutex<Vec<AuditEvent>>>);

impl MemoryAudit {
    pub fn events(&self) -> Vec<AuditEvent> {
        self.0.lock().unwrap().clone()
    }

    pub fn names(&self) -> Vec<String> {
        self.events().into_iter().map(|e| e.event).collect()
    }
}

impl AuditSink for MemoryAudit {
    fn record(&mut self, event: &AuditEvent) {
        self.0.lock().unwrap().push(event.clone());
    }
}

/// JSON Lines file, owner-readable only.
pub struct FileAudit {
    file: File,
}

impl FileAudit {
    pub fn open(path: &Path) -> std::io::Result<Self> {
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir)?;
        }
        let mut opts = OpenOptions::new();
        opts.create(true).append(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            opts.mode(0o600);
        }
        Ok(Self {
            file: opts.open(path)?,
        })
    }
}

impl AuditSink for FileAudit {
    fn record(&mut self, event: &AuditEvent) {
        if let Ok(mut line) = serde_json::to_vec(event) {
            line.push(b'\n');
            if let Err(e) = self.file.write_all(&line).and_then(|_| self.file.flush()) {
                tracing::error!("audit write failed: {e}");
            }
        }
    }
}
