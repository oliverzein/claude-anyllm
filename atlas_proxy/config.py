import argparse
import os
from dataclasses import dataclass


DEFAULT_ATLAS_BASE_URL = "https://api.atlascloud.ai/v1"
DEFAULT_LISTEN_HOST = "127.0.0.1"
DEFAULT_LISTEN_PORT = 8082
DEFAULT_MODEL = "qwen/qwen3.6-plus"


def env_flag(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    atlas_base_url: str
    atlas_api_key: str | None
    default_model: str
    timeout_seconds: float
    enable_upstream_streaming: bool
    debug: bool
    max_request_bytes: int | None


def build_config(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.getenv("ATLAS_PROXY_HOST", DEFAULT_LISTEN_HOST))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("ATLAS_PROXY_PORT", str(DEFAULT_LISTEN_PORT))),
    )
    parser.add_argument(
        "--atlas-base-url",
        default=os.getenv("ATLAS_BASE_URL", DEFAULT_ATLAS_BASE_URL),
    )
    parser.add_argument(
        "--default-model",
        default=os.getenv("ATLAS_PROXY_DEFAULT_MODEL", DEFAULT_MODEL),
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=float(os.getenv("ATLAS_PROXY_TIMEOUT_SECONDS", "600")),
    )
    parser.add_argument(
        "--enable-upstream-streaming",
        action="store_true",
        default=env_flag("ATLAS_PROXY_ENABLE_UPSTREAM_STREAMING", True),
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=env_flag("ATLAS_PROXY_DEBUG", False),
    )
    parser.add_argument(
        "--max-request-bytes",
        type=int,
        default=int(os.getenv("ATLAS_PROXY_MAX_REQUEST_BYTES", "0")),
    )
    args = parser.parse_args(argv)

    if not args.host:
        parser.error("--host must not be empty")

    if not (1 <= args.port <= 65535):
        parser.error(f"--port must be between 1 and 65535, got {args.port}")

    if args.timeout_seconds <= 0:
        parser.error(f"--timeout-seconds must be positive, got {args.timeout_seconds}")

    if not args.default_model:
        parser.error("--default-model must not be empty")

    if not args.atlas_base_url:
        parser.error("--atlas-base-url must not be empty")

    return Config(
        host=args.host,
        port=args.port,
        atlas_base_url=args.atlas_base_url.rstrip("/"),
        atlas_api_key=os.getenv("ATLASCLOUD_API_KEY"),
        default_model=args.default_model,
        timeout_seconds=args.timeout_seconds,
        enable_upstream_streaming=args.enable_upstream_streaming,
        debug=args.debug,
        max_request_bytes=args.max_request_bytes if args.max_request_bytes > 0 else None,
    )
