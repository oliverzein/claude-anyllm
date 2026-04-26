# Docker Deployment

Production-ready Docker configuration for deploying the `claude-anyllm` proxy.

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Atlas Cloud API key (`ATLASCLOUD_API_KEY`)

### Option 1: Docker Compose (Recommended)

```bash
export ATLASCLOUD_API_KEY="your-api-key"
docker compose up -d
```

This builds the image and starts the proxy on port 8082 with automatic restart and health checks.

### Option 2: Docker Run

```bash
# Build the image
docker build -t claude-anyllm .

# Run the container
docker run -d \
  --name claude-anyllm-proxy \
  -p 8082:8082 \
  -e ATLASCLOUD_API_KEY=your-api-key \
  --restart unless-stopped \
  claude-anyllm
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ATLASCLOUD_API_KEY` | Yes | — | Atlas Cloud API key |
| `ATLAS_PROXY_HOST` | No | `127.0.0.1` | Host to bind to (set to `0.0.0.0` in Docker) |
| `ATLAS_PROXY_PORT` | No | `8082` | Port to listen on |
| `ATLAS_BASE_URL` | No | `https://api.atlascloud.ai/v1` | Upstream API base URL |
| `ATLAS_PROXY_DEFAULT_MODEL` | No | `qwen/qwen3.6-plus` | Default model name |
| `ATLAS_PROXY_TIMEOUT_SECONDS` | No | `600` | Request timeout |
| `ATLAS_PROXY_ENABLE_UPSTREAM_STREAMING` | No | `true` | Enable upstream streaming |
| `ATLAS_PROXY_DEBUG` | No | `false` | Enable debug logging |
| `ATLAS_PROXY_MAX_REQUEST_BYTES` | No | — | Max request body size guardrail |

### Docker Compose with Custom Settings

Create a `.env` file:

```env
ATLASCLOUD_API_KEY=your-api-key
ATLAS_PROXY_DEFAULT_MODEL=moonshotai/kimi-k2.6
ATLAS_PROXY_DEBUG=false
```

Then run:

```bash
docker compose up -d
```

Or override in `docker-compose.yml`:

```yaml
environment:
  - ATLASCLOUD_API_KEY=${ATLASCLOUD_API_KEY}
  - ATLAS_PROXY_DEFAULT_MODEL=moonshotai/kimi-k2.6
  - ATLAS_PROXY_TIMEOUT_SECONDS=300
```

## Using the Proxy

Point your Anthropic-compatible client at the proxy:

```bash
# For Claude Code
export ANTHROPIC_BASE_URL=http://localhost:8082
export ANTHROPIC_AUTH_TOKEN=dummy
export ANTHROPIC_MODEL=qwen/qwen3.6-plus

# For Python SDK
import os
os.environ["ANTHROPIC_BASE_URL"] = "http://localhost:8082"
os.environ["ANTHROPIC_AUTH_TOKEN"] = "dummy"
```

## Health Checks

The Docker image includes a built-in health check that queries `/health` every 30 seconds:

```bash
# Check container health
docker ps --filter name=claude-anyllm-proxy

# Or query the health endpoint directly
curl http://localhost:8082/health
# Returns: {"ok": true, "streaming": true}
```

Additional health endpoints:
- `GET /health` — Liveness check (always returns 200)
- `GET /ready` — Readiness check (returns 503 if upstream is unreachable)
- `GET /v1/models` — List available models

## Docker Image Details

- **Base image:** `python:3.13-slim` (~129MB total)
- **User:** Runs as non-root `appuser` (uid 1001)
- **Package:** Installed via `pip install -e .`
- **Build context:** Filtered by `.dockerignore`

## Unraid Deployment

### Method 1: Docker Compose (Recommended)

1. Copy the repo to your Unraid server
2. Create a `.env` file with your API key
3. Run `docker compose up -d`

### Method 2: Unraid Docker GUI

1. Go to **Docker** → **Add Container**
2. Set:
   - **Name:** `claude-anyllm-proxy`
   - **Repository:** Build locally or use registry
   - **Port:** `8082:8082`
   - **Environment Variable:** `ATLASCLOUD_API_KEY` = your key
3. Apply

### Method 3: Docker Run (Unraid Terminal)

```bash
docker run -d \
  --name claude-anyllm-proxy \
  -p 8082:8082 \
  -e ATLASCLOUD_API_KEY=your-api-key \
  -e ATLAS_PROXY_HOST=0.0.0.0 \
  --restart unless-stopped \
  --label net.unraid.docker.managed=dockerman \
  claude-anyllm
```

## Troubleshooting

### Container won't start

```bash
# Check logs
docker logs claude-anyllm-proxy

# Common issue: missing API key
docker logs claude-anyllm-proxy 2>&1 | grep -i "api_key"
```

### Health check failing

```bash
# Query health endpoint
curl http://localhost:8082/health

# Check readiness
curl http://localhost:8082/ready

# Verify upstream connectivity
curl http://localhost:8082/v1/models
```

### Rebuild after code changes

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

### View debug logs

```bash
# Set debug mode
export ATLAS_PROXY_DEBUG=true
docker compose up -d

# Follow logs
docker logs -f claude-anyllm-proxy
```
