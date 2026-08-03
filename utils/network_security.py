"""Network-boundary helpers for user-supplied HTTP(S) URLs."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse


class UnsafeUrlError(ValueError):
    """Raised when a URL can reach a non-public network destination."""


def validate_public_http_url(url: str) -> str:
    value = str(url or "").strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("只允许访问有效的 HTTP/HTTPS URL")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("URL 不允许包含用户名或密码")

    host = parsed.hostname.rstrip(".")
    try:
        literal = ipaddress.ip_address(host)
        addresses = {literal}
    except ValueError:
        try:
            records = socket.getaddrinfo(
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise UnsafeUrlError(f"无法解析目标主机: {host}") from exc
        addresses = {ipaddress.ip_address(record[4][0]) for record in records}

    if not addresses or any(not address.is_global for address in addresses):
        raise UnsafeUrlError("不允许访问本机、私网、链路本地或保留地址")
    return value


def safe_get(client, url: str, *, max_redirects: int = 5, **kwargs):
    """GET a public URL while re-validating every redirect destination."""
    kwargs.pop("allow_redirects", None)
    current = validate_public_http_url(url)
    for redirect_count in range(max_redirects + 1):
        response = client.get(current, allow_redirects=False, **kwargs)
        if getattr(response, "status_code", 200) not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("Location")
        if not location:
            return response
        response.close()
        if redirect_count == max_redirects:
            raise UnsafeUrlError("重定向次数过多")
        current = validate_public_http_url(urljoin(current, location))
    raise UnsafeUrlError("重定向次数过多")
