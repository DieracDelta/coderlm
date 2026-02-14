use std::path::PathBuf;
use std::sync::Arc;

use chrono::{DateTime, Utc};
use dashmap::DashMap;
use serde::{Deserialize, Serialize};

// ── Buffer types ─────────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Buffer {
    pub name: String,
    pub content: String,
    pub source: BufferSource,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum BufferSource {
    File {
        path: String,
        start_line: usize,
        end_line: usize,
    },
    Symbol {
        name: String,
        file: String,
    },
    Grep {
        pattern: String,
    },
    SubLmResult {
        query: String,
    },
    Computed {
        description: String,
    },
}

/// Metadata-only view of a buffer (never includes full content).
#[derive(Debug, Clone, Serialize)]
pub struct BufferInfo {
    pub name: String,
    pub size_bytes: usize,
    pub line_count: usize,
    pub source: BufferSource,
    pub preview: String,
    pub created_at: DateTime<Utc>,
}

impl BufferInfo {
    pub fn from_buffer(buf: &Buffer) -> Self {
        let preview = if buf.content.len() > 200 {
            format!("{}...", &buf.content[..200])
        } else {
            buf.content.clone()
        };
        Self {
            name: buf.name.clone(),
            size_bytes: buf.content.len(),
            line_count: buf.content.lines().count(),
            source: buf.source.clone(),
            preview,
            created_at: buf.created_at,
        }
    }
}

// ── REPL state ───────────────────────────────────────────────────────

#[derive(Debug, Default)]
pub struct ReplState {
    pub buffers: DashMap<String, Buffer>,
    pub variables: DashMap<String, serde_json::Value>,
}

// ── History & Session ────────────────────────────────────────────────

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryEntry {
    pub timestamp: DateTime<Utc>,
    pub method: String,
    pub path: String,
    pub response_preview: String,
}

#[derive(Debug, Clone)]
pub struct Session {
    pub id: String,
    pub project_path: PathBuf,
    pub created_at: DateTime<Utc>,
    pub last_active: DateTime<Utc>,
    pub history: Vec<HistoryEntry>,
    pub repl_state: Arc<ReplState>,
}

impl Session {
    pub fn new(id: String, project_path: PathBuf) -> Self {
        let now = Utc::now();
        Self {
            id,
            project_path,
            created_at: now,
            last_active: now,
            history: Vec::new(),
            repl_state: Arc::new(ReplState::default()),
        }
    }

    pub fn record(&mut self, method: &str, path: &str, response_preview: &str) {
        self.last_active = Utc::now();
        self.history.push(HistoryEntry {
            timestamp: Utc::now(),
            method: method.to_string(),
            path: path.to_string(),
            response_preview: if response_preview.len() > 200 {
                format!("{}...", &response_preview[..200])
            } else {
                response_preview.to_string()
            },
        });
    }
}
