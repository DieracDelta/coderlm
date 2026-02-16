# Using CodeRLM with Gemini CLI

This repository includes a Gemini CLI skill that enables structural codebase exploration.

## Installation

1.  **Build the Server**:
    ```bash
    cd server
    cargo build --release
    ```

2.  **Start the Server**:
    ```bash
    ./target/release/coderlm-server serve /path/to/your/project
    ```

3.  **Install the Skill**:
    If you are in the `coderlm-gemini` directory, you can use the local skill:
    ```bash
    gemini skills install ./plugin/skills/coderlm-gemini --scope project
    ```

## Usage

Once the server is running and the skill is installed, you can use the `/coderlm` skill in your Gemini CLI sessions.

### Initialization

The skill needs to be initialized in each project you want to explore:

```bash
python3 .gemini/coderlm_state/coderlm_cli.py init
```

### Exploration

You can then ask Gemini to explore the codebase:

```
/coderlm query="How does the indexing logic work?"
```

## How it Works

The Gemini skill uses a Python CLI wrapper (`coderlm_cli.py`) to communicate with the Rust-based `coderlm-server`. For complex queries, it can spawn sub-agents (recursive calls to Gemini CLI) to analyze specific parts of the codebase without overloading the main conversation context.
