mod config;
mod index;
mod ops;
mod server;
mod symbols;

use std::path::PathBuf;

use clap::Parser;
use tracing::info;

use server::state::AppState;

#[derive(Parser)]
#[command(name = "coderlm", about = "CoderLM REPL server for code-aware agent sessions")]
struct Cli {
    /// Subcommand
    #[command(subcommand)]
    command: Commands,
}

#[derive(clap::Subcommand)]
enum Commands {
    /// Start the REPL server against a codebase
    Serve {
        /// Optional initial project directory to pre-index
        path: Option<PathBuf>,

        /// Port to listen on
        #[arg(short, long, default_value = "3001")]
        port: u16,

        /// Bind address
        #[arg(short, long, default_value = "127.0.0.1")]
        bind: String,

        /// Maximum file size in bytes to index
        #[arg(long, default_value_t = config::DEFAULT_MAX_FILE_SIZE)]
        max_file_size: u64,

        /// Maximum number of concurrent indexed projects
        #[arg(long, default_value = "5")]
        max_projects: usize,
    },
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .init();

    info!("coderlm v{}", env!("CARGO_PKG_VERSION"));

    let cli = Cli::parse();

    match cli.command {
        Commands::Serve {
            path,
            port,
            bind,
            max_file_size,
            max_projects,
        } => {
            run_server(path, port, bind, max_file_size, max_projects).await?;
        }
    }

    Ok(())
}

async fn run_server(
    path: Option<PathBuf>,
    port: u16,
    bind: String,
    max_file_size: u64,
    max_projects: usize,
) -> anyhow::Result<()> {
    // Create shared state
    let state = AppState::new(max_projects, max_file_size);

    // If an initial path was provided, pre-index it
    if let Some(ref p) = path {
        info!("Pre-indexing project: {}", p.display());
        state.get_or_create_project(p).map_err(|e| {
            anyhow::anyhow!("Failed to index '{}': {}", p.display(), e)
        })?;
    }

    // Build router
    let app = server::build_router(state);

    let addr = format!("{}:{}", bind, port);
    let listener = tokio::net::TcpListener::bind(&addr).await?;

    if let Some(ref p) = path {
        info!("coderlm serving {} on http://{}", p.display(), addr);
    } else {
        info!("coderlm server listening on http://{} (no project pre-indexed)", addr);
    }

    axum::serve(listener, app).await?;

    Ok(())
}
