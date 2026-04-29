import json
import unittest

from atlas_proxy.anthropic import (
    anthropic_message_to_sse_events,
    anthropic_to_openai_request,
    finalize_sse_events,
    openai_stream_chunk_to_sse_events,
    openai_to_anthropic_message,
)


def decode_sse(events):
    decoded = []
    for event in events:
        text = event.decode("utf-8")
        lines = [line for line in text.splitlines() if line]
        decoded.append(
            {
                "event": lines[0].split(": ", 1)[1],
                "data": json.loads(lines[1].split(": ", 1)[1]),
            }
        )
    return decoded


class AnthropicBridgeTests(unittest.TestCase):
    def test_anthropic_to_openai_request_maps_tool_choice_and_stop(self):
        payload = {
            "model": "qwen/test",
            "max_tokens": 100,
            "stop_sequences": ["DONE"],
            "tool_choice": {"type": "tool", "name": "read_file"},
            "tools": [
                {
                    "name": "read_file",
                    "description": "Read a file",
                    "input_schema": {"type": "object"},
                }
            ],
            "messages": [{"role": "user", "content": "hello"}],
        }
        request = anthropic_to_openai_request(payload, default_model="fallback", stream=True)
        self.assertEqual(request["model"], "qwen/test")
        self.assertEqual(request["stop"], ["DONE"])
        self.assertEqual(request["tool_choice"]["function"]["name"], "read_file")
        self.assertTrue(request["stream"])

    def test_openai_to_anthropic_message_maps_tool_calls(self):
        response = {
            "id": "resp_1",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "function": {
                                    "name": "read_file",
                                    "arguments": "{\"path\": \"a.txt\"}",
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 7},
        }
        message = openai_to_anthropic_message(response, "qwen/test")
        self.assertEqual(message["stop_reason"], "tool_use")
        self.assertEqual(message["content"][0]["type"], "tool_use")
        self.assertEqual(message["content"][0]["input"]["path"], "a.txt")

    def test_openai_to_anthropic_message_infers_tool_stop_reason_from_content(self):
        response = {
            "id": "resp_2",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_2",
                                "function": {
                                    "name": "read_file",
                                    "arguments": "{\"path\":\"test.py\"}",
                                },
                            }
                        ],
                    },
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        message = openai_to_anthropic_message(response, "qwen/test")
        self.assertEqual(message["stop_reason"], "tool_use")

    def test_anthropic_message_sse_includes_tool_use(self):
        message = {
            "id": "msg_1",
            "model": "qwen/test",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "tool_use", "id": "call_1", "name": "read_file", "input": {"path": "a.txt"}},
            ],
            "stop_reason": "tool_use",
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 2},
        }
        events = decode_sse(anthropic_message_to_sse_events(message))
        self.assertEqual(events[0]["event"], "message_start")
        self.assertEqual(events[1]["event"], "content_block_start")
        self.assertEqual(events[4]["event"], "content_block_start")
        self.assertEqual(events[5]["data"]["delta"]["type"], "input_json_delta")

    def test_streaming_text_emits_message_stop(self):
        state = {
            "started": False,
            "done": False,
            "next_block_index": 1,
            "text": {"index": 0, "started": False, "closed": False},
            "tool_calls": {},
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        chunk = {
            "choices": [
                {
                    "delta": {"content": "Hello"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 5},
        }
        events = decode_sse(openai_stream_chunk_to_sse_events(chunk, "msg_1", "qwen/test", state))
        self.assertEqual(events[0]["event"], "message_start")
        self.assertEqual(events[0]["data"]["message"]["usage"]["input_tokens"], 9)
        self.assertEqual(events[-1]["event"], "message_stop")

    def test_streaming_tool_call_emits_input_json_delta(self):
        state = {
            "started": False,
            "done": False,
            "next_block_index": 1,
            "text": {"index": 0, "started": False, "closed": False},
            "tool_calls": {},
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        first = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call_1",
                                "function": {"name": "read_file", "arguments": "{\"path\":\""},
                            }
                        ]
                    },
                    "finish_reason": None,
                }
            ]
        }
        second = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {"arguments": "a.txt\"}"},
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
        events = decode_sse(openai_stream_chunk_to_sse_events(first, "msg_1", "qwen/test", state))
        events += decode_sse(openai_stream_chunk_to_sse_events(second, "msg_1", "qwen/test", state))
        self.assertTrue(any(e["data"].get("delta", {}).get("type") == "input_json_delta" for e in events))
        self.assertEqual(events[-1]["event"], "message_stop")
        self.assertEqual(events[-2]["data"]["delta"]["stop_reason"], "tool_use")

    def test_tool_result_becomes_openai_tool_message(self):
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "call_1", "content": "file contents"}
                    ],
                }
            ]
        }
        request = anthropic_to_openai_request(payload, default_model="qwen/test")
        self.assertEqual(request["messages"][0]["role"], "tool")
        self.assertEqual(request["messages"][0]["tool_call_id"], "call_1")

    def test_finalize_sse_events_closes_open_text_block(self):
        state = {
            "started": True,
            "done": False,
            "next_block_index": 1,
            "text": {"index": 0, "started": True, "closed": False},
            "tool_calls": {},
            "usage": {"input_tokens": 0, "output_tokens": 3},
        }
        events = decode_sse(finalize_sse_events(state))
        self.assertEqual(events[0]["event"], "content_block_stop")
        self.assertEqual(events[-1]["event"], "message_stop")

    def test_usage_maps_reasoning_tokens_to_cache_creation(self):
        response = {
            "id": "chatcmpl-456",
            "choices": [
                {"message": {"content": "hello", "role": "assistant"}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 25,
                "total_tokens": 36,
                "completion_tokens_details": {"reasoning_tokens": 10, "text_tokens": 25},
                "cache_read_input_tokens": 5,
            },
        }
        result = openai_to_anthropic_message(response, "test-model")
        self.assertEqual(result["usage"]["input_tokens"], 11)
        self.assertEqual(result["usage"]["output_tokens"], 25)
        self.assertEqual(result["usage"]["cache_creation_input_tokens"], 10)
        self.assertEqual(result["usage"]["cache_read_input_tokens"], 5)

    def test_usage_without_cache_tokens(self):
        response = {
            "id": "chatcmpl-789",
            "choices": [
                {"message": {"content": "hello", "role": "assistant"}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 25,
            },
        }
        result = openai_to_anthropic_message(response, "test-model")
        self.assertEqual(result["usage"]["input_tokens"], 11)
        self.assertEqual(result["usage"]["output_tokens"], 25)
        self.assertNotIn("cache_creation_input_tokens", result["usage"])
        self.assertNotIn("cache_read_input_tokens", result["usage"])

    def test_usage_with_both_cache_and_reasoning_adds_them(self):
        response = {
            "id": "chatcmpl-abc",
            "choices": [
                {"message": {"content": "hello", "role": "assistant"}, "finish_reason": "stop"}
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "cache_creation_input_tokens": 5,
                "cache_read_input_tokens": 20,
                "completion_tokens_details": {"reasoning_tokens": 15, "text_tokens": 35},
            },
        }
        result = openai_to_anthropic_message(response, "test-model")
        self.assertEqual(result["usage"]["cache_creation_input_tokens"], 20)
        self.assertEqual(result["usage"]["cache_read_input_tokens"], 20)


if __name__ == "__main__":
    unittest.main()
