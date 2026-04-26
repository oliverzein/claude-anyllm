# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with this repository.

## Overview

This repo contains a lightweight HTTP proxy that translates Anthropic Messages API requests into OpenAI-compatible calls against the Atlas Cloud API (`https://api.atlascloud.ai/v1`). It allows tools expecting the Anthropic API shape to work with Atlas Cloud models.

## Key Files

- `test.py` — Minimal smoke test using the `openai` SDK to hit Atlas Cloud directly.
- `tests/` — Unit tests for the modular proxy package.

## Running the Proxy

After installing the package (`pip install -e .`), use the console script:

```bash
export ATLASCLOUD_API_KEY="your-key"
atlas-anthropic-proxy
```

Or, without installing:

```bash
export ATLASCLOUD_API_KEY="your-key"
python -m atlas_proxy.server
```

The proxy exposes:
- `POST /v1/messages` — Anthropic-compatible Messages API endpoint (supports `stream: true`)
- `POST /v1/messages/count_tokens` — Approximate token count estimate
- `GET /health` — Liveness check. Always returns `200` with `{"ok": true, "streaming": <bool>}`. Does **not** verify upstream connectivity — use this for load-balancer health probes.
- `GET /ready` — Readiness check. Calls `list_models()` upstream and verifies the default model exists. Returns `200` or `503`.
- `GET /v1/models` — Proxy for upstream `/v1/models`.

### Environment Variables

| Variable | Purpose |
|---|---|
| `ATLASCLOUD_API_KEY` | Required. API key for Atlas Cloud |
| `ANTHROPIC_BASE_URL` | Point to the proxy (e.g. `http://127.0.0.1:8082`) |
| `ANTHROPIC_AUTH_TOKEN` | Set to any dummy value (proxy reads key from env) |
| `ANTHROPIC_MODEL` | Model name passed to Anthropic API |

### CLI Flags / Env Vars (modular version)

| Flag | Env Var | Default |
|---|---|---|
| `--host` | `ATLAS_PROXY_HOST` | `127.0.0.1` |
| `--port` | `ATLAS_PROXY_PORT` | `8082` |
| `--atlas-base-url` | `ATLAS_BASE_URL` | `https://api.atlascloud.ai/v1` |
| `--default-model` | `ATLAS_PROXY_DEFAULT_MODEL` | `qwen/qwen3.6-plus` |
| `--timeout-seconds` | `ATLAS_PROXY_TIMEOUT_SECONDS` | `600` |
| `--enable-upstream-streaming` | `ATLAS_PROXY_ENABLE_UPSTREAM_STREAMING` | `true` |
| `--debug` | `ATLAS_PROXY_DEBUG` | `false` |

### Running Tests

```bash
python -m unittest discover -s tests
# or individual files
python -m unittest tests/test_anthropic_bridge.py
python -m unittest tests/test_atlas_client.py
python -m unittest tests/test_validation.py
python -m unittest tests/test_server.py
python -m unittest tests/test_config.py
```

## Architecture

The modular proxy (`atlas_proxy/`) splits responsibilities across:

1. **Config** (`config.py`): `Config` dataclass with CLI/CLI+env parsing. Supports host, port, base URL, API key, timeout, streaming toggle, and debug mode.

2. **Validation** (`validation.py`): Validates incoming Anthropic requests — checks messages array, content block types (`text`, `tool_use`, `tool_result`), tool definitions (no duplicate names), and `tool_choice` semantics (auto/any/tool with name reference validation). Raises `ProxyError` on failure.

3. **Protocol Translation** (`anthropic.py`): Bidirectional mapping between Anthropic and OpenAI formats:
   - `anthropic_to_openai_request()` — Converts system blocks, multi-part content, tools, `tool_choice` (auto→auto, any→required, tool→function binding), `stop_sequences`→`stop`, `top_p`.
   - `openai_to_anthropic_message()` — Wraps OpenAI responses in Anthropic `message` type with proper `stop_reason` inference (tool_use vs end_turn).
   - SSE event generation for streaming: `anthropic_message_to_sse_events()` (non-streaming → faux-SSE), `openai_stream_chunk_to_sse_events()` (incremental streaming → Anthropic SSE), `finalize_sse_events()` (cleanup on stream end).

4. **Atlas Transport** (`atlas.py`): `AtlasClient` wraps `httpx` for non-streaming (`create_chat_completion`) and streaming (`iter_chat_completion_stream`) requests. Includes retry logic for connect/read errors (2 retries), upstream error mapping, `list_models()`, and `readiness_check()`.

5. **Error Mapping** (`errors.py`): `ProxyError` exception with `to_anthropic()` method for Anthropic-shaped error responses. `map_upstream_error()` translates HTTP status codes to Anthropic error types (400→invalid_request, 401/403→authentication, 429→rate_limit).

6. **HTTP Server** (`server.py`): `ProxyHandler` handles routing, validation, and mode dispatch. Routes `stream: true` → `handle_streaming_request()` (SSE pass-through) vs `handle_non_streaming_request()` (full response). Also handles `/v1/messages/count_tokens` endpoint.

7. **Logging** (`logging_utils.py`): JSON debug logging to stderr, controlled by `--debug` flag.

The default model is `qwen/qwen3.6-plus`.
