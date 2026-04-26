# STATUS

## Current State

This repo contains a modular Anthropic-to-OpenAI compatibility proxy for Atlas Cloud in [atlas_proxy](/home/oliverzein/atlas_test/atlas_proxy).

The proxy is actively used to run Claude Code against Atlas Cloud models that are only exposed through the OpenAI-compatible `/v1/chat/completions` API.

The project-local Claude settings currently point Claude Code at the local proxy on `127.0.0.1:8083` and use:

- `moonshotai/kimi-k2.6`

File:

- [.claude/settings.local.json](/home/oliverzein/atlas_test/.claude/settings.local.json)

## Canonical Run Command

After installing the package, start the proxy with:

```bash
atlas-anthropic-proxy --port 8083 --debug
```

Prerequisite:

```bash
export ATLASCLOUD_API_KEY="your-key"
```

Notes:

- The old `atlas_anthropic_proxy.py` launcher has been removed.
- `python -m atlas_proxy.server` currently triggers a `runpy` warning because `atlas_proxy.__init__` imports `server`.
- For direct repo execution without installing, use:

```bash
.venv/bin/python -c 'from atlas_proxy import run_server; run_server(["--port","8083","--debug"])'
```

## Endpoints

- `POST /v1/messages`
- `POST /v1/messages/count_tokens`
- `GET /health`
- `GET /ready`
- `GET /v1/models`

## What Works

- Non-streaming Anthropic-compatible message requests
- Streaming Anthropic-compatible message requests
- Tool-call translation (`tool_use`)
- Tool-result round trips (`tool_result`)
- Multi-turn tool loops
- Claude Code running against the local proxy
- `count_tokens` compatibility route for Claude Code

## Known Limitations

- `/v1/messages/count_tokens` is only an approximation, not a true tokenizer-based count
- Streaming usage accounting is approximate
- Long Kimi sessions can hit upstream Atlas `400 bad request` failures after many turns
- Those late-session failures appear correlated with large accumulated request payloads
- Request-size logging is now present, but a production default guardrail is not yet configured
- The packaged CLI exists, but some docs may still refer to older startup commands

## Recent Fixes

- Suppressed noisy `ConnectionResetError` tracebacks when clients disconnect
- Implemented `/v1/messages/count_tokens`
- Closed SSE connections explicitly after `message_stop` so Claude Code does not hang
- Added response-summary debug logging
- Added request-size logging via `request_bytes`
- Added optional local request-size guardrail support via:
  - `ATLAS_PROXY_MAX_REQUEST_BYTES`
  - `--max-request-bytes`

## Recommended Checks In A New Session

1. Read [CLAUDE.md](/home/oliverzein/atlas_test/CLAUDE.md)
2. Read this file
3. Confirm proxy settings in [.claude/settings.local.json](/home/oliverzein/atlas_test/.claude/settings.local.json)
4. Run:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

5. If needed, start the proxy with the canonical run command above

## Immediate Next Priorities

1. Improve server-level streaming tests
2. Use `request_bytes` logs to identify a sensible default request-size guardrail
3. Investigate Atlas/Kimi late-session `400 bad request` failures with concrete size data
4. Keep generated docs aligned with the packaged CLI and current guardrail options
