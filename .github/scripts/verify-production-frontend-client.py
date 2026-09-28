import json
import socket
import ssl
from http.client import HTTPConnection, HTTPSConnection

HOST = "app.example.test"
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)
# The QA container uses Caddy's internal issuer; trust is not under test here.
TLS = ssl._create_unverified_context()


def request(path: str, *, host: str = HOST, headers: dict[str, str] | None = None):
    connection = HTTPSConnection(HOST, 443, context=TLS, timeout=5)
    connection.request("GET", path, headers={"Host": host, **(headers or {})})
    response = connection.getresponse()
    return response, response.read()


with socket.create_connection((HOST, 443), timeout=5) as probe:
    expected_client_ip = probe.getsockname()[0]

response, body = request(
    "/api/headers?code=secret-code&state=secret-state&error=secret-error&"
    "error_description=secret-description&visible=kept",
    headers={
        "Forwarded": "for=203.0.113.30;proto=http;host=evil.test",
        "X-Forwarded-For": "203.0.113.30, 198.51.100.10",
        "X-Forwarded-Host": "evil.test",
        "X-Forwarded-Proto": "http",
        "X-Schatten-Client-IP": "203.0.113.40",
        "X-CSRF-Token": "csrf-header-secret",
        "Authorization": "Bearer credential-secret",
        "Cookie": "session=credential-cookie",
    },
)
assert response.status == 200, response.status
forwarded = json.loads(body)
assert forwarded == {
    "host": HOST,
    "forwarded": None,
    "forwardedHost": HOST,
    "forwardedProto": "https",
    "forwardedFor": expected_client_ip,
    "clientIp": expected_client_ip,
}, forwarded
assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
assert response.headers["Referrer-Policy"] == "no-referrer"
assert response.headers["X-Content-Type-Options"] == "nosniff"
assert response.headers["X-Frame-Options"] == "DENY"
assert response.headers["Content-Security-Policy"] == CSP
assert "Alt-Svc" not in response.headers

response, body = request("/workspace/deep-link")
assert response.status == 200
assert b'<div id="root"></div>' in body

response, _ = request("/", host="evil.test")
assert response.status == 400

response, body = request("/health")
assert response.status == 200 and body == b"OK"

plain = HTTPConnection(HOST, 80, timeout=5)
plain.request("GET", "/login?x=1", headers={"Host": HOST})
redirect = plain.getresponse()
assert redirect.status == 308, redirect.status
assert redirect.headers["Location"] == f"https://{HOST}/login?x=1"

plain = HTTPConnection(HOST, 80, timeout=5)
plain.request("GET", "/", headers={"Host": "evil.test"})
assert plain.getresponse().status == 400
