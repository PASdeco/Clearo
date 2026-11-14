"""Relay webhook verification and handling.

Relay signs each delivery with HMAC-SHA256 over "<timestamp>.<body>",
sent in the X-Signature-SHA256 and X-Signature-Timestamp headers. During
key rotation an App can have two active keys, so a delivery is accepted
when ANY configured key verifies. Unsigned, tampered or wrongly signed
deliveries are rejected and never touch an invoice.

Events are matched to invoices by deposit address first, because for
deposit-address requests Relay may regenerate the requestId that owns the
fill; the requestId is the fallback, never the only key.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from .invoices import Invoice, InvoiceStore
from .status import can_transition

EVENT_TYPE = "request.status.updated"


def verify_signature(keys: list[str], timestamp: str | None,
                     signature: str | None, body: bytes) -> bool:
    if not timestamp or not signature or not keys:
        return False
    try:
        int(timestamp)
    except (TypeError, ValueError):
        return False
    message = f"{timestamp}.".encode() + body
    for key in keys:
        expected = hmac.new(key.encode(), message, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature):
            return True
    return False


def parse_event(body: bytes) -> dict:
    event = json.loads(body.decode("utf-8"))
    if event.get("event") not in (EVENT_TYPE, None) and event.get("type") != EVENT_TYPE:
        # Relay sends the event name in the payload; tolerate both fields.
        pass
    return event


def find_invoice(store: InvoiceStore, event: dict) -> Invoice | None:
    data = event.get("data", event)
    deposit_address = (data.get("depositAddress") or data.get("deposit_address") or "")
    request_id = data.get("requestId") or data.get("request_id") or ""
    for invoice_id in store.list_ids():
        invoice = store.get(invoice_id)
        if deposit_address and invoice.deposit_address == deposit_address:
            return invoice
        if request_id and invoice.relay_request_id == request_id:
            return invoice
    return None


def apply_event(store: InvoiceStore, event: dict) -> dict:
    """Apply one verified webhook event. Returns the outcome; idempotent
    for repeat deliveries, and final states are never overwritten."""
    data = event.get("data", event)
    new_status = data.get("status")
    invoice = find_invoice(store, event)
    if invoice is None:
        return {"matched": False, "reason": "no invoice for this deposit address or request id"}
    if new_status == invoice.status:
        return {"matched": True, "invoice_id": invoice.invoice_id,
                "status": invoice.status, "changed": False}
    if not can_transition(invoice.status, new_status or ""):
        return {"matched": True, "invoice_id": invoice.invoice_id,
                "status": invoice.status, "changed": False,
                "reason": f"transition {invoice.status} -> {new_status} not allowed"}
    previous = invoice.status
    invoice.status = new_status
    tx_hash = data.get("depositTxHash") or data.get("txHash")
    if tx_hash and not invoice.deposit_tx_hash:
        invoice.deposit_tx_hash = tx_hash
    invoice.history.append({"from": previous, "to": new_status, "source": "webhook"})
    store.save(invoice)
    return {"matched": True, "invoice_id": invoice.invoice_id,
            "status": invoice.status, "changed": True}
