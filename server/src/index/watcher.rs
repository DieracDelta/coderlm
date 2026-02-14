use anyhow::Result;
use chrono::{DateTime, Utc};
use notify_debouncer_mini::{new_debouncer, DebouncedEventKind};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;
use tracing::{debug, info, warn};

use crate::config;
use crate::index::file_entry::FileEntry;
use crate::index::file_tree::FileTree;
use crate::symbols::parser::extract_symbols_from_file;
use crate::symbols::SymbolTable;

/// Start the filesystem watcher. Returns a handle that keeps the watcher alive.
/// Drop the handle to stop watching.
pub fn start_watcher(
    root: &Path,
    file_tree: Arc<FileTree>,
    symbol_table: Arc<SymbolTable>,
    max_file_size: u64,
) -> Result<WatcherHandle> {
    let root_buf = root.to_path_buf();
    let root_for_handler = root_buf.clone();

    let mut debouncer = new_debouncer(
        Duration::from_millis(500),
        move |result: Result<Vec<notify_debouncer_mini::DebouncedEvent>, notify::Error>| {
            match result {
                Ok(events) => {
                    handle_events(
                        &root_for_handler,
                        &file_tree,
                        &symbol_table,
                        max_file_size,
                        events,
                    );
                }
                Err(e) => {
                    warn!("Filesystem watcher error: {}", e);
                }
            }
        },
    )?;

    debouncer
        .watcher()
        .watch(&root_buf, notify::RecursiveMode::Recursive)?;

    info!("Filesystem watcher started for {}", root_buf.display());

    Ok(WatcherHandle {
        _debouncer: Some(debouncer),
    })
}

pub struct WatcherHandle {
    _debouncer: Option<notify_debouncer_mini::Debouncer<notify::RecommendedWatcher>>,
}

fn handle_events(
    root: &PathBuf,
    file_tree: &Arc<FileTree>,
    symbol_table: &Arc<SymbolTable>,
    max_file_size: u64,
    events: Vec<notify_debouncer_mini::DebouncedEvent>,
) {
    for event in events {
        let path = &event.path;

        // Get relative path
        let rel_path = match path.strip_prefix(root) {
            Ok(r) => r.to_string_lossy().to_string(),
            Err(_) => continue,
        };

        // Skip ignored paths
        if should_skip(&rel_path) {
            continue;
        }

        match event.kind {
            DebouncedEventKind::Any => {
                if path.is_file() {
                    handle_file_change(root, file_tree, symbol_table, max_file_size, &rel_path, path);
                } else if !path.exists() {
                    handle_file_delete(file_tree, symbol_table, &rel_path);
                }
            }
            DebouncedEventKind::AnyContinuous => {
                // Ignore continuous events (they'll be followed by a final Any)
            }
            _ => {}
        }
    }
}

fn handle_file_change(
    root: &PathBuf,
    file_tree: &Arc<FileTree>,
    symbol_table: &Arc<SymbolTable>,
    max_file_size: u64,
    rel_path: &str,
    abs_path: &Path,
) {
    // Check extension-based ignoring
    if config::should_ignore_extension(rel_path) {
        return;
    }

    let metadata = match std::fs::metadata(abs_path) {
        Ok(m) => m,
        Err(_) => return,
    };

    let size = metadata.len();
    if size > max_file_size {
        return;
    }

    let modified: DateTime<Utc> = metadata
        .modified()
        .map(DateTime::from)
        .unwrap_or_else(|_| Utc::now());

    // Update file tree
    let entry = FileEntry::new(rel_path.to_string(), size, modified);
    let language = entry.language;
    file_tree.insert(entry);

    // Re-convert PDF before symbol extraction
    if language == crate::index::file_entry::Language::Pdf {
        if let Err(e) = crate::index::pdf::convert_pdf(root, rel_path) {
            debug!("Failed to re-convert PDF {}: {}", rel_path, e);
        }
    }

    // Re-extract symbols
    symbol_table.remove_file(rel_path);
    if language.has_tree_sitter_support() {
        match extract_symbols_from_file(root, rel_path, language) {
            Ok(symbols) => {
                let count = symbols.len();
                for sym in symbols {
                    symbol_table.insert(sym);
                }
                if let Some(mut entry) = file_tree.files.get_mut(rel_path) {
                    entry.symbols_extracted = true;
                }
                debug!("Re-extracted {} symbols from {}", count, rel_path);
            }
            Err(e) => {
                debug!("Failed to re-extract symbols from {}: {}", rel_path, e);
            }
        }
    }
}

fn handle_file_delete(
    file_tree: &Arc<FileTree>,
    symbol_table: &Arc<SymbolTable>,
    rel_path: &str,
) {
    if file_tree.remove(rel_path).is_some() {
        symbol_table.remove_file(rel_path);
        debug!("Removed {} from index", rel_path);
    }
}

fn should_skip(rel_path: &str) -> bool {
    for component in rel_path.split('/') {
        if config::should_ignore_dir(component) {
            return true;
        }
    }
    false
}
