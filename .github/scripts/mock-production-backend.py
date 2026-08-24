import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps(
            {
                "host": self.headers.get("Host"),
                "forwarded": self.headers.get("Forwarded"),
                "forwardedHost": self.headers.get("X-Forwarded-Host"),
                "forwardedProto": self.headers.get("X-Forwarded-Proto"),
                "forwardedFor": self.headers.get("X-Forwarded-For"),
                "clientIp": self.headers.get("X-Schatten-Client-IP"),
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: object) -> None:
        return


ThreadingHTTPServer(("0.0.0.0", 8000), Handler).serve_forever()
