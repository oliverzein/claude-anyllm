import unittest

from atlas_proxy.config import build_config


class ConfigValidationTests(unittest.TestCase):
    def test_valid_defaults(self):
        config = build_config([])
        self.assertEqual(config.host, "127.0.0.1")
        self.assertEqual(config.port, 8082)
        self.assertEqual(config.default_model, "qwen/qwen3.6-plus")
        self.assertEqual(config.atlas_base_url, "https://api.atlascloud.ai/v1")
        self.assertEqual(config.timeout_seconds, 600)
        self.assertTrue(config.enable_upstream_streaming)
        self.assertFalse(config.debug)

    def test_custom_values(self):
        config = build_config([
            "--host", "0.0.0.0",
            "--port", "9090",
            "--default-model", "custom/model",
            "--timeout-seconds", "30",
            "--debug",
        ])
        self.assertEqual(config.host, "0.0.0.0")
        self.assertEqual(config.port, 9090)
        self.assertEqual(config.default_model, "custom/model")
        self.assertEqual(config.timeout_seconds, 30.0)
        self.assertTrue(config.debug)

    def test_port_zero_errors(self):
        with self.assertRaises(SystemExit):
            build_config(["--port", "0"])

    def test_port_negative_errors(self):
        with self.assertRaises(SystemExit):
            build_config(["--port", "-1"])

    def test_port_too_high_errors(self):
        with self.assertRaises(SystemExit):
            build_config(["--port", "65536"])

    def test_port_boundary_low(self):
        config = build_config(["--port", "1"])
        self.assertEqual(config.port, 1)

    def test_port_boundary_high(self):
        config = build_config(["--port", "65535"])
        self.assertEqual(config.port, 65535)

    def test_timeout_zero_errors(self):
        with self.assertRaises(SystemExit):
            build_config(["--timeout-seconds", "0"])

    def test_timeout_negative_errors(self):
        with self.assertRaises(SystemExit):
            build_config(["--timeout-seconds", "-1"])

    def test_empty_host_errors(self):
        with self.assertRaises(SystemExit):
            build_config(["--host", ""])

    def test_empty_model_errors(self):
        with self.assertRaises(SystemExit):
            build_config(["--default-model", ""])

    def test_empty_atlas_base_url_errors(self):
        with self.assertRaises(SystemExit):
            build_config(["--atlas-base-url", ""])

    def test_streaming_disabled_via_env(self):
        import os
        old = os.environ.get("ATLAS_PROXY_ENABLE_UPSTREAM_STREAMING")
        os.environ["ATLAS_PROXY_ENABLE_UPSTREAM_STREAMING"] = "false"
        try:
            config = build_config([])
            self.assertFalse(config.enable_upstream_streaming)
        finally:
            if old is None:
                os.environ.pop("ATLAS_PROXY_ENABLE_UPSTREAM_STREAMING", None)
            else:
                os.environ["ATLAS_PROXY_ENABLE_UPSTREAM_STREAMING"] = old

    def test_max_request_bytes_default_none(self):
        config = build_config([])
        self.assertIsNone(config.max_request_bytes)

    def test_max_request_bytes_set(self):
        config = build_config(["--max-request-bytes", "1048576"])
        self.assertEqual(config.max_request_bytes, 1048576)

    def test_atlas_base_url_trailing_slash_stripped(self):
        config = build_config(["--atlas-base-url", "https://example.com/"])
        self.assertEqual(config.atlas_base_url, "https://example.com")


if __name__ == "__main__":
    unittest.main()
