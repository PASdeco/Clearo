"""Fee verification: quoted against actual, checked on Relay's own record.

When an invoice reaches a final state, Clearo reads the request record on
GET /requests/v3 and compares the app fee Relay actually charged with the
fee the quote promised. Outcomes:

- match:          actual equals quoted, to the digit.
- not_collected:  the quoted fee was under the $0.025 range where Relay may
                  not collect, and the actual fee is zero. Informational,
                  recorded honestly, not an error.
- mismatch:       anything else. Flagged the same day; never hidden.
- unavailable:    Relay has no record yet (for example an unpaid quote).
                  Nothing is claimed either way.

Every verification is written to the settlement ledger, and the sum of
verified actual fees is Clearo's accrual book: the number that a Relay
fee balance must agree with before any claim is made.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation

from .invoices import Invoice, InvoiceStore
from .ledger import append_event
from .relay_client import RelayClient, RelayError

COLLECTION_FLOOR = Decimal("0.025")


def _dec(value) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def extract_actual_app_fee(record) -> Decimal | None:
    """Find the actual app fee in a /requests/v3 record, tolerating the
    shapes the API uses (record, record.data, or a requests list)."""
    if record is None:
        return None
    if isinstance(record, dict) and isinstance(record.get("requests"), list):
        for item in record["requests"]:
            fee = extract_actual_app_fee(item)
            if fee is not None:
                return fee
        return None
    if isinstance(record, list):
        for item in record:
            fee = extract_actual_app_fee(item)
            if fee is not None:
                return fee
        return None
    if not isinstance(record, dict):
        return None
    node = record.get("data", record)
    fees = (node or {}).get("fees") or {}
    app = fees.get("app")
    if isinstance(app, dict):
        for key in ("amountFormatted", "amount", "actual", "value"):
            if app.get(key) is not None:
                return _dec(app[key])
    if isinstance(app, (str, int, float)):
        return _dec(app)
    return None


@dataclass
class FeeVerification:
    invoice_id: str
    quoted_app_fee_usdc: str | None
    actual_app_fee_usdc: str | None
    outcome: str  # match | not_collected | mismatch | unavailable

    def as_dict(self) -> dict:
        return asdict(self)


def verify_invoice_fee(client: RelayClient, store: InvoiceStore,
                       invoice: Invoice) -> FeeVerification:
    quoted = _dec(invoice.quoted_app_fee_usdc)
    try:
        record = client.get_request_record(invoice.relay_request_id) if invoice.relay_request_id else None
    except RelayError:
        record = None
    actual = extract_actual_app_fee(record)
    if actual is None:
        outcome = "unavailable"
    elif quoted is not None and actual == quoted:
        outcome = "match"
    elif actual == 0 and quoted is not None and quoted <= COLLECTION_FLOOR:
        outcome = "not_collected"
    else:
        outcome = "mismatch"
    result = FeeVerification(
        invoice_id=invoice.invoice_id,
        quoted_app_fee_usdc=str(quoted) if quoted is not None else None,
        actual_app_fee_usdc=str(actual) if actual is not None else None,
        outcome=outcome)
    invoice.fee_verification = result.as_dict()
    store.save(invoice)
    fields = {k: v for k, v in result.as_dict().items() if k != "invoice_id"}
    append_event(store.dir, "fee_mismatch" if outcome == "mismatch" else "fee_verified",
                 invoice_id=invoice.invoice_id, **fields)
    return result


def reconcile(client: RelayClient, store: InvoiceStore) -> dict:
    """Verify every final invoice and total the accrual book."""
    summary = {"verified": 0, "match": 0, "not_collected": 0, "mismatch": 0,
               "unavailable": 0, "accrued_actual_fees_usdc": "0"}
    accrued = Decimal("0")
    for invoice_id in store.list_ids():
        invoice = store.get(invoice_id)
        if invoice.status not in ("success", "refund"):
            continue
        result = verify_invoice_fee(client, store, invoice)
        summary["verified"] += 1
        summary[result.outcome] += 1
        if result.outcome == "match" and result.actual_app_fee_usdc is not None:
            accrued += Decimal(result.actual_app_fee_usdc)
    summary["accrued_actual_fees_usdc"] = str(accrued)
    return summary
