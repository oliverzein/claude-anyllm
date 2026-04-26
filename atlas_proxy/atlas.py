import json
import time
import uuid

import httpx

from .errors import ProxyError, map_upstream_error
from .logging_utils import log_debug


class AtlasClient:
    def __init__(self, config):
        if not config.atlas_api_key:
            raise ProxyError(
                "ATLASCLOUD_API_KEY is not set",
                status_code=500,
                error_type="authentication_error",
            )
        self.config = config
        self.client = httpx.Client(
            timeout=config.timeout_seconds,
            headers={
                "Authorization": f"Bearer {config.atlas_api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "atlas-anthropic-proxy/0.2",
            },
        )
        self.max_retries = 2

    def _request_with_retries(self, method, url, **kwargs):
        attempts = 0
        last_error = None
        while attempts <= self.max_retries:
            attempts += 1
            started_at = time.monotonic()
            try:
                response = self.client.request(method, url, **kwargs)
                duration_ms = int((time.monotonic() - started_at) * 1000)
                log_debug(
                    self.config.debug,
                    "atlas_response",
                    method=method,
                    url=url,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    request_id=response.headers.get("x-request-id"),
                    attempts=attempts,
                )
                return response
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_error = exc
                log_debug(
                    self.config.debug,
                    "atlas_retry",
                    method=method,
                    url=url,
                    attempts=attempts,
                    error=str(exc),
                )
                if attempts > self.max_retries:
                    break
        raise ProxyError(
            f"Upstream Atlas request failed after retries: {last_error}",
            status_code=502,
            error_type="api_error",
        )

    def create_chat_completion(self, request_payload):
        url = f"{self.config.atlas_base_url}/chat/completions"
        response = self._request_with_retries("POST", url, json=request_payload)
        if response.is_error:
            raise map_upstream_error(
                response.status_code,
                response.text,
                request_id=response.headers.get("x-request-id"),
            )
        return response.json()

    def list_models(self):
        url = f"{self.config.atlas_base_url}/models"
        response = self._request_with_retries("GET", url)
        if response.is_error:
            raise map_upstream_error(
                response.status_code,
                response.text,
                request_id=response.headers.get("x-request-id"),
            )
        return response.json()

    def readiness_check(self, model):
        models = self.list_models()
        data = models.get("data") if isinstance(models, dict) else None
        model_found = False
        if isinstance(data, list):
            model_found = any(item.get("id") == model for item in data if isinstance(item, dict))
        return {
            "ok": True,
            "atlas_base_url": self.config.atlas_base_url,
            "default_model": model,
            "model_found": model_found,
        }

    def iter_chat_completion_stream(self, request_payload):
        url = f"{self.config.atlas_base_url}/chat/completions"
        started_at = time.monotonic()
        with self.client.stream("POST", url, json=request_payload) as response:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            log_debug(
                self.config.debug,
                "atlas_stream_open",
                url=url,
                status_code=response.status_code,
                duration_ms=duration_ms,
                request_id=response.headers.get("x-request-id"),
            )
            if response.is_error:
                body = response.read().decode("utf-8", errors="replace")
                raise map_upstream_error(
                    response.status_code,
                    body,
                    request_id=response.headers.get("x-request-id"),
                )

            for line in response.iter_lines():
                if not line:
                    continue
                if isinstance(line, bytes):
                    line = line.decode("utf-8", errors="replace")
                if line.startswith("data: "):
                    line = line[6:]
                if line == "[DONE]":
                    break
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    @staticmethod
    def build_message_id():
        return f"msg_{uuid.uuid4().hex}"
