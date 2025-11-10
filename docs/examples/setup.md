# Setup

Here we include some examples of how to use Cancelable and what it can do.

## Installation

Install Cancelable with the examples dependencies:

=== "uv"
    ```bash
    uv add "hother-cancelable[examples]"
    ```

=== "pip"
    ```bash
    pip install "hother-cancelable[examples]"
    ```

This installs the core library plus dependencies for running all examples:

- `google-genai` - For LLM streaming examples
- `pynput` - For keyboard input monitoring
- `psutil` - For system resource monitoring

## Getting the Examples

The examples are available in the [GitHub repository](https://github.com/hotherio/cancelable).

=== "uv"
    ```bash
    # Clone the repository
    git clone https://github.com/hotherio/cancelable.git
    cd cancelable

    # Install all dependencies
    uv sync
    ```

=== "pip"
    ```bash
    # Clone the repository
    git clone https://github.com/hotherio/cancelable.git
    cd cancelable

    # Create virtual environment
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate

    # Install dependencies
    pip install -e ".[examples]"
    ```

## Running Examples

Navigate to the examples directory and run any example:

```bash
cd examples

# Basic examples
uv run python 01_basics/01_basic_cancelation.py
```

## Optional Dependencies

Different examples require different integration libraries. Install only what you need:

### Web Framework (FastAPI)

For FastAPI examples:

=== "uv"
    ```bash
    uv add "hother-cancelable[fastapi]"
    ```

=== "pip"
    ```bash
    pip install "hother-cancelable[fastapi]"
    ```

**Examples requiring this:**
- `03_integrations/04_fastapi_example.py`

### All Integrations

Install everything at once:

=== "uv"
    ```bash
    uv add "hother-cancelable[fastapi,examples]"
    ```

=== "pip"
    ```bash
    pip install "hother-cancelable[fastapi,examples]"
    ```

## Environment Variables

Some examples require API keys or configuration:

### LLM Examples

The LLM streaming example requires a Gemini API key:

```bash
# Get your API key from https://aistudio.google.com/app/apikey
export GEMINI_API_KEY="your-api-key-here"

# Run the LLM example
python 06_llm/01_llm_streaming.py
```

!!! warning "API Key Required"
    Without a valid API key, the LLM examples will fail. All other examples work without any API keys.
