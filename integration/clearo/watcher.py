"""The Clearo watcher: polling backup for the webhook receiver.

For every open invoice it asks Relay for the current status, applies the
same transition rules the webhook path uses, and closes invoices that pass
their expiry unpaid. Polling never marks anything settled by hand: only a
Relay-reported success is final, exactly as with webhooks.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from .invoices import InvoiceStore
from .relay_client import RelayClient, RelayError
from .status import can_transition, is_final

log = logging.getLogger("clearo.watcher")


def poll_invoice(client: RelayClient, store: InvoiceStore, invoice) -> dict:
    if is_final(invoice.status) or invoice.status == "expired":
        return {"invoice_id": invoice.invoice_id, "status": invoice.status, "changed": False}
    now = datetime.now(timezone.utc)
    expires = datetime.fromisoformat(invoice.expires_at)
    if invoice.status == "waiting" and now > expires:
        invoice.status = "expired"
        invoice.history.append({"from": "waiting", "to": "expired", "source": "watcher-expiry"})
        store.save(invoice)
        return {"invoice_id": invoice.invoice_id, "status": "expired", "changed": True}
    if not invoice.relay_request_id:
        return {"invoice_id": invoice.invoice_id, "status": invoice.status, "changed": False}
    try:
        record = client.get_intent_status(invoice.relay_request_id)
    except RelayError as exc:
        # A quote that was never paid may have no request record yet.
        # That means "no deposit seen", not an error worth waking anyone for.
        log.debug("status lookup for %s: %s", invoice.invoice_id, exc)
        return {"invoice_id": invoice.invoice_id, "status": invoice.status,
                "changed": False, "note": "no Relay record yet"}
    new_status = record.get("status")
    if new_status and new_status != invoice.status and can_transition(invoice.status, new_status):
        previous = invoice.status
        invoice.status = new_status
        invoice.history.append({"from": previous, "to": new_status, "source": "poll"})
        store.save(invoice)
        return {"invoice_id": invoice.invoice_id, "status": new_status, "changed": True}
    return {"invoice_id": invoice.invoice_id, "status": invoice.status, "changed": False}


def poll_all(client: RelayClient, store: InvoiceStore) -> list[dict]:
    return [poll_invoice(client, store, store.get(i)) for i in store.list_ids()]
