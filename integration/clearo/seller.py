"""The seller bridge: how a seller agent plugs in to Clearo.

Plugging in means two automatic touches and nothing else:

1. When the seller agrees a job, it calls `on_job_agreed` and Clearo
   issues the invoice and the payment instructions.
2. When Clearo reports the payment final (success, and only success),
   `release_due` writes a delivery release for that job, exactly once,
   which the seller's own runner picks up and delivers against.

A seller integrates once, in a few lines. A buyer never plugs in at all:
it receives payment instructions and pays from its own wallet.

This module ships with our own seller's profile as the reference
integration (seller id "pasdeco"). Other sellers set their own profile
through the same environment variables.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .invoices import Invoice, InvoiceStore, create_invoice
from .ledger import append_event
from .relay_client import RelayClient

DELIVERIES_NAME = "deliveries.jsonl"


@dataclass(frozen=True)
class SellerProfile:
    seller_id: str = "pasdeco"
    seller_name: str = "pasdeco seller"
    wallet: str | None = None
    receive_chain_id: int = 8453

    @classmethod
    def from_env(cls) -> "SellerProfile":
        return cls(
            seller_id=os.environ.get("CLEARO_SELLER_ID", "pasdeco"),
            seller_name=os.environ.get("CLEARO_SELLER_NAME", "pasdeco seller"),
            wallet=os.environ.get("CLEARO_SELLER_WALLET") or None,
            receive_chain_id=int(os.environ.get("CLEARO_SELLER_RECEIVE_CHAIN", "8453")),
        )


class SellerBridge:
    def __init__(self, profile: SellerProfile):
        self.profile = profile

    @classmethod
    def from_env(cls) -> "SellerBridge":
        return cls(SellerProfile.from_env())

    def on_job_agreed(self, client: RelayClient, config: Config, store: InvoiceStore, *,
                      job_ref: str, amount_usdc: str, buyer_refund_address: str,
                      pay_from_chain_id: int, buyer_id: str | None = None) -> Invoice:
        """Job agreed -> invoice issued, ready to hand to the buyer."""
        if not self.profile.wallet:
            raise ValueError("CLEARO_SELLER_WALLET is not set for this seller profile")
        return create_invoice(
            client, config, store,
            seller_id=self.profile.seller_id, seller_name=self.profile.seller_name,
            seller_wallet=self.profile.wallet,
            receive_chain_id=self.profile.receive_chain_id,
            amount_usdc=amount_usdc, job_ref=job_ref,
            refund_address=buyer_refund_address,
            pay_from_chain_id=pay_from_chain_id, buyer_id=buyer_id)

    def release_due(self, store: InvoiceStore) -> list[dict]:
        """Release delivery for every invoice that is final-paid and not
        yet released. Only success releases. Exactly once per invoice."""
        released = []
        outbox = Path(store.dir) / DELIVERIES_NAME
        for invoice_id in store.list_ids():
            invoice = store.get(invoice_id)
            if invoice.seller_id != self.profile.seller_id:
                continue
            if invoice.status != "success" or invoice.delivery_released:
                continue
            entry = {"invoice_id": invoice.invoice_id, "job_ref": invoice.job_ref,
                     "seller_id": invoice.seller_id, "amount_usdc": invoice.amount_usdc,
                     "action": "deliver"}
            with outbox.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
            invoice.delivery_released = True
            store.save(invoice)
            append_event(store.dir, "delivery_released", invoice_id=invoice.invoice_id,
                         job_ref=invoice.job_ref, seller_id=invoice.seller_id)
            released.append(entry)
        return released
