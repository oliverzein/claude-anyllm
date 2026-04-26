import unittest
from unittest.mock import Mock, patch

import httpx

from atlas_proxy.atlas import AtlasClient
from atlas_proxy.config import Config
from atlas_proxy.errors import ProxyError


class AtlasClientTests(unittest.TestCase):
    def make_config(self):
        return Config(
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

    def test_readiness_check_marks_known_model(self):
        client = AtlasClient(self.make_config())
        client.list_models = Mock(
            return_value={"data": [{"id": "qwen/test"}, {"id": "other"}]}
        )
        result = client.readiness_check("qwen/test")
        self.assertTrue(result["ok"])
        self.assertTrue(result["model_found"])

    def test_request_retries_connect_error(self):
        client = AtlasClient(self.make_config())
        ok_response = httpx.Response(200, json={"ok": True})
        with patch.object(
            client.client,
            "request",
            side_effect=[httpx.ConnectError("boom"), ok_response],
        ):
            response = client._request_with_retries("GET", "https://example.com")
        self.assertEqual(response.status_code, 200)

    def test_request_raises_after_retries(self):
        client = AtlasClient(self.make_config())
        with patch.object(
            client.client,
            "request",
            side_effect=httpx.ReadTimeout("timeout"),
        ):
            with self.assertRaises(ProxyError) as ctx:
                client._request_with_retries("GET", "https://example.com")
        self.assertEqual(ctx.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
