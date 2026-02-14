use super::LanguageConfig;

pub const SYMBOLS_QUERY: &str = r#"
(section
  (atx_heading
    heading_content: (inline) @mod.name)) @mod.def

(section
  (setext_heading
    heading_content: (paragraph) @mod.name)) @mod.def
"#;

pub const CALLERS_QUERY: &str = "";
pub const VARIABLES_QUERY: &str = "";

pub fn config() -> LanguageConfig {
    LanguageConfig {
        language: tree_sitter_md::LANGUAGE.into(),
        symbols_query: SYMBOLS_QUERY,
        callers_query: CALLERS_QUERY,
        variables_query: VARIABLES_QUERY,
        test_patterns: vec![],
    }
}
