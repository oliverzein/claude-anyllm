from .errors import ProxyError


SUPPORTED_CONTENT_BLOCK_TYPES = {"text", "tool_use", "tool_result"}


def validate_messages_request(payload):
    if not isinstance(payload, dict):
        raise ProxyError(
            "Request body must be a JSON object",
            status_code=400,
            error_type="invalid_request_error",
        )

    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ProxyError(
            "`messages` must be a non-empty array",
            status_code=400,
            error_type="invalid_request_error",
        )

    max_tokens = payload.get("max_tokens")
    if max_tokens is not None and (not isinstance(max_tokens, int) or max_tokens <= 0):
        raise ProxyError(
            "`max_tokens` must be a positive integer",
            status_code=400,
            error_type="invalid_request_error",
        )

    tools = payload.get("tools")
    tool_names = set()
    if tools is not None:
        if not isinstance(tools, list):
            raise ProxyError(
                "`tools` must be an array",
                status_code=400,
                error_type="invalid_request_error",
            )
        for tool in tools:
            if not isinstance(tool, dict):
                raise ProxyError(
                    "Each tool must be an object",
                    status_code=400,
                    error_type="invalid_request_error",
                )
            name = tool.get("name")
            if not isinstance(name, str) or not name:
                raise ProxyError(
                    "Each tool must have a non-empty string `name`",
                    status_code=400,
                    error_type="invalid_request_error",
                )
            if name in tool_names:
                raise ProxyError(
                    f"Duplicate tool name `{name}`",
                    status_code=400,
                    error_type="invalid_request_error",
                )
            tool_names.add(name)

    tool_choice = payload.get("tool_choice")
    if tool_choice is not None:
        if not isinstance(tool_choice, dict):
            raise ProxyError(
                "`tool_choice` must be an object",
                status_code=400,
                error_type="invalid_request_error",
            )
        choice_type = tool_choice.get("type")
        if choice_type not in {"auto", "any", "tool"}:
            raise ProxyError(
                "`tool_choice.type` must be one of `auto`, `any`, or `tool`",
                status_code=400,
                error_type="invalid_request_error",
            )
        if choice_type == "tool":
            name = tool_choice.get("name")
            if not isinstance(name, str) or not name:
                raise ProxyError(
                    "`tool_choice.name` must be set when `tool_choice.type` is `tool`",
                    status_code=400,
                    error_type="invalid_request_error",
                )
            if tools is not None and name not in tool_names:
                raise ProxyError(
                    f"`tool_choice.name` references unknown tool `{name}`",
                    status_code=400,
                    error_type="invalid_request_error",
                )

    for message in messages:
        validate_message(message)


def validate_message(message):
    if not isinstance(message, dict):
        raise ProxyError(
            "Each message must be an object",
            status_code=400,
            error_type="invalid_request_error",
        )

    role = message.get("role")
    if role not in {"user", "assistant"}:
        raise ProxyError(
            "Each message role must be `user` or `assistant`",
            status_code=400,
            error_type="invalid_request_error",
        )

    content = message.get("content")
    if isinstance(content, str):
        return
    if not isinstance(content, list) or not content:
        raise ProxyError(
            "Each message content must be a string or non-empty array of content blocks",
            status_code=400,
            error_type="invalid_request_error",
        )

    for block in content:
        if not isinstance(block, dict):
            raise ProxyError(
                "Each content block must be an object",
                status_code=400,
                error_type="invalid_request_error",
            )
        block_type = block.get("type")
        if block_type not in SUPPORTED_CONTENT_BLOCK_TYPES:
            raise ProxyError(
                f"Unsupported content block type `{block_type}`",
                status_code=400,
                error_type="invalid_request_error",
            )
        if block_type == "text" and not isinstance(block.get("text"), str):
            raise ProxyError(
                "`text` blocks must include a string `text` field",
                status_code=400,
                error_type="invalid_request_error",
            )
        if block_type == "tool_use":
            if not isinstance(block.get("id"), str) or not block["id"]:
                raise ProxyError(
                    "`tool_use` blocks must include a non-empty string `id`",
                    status_code=400,
                    error_type="invalid_request_error",
                )
            if not isinstance(block.get("name"), str) or not block["name"]:
                raise ProxyError(
                    "`tool_use` blocks must include a non-empty string `name`",
                    status_code=400,
                    error_type="invalid_request_error",
                )
        if block_type == "tool_result":
            if not isinstance(block.get("tool_use_id"), str) or not block["tool_use_id"]:
                raise ProxyError(
                    "`tool_result` blocks must include a non-empty string `tool_use_id`",
                    status_code=400,
                    error_type="invalid_request_error",
                )


def validate_request_size(raw_body, max_request_bytes):
    if max_request_bytes is None:
        return
    size = len(raw_body)
    if size > max_request_bytes:
        raise ProxyError(
            (
                f"Request body is too large for the local proxy guardrail "
                f"({size} bytes > {max_request_bytes} bytes)"
            ),
            status_code=413,
            error_type="invalid_request_error",
            details={"request_bytes": size, "max_request_bytes": max_request_bytes},
        )
