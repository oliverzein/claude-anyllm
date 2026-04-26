import json


class ProxyError(Exception):
    def __init__(self, message, status_code=500, error_type="api_error", details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type
        self.details = details or {}

    def to_anthropic(self):
        payload = {
            "type": "error",
            "error": {
                "type": self.error_type,
                "message": self.message,
            },
        }
        if self.details:
            payload["error"]["details"] = self.details
        return payload


def map_upstream_error(status_code, body, request_id=None):
    message = extract_error_message(body)
    error_type = "api_error"
    if status_code == 400:
        error_type = "invalid_request_error"
    elif status_code in {401, 403}:
        error_type = "authentication_error"
    elif status_code == 404:
        error_type = "not_found_error"
    elif status_code == 429:
        error_type = "rate_limit_error"

    details = {"upstream_body": body}
    if request_id:
        details["request_id"] = request_id

    return ProxyError(
        message=message,
        status_code=status_code,
        error_type=error_type,
        details=details,
    )


def extract_error_message(body):
    if not body:
        return "Upstream request failed"
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return body

    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and error.get("message"):
            return error["message"]
        if isinstance(error, str):
            return error
        if data.get("msg"):
            return data["msg"]
        if data.get("message"):
            return data["message"]
    return body
