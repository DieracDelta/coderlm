pub mod parser;
pub mod queries;
pub mod symbol;

use dashmap::DashMap;
use std::collections::HashSet;

use symbol::Symbol;

/// A cached reference to a call site.
#[derive(Debug, Clone, serde::Serialize)]
pub struct CallerRef {
    pub file: String,
    pub line: usize,
    pub text: String,
}

/// Thread-safe symbol table with secondary indices for fast lookup.
pub struct SymbolTable {
    /// Primary store: keyed by "file::name"
    pub symbols: DashMap<String, Symbol>,
    /// Secondary index: symbol name -> set of primary keys
    pub by_name: DashMap<String, HashSet<String>>,
    /// Secondary index: file path -> set of primary keys
    pub by_file: DashMap<String, HashSet<String>>,
    /// Reverse call graph: callee name -> list of call sites.
    /// Populated during symbol extraction for O(1) caller lookup.
    pub reverse_call_graph: DashMap<String, Vec<CallerRef>>,
}

impl SymbolTable {
    pub fn new() -> Self {
        Self {
            symbols: DashMap::new(),
            by_name: DashMap::new(),
            by_file: DashMap::new(),
            reverse_call_graph: DashMap::new(),
        }
    }

    /// Record a call site: `callee_name` is called from `file` at `line`.
    pub fn add_caller(&self, callee_name: &str, file: &str, line: usize, text: &str) {
        self.reverse_call_graph
            .entry(callee_name.to_string())
            .or_default()
            .push(CallerRef {
                file: file.to_string(),
                line,
                text: text.to_string(),
            });
    }

    /// Get cached callers for a symbol name. Returns None if not populated.
    pub fn get_callers(&self, name: &str) -> Option<Vec<CallerRef>> {
        self.reverse_call_graph.get(name).map(|v| v.clone())
    }

    pub fn make_key(file: &str, name: &str) -> String {
        format!("{}::{}", file, name)
    }

    pub fn insert(&self, symbol: Symbol) {
        let key = Self::make_key(&symbol.file, &symbol.name);

        // Update secondary indices
        self.by_name
            .entry(symbol.name.clone())
            .or_insert_with(HashSet::new)
            .insert(key.clone());
        self.by_file
            .entry(symbol.file.clone())
            .or_insert_with(HashSet::new)
            .insert(key.clone());

        self.symbols.insert(key, symbol);
    }

    /// Remove call graph entries originating from a file.
    pub fn remove_callers_from_file(&self, file: &str) {
        for mut entry in self.reverse_call_graph.iter_mut() {
            entry.value_mut().retain(|c| c.file != file);
        }
        // Clean up empty entries
        self.reverse_call_graph.retain(|_, v| !v.is_empty());
    }

    pub fn remove_file(&self, file: &str) {
        self.remove_callers_from_file(file);
        if let Some((_, keys)) = self.by_file.remove(file) {
            for key in &keys {
                if let Some((_, sym)) = self.symbols.remove(key) {
                    if let Some(mut name_set) = self.by_name.get_mut(&sym.name) {
                        name_set.remove(key);
                        if name_set.is_empty() {
                            drop(name_set);
                            self.by_name.remove(&sym.name);
                        }
                    }
                }
            }
        }
    }

    pub fn get(&self, file: &str, name: &str) -> Option<Symbol> {
        let key = Self::make_key(file, name);
        self.symbols.get(&key).map(|r| r.value().clone())
    }

    pub fn search(&self, query: &str, limit: usize) -> Vec<Symbol> {
        let query_lower = query.to_lowercase();
        let mut results = Vec::new();
        for entry in self.symbols.iter() {
            if entry.value().name.to_lowercase().contains(&query_lower) {
                results.push(entry.value().clone());
                if results.len() >= limit {
                    break;
                }
            }
        }
        results
    }

    pub fn list_by_file(&self, file: &str) -> Vec<Symbol> {
        if let Some(keys) = self.by_file.get(file) {
            keys.iter()
                .filter_map(|key| self.symbols.get(key).map(|r| r.value().clone()))
                .collect()
        } else {
            Vec::new()
        }
    }

    pub fn all_symbols(&self) -> Vec<Symbol> {
        self.symbols.iter().map(|r| r.value().clone()).collect()
    }

    pub fn len(&self) -> usize {
        self.symbols.len()
    }
}
