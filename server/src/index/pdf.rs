use anyhow::{Context, Result};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use tracing::debug;

/// Returns the cache path for converted PDF markdown: `<root>/.coderlm/converted/<rel_path>.md`
pub fn cache_path(root: &Path, rel_path: &str) -> PathBuf {
    root.join(".coderlm")
        .join("converted")
        .join(format!("{}.md", rel_path))
}

/// Reads cached markdown if it exists and is newer than the source PDF.
pub fn get_cached_markdown(root: &Path, rel_path: &str) -> Option<String> {
    let cached = cache_path(root, rel_path);
    let pdf_path = root.join(rel_path);

    let pdf_mtime = fs::metadata(&pdf_path).ok()?.modified().ok()?;
    let cache_mtime = fs::metadata(&cached).ok()?.modified().ok()?;

    if cache_mtime >= pdf_mtime {
        fs::read_to_string(&cached).ok()
    } else {
        None
    }
}

/// Convert a PDF to markdown using pymupdf4llm, caching the result.
/// Returns the markdown content.
pub fn convert_pdf(root: &Path, rel_path: &str) -> Result<String> {
    // Check cache first
    if let Some(cached) = get_cached_markdown(root, rel_path) {
        debug!("Using cached markdown for {}", rel_path);
        return Ok(cached);
    }

    let abs_path = root.join(rel_path);
    let abs_str = abs_path
        .to_str()
        .context("PDF path is not valid UTF-8")?;

    debug!("Converting PDF to markdown: {}", rel_path);

    let output = Command::new("python3")
        .arg("-c")
        .arg("import pymupdf4llm, sys; print(pymupdf4llm.to_markdown(sys.argv[1]))")
        .arg(abs_str)
        .output()
        .context("Failed to spawn python3 for PDF conversion — is pymupdf4llm installed?")?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        anyhow::bail!("pymupdf4llm failed for '{}': {}", rel_path, stderr.trim());
    }

    let markdown = String::from_utf8(output.stdout)
        .context("pymupdf4llm produced non-UTF-8 output")?;

    // Write to cache
    let cached = cache_path(root, rel_path);
    if let Some(parent) = cached.parent() {
        fs::create_dir_all(parent)
            .with_context(|| format!("Failed to create cache dir {:?}", parent))?;
    }
    fs::write(&cached, &markdown)
        .with_context(|| format!("Failed to write cache file {:?}", cached))?;

    debug!("Cached converted markdown for {} ({} bytes)", rel_path, markdown.len());
    Ok(markdown)
}
