import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .anthropic import (
    approximate_anthropic_input_tokens,
    anthropic_message_to_sse_events,
    anthropic_to_openai_request,
    finalize_sse_events,
    openai_stream_chunk_to_sse_events,
    openai_to_anthropic_message,
    sse_event,
    summarize_anthropic_content_blocks,
)
from .atlas import AtlasClient
from .config import build_config
from .errors import ProxyError
from .logging_utils import log_debug
from .validation import validate_messages_request
from .validation import validate_request_size


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AtlasAnthropicProxy/0.2"

    def handle(self):
        try:
            super().handle()
        except ConnectionResetError:
            if getattr(self.server.config, "debug", False):
                log_debug(
                    self.server.config.debug,
                    "client_disconnect",
                    client=self.client_address[0],
                )

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_json({"ok": True, "streaming": self.server.config.enable_upstream_streaming})
            return
        if self.path == "/ready":
            readiness = self.server.atlas_client.readiness_check(self.server.config.default_model)
            self.send_json(readiness, status=200 if readiness["ok"] else 503)
            return
        if self.path == "/v1/models":
            self.send_json(self.server.atlas_client.list_models())
            return
        self.send_error(404)

    def do_POST(self):
        if self.path.startswith("/v1/messages/count_tokens"):
            try:
                payload = self.read_json_body()
                validate_messages_request(payload)
                self.handle_count_tokens_request(payload)
            except ProxyError as exc:
                self.send_json(exc.to_anthropic(), status=exc.status_code)
            except json.JSONDecodeError:
                self.send_json(
                    ProxyError(
                        "Request body must be valid JSON",
                        status_code=400,
                        error_type="invalid_request_error",
                    ).to_anthropic(),
                    status=400,
                )
            except Exception as exc:
                self.send_json(
                    ProxyError(str(exc), status_code=500, error_type="api_error").to_anthropic(),
                    status=500,
                )
            return

        if not self.path.startswith("/v1/messages"):
            self.send_error(404)
            return

        try:
            payload = self.read_json_body()
            validate_messages_request(payload)
            wants_stream = bool(payload.get("stream"))
            if wants_stream:
                self.handle_streaming_request(payload)
                return
            self.handle_non_streaming_request(payload)
        except ProxyError as exc:
            self.send_json(exc.to_anthropic(), status=exc.status_code)
        except json.JSONDecodeError:
            self.send_json(
                ProxyError(
                    "Request body must be valid JSON",
                    status_code=400,
                    error_type="invalid_request_error",
                ).to_anthropic(),
                status=400,
            )
        except Exception as exc:
            self.send_json(
                ProxyError(str(exc), status_code=500, error_type="api_error").to_anthropic(),
                status=500,
            )

    def read_json_body(self):
        length = int(self.headers.get("content-length", "0"))
        raw = self.rfile.read(length)
        validate_request_size(raw, self.server.config.max_request_bytes)
        return json.loads(raw.decode("utf-8"))

    def handle_non_streaming_request(self, payload):
        request_payload = anthropic_to_openai_request(
            payload,
            default_model=self.server.config.default_model,
            stream=False,
        )
        log_debug(
            self.server.config.debug,
            "proxy_request",
            mode="json",
            model=request_payload["model"],
            message_count=len(request_payload.get("messages", [])),
            tool_count=len(request_payload.get("tools", [])),
            request_bytes=len(json.dumps(request_payload, ensure_ascii=True).encode("utf-8")),
        )
        response = self.server.atlas_client.create_chat_completion(request_payload)
        translated = openai_to_anthropic_message(
            response,
            payload.get("model") or self.server.config.default_model,
        )
        translated["usage"]["input_tokens"] = approximate_anthropic_input_tokens(payload)
        log_debug(
            self.server.config.debug,
            "proxy_response",
            mode="json",
            model=translated["model"],
            stop_reason=translated["stop_reason"],
            content_blocks=summarize_anthropic_content_blocks(translated.get("content")),
            output_tokens=translated.get("usage", {}).get("output_tokens", 0),
        )
        self.send_json(translated)

    def handle_count_tokens_request(self, payload):
        count = approximate_anthropic_input_tokens(payload)
        self.send_json({"input_tokens": count})

    def handle_streaming_request(self, payload):
        model = payload.get("model") or self.server.config.default_model
        request_payload = anthropic_to_openai_request(
            payload,
            default_model=self.server.config.default_model,
            stream=self.server.config.enable_upstream_streaming,
        )
        log_debug(
            self.server.config.debug,
            "proxy_request",
            mode="sse",
            model=request_payload["model"],
            upstream_stream=self.server.config.enable_upstream_streaming,
            message_count=len(request_payload.get("messages", [])),
            tool_count=len(request_payload.get("tools", [])),
            request_bytes=len(json.dumps(request_payload, ensure_ascii=True).encode("utf-8")),
        )
        if not self.server.config.enable_upstream_streaming:
            response = self.server.atlas_client.create_chat_completion(request_payload | {"stream": False})
            message = openai_to_anthropic_message(response, model)
            message["usage"]["input_tokens"] = approximate_anthropic_input_tokens(payload)
            self.send_sse_response(anthropic_message_to_sse_events(message))
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        input_tokens = approximate_anthropic_input_tokens(payload)
        state = {
            "started": False,
            "done": False,
            "next_block_index": 1,
            "text": {
                "index": 0,
                "started": False,
                "closed": False,
            },
            "tool_calls": {},
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": 0,
            },
        }
        message_id = self.server.atlas_client.build_message_id()
        try:
            for chunk in self.server.atlas_client.iter_chat_completion_stream(request_payload):
                for event in openai_stream_chunk_to_sse_events(chunk, message_id, model, state):
                    self.wfile.write(event)
                    self.wfile.flush()
            for event in finalize_sse_events(state):
                self.wfile.write(event)
                self.wfile.flush()
            log_debug(
                self.server.config.debug,
                "proxy_response",
                mode="sse",
                model=model,
                stop_reason=state.get("final_stop_reason"),
                content_blocks=summarize_sse_state(state),
                output_tokens=state["usage"]["output_tokens"],
            )
        except BrokenPipeError:
            return

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_sse_response(self, events):
        body = b"".join(events)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def log_message(self, fmt, *args):
        if getattr(self.server.config, "debug", False):
            sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))


def run_server(argv=None):
    config = build_config(argv)
    atlas_client = AtlasClient(config)
    server = ThreadingHTTPServer((config.host, config.port), ProxyHandler)
    server.config = config
    server.atlas_client = atlas_client
    print(
        f"Atlas Anthropic proxy listening on http://{config.host}:{config.port}",
        flush=True,
    )
    server.serve_forever()


def summarize_sse_state(state):
    blocks = []
    if state["text"]["started"]:
        blocks.append({"type": "text"})
    for tool_index in sorted(state["tool_calls"]):
        tool_state = state["tool_calls"][tool_index]
        blocks.append(
            {
                "type": "tool_use",
                "name": tool_state.get("name"),
                "id": tool_state.get("id"),
            }
        )
    return blocks
