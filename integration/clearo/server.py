"""Clearo HTTP surface (standard library only).

POST /webhooks/relay   Relay status webhooks, HMAC-verified before belief.
GET  /invoices/<id>    An invoice's public status and payment instructions.
GET  /health           Liveness.

Webhook keys come from RELAY_WEBHOOK_KEYS (comma separated, two entries
during key rotation) and fall back to RELAY_API_KEY.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .invoices import InvoiceStore
from .webhooks import apply_event, verify_signature


def webhook_keys() -> list[str]:
    raw = os.environ.get("RELAY_WEBHOOK_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys and os.environ.get("RELAY_API_KEY"):
        keys = [os.environ["RELAY_API_KEY"]]
    return keys


def make_handler(store: InvoiceStore):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep stdout clean
            pass

        def _send(self, code: int, payload: dict):
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                return self._send(200, {"service": "clearo", "status": "ok"})
            if self.path.startswith("/invoices/"):
                invoice_id = self.path.split("/", 2)[2]
                try:
                    invoice = store.get(invoice_id)
                except Exception:
                    return self._send(404, {"error": "unknown invoice"})
                return self._send(200, {"invoice_id": invoice.invoice_id,
                                        "status": invoice.status,
                                        "instructions": invoice.payment_instructions()})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/webhooks/relay":
                return self._send(404, {"error": "not found"})
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            ok = verify_signature(webhook_keys(),
                                  self.headers.get("X-Signature-Timestamp"),
                                  self.headers.get("X-Signature-SHA256"), body)
            if not ok:
                return self._send(401, {"error": "signature verification failed"})
            try:
                event = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._send(400, {"error": "invalid JSON"})
            return self._send(200, apply_event(store, event))

    return Handler


def serve(store: InvoiceStore, port: int) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(store))
    print(f"clearo listening on :{port}")
    server.serve_forever()
