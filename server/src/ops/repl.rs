use std::path::Path;
use std::sync::Arc;

use chrono::Utc;
use serde::Serialize;

use crate::index::file_entry::Language;
use crate::index::file_tree::FileTree;
use crate::server::session::{Buffer, BufferInfo, BufferSource, ReplState, SubcallResult};
use crate::symbols::SymbolTable;

// ── Buffer operations ────────────────────────────────────────────────

pub fn buffer_create(
    repl: &Arc<ReplState>,
    name: &str,
    content: String,
    description: &str,
) -> BufferInfo {
    let buf = Buffer {
        name: name.to_string(),
        content,
        source: BufferSource::Computed {
            description: description.to_string(),
        },
        created_at: Utc::now(),
    };
    let info = BufferInfo::from_buffer(&buf);
    repl.buffers.insert(name.to_string(), buf);
    info
}

pub fn buffer_from_file(
    repl: &Arc<ReplState>,
    root: &Path,
    file_tree: &Arc<FileTree>,
    name: &str,
    file: &str,
    start: usize,
    end: usize,
) -> Result<BufferInfo, String> {
    let entry = file_tree
        .get(file)
        .ok_or_else(|| format!("File '{}' not found in index", file))?;

    let abs_path = root.join(file);
    let source = if entry.language == Language::Pdf {
        crate::index::pdf::convert_pdf(root, file)
            .map_err(|e| format!("PDF conversion failed for '{}': {}", file, e))?
    } else {
        std::fs::read_to_string(&abs_path)
            .map_err(|e| format!("Failed to read '{}': {}", file, e))?
    };

    let lines: Vec<&str> = source.lines().collect();
    let total_lines = lines.len();
    let start = start.min(total_lines);
    let end = end.min(total_lines);

    let content: String = lines[start..end].join("\n");

    let buf = Buffer {
        name: name.to_string(),
        content,
        source: BufferSource::File {
            path: file.to_string(),
            start_line: start,
            end_line: end,
        },
        created_at: Utc::now(),
    };
    let info = BufferInfo::from_buffer(&buf);
    repl.buffers.insert(name.to_string(), buf);
    Ok(info)
}

pub fn buffer_from_symbol(
    repl: &Arc<ReplState>,
    root: &Path,
    symbol_table: &Arc<SymbolTable>,
    name: &str,
    symbol_name: &str,
    file: &str,
) -> Result<BufferInfo, String> {
    let sym = symbol_table
        .get(file, symbol_name)
        .ok_or_else(|| format!("Symbol '{}' not found in '{}'", symbol_name, file))?;

    let abs_path = root.join(&sym.file);
    let source = if sym.language == Language::Pdf {
        crate::index::pdf::convert_pdf(root, &sym.file)
            .map_err(|e| format!("PDF conversion failed for '{}': {}", sym.file, e))?
    } else {
        std::fs::read_to_string(&abs_path)
            .map_err(|e| format!("Failed to read '{}': {}", sym.file, e))?
    };

    let start = sym.byte_range.0;
    let end = sym.byte_range.1.min(source.len());
    let content = source[start..end].to_string();

    let buf = Buffer {
        name: name.to_string(),
        content,
        source: BufferSource::Symbol {
            name: symbol_name.to_string(),
            file: file.to_string(),
        },
        created_at: Utc::now(),
    };
    let info = BufferInfo::from_buffer(&buf);
    repl.buffers.insert(name.to_string(), buf);
    Ok(info)
}

pub fn buffer_peek(
    repl: &Arc<ReplState>,
    name: &str,
    start: usize,
    end: usize,
) -> Result<String, String> {
    let buf = repl
        .buffers
        .get(name)
        .ok_or_else(|| format!("Buffer '{}' not found", name))?;

    let content = &buf.content;
    let start = start.min(content.len());
    let end = end.min(content.len());
    Ok(content[start..end].to_string())
}

pub fn buffer_list(repl: &Arc<ReplState>) -> Vec<BufferInfo> {
    repl.buffers
        .iter()
        .map(|entry| BufferInfo::from_buffer(entry.value()))
        .collect()
}

pub fn buffer_info(repl: &Arc<ReplState>, name: &str) -> Result<BufferInfo, String> {
    let buf = repl
        .buffers
        .get(name)
        .ok_or_else(|| format!("Buffer '{}' not found", name))?;
    Ok(BufferInfo::from_buffer(buf.value()))
}

pub fn buffer_delete(repl: &Arc<ReplState>, name: &str) -> Result<(), String> {
    repl.buffers
        .remove(name)
        .map(|_| ())
        .ok_or_else(|| format!("Buffer '{}' not found", name))
}

// ── Variable operations ──────────────────────────────────────────────

pub fn var_set(repl: &Arc<ReplState>, name: &str, value: serde_json::Value) {
    repl.variables.insert(name.to_string(), value);
}

pub fn var_get(repl: &Arc<ReplState>, name: &str) -> Result<serde_json::Value, String> {
    repl.variables
        .get(name)
        .map(|v| v.value().clone())
        .ok_or_else(|| format!("Variable '{}' not found", name))
}

pub fn var_list(repl: &Arc<ReplState>) -> Vec<(String, serde_json::Value)> {
    repl.variables
        .iter()
        .map(|entry| (entry.key().clone(), entry.value().clone()))
        .collect()
}

pub fn var_delete(repl: &Arc<ReplState>, name: &str) -> Result<(), String> {
    repl.variables
        .remove(name)
        .map(|_| ())
        .ok_or_else(|| format!("Variable '{}' not found", name))
}

pub fn check_final(repl: &Arc<ReplState>) -> Option<serde_json::Value> {
    repl.variables.get("Final").map(|v| v.value().clone())
}

// ── Subcall results ──────────────────────────────────────────────────

pub fn add_subcall_result(repl: &Arc<ReplState>, result: SubcallResult) {
    repl.subcall_results.lock().push(result);
}

pub fn list_subcall_results(repl: &Arc<ReplState>) -> Vec<SubcallResult> {
    repl.subcall_results.lock().clone()
}

pub fn clear_subcall_results(repl: &Arc<ReplState>) {
    repl.subcall_results.lock().clear();
}

// ── Semantic chunking ────────────────────────────────────────────────

#[derive(Debug, Serialize)]
pub struct SemanticChunk {
    pub index: usize,
    pub byte_start: usize,
    pub byte_end: usize,
    pub line_start: usize,
    pub line_end: usize,
    pub symbols: Vec<String>,
    pub preview: String,
}

pub fn semantic_chunks(
    root: &Path,
    file_tree: &Arc<FileTree>,
    symbol_table: &Arc<SymbolTable>,
    file: &str,
    max_chunk_bytes: usize,
) -> Result<Vec<SemanticChunk>, String> {
    let entry = file_tree
        .get(file)
        .ok_or_else(|| format!("File '{}' not found in index", file))?;

    let abs_path = root.join(file);
    let source = if entry.language == Language::Pdf {
        crate::index::pdf::convert_pdf(root, file)
            .map_err(|e| format!("PDF conversion failed for '{}': {}", file, e))?
    } else {
        std::fs::read_to_string(&abs_path)
            .map_err(|e| format!("Failed to read '{}': {}", file, e))?
    };

    // Get all symbols in this file, sorted by byte range start
    let mut file_symbols = symbol_table.list_by_file(file);
    file_symbols.sort_by_key(|s| s.byte_range.0);

    if file_symbols.is_empty() {
        // No symbols: fall back to byte-boundary chunks
        return Ok(simple_chunks(&source, max_chunk_bytes));
    }

    // Build chunks aligned to symbol boundaries
    let mut chunks = Vec::new();
    let mut chunk_start = 0usize;
    let mut chunk_symbols: Vec<String> = Vec::new();
    let mut chunk_index = 0usize;

    for sym in &file_symbols {
        let sym_start = sym.byte_range.0;
        let sym_end = sym.byte_range.1.min(source.len());
        let sym_size = sym_end - sym_start;

        // If adding this symbol would exceed the budget and we have content,
        // finalize the current chunk
        if chunk_start < sym_start
            && (sym_end - chunk_start) > max_chunk_bytes
            && !chunk_symbols.is_empty()
        {
            // Close chunk at the start of this symbol
            let chunk_end = sym_start;
            chunks.push(make_chunk(
                &source,
                chunk_index,
                chunk_start,
                chunk_end,
                &chunk_symbols,
            ));
            chunk_index += 1;
            chunk_symbols.clear();
            chunk_start = sym_start;
        }

        // If a single symbol exceeds the budget, it gets its own chunk
        if sym_size > max_chunk_bytes && chunk_symbols.is_empty() {
            chunk_symbols.push(sym.name.clone());
            chunks.push(make_chunk(
                &source,
                chunk_index,
                sym_start,
                sym_end,
                &chunk_symbols,
            ));
            chunk_index += 1;
            chunk_symbols.clear();
            chunk_start = sym_end;
            continue;
        }

        chunk_symbols.push(sym.name.clone());
    }

    // Final chunk: from chunk_start to end of file
    if chunk_start < source.len() {
        chunks.push(make_chunk(
            &source,
            chunk_index,
            chunk_start,
            source.len(),
            &chunk_symbols,
        ));
    }

    Ok(chunks)
}

fn make_chunk(
    source: &str,
    index: usize,
    byte_start: usize,
    byte_end: usize,
    symbols: &[String],
) -> SemanticChunk {
    let line_start = source[..byte_start].lines().count();
    let line_end = source[..byte_end].lines().count();
    let slice = &source[byte_start..byte_end];
    let preview = if slice.len() > 200 {
        let trunc = slice.floor_char_boundary(200);
        format!("{}...", &slice[..trunc])
    } else {
        slice.to_string()
    };

    SemanticChunk {
        index,
        byte_start,
        byte_end,
        line_start,
        line_end,
        symbols: symbols.to_vec(),
        preview,
    }
}

fn simple_chunks(source: &str, max_chunk_bytes: usize) -> Vec<SemanticChunk> {
    let mut chunks = Vec::new();
    let mut start = 0;
    let mut index = 0;

    while start < source.len() {
        let mut end = source.floor_char_boundary((start + max_chunk_bytes).min(source.len()));
        // Try to break at a newline
        if end < source.len() {
            if let Some(nl) = source[start..end].rfind('\n') {
                end = start + nl + 1;
            }
        }
        chunks.push(make_chunk(source, index, start, end, &[]));
        index += 1;
        start = end;
    }

    chunks
}
