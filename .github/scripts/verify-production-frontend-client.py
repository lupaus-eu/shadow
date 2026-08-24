import json
import os
import socket
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ORIGIN = "http://frontend:8080"
HOST = "app.example.test"
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)
PROXY_TEST_MODE = os.environ.get("PROXY_TEST_MODE", "trusted")


def request(path: str, *, host: str = HOST, headers: dict[str, str] | None = None):
    request_headers = {"Host": host, **(headers or {})}
    try:
        return urlopen(Request(f"{ORIGIN}{path}", headers=request_headers), timeout=5)
    except HTTPError as error:
        return error


if PROXY_TEST_MODE == "trusted":
    forwarded_for = "203.0.113.30, 198.51.100.10"
    expected_client_ip = "198.51.100.10"
elif PROXY_TEST_MODE == "untrusted":
    with socket.create_connection(("frontend", 8080), timeout=5) as connection:
        expected_client_ip = connection.getsockname()[0]
    forwarded_for = "203.0.113.30, 198.51.100.10"
else:
    raise ValueError(f"Unknown PROXY_TEST_MODE: {PROXY_TEST_MODE}")


with request(
    "/api/headers?code=secret-code&state=secret-state&error=secret-error&"
    "error_description=secret-description&visible=kept",
    headers={
        "Forwarded": "for=203.0.113.30;proto=http;host=evil.test",
        "X-Forwarded-For": forwarded_for,
        "X-Forwarded-Host": "evil.test",
        "X-Forwarded-Proto": "http",
        "X-Schatten-Client-IP": "203.0.113.40",
        "Authorization": "Bearer credential-secret",
        "Cookie": "session=credential-cookie",
    },
) as response:
    assert response.status == 200
    forwarded = json.load(response)
    expected_forwarded = {
        "host": HOST,
        "forwarded": None,
        "forwardedHost": HOST,
        "forwardedProto": "https",
        "forwardedFor": expected_client_ip,
        "clientIp": expected_client_ip,
    }
    assert forwarded == expected_forwarded, forwarded
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Content-Security-Policy"] == CSP

if PROXY_TEST_MODE == "trusted":
    with request("/workspace/deep-link") as response:
        assert response.status == 200
        assert b'<div id="root"></div>' in response.read()

    with request("/", host="evil.test") as response:
        assert response.status == 400

    with request("/health") as response:
        assert response.status == 200
        assert response.read() == b"OK"
