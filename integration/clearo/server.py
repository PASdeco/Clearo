"""Clearo HTTP surface (standard library only).

POST /invoices          A plugged-in seller creates an invoice for an
                        agreed job. Authenticated with the seller's token
                        (X-Clearo-Token) when CLEARO_SELLER_TOKENS is set.
POST /webhooks/relay    Relay status webhooks, HMAC-verified before belief.
GET  /invoices/<id>     An invoice's public status and payment instructions.
GET  /health            Liveness.

Webhook keys come from RELAY_WEBHOOK_KEYS (comma separated, two entries
during key rotation) and fall back to RELAY_API_KEY. Seller tokens come
from CLEARO_SELLER_TOKENS, a JSON object mapping seller id to token; a
seller's token only ever creates invoices under its own seller id.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import Config
from .invoices import InvoiceStore
from .relay_client import RelayClient
from .seller import SellerBridge, SellerProfile
from .webhooks import apply_event, verify_signature


def webhook_keys() -> list[str]:
    raw = os.environ.get("RELAY_WEBHOOK_KEYS", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys and os.environ.get("RELAY_API_KEY"):
        keys = [os.environ["RELAY_API_KEY"]]
    return keys


def seller_tokens() -> dict:
    raw = os.environ.get("CLEARO_SELLER_TOKENS", "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


def make_handler(store: InvoiceStore, config: Config):
    client = RelayClient(config.relay_api_key, config.relay_api_base)
    tokens = seller_tokens()

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

        def _read_json(self) -> dict | None:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b""
            try:
                parsed = json.loads(raw.decode("utf-8"))
                return parsed if isinstance(parsed, dict) else None
            except (ValueError, UnicodeDecodeError):
                return None

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
            if self.path == "/invoices":
                return self._create_invoice()
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
            result = apply_event(store, event)
            try:
                SellerBridge.release_all_due(store)
            except Exception:
                pass  # a release pass also runs on watch; never fail a webhook on it
            return self._send(200, result)

        def _create_invoice(self):
            body = self._read_json()
            if body is None:
                return self._send(400, {"error": "invalid JSON"})
            seller = body.get("seller") or {}
            seller_id = seller.get("id")
            if tokens:
                token = self.headers.get("X-Clearo-Token")
                if not seller_id or tokens.get(seller_id) != token:
                    return self._send(401, {"error": "seller authentication failed"})
            try:
                profile = SellerProfile(
                    seller_id=seller_id or "unknown",
                    seller_name=seller.get("name") or seller_id or "seller",
                    wallet=seller.get("wallet"),
                    receive_chain_id=int(seller.get("receive_chain_id") or 8453))
                invoice = SellerBridge(profile).on_job_agreed(
                    client, config, store,
                    job_ref=body.get("job_ref") or "",
                    amount_usdc=str(body.get("amount_usdc") or ""),
                    buyer_refund_address=body.get("buyer_refund_address") or "",
                    pay_from_chain_id=int(body.get("pay_from_chain_id") or 0),
                    buyer_id=body.get("buyer_id"))
            except Exception as exc:
                return self._send(400, {"error": str(exc)[:300]})
            return self._send(201, {"invoice_id": invoice.invoice_id,
                                    "status": invoice.status,
                                    "instructions": invoice.payment_instructions()})

    return Handler


def serve(store: InvoiceStore, port: int) -> None:
    config = Config.from_env()
    server = ThreadingHTTPServer(("0.0.0.0", port), make_handler(store, config))
    print(f"clearo listening on :{port}")
    server.serve_forever()
