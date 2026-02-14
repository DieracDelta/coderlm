use crate::server::session::HistoryEntry;
use crate::server::state::AppState;
use serde::Serialize;

pub fn get_history(state: &AppState, session_id: &str, limit: usize) -> Result<Vec<HistoryEntry>, String> {
    let session = state
        .inner
        .sessions
        .get(session_id)
        .ok_or_else(|| format!("Session '{}' not found", session_id))?;

    let history = &session.history;
    let start = history.len().saturating_sub(limit);
    Ok(history[start..].to_vec())
}

#[derive(Debug, Serialize)]
pub struct SessionHistoryBlock {
    pub session_id: String,
    pub project: String,
    pub entries: Vec<HistoryEntry>,
}

/// Return history from all active sessions, ordered by timestamp.
pub fn get_all_history(state: &AppState, limit: usize) -> Vec<SessionHistoryBlock> {
    let mut blocks: Vec<SessionHistoryBlock> = state
        .inner
        .sessions
        .iter()
        .map(|entry| {
            let session = entry.value();
            let history = &session.history;
            let start = history.len().saturating_sub(limit);
            SessionHistoryBlock {
                session_id: session.id.clone(),
                project: session.project_path.display().to_string(),
                entries: history[start..].to_vec(),
            }
        })
        .collect();

    // Sort blocks by most recent activity (latest entry timestamp descending)
    blocks.sort_by(|a, b| {
        let a_latest = a.entries.last().map(|e| e.timestamp);
        let b_latest = b.entries.last().map(|e| e.timestamp);
        b_latest.cmp(&a_latest)
    });

    blocks
}

/// Compact history: group consecutive same-path operations into summaries,
/// keeping the most recent `keep_recent` entries uncompacted.
pub fn compact_history(
    state: &AppState,
    session_id: &str,
    keep_recent: usize,
) -> Result<CompactResult, String> {
    let mut session = state
        .inner
        .sessions
        .get_mut(session_id)
        .ok_or_else(|| format!("Session '{}' not found", session_id))?;

    let total = session.history.len();
    if total <= keep_recent {
        return Ok(CompactResult {
            original_count: total,
            compacted_count: total,
            removed: 0,
        });
    }

    let split_point = total - keep_recent;
    let to_compact = &session.history[..split_point];
    let recent = session.history[split_point..].to_vec();

    // Group consecutive entries by (method, path)
    let mut compacted: Vec<HistoryEntry> = Vec::new();
    let mut i = 0;
    while i < to_compact.len() {
        let current = &to_compact[i];
        let mut count = 1;
        while i + count < to_compact.len()
            && to_compact[i + count].method == current.method
            && to_compact[i + count].path == current.path
        {
            count += 1;
        }

        if count > 1 {
            compacted.push(HistoryEntry {
                timestamp: current.timestamp,
                method: current.method.clone(),
                path: current.path.clone(),
                response_preview: format!("[{} calls compacted]", count),
            });
        } else {
            compacted.push(current.clone());
        }
        i += count;
    }

    let compacted_count = compacted.len() + recent.len();
    let removed = total - compacted_count;

    compacted.extend(recent);
    session.history = compacted;

    Ok(CompactResult {
        original_count: total,
        compacted_count,
        removed,
    })
}

#[derive(Debug, Serialize)]
pub struct CompactResult {
    pub original_count: usize,
    pub compacted_count: usize,
    pub removed: usize,
}
