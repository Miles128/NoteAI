from __future__ import annotations

import socket

import pytest

from utils.network_security import UnsafeUrlError, safe_get, validate_public_http_url


def test_rejects_loopback_and_private_literal_addresses() -> None:
    for url in ("http://127.0.0.1/admin", "http://10.0.0.8/", "http://[::1]/"):
        with pytest.raises(UnsafeUrlError):
            validate_public_http_url(url)


def test_rejects_hostname_that_resolves_to_private_address(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.9", 80))],
    )

    with pytest.raises(UnsafeUrlError):
        validate_public_http_url("https://internal.example/")


def test_safe_get_revalidates_redirect_targets(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
    )

    class Response:
        status_code = 302
        headers = {"Location": "http://127.0.0.1/private"}

        def close(self):
            return None

    class Client:
        def get(self, *_args, **_kwargs):
            return Response()

    with pytest.raises(UnsafeUrlError):
        safe_get(Client(), "https://example.com/start")
