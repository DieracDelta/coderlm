use super::LanguageConfig;

pub const SYMBOLS_QUERY: &str = r#"
(def
  name: (identifier) @function.name) @function.def

(theorem
  name: (identifier) @function.name) @function.def

(abbrev
  name: (identifier) @function.name) @function.def

(instance
  name: (identifier) @function.name) @function.def

(structure
  "structure"
  name: (identifier) @struct.name) @struct.def

(structure
  "class"
  name: (identifier) @class.name) @class.def

(class_inductive
  name: (identifier) @class.name) @class.def

(inductive
  name: (identifier) @enum.name) @enum.def

(constant
  name: (identifier) @const.name) @const.def

(axiom
  name: (identifier) @const.name) @const.def

(namespace
  name: (identifier) @mod.name) @mod.def
"#;

pub const CALLERS_QUERY: &str = r#"
(apply
  name: (identifier) @callee)
"#;

pub const VARIABLES_QUERY: &str = r#"
(let
  name: (identifier) @var.name)
"#;

pub fn config() -> LanguageConfig {
    LanguageConfig {
        language: tree_sitter_lean::LANGUAGE.into(),
        symbols_query: SYMBOLS_QUERY,
        callers_query: CALLERS_QUERY,
        variables_query: VARIABLES_QUERY,
        test_patterns: vec![],
    }
}
