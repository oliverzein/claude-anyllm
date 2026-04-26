import unittest

from atlas_proxy.errors import ProxyError
from atlas_proxy.validation import validate_messages_request, validate_request_size


class ValidationTests(unittest.TestCase):
    def test_valid_minimal_payload(self):
        payload = {"messages": [{"role": "user", "content": "hello"}]}
        validate_messages_request(payload)

    def test_requires_messages(self):
        with self.assertRaises(ProxyError) as ctx:
            validate_messages_request({})
        self.assertEqual(ctx.exception.status_code, 400)

    def test_rejects_unknown_tool_choice_reference(self):
        payload = {
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [{"name": "read_file", "input_schema": {"type": "object"}}],
            "tool_choice": {"type": "tool", "name": "other_tool"},
        }
        with self.assertRaises(ProxyError) as ctx:
            validate_messages_request(payload)
        self.assertIn("unknown tool", ctx.exception.message)

    def test_rejects_invalid_tool_result(self):
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "tool_result", "content": "done"}],
                }
            ]
        }
        with self.assertRaises(ProxyError) as ctx:
            validate_messages_request(payload)
        self.assertIn("tool_use_id", ctx.exception.message)

    def test_rejects_duplicate_tool_names(self):
        payload = {
            "messages": [{"role": "user", "content": "hello"}],
            "tools": [
                {"name": "read_file", "input_schema": {"type": "object"}},
                {"name": "read_file", "input_schema": {"type": "object"}},
            ],
        }
        with self.assertRaises(ProxyError) as ctx:
            validate_messages_request(payload)
        self.assertIn("Duplicate tool name", ctx.exception.message)

    def test_request_size_guardrail_rejects_large_body(self):
        with self.assertRaises(ProxyError) as ctx:
            validate_request_size(b"x" * 11, 10)
        self.assertEqual(ctx.exception.status_code, 413)

    def test_request_size_guardrail_allows_when_unset(self):
        validate_request_size(b"x" * 100, None)


if __name__ == "__main__":
    unittest.main()
