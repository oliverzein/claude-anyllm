import io
import json
import unittest
from unittest.mock import Mock, patch

from atlas_proxy.config import Config
from atlas_proxy.server import ProxyHandler, run_server


class ServerTests(unittest.TestCase):
    def make_config(self, **overrides):
        defaults = dict(
            host="127.0.0.1",
            port=8082,
            atlas_base_url="https://api.atlascloud.ai/v1",
            atlas_api_key="test-key",
            default_model="qwen/test",
            timeout_seconds=10.0,
            enable_upstream_streaming=True,
            debug=False,
            max_request_bytes=None,
        )
        defaults.update(overrides)
        return Config(**defaults)

    def make_server(self, config=None, **config_overrides):
        if config is None:
            config = self.make_config(**config_overrides)
        server = Mock()
        server.config = config
        server.atlas_client = Mock()
        return server

    def make_handler(self, method, path, body=b"", headers=None, server=None):
        server = server or self.make_server()
        handler = ProxyHandler.__new__(ProxyHandler)
        handler.client_address = ("127.0.0.1", 12345)
        handler.server = server
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.headers = Mock()
        handler.headers.get = Mock(return_value=str(len(body)) if body else "0")
        handler.command = method
        handler.path = path
        handler.request_version = "HTTP/1.1"
        handler.requestline = f"{method} {path} HTTP/1.1"
        handler.raw_requestline = handler.requestline.encode("utf-8")
        return handler

    def call_handler(self, handler):
        if handler.command == "GET":
            handler.do_GET()
        elif handler.command == "POST":
            handler.do_POST()
        elif handler.command == "HEAD":
            handler.do_HEAD()
        handler.wfile.seek(0)
        return handler.wfile.read()

    def parse_response(self, data):
        header_body_split = data.split(b"\r\n\r\n", 1)
        if len(header_body_split) != 2:
            return None, None, data
        raw_headers, body = header_body_split
        status_line = raw_headers.split(b"\r\n")[0].decode("utf-8")
        status = int(status_line.split()[1])
        return status, dict(h.split(b": ", 1) for h in raw_headers.split(b"\r\n")[1:]), body

    def test_get_health(self):
        handler = self.make_handler("GET", "/health", server=self.make_server())
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True, "streaming": True})

    def test_get_health_no_streaming(self):
        handler = self.make_handler(
            "GET", "/health", server=self.make_server(enable_upstream_streaming=False)
        )
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"ok": True, "streaming": False})

    def test_get_ready_ok(self):
        server = self.make_server()
        server.atlas_client.readiness_check.return_value = {
            "ok": True,
            "model_found": True,
        }
        handler = self.make_handler("GET", "/ready", server=server)
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["ok"], True)

    def test_get_ready_not_ready(self):
        server = self.make_server()
        server.atlas_client.readiness_check.return_value = {
            "ok": False,
            "model_found": False,
        }
        handler = self.make_handler("GET", "/ready", server=server)
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 503)

    def test_get_models(self):
        server = self.make_server()
        server.atlas_client.list_models.return_value = {"data": [{"id": "qwen/test"}]}
        handler = self.make_handler("GET", "/v1/models", server=server)
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["data"][0]["id"], "qwen/test")

    def test_get_unknown_returns_404(self):
        handler = self.make_handler("GET", "/unknown")
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 404)

    def test_post_messages_non_streaming(self):
        server = self.make_server()
        server.atlas_client.create_chat_completion.return_value = {
            "id": "resp_1",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "Hello"},
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }
        body = json.dumps({"messages": [{"role": "user", "content": "hi"}]}).encode()
        handler = self.make_handler("POST", "/v1/messages", body=body, server=server)
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 200)
        resp = json.loads(body)
        self.assertEqual(resp["type"], "message")
        self.assertEqual(resp["content"][0]["text"], "Hello")
        self.assertEqual(resp["stop_reason"], "end_turn")

    def test_post_messages_streaming_disabled(self):
        server = self.make_server(enable_upstream_streaming=False)
        server.atlas_client.create_chat_completion.return_value = {
            "id": "resp_1",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "Hello"},
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2},
        }
        body = json.dumps(
            {"messages": [{"role": "user", "content": "hi"}], "stream": True}
        ).encode()
        handler = self.make_handler("POST", "/v1/messages", body=body, server=server)
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 200)
        self.assertEqual(headers[b"Content-Type"], b"text/event-stream")

    def test_post_messages_validation_error(self):
        body = json.dumps({"messages": []}).encode()
        handler = self.make_handler("POST", "/v1/messages", body=body)
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 400)
        resp = json.loads(body)
        self.assertEqual(resp["type"], "error")
        self.assertEqual(resp["error"]["type"], "invalid_request_error")

    def test_post_messages_invalid_json(self):
        handler = self.make_handler("POST", "/v1/messages", body=b"not json")
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 400)
        resp = json.loads(body)
        self.assertEqual(resp["error"]["type"], "invalid_request_error")

    def test_post_messages_upstream_error(self):
        from atlas_proxy.errors import ProxyError

        server = self.make_server()
        server.atlas_client.create_chat_completion.side_effect = ProxyError(
            "upstream failed", status_code=502, error_type="api_error"
        )
        body = json.dumps({"messages": [{"role": "user", "content": "hi"}]}).encode()
        handler = self.make_handler("POST", "/v1/messages", body=body, server=server)
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 502)
        resp = json.loads(body)
        self.assertEqual(resp["error"]["type"], "api_error")

    def test_post_count_tokens(self):
        body = json.dumps({"messages": [{"role": "user", "content": "hello world"}]}).encode()
        handler = self.make_handler("POST", "/v1/messages/count_tokens", body=body)
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 200)
        resp = json.loads(body)
        self.assertIn("input_tokens", resp)
        self.assertIsInstance(resp["input_tokens"], int)

    def test_post_count_tokens_validation_error(self):
        body = json.dumps({"messages": []}).encode()
        handler = self.make_handler("POST", "/v1/messages/count_tokens", body=body)
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 400)

    def test_post_unknown_returns_404(self):
        body = json.dumps({"foo": "bar"}).encode()
        handler = self.make_handler("POST", "/v1/unknown", body=body)
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 404)

    def test_head_returns_200(self):
        handler = self.make_handler("HEAD", "/")
        data = self.call_handler(handler)
        status, headers, body = self.parse_response(data)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")


if __name__ == "__main__":
    unittest.main()
