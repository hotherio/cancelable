# Installation

Cancelable requires **Python 3.12+**.

## Quick Start

=== "uv"
    ```bash
    uv add hother-cancelable
    ```

=== "pip"
    ```bash
    pip install hother-cancelable
    ```

## With Integrations

Install with optional integration groups:

=== "uv"
    ```bash
    # Web framework
    uv add "hother-cancelable[fastapi]"
    ```

=== "pip"
    ```bash
    # Web framework
    pip install "hother-cancelable[fastapi]"
    ```

## With Examples

To run the example scripts from the repository:

=== "uv"
    ```bash
    uv add "hother-cancelable[examples]"
    ```

=== "pip"
    ```bash
    pip install "hother-cancelable[examples]"
    ```

Includes:

- `google-genai` - For LLM streaming examples
- `pynput` - For input monitoring examples
- `psutil` - For resource monitoring

Then clone the repository and run examples:

```bash
git clone https://github.com/hotherio/cancelable.git
cd cancelable
uv run examples/01_basics/01_basic_cancelation.py
```

Browse all examples: [Examples Documentation](examples/index.md)


## Available Extras

| Extra | Includes | Use Case |
|-------|----------|----------|
| `fastapi` | fastapi | Web framework integration |
| `examples` | google-genai, pynput, psutil | Running example scripts from repository |

## Next Steps

<div class="grid cards" markdown>

-   :material-clock-fast:{ .lg .middle } __Getting Started__

    ---

    Learn the basics and start using Cancelable

    [:octicons-arrow-right-24: Get Started](getting_started.md)

-   :material-code-braces:{ .lg .middle } __Browse Examples__

    ---

    Complete runnable examples for common use cases

    [:octicons-arrow-right-24: View Examples](examples/index.md)

-   :material-book-open-variant:{ .lg .middle } __Integrations__

    ---

    Framework-specific integration guides

    [:octicons-arrow-right-24: Learn Integrations](integrations/index.md)

-   :material-api:{ .lg .middle } __API Reference__

    ---

    Complete API documentation

    [:octicons-arrow-right-24: API Docs](reference/index.md)

</div>
