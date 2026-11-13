"""Which client IP the app is willing to enforce limits on."""

from starlette.requests import Request

from core.client_info import client_ip_for_logging, trusted_client_ip


def request_with(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("10.0.0.9", 1234),
        }
    )


def test_proxy_header_is_ignored_by_default():
    request = request_with({"X-Real-IP": "203.0.113.7"})

    assert trusted_client_ip(request) is None
    assert client_ip_for_logging(request) == "10.0.0.9"


def test_proxy_header_is_used_when_trusted(settings_override):
    settings_override(TRUST_PROXY_HEADERS=True)
    request = request_with({"X-Real-IP": "203.0.113.7"})

    assert trusted_client_ip(request) == "203.0.113.7"
    assert client_ip_for_logging(request) == "203.0.113.7"
