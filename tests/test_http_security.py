"""Transport effects are observed; policy is exercised before any body read."""

import gzip
import socket

import pytest

from kdrx.integrations.http import SafeHTTPTransport, TransportError


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:pass@example.com",
        "http://127.0.0.1",
        "http://[::1]",
        "http://169.254.169.254/latest",
        "http://10.0.0.1",
        "http://example.com:22",
    ],
)
def test_non_public_and_special_destinations_blocked(url):
    with pytest.raises(TransportError) as error:
        SafeHTTPTransport().fetch(url)
    assert error.value.code == "policy_blocked"


class Response:
    def __init__(self, body=b"ok", status=200, headers=None):
        self.body, self.status, self.headers = body, status, headers or {}
        self.read = 0

    def getheaders(self):
        return list(self.headers.items())

    def read1(self, size):
        self.read += 1
        data, self.body = self.body[:size], self.body[size:]
        return data


class Connection:
    sock = None

    def __init__(self, response, requests):
        self.response, self.requests = response, requests

    def request(self, method, target, headers):
        self.requests.append((method, target, dict(headers)))

    def getresponse(self):
        return self.response

    def close(self):
        pass


def public_dns(monkeypatch):
    def addresses(host, port, **kwargs):
        ip = "169.254.169.254" if host == "metadata.invalid" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port))]

    monkeypatch.setattr(socket, "getaddrinfo", addresses)


def test_redirect_to_metadata_is_blocked_before_connection(monkeypatch):
    public_dns(monkeypatch)
    initial = Response(
        status=302, headers={"Location": "http://metadata.invalid/latest"}
    )
    requests = []
    transport = SafeHTTPTransport()
    monkeypatch.setattr(
        transport, "_connection", lambda *args: Connection(initial, requests)
    )
    with pytest.raises(TransportError, match="policy"):
        transport.fetch("https://example.org")
    assert len(requests) == 1 and initial.read == 0


@pytest.mark.parametrize("compressed", [False, True])
def test_stream_and_decompression_limits(monkeypatch, compressed):
    public_dns(monkeypatch)
    response = Response(
        gzip.compress(b"x" * 10000) if compressed else b"x" * 10000,
        headers={"Content-Encoding": "gzip"} if compressed else {},
    )
    transport = SafeHTTPTransport(max_bytes=100)
    monkeypatch.setattr(
        transport, "_connection", lambda *args: Connection(response, [])
    )
    with pytest.raises(TransportError) as error:
        transport.fetch("https://example.org")
    assert error.value.code == "size_limit"


def test_credentials_removed_across_origin(monkeypatch):
    public_dns(monkeypatch)
    responses = iter(
        [
            Response(status=302, headers={"Location": "https://other.org/end"}),
            Response(b"\x00\xff"),
        ]
    )
    requests = []
    transport = SafeHTTPTransport()
    monkeypatch.setattr(
        transport, "_connection", lambda *args: Connection(next(responses), requests)
    )
    response = transport.fetch(
        "https://example.org/start",
        {"Authorization": "Bearer fixture", "Cookie": "fixture"},
    )
    assert response.data == b"\x00\xff"
    assert "Authorization" in requests[0][2]
    assert "Authorization" not in requests[1][2] and "Cookie" not in requests[1][2]


def test_all_dns_addresses_checked(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(TransportError, match="policy"):
        SafeHTTPTransport().resolve("https://example.org")
