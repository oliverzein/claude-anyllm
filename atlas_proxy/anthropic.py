import json
import time


def text_from_blocks(blocks):
    if isinstance(blocks, str):
        return blocks
    parts = []
    for block in blocks or []:
        if isinstance(block, str):
            parts.append(block)
        elif block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(part for part in parts if part)


def approximate_anthropic_input_tokens(payload):
    serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    # Coarse heuristic: ~4 chars/token is a practical approximation for English/code mix.
    return max(1, (len(serialized) + 3) // 4)


def summarize_anthropic_content_blocks(blocks):
    summary = []
    for block in blocks or []:
        block_type = block.get("type")
        item = {"type": block_type}
        if block_type == "tool_use":
            item["name"] = block.get("name")
            item["id"] = block.get("id")
        elif block_type == "text":
            item["chars"] = len(block.get("text", ""))
        summary.append(item)
    return summary


def anthropic_to_openai_messages(payload):
    messages = []
    system = text_from_blocks(payload.get("system"))
    if system:
        messages.append({"role": "system", "content": system})

    for message in payload.get("messages", []):
        role = message.get("role")
        content = message.get("content", "")

        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue

        text_parts = []
        tool_calls = []
        for block in content or []:
            block_type = block.get("type")
            if block_type == "text":
                text_parts.append(block.get("text", ""))
            elif block_type == "thinking":
                thinking_text = block.get("thinking", "")
                if thinking_text:
                    text_parts.append(f"[thinking]{thinking_text}[/thinking]")
            elif block_type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id"),
                        "type": "function",
                        "function": {
                            "name": block.get("name"),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    }
                )
            elif block_type == "tool_result":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id"),
                        "content": text_from_blocks(block.get("content")),
                    }
                )

        if text_parts or tool_calls:
            out = {"role": role, "content": "\n".join(text_parts) or None}
            if tool_calls:
                out["tool_calls"] = tool_calls
            messages.append(out)

    return messages


def anthropic_to_openai_tools(tools):
    return [
        {
            "type": "function",
            "function": {
                "name": tool.get("name"),
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object"}),
            },
        }
        for tool in tools or []
    ]


def anthropic_to_openai_request(payload, default_model, stream=False):
    data = {
        "model": payload.get("model") or default_model,
        "messages": anthropic_to_openai_messages(payload),
        "max_tokens": payload.get("max_tokens", 4096),
        "stream": stream,
    }
    if payload.get("temperature") is not None:
        data["temperature"] = payload["temperature"]
    if payload.get("top_p") is not None:
        data["top_p"] = payload["top_p"]
    if payload.get("stop_sequences"):
        data["stop"] = payload["stop_sequences"]
    tools = anthropic_to_openai_tools(payload.get("tools"))
    if tools:
        data["tools"] = tools

    tool_choice = payload.get("tool_choice")
    if isinstance(tool_choice, dict):
        choice_type = tool_choice.get("type")
        if choice_type == "auto":
            data["tool_choice"] = "auto"
        elif choice_type == "any":
            data["tool_choice"] = "required"
        elif choice_type == "tool" and tool_choice.get("name"):
            data["tool_choice"] = {
                "type": "function",
                "function": {"name": tool_choice["name"]},
            }

    return data


def openai_to_anthropic_message(openai_response, model):
    choice = openai_response["choices"][0]
    message = choice.get("message", {})
    content = []
    has_tool_calls = bool(message.get("tool_calls"))

    if message.get("content"):
        content.append({"type": "text", "text": message["content"]})

    for tool_call in message.get("tool_calls") or []:
        fn = tool_call.get("function", {})
        args = fn.get("arguments") or "{}"
        try:
            parsed_args = json.loads(args)
        except json.JSONDecodeError:
            parsed_args = {}
        content.append(
            {
                "type": "tool_use",
                "id": tool_call.get("id"),
                "name": fn.get("name"),
                "input": parsed_args,
            }
        )

    finish_reason = choice.get("finish_reason")
    stop_reason = "tool_use" if finish_reason == "tool_calls" or has_tool_calls else "end_turn"
    usage = openai_response.get("usage", {})
    anthropic_usage = {
        "input_tokens": usage.get("prompt_tokens", 0),
        "output_tokens": usage.get("completion_tokens", 0),
    }
    if usage.get("cache_creation_input_tokens"):
        anthropic_usage["cache_creation_input_tokens"] = usage["cache_creation_input_tokens"]
    if usage.get("cache_read_input_tokens"):
        anthropic_usage["cache_read_input_tokens"] = usage["cache_read_input_tokens"]
    details = usage.get("completion_tokens_details") or {}
    if details.get("reasoning_tokens"):
        anthropic_usage["cache_creation_input_tokens"] = anthropic_usage.get(
            "cache_creation_input_tokens", 0
        ) + details["reasoning_tokens"]
    return {
        "id": openai_response.get("id", f"msg_{int(time.time() * 1000)}"),
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": anthropic_usage,
    }


def sse_event(name, payload):
    return f"event: {name}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")


def anthropic_message_to_sse_events(message):
    message_id = message["id"]
    model = message["model"]
    events = [
        sse_event(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {
                        "input_tokens": message.get("usage", {}).get("input_tokens", 0),
                        "output_tokens": 0,
                    },
                },
            },
        )
    ]

    for index, block in enumerate(message.get("content", [])):
        events.extend(single_block_to_sse_events(index, block))

    events.append(
        sse_event(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {
                    "stop_reason": message.get("stop_reason"),
                    "stop_sequence": message.get("stop_sequence"),
                },
                "usage": {
                    "output_tokens": message.get("usage", {}).get("output_tokens", 0),
                },
            },
        )
    )
    events.append(sse_event("message_stop", {"type": "message_stop"}))
    return events


def single_block_to_sse_events(index, block):
    block_type = block.get("type")
    if block_type == "text":
        return [
            sse_event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {"type": "text", "text": ""},
                },
            ),
            sse_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {"type": "text_delta", "text": block.get("text", "")},
                },
            ),
            sse_event("content_block_stop", {"type": "content_block_stop", "index": index}),
        ]

    if block_type == "tool_use":
        return [
            sse_event(
                "content_block_start",
                {
                    "type": "content_block_start",
                    "index": index,
                    "content_block": {
                        "type": "tool_use",
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "input": {},
                    },
                },
            ),
            sse_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": index,
                    "delta": {
                        "type": "input_json_delta",
                        "partial_json": json.dumps(block.get("input", {})),
                    },
                },
            ),
            sse_event("content_block_stop", {"type": "content_block_stop", "index": index}),
        ]

    return []


def _ensure_started(events, message_id, model, state, input_tokens=0):
    if state["started"]:
        return
    events.append(
        sse_event(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "model": model,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": input_tokens, "output_tokens": 0},
                },
            },
        )
    )
    state["started"] = True


def _start_text_block(events, state):
    if state["text"]["started"]:
        return
    events.append(
        sse_event(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": state["text"]["index"],
                "content_block": {"type": "text", "text": ""},
            },
        )
    )
    state["text"]["started"] = True


def _close_text_block(events, state):
    if not state["text"]["started"] or state["text"]["closed"]:
        return
    events.append(
        sse_event(
            "content_block_stop",
            {"type": "content_block_stop", "index": state["text"]["index"]},
        )
    )
    state["text"]["closed"] = True


def _tool_state(state, tool_index):
    if tool_index not in state["tool_calls"]:
        state["tool_calls"][tool_index] = {
            "index": state["next_block_index"],
            "started": False,
            "closed": False,
            "id": None,
            "name": None,
        }
        state["next_block_index"] += 1
    return state["tool_calls"][tool_index]


def _start_tool_block(events, tool_state):
    if tool_state["started"]:
        return
    events.append(
        sse_event(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": tool_state["index"],
                "content_block": {
                    "type": "tool_use",
                    "id": tool_state["id"],
                    "name": tool_state["name"],
                    "input": {},
                },
            },
        )
    )
    tool_state["started"] = True


def _close_tool_blocks(events, state):
    for tool_index in sorted(state["tool_calls"]):
        tool_state = state["tool_calls"][tool_index]
        if tool_state["started"] and not tool_state["closed"]:
            events.append(
                sse_event(
                    "content_block_stop",
                    {"type": "content_block_stop", "index": tool_state["index"]},
                )
            )
            tool_state["closed"] = True


def _has_tool_calls(state):
    return any(tool_state["started"] for tool_state in state["tool_calls"].values())


def openai_stream_chunk_to_sse_events(chunk, message_id, model, state):
    events = []
    usage = chunk.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens", state["usage"]["input_tokens"])
    _ensure_started(events, message_id, model, state, input_tokens=prompt_tokens)

    choices = chunk.get("choices") or []
    if not choices:
        return events

    choice = choices[0]
    delta = choice.get("delta", {})

    if delta.get("content"):
        _start_text_block(events, state)
        events.append(
            sse_event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": state["text"]["index"],
                    "delta": {"type": "text_delta", "text": delta["content"]},
                },
            )
        )

    for tool_call in delta.get("tool_calls") or []:
        _close_text_block(events, state)
        tool_index = tool_call.get("index", 0)
        tool_state = _tool_state(state, tool_index)
        function = tool_call.get("function", {})
        if tool_call.get("id"):
            tool_state["id"] = tool_call["id"]
        if function.get("name"):
            tool_state["name"] = function["name"]
        _start_tool_block(events, tool_state)
        arguments = function.get("arguments")
        if arguments:
            events.append(
                sse_event(
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": tool_state["index"],
                        "delta": {
                            "type": "input_json_delta",
                            "partial_json": arguments,
                        },
                    },
                )
            )

    if usage:
        state["usage"]["input_tokens"] = usage.get("prompt_tokens", state["usage"]["input_tokens"])
        state["usage"]["output_tokens"] = usage.get(
            "completion_tokens", state["usage"]["output_tokens"]
        )

    finish_reason = choice.get("finish_reason")
    if finish_reason:
        _close_text_block(events, state)
        _close_tool_blocks(events, state)
        stop_reason = "tool_use" if finish_reason == "tool_calls" or _has_tool_calls(state) else "end_turn"
        state["final_stop_reason"] = stop_reason
        events.append(
            sse_event(
                "message_delta",
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                    "usage": {"output_tokens": state["usage"]["output_tokens"]},
                },
            )
        )
        events.append(sse_event("message_stop", {"type": "message_stop"}))
        state["done"] = True

    return events


def finalize_sse_events(state):
    if not state["started"] or state["done"]:
        return []

    events = []
    _close_text_block(events, state)
    _close_tool_blocks(events, state)
    stop_reason = "tool_use" if _has_tool_calls(state) else "end_turn"
    state["final_stop_reason"] = stop_reason
    events.append(
        sse_event(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": state["usage"]["output_tokens"]},
            },
        )
    )
    events.append(sse_event("message_stop", {"type": "message_stop"}))
    state["done"] = True
    return events
