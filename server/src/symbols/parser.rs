use anyhow::Result;
use std::path::Path;
use std::sync::Arc;
use tree_sitter::StreamingIterator;
use tracing::{debug, warn};

use crate::index::file_entry::Language;
use crate::index::file_tree::FileTree;
use crate::symbols::queries;
use crate::symbols::symbol::{Symbol, SymbolKind};
use crate::symbols::SymbolTable;

/// Extract symbols from a single file.
pub fn extract_symbols_from_file(
    root: &Path,
    rel_path: &str,
    language: Language,
) -> Result<Vec<Symbol>> {
    let config = match queries::get_language_config(language) {
        Some(c) => c,
        None => return Ok(Vec::new()),
    };

    let abs_path = root.join(rel_path);
    let source = if language == Language::Pdf {
        crate::index::pdf::convert_pdf(root, rel_path)
            .map_err(|e| { warn!("PDF conversion failed for {}: {}", rel_path, e); e })?
    } else {
        std::fs::read_to_string(&abs_path)?
    };

    let mut parser = tree_sitter::Parser::new();
    parser.set_language(&config.language)?;

    let tree = match parser.parse(&source, None) {
        Some(t) => t,
        None => {
            warn!("Failed to parse {}", rel_path);
            return Ok(Vec::new());
        }
    };

    let query = tree_sitter::Query::new(&config.language, config.symbols_query)?;
    let mut cursor = tree_sitter::QueryCursor::new();
    let mut matches = cursor.matches(&query, tree.root_node(), source.as_bytes());

    let capture_names: Vec<String> = query.capture_names().iter().map(|s| s.to_string()).collect();

    let mut symbols = Vec::new();
    let mut current_impl_type: Option<String> = None;

    while let Some(m) = matches.next() {
        let mut name: Option<String> = None;
        let mut kind: Option<SymbolKind> = None;
        let mut def_node: Option<tree_sitter::Node> = None;
        let mut parent: Option<String> = None;

        for cap in m.captures {
            let cap_name = &capture_names[cap.index as usize];
            let text = cap.node.utf8_text(source.as_bytes()).unwrap_or("");

            match cap_name.as_str() {
                "function.name" => {
                    name = Some(text.to_string());
                    kind = Some(SymbolKind::Function);
                }
                "function.def" => {
                    def_node = Some(cap.node);
                }
                "method.name" => {
                    name = Some(text.to_string());
                    kind = Some(SymbolKind::Method);
                    parent = current_impl_type.clone();
                }
                "method.def" => {
                    def_node = Some(cap.node);
                }
                "impl.type" => {
                    current_impl_type = Some(text.to_string());
                }
                "struct.name" => {
                    name = Some(text.to_string());
                    kind = Some(SymbolKind::Struct);
                }
                "struct.def" => {
                    def_node = Some(cap.node);
                }
                "enum.name" => {
                    name = Some(text.to_string());
                    kind = Some(SymbolKind::Enum);
                }
                "enum.def" => {
                    def_node = Some(cap.node);
                }
                "trait.name" => {
                    name = Some(text.to_string());
                    kind = Some(SymbolKind::Trait);
                }
                "trait.def" => {
                    def_node = Some(cap.node);
                }
                "class.name" => {
                    name = Some(text.to_string());
                    kind = Some(SymbolKind::Class);
                }
                "class.def" => {
                    def_node = Some(cap.node);
                }
                "interface.name" => {
                    name = Some(text.to_string());
                    kind = Some(SymbolKind::Interface);
                }
                "interface.def" => {
                    def_node = Some(cap.node);
                }
                "type.name" => {
                    name = Some(text.to_string());
                    kind = Some(SymbolKind::Type);
                }
                "type.def" => {
                    def_node = Some(cap.node);
                }
                "const.name" => {
                    name = Some(text.to_string());
                    kind = Some(SymbolKind::Constant);
                }
                "const.def" => {
                    def_node = Some(cap.node);
                }
                "static.name" => {
                    name = Some(text.to_string());
                    kind = Some(SymbolKind::Constant);
                }
                "static.def" => {
                    def_node = Some(cap.node);
                }
                "mod.name" => {
                    name = Some(text.to_string());
                    kind = Some(SymbolKind::Module);
                }
                "mod.def" => {
                    def_node = Some(cap.node);
                }
                _ => {}
            }
        }

        if let (Some(name), Some(kind), Some(node)) = (name, kind, def_node) {
            let start = node.start_position();
            let end = node.end_position();
            let byte_range = (node.start_byte(), node.end_byte());
            let line_range = (start.row + 1, end.row + 1); // 1-indexed

            // Extract signature (first line of the definition)
            let node_text = node.utf8_text(source.as_bytes()).unwrap_or("");
            let signature = node_text.lines().next().unwrap_or("").to_string();

            symbols.push(Symbol {
                name,
                kind,
                file: rel_path.to_string(),
                byte_range,
                line_range,
                language,
                signature,
                definition: None,
                parent,
            });
        }
    }

    debug!("Extracted {} symbols from {}", symbols.len(), rel_path);
    Ok(symbols)
}

/// Extract call expressions from a file and return (callee_name, line, text) tuples.
fn extract_call_sites(
    root: &Path,
    rel_path: &str,
    language: Language,
) -> Vec<(String, usize, String)> {
    let config = match queries::get_language_config(language) {
        Some(c) => c,
        None => return Vec::new(),
    };

    let abs_path = root.join(rel_path);
    let source = if language == Language::Pdf {
        match crate::index::pdf::convert_pdf(root, rel_path) {
            Ok(s) => s,
            Err(_) => return Vec::new(),
        }
    } else {
        match std::fs::read_to_string(&abs_path) {
            Ok(s) => s,
            Err(_) => return Vec::new(),
        }
    };

    let mut parser = tree_sitter::Parser::new();
    if parser.set_language(&config.language).is_err() {
        return Vec::new();
    }

    let tree = match parser.parse(&source, None) {
        Some(t) => t,
        None => return Vec::new(),
    };

    let query = match tree_sitter::Query::new(&config.language, config.callers_query) {
        Ok(q) => q,
        Err(_) => return Vec::new(),
    };

    let capture_names: Vec<String> = query.capture_names().iter().map(|s| s.to_string()).collect();
    let callee_idx = capture_names.iter().position(|n| n == "callee");

    let mut cursor = tree_sitter::QueryCursor::new();
    let mut matches = cursor.matches(&query, tree.root_node(), source.as_bytes());
    let mut results = Vec::new();
    let lines: Vec<&str> = source.lines().collect();

    while let Some(m) = matches.next() {
        for cap in m.captures {
            if Some(cap.index as usize) == callee_idx {
                let text = cap.node.utf8_text(source.as_bytes()).unwrap_or("");
                if !text.is_empty() {
                    let line_num = cap.node.start_position().row + 1;
                    let line_text = lines
                        .get(line_num.saturating_sub(1))
                        .map(|l| l.trim().to_string())
                        .unwrap_or_default();
                    results.push((text.to_string(), line_num, line_text));
                }
            }
        }
    }

    results
}

/// Extract symbols from all files in the tree using rayon for parallelism.
/// Also builds the reverse call graph for O(1) caller lookups.
pub async fn extract_all_symbols(
    root: &Path,
    file_tree: &Arc<FileTree>,
    symbol_table: &Arc<SymbolTable>,
) -> Result<usize> {
    let root = root.to_path_buf();
    let file_tree = file_tree.clone();
    let symbol_table = symbol_table.clone();

    let count = tokio::task::spawn_blocking(move || -> Result<usize> {
        use rayon::prelude::*;

        let paths: Vec<(String, Language)> = file_tree
            .files
            .iter()
            .filter(|e| e.value().language.has_tree_sitter_support())
            .map(|e| (e.key().clone(), e.value().language))
            .collect();

        // Phase 1: Extract symbols in parallel
        let results: Vec<(String, Language, Vec<Symbol>)> = paths
            .par_iter()
            .filter_map(|(rel_path, language)| {
                match extract_symbols_from_file(&root, rel_path, *language) {
                    Ok(symbols) => Some((rel_path.clone(), *language, symbols)),
                    Err(e) => {
                        debug!("Failed to extract symbols from {}: {}", rel_path, e);
                        None
                    }
                }
            })
            .collect();

        // Insert symbols (sequential — DashMap is thread-safe but we batch for efficiency)
        let mut total = 0;
        for (rel_path, _, symbols) in &results {
            let count = symbols.len();
            for sym in symbols {
                symbol_table.insert(sym.clone());
            }
            if let Some(mut entry) = file_tree.files.get_mut(rel_path) {
                entry.symbols_extracted = true;
            }
            total += count;
        }

        // Phase 2: Build reverse call graph in parallel
        let call_sites: Vec<(String, Vec<(String, usize, String)>)> = paths
            .par_iter()
            .map(|(rel_path, language)| {
                let sites = extract_call_sites(&root, rel_path, *language);
                (rel_path.clone(), sites)
            })
            .collect();

        for (rel_path, sites) in call_sites {
            for (callee_name, line, text) in sites {
                symbol_table.add_caller(&callee_name, &rel_path, line, &text);
            }
        }

        Ok(total)
    })
    .await??;

    Ok(count)
}
