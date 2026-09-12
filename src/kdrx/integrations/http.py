"""Bounded HTTP with pinned DNS, per-hop policy and binary provenance."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import socket
import ssl
import time
import urllib.parse
import zlib
from dataclasses import dataclass


class TransportError(Exception):
    def __init__(
        self,
        message: str,
        code: str = "provider_unavailable",
        *,
        retry_after: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


@dataclass(frozen=True)
class FetchResponse:
    data: bytes
    status: int
    headers: dict[str, str]
    final_url: str
    redirect_chain: tuple[str, ...]
    elapsed_seconds: float
    sha256: str

    def text(self) -> str:
        content_type = self.headers.get("content-type", "")
        charset = "utf-8"
        for part in content_type.split(";")[1:]:
            if part.strip().lower().startswith("charset="):
                charset = part.split("=", 1)[1].strip(' "')
        try:
            return self.data.decode(charset)
        except (LookupError, UnicodeError) as exc:
            raise TransportError(
                "response cannot be decoded with declared charset", "parse_failed"
            ) from exc


class SafeHTTPTransport:
    def __init__(
        self,
        timeout: float = 20,
        user_agent: str = "kdr-x/0.3",
        *,
        max_bytes: int = 8 * 1024 * 1024,
        max_redirects: int = 5,
        allowlist: set[str] | None = None,
        denylist: set[str] | None = None,
    ):
        if timeout <= 0 or max_bytes <= 0 or max_redirects < 0:
            raise ValueError("invalid HTTP limits")
        self.timeout, self.user_agent = timeout, user_agent
        self.max_bytes, self.max_redirects = max_bytes, max_redirects
        self.allowlist, self.denylist = allowlist, denylist

    def resolve(self, url: str) -> tuple[str, str, int, str]:
        from kdrx.security import egress_allowed

        try:
            parts = urllib.parse.urlsplit(url)
            if (
                parts.scheme not in {"http", "https"}
                or not parts.hostname
                or parts.username is not None
                or parts.password is not None
                or any(ord(char) < 33 for char in url)
                or "\\" in url
            ):
                raise ValueError("scheme, hostname or credentials disallowed")
            host = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
            port = parts.port or (443 if parts.scheme == "https" else 80)
            if port not in {80, 443}:
                raise ValueError("port disallowed")
            if not egress_allowed(
                host, allowlist=self.allowlist, denylist=self.denylist
            ):
                raise ValueError("host disallowed")
            addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
            ips = {item[4][0] for item in addresses}
            if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
                raise ValueError("non-public destination disallowed")
        except (ValueError, UnicodeError) as exc:
            raise TransportError(
                "egress policy blocked destination", "policy_blocked"
            ) from exc
        except OSError as exc:
            raise TransportError("DNS resolution unavailable") from exc
        return parts.scheme, host, port, sorted(ips)[0]

    def _connection(self, scheme: str, host: str, port: int, ip: str, remaining: float):
        context = ssl.create_default_context()
        conn = (
            http.client.HTTPSConnection(host, port, timeout=remaining, context=context)
            if scheme == "https"
            else http.client.HTTPConnection(host, port, timeout=remaining)
        )

        def connect_pinned(address, timeout=None, source_address=None):
            sock = socket.create_connection(
                (ip, port), timeout=timeout, source_address=source_address
            )
            if ipaddress.ip_address(sock.getpeername()[0]) != ipaddress.ip_address(ip):
                sock.close()
                raise TransportError(
                    "connected peer differs from authorized IP", "policy_blocked"
                )
            return sock

        conn._create_connection = connect_pinned
        return conn

    def fetch(self, url: str, headers: dict[str, str] | None = None) -> FetchResponse:
        start = time.monotonic()
        deadline = start + self.timeout
        current = url
        chain = []
        request_headers = {
            "User-Agent": self.user_agent,
            "Accept-Encoding": "identity",
            **(headers or {}),
        }
        previous_origin = None
        try:
            for hop in range(self.max_redirects + 1):
                scheme, host, port, ip = self.resolve(current)
                origin = (scheme, host, port)
                if previous_origin is not None and origin != previous_origin:
                    request_headers = {
                        k: v
                        for k, v in request_headers.items()
                        if k.lower()
                        not in {"authorization", "cookie", "proxy-authorization"}
                    }
                previous_origin = origin
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TransportError("total HTTP deadline exceeded", "timeout")
                conn = self._connection(scheme, host, port, ip, remaining)
                try:
                    parts = urllib.parse.urlsplit(current)
                    target = urllib.parse.urlunsplit(
                        ("", "", parts.path or "/", parts.query, "")
                    )
                    conn.request("GET", target, headers=request_headers)
                    response = conn.getresponse()
                    meta = {key.lower(): value for key, value in response.getheaders()}
                    if response.status in {301, 302, 303, 307, 308}:
                        if hop == self.max_redirects or "location" not in meta:
                            raise TransportError(
                                "redirect limit or missing location", "policy_blocked"
                            )
                        chain.append(current)
                        current = urllib.parse.urljoin(current, meta["location"])
                        continue
                    if response.status >= 400:
                        code = {
                            401: "unauthorized",
                            403: "unauthorized",
                            404: "not_found",
                            429: "rate_limited",
                        }.get(response.status, "provider_unavailable")
                        raise TransportError(
                            f"HTTP {response.status}",
                            code,
                            retry_after=meta.get("retry-after"),
                        )
                    declared = meta.get("content-length")
                    if declared and int(declared) > self.max_bytes:
                        raise TransportError(
                            "response byte limit exceeded", "size_limit"
                        )
                    encoding = meta.get("content-encoding", "identity").lower()
                    if encoding not in {"identity", "gzip", "deflate"}:
                        raise TransportError(
                            "unsupported content encoding", "parse_failed"
                        )
                    decoder = (
                        zlib.decompressobj(31 if encoding == "gzip" else zlib.MAX_WBITS)
                        if encoding != "identity"
                        else None
                    )
                    chunks = []
                    wire = decoded = 0
                    while True:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TransportError(
                                "total HTTP deadline exceeded", "timeout"
                            )
                        if conn.sock is not None:
                            conn.sock.settimeout(remaining)
                        chunk = response.read1(min(65536, self.max_bytes - wire + 1))
                        if not chunk:
                            break
                        wire += len(chunk)
                        if wire > self.max_bytes:
                            raise TransportError(
                                "response byte limit exceeded", "size_limit"
                            )
                        chunk = (
                            decoder.decompress(chunk, self.max_bytes - decoded + 1)
                            if decoder
                            else chunk
                        )
                        decoded += len(chunk)
                        if decoded > self.max_bytes:
                            raise TransportError(
                                "decompressed byte limit exceeded", "size_limit"
                            )
                        chunks.append(chunk)
                    if decoder and (not decoder.eof or decoder.unused_data):
                        raise TransportError(
                            "truncated or concatenated compressed response",
                            "parse_failed",
                        )
                    data = b"".join(chunks)
                    return FetchResponse(
                        data,
                        response.status,
                        meta,
                        current,
                        tuple(chain),
                        time.monotonic() - start,
                        hashlib.sha256(data).hexdigest(),
                    )
                finally:
                    conn.close()
        except TransportError:
            raise
        except (TimeoutError, socket.timeout) as exc:
            raise TransportError("HTTP timeout", "timeout") from exc
        except (OSError, ValueError, http.client.HTTPException, zlib.error) as exc:
            raise TransportError("HTTP transport failure") from exc
        raise TransportError("redirect limit exceeded", "policy_blocked")

    def __call__(self, url: str, headers: dict[str, str] | None = None) -> str:
        return self.fetch(url, headers).text()
