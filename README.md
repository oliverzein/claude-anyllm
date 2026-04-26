# Atlas Anthropic Proxy

A lightweight HTTP proxy that translates [Anthropic Messages API](https://docs.anthropic.com/en/api/messages) requests into OpenAI-compatible calls against the [Atlas Cloud API](https://api.atlascloud.ai/v1). Allows tools expecting the Anthropic API shape (e.g. Claude Code) to work with Atlas Cloud models.

## Requirements

- Python >= 3.11

## Installation

From the project root:

```bash
.venv/bin/python -m pip install -e .
```

Or to install with dev dependencies (for running tests):

```bash
.venv/bin/python -m pip install -e ".[dev]"
```

If you prefer the shorter `pip` and `atlas-anthropic-proxy` commands, activate the
virtualenv first.

For `fish`:

```fish
source .venv/bin/activate.fish
python -m pip install -e .
```

For `bash`/`zsh`:

```bash
source .venv/bin/activate
python -m pip install -e .
```

## Quick Start

If you have not activated the virtualenv, call the script via the repo-local path:

```bash
export ATLASCLOUD_API_KEY="your-key"
.venv/bin/atlas-anthropic-proxy
```

The proxy listens on `http://127.0.0.1:8082` by default.

If you activated the venv first, the shorter command also works:

```bash
source .venv/bin/activate
atlas-anthropic-proxy
```

If you don't want to install the package, you can run directly:

```bash
export ATLASCLOUD_API_KEY="your-key"
.venv/bin/python -c 'from atlas_proxy import run_server; run_server()'
```

`python -m atlas_proxy.server` currently emits a `runpy` warning because
`atlas_proxy.__init__` imports `server`, so the direct `python -c` form above is
the cleaner non-installed entry point.

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ATLASCLOUD_API_KEY` | Yes | — | API key for Atlas Cloud |
| `ATLAS_PROXY_HOST` | No | `127.0.0.1` | Bind address |
| `ATLAS_PROXY_PORT` | No | `8082` | Bind port (1–65535) |
| `ATLAS_BASE_URL` | No | `https://api.atlascloud.ai/v1` | Upstream API base URL |
| `ATLAS_PROXY_DEFAULT_MODEL` | No | `qwen/qwen3.6-plus` | Fallback model when the client request omits one |
| `ATLAS_PROXY_TIMEOUT_SECONDS` | No | `600` | Request timeout (> 0) |
| `ATLAS_PROXY_ENABLE_UPSTREAM_STREAMING` | No | `true` | Enable SSE streaming |
| `ATLAS_PROXY_DEBUG` | No | `false` | Enable JSON debug logging |
| `ATLAS_PROXY_MAX_REQUEST_BYTES` | No | unset | Reject oversized requests before forwarding upstream |

### CLI Flags

All flags mirror the env vars above:

```bash
.venv/bin/atlas-anthropic-proxy \
  --host 0.0.0.0 \
  --port 9090 \
  --default-model "other/model" \
  --timeout-seconds 30 \
  --max-request-bytes 1048576 \
  --debug
```

## Usage with Anthropic SDKs

Point your Anthropic-compatible tool at the proxy:

```bash
export ANTHROPIC_BASE_URL="http://127.0.0.1:8082"
export ANTHROPIC_AUTH_TOKEN="dummy"    # any non-empty value
export ANTHROPIC_MODEL="qwen/qwen3.6-plus"
```

Then use any Anthropic SDK or tool normally — requests will be proxied to Atlas Cloud.

The model set via `ANTHROPIC_MODEL` is sent with every request and always takes precedence. The proxy's `--default-model` flag is only used as a fallback when a client request omits the model field entirely.

## API Endpoints

| Endpoint | Description |
|---|---|
| `POST /v1/messages` | Anthropic-compatible messages endpoint. Supports `stream: true` for SSE streaming. |
| `POST /v1/messages/count_tokens` | Returns an approximate input token count. |
| `GET /health` | Liveness probe. Always returns `200` — safe for load balancer health checks. |
| `GET /ready` | Readiness probe. Verifies upstream connectivity and that the default model exists. Returns `200` or `503`. |
| `GET /v1/models` | Lists available Atlas Cloud models. |

## Running Tests

```bash
python -m unittest discover -s tests
```

## Architecture

The proxy is structured as a modular package under `atlas_proxy/`:

- **`config.py`** — Configuration dataclass with CLI + env var parsing and validation
- **`validation.py`** — Request validation (messages, tools, tool_choice)
- **`anthropic.py`** — Bidirectional protocol translation + SSE event generation for streaming
- **`atlas.py`** — HTTP transport to Atlas Cloud with retry logic and streaming support
- **`errors.py`** — Error types mapped to Anthropic error shapes
- **`server.py`** — HTTP request handler with routing and streaming dispatch
- **`logging_utils.py`** — JSON debug logging

The default model is `qwen/qwen3.6-plus`.
