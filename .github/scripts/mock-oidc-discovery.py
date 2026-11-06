"""Simulated Authentik discovery endpoint for disposable runtime QA only.

Serves the per-provider discovery document and a JWKS over HTTPS with a throwaway QA
certificate so the production backend can start without an identity provider. It issues no
tokens; interactive login is outside this harness.
"""

import json
import os
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.environ.get("QA_IDENTITY_HOST", "id.qa.example.test")
SLUG = os.environ.get("QA_PROVIDER_SLUG", "shadow")
ORIGIN = f"https://{HOST}"
ISSUER = f"{ORIGIN}/application/o/{SLUG}/"
DOCUMENTS = {
    f"/application/o/{SLUG}/.well-known/openid-configuration": {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ORIGIN}/application/o/authorize/",
        "token_endpoint": f"{ORIGIN}/application/o/token/",
        "jwks_uri": f"{ISSUER}jwks/",
        "end_session_endpoint": f"{ISSUER}end-session/",
        "id_token_signing_alg_values_supported": ["RS256"],
    },
    f"/application/o/{SLUG}/jwks/": {
        "keys": [{"kty": "RSA", "kid": "qa", "use": "sig", "n": "sXch", "e": "AQAB"}]
    },
}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        document = DOCUMENTS.get(self.path)
        body = json.dumps(document or {"error": "not_found"}).encode()
        self.send_response(200 if document else 404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.load_cert_chain(os.environ["QA_TLS_CERT"], os.environ["QA_TLS_KEY"])
server = ThreadingHTTPServer(("0.0.0.0", 443), Handler)
server.socket = context.wrap_socket(server.socket, server_side=True)
server.serve_forever()
