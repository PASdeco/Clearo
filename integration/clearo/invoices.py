"""Clearo invoices.

One invoice is one payment for one job: exact amount, one-time strict
deposit address, a buyer refund address recorded before any payment
instructions exist, and instructions a buyer agent can follow without
guessing a token, a chain or an amount. Clearo never holds funds: the
buyer pays Relay's deposit address and Relay delivers to the seller.
"""
from __future__ import annotations

import json
import re
import secrets
from dataclasses import asdict, dataclass, field, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Config
from .relay_client import RelayClient

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

# Chains a seller can receive USDC on at launch (spec section 3).
RECEIVE_CHAINS = {8453: "Base", 56: "BNB Chain"}
# USDC contracts per chain, origin and destination.
USDC = {
    8453: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    42161: "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    56: "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
}
CHAIN_NAMES = {8453: "Base", 42161: "Arbitrum", 56: "BNB Chain"}

BLOCKED_PLATFORMS = ["ChangeNOW", "FixedFloat", "HTX", "CoinEx", "Tornado.cash"]
EXPIRY_HOURS = 24


class InvoiceError(ValueError):
    pass


def _check_address(value: str, label: str) -> str:
    if not value or not ADDRESS_RE.match(value):
        raise InvoiceError(f"{label} must be a valid EVM address, got {value!r}")
    return value


def to_base_units(amount_usdc: str) -> str:
    value = float(amount_usdc)
    if value <= 0:
        raise InvoiceError("amount must be greater than zero")
    return str(int(round(value * 1_000_000)))


def extract_deposit_address(quote: dict) -> str | None:
    """Find the deposit address in a Relay quote response, wherever the
    current API places it (top level or inside the deposit step)."""
    if quote.get("depositAddress"):
        return quote["depositAddress"]
    for step in quote.get("steps", []) or []:
        if step.get("depositAddress"):
            return step["depositAddress"]
        for item in step.get("items", []) or []:
            data = item.get("data", {}) or {}
            if data.get("depositAddress"):
                return data["depositAddress"]
    return None


@dataclass
class Invoice:
    invoice_id: str
    job_ref: str
    seller_id: str
    seller_name: str
    seller_wallet: str
    receive_chain_id: int
    amount_usdc: str            # exact amount the seller receives
    fee_bps: int
    quoted_app_fee_usdc: str | None
    quoted_relayer_fee_usdc: str | None
    pay_from_chain_id: int
    amount_to_send_usdc: str | None   # exact amount the buyer must deposit
    deposit_address: str | None
    refund_address: str
    buyer_id: str | None
    relay_request_id: str | None
    status: str                 # waiting on creation; lifecycle in spec section 5
    created_at: str
    expires_at: str
    deposit_tx_hash: str | None = None
    fee_verification: dict | None = None
    delivery_released: bool = False
    amount_mode: str = "exact_output"   # or "exact_input" (see create_invoice)
    expected_receive_usdc: str | None = None  # exact_input only: quoted estimate
    history: list = field(default_factory=list)

    def payment_instructions(self) -> dict:
        """Machine-readable instructions. A buyer agent must never have to
        guess a token, a chain or an amount."""
        return {
            "invoice_id": self.invoice_id,
            "job_ref": self.job_ref,
            "seller": {"id": self.seller_id, "name": self.seller_name,
                       "receives_at": self.seller_wallet,
                       "receive_chain_id": self.receive_chain_id,
                       "receive_chain": CHAIN_NAMES.get(self.receive_chain_id)},
            "pay": {
                "token": "USDC",
                "token_contract": USDC[self.pay_from_chain_id],
                "chain_id": self.pay_from_chain_id,
                "chain": CHAIN_NAMES.get(self.pay_from_chain_id),
                "exact_amount_usdc": self.amount_to_send_usdc,
                "deposit_address": self.deposit_address,
                "deposit_address_type": "strict, one-time use",
            },
            "amount_mode": self.amount_mode,
            "seller_receives_usdc": self.amount_usdc if self.amount_mode == "exact_output" else None,
            "seller_expected_usdc": self.expected_receive_usdc if self.amount_mode == "exact_input" else None,
            "clearo_fee_bps": self.fee_bps,
            "clearo_fee_usdc_quoted": self.quoted_app_fee_usdc,
            "refund_address_on_record": self.refund_address,
            "expires_at": self.expires_at,
            "warnings": [
                "Send only the exact token contract on the exact chain named above. "
                "A different token may be unrecoverable.",
                "This deposit address is one-time. Never reuse it for another payment; "
                "a second deposit is refunded to the refund address.",
                "Pay the exact amount. Paying too little does not fill and is refunded "
                "to the refund address, minus gas.",
                "Do not send from these platforms; screening can stop the payment: "
                + ", ".join(BLOCKED_PLATFORMS) + ".",
                "Clearo never holds your money. You pay Relay's deposit address and "
                "Relay delivers USDC directly to the seller.",
            ],
        }

    def instructions_text(self) -> str:
        ins = self.payment_instructions()
        pay = ins["pay"]
        lines = [
            f"Clearo invoice {self.invoice_id} for job {self.job_ref}",
            f"Seller: {self.seller_name} ({self.seller_id}), receiving USDC on "
            f"{ins['seller']['receive_chain']}",
            "",
            "To pay:",
            f"  Send exactly {pay['exact_amount_usdc']} USDC",
            f"  Token contract: {pay['token_contract']}",
            f"  On chain: {pay['chain']} (chain ID {pay['chain_id']})",
            f"  To this one-time deposit address: {pay['deposit_address']}",
            (f"  The seller receives {self.amount_usdc} USDC. Clearo's fee is "
             f"{self.fee_bps} bps, quoted at {self.quoted_app_fee_usdc} USDC."
             if self.amount_mode == "exact_output" else
             f"  The seller receives about {self.expected_receive_usdc} USDC "
             f"(market fill on a send-exact invoice). Clearo's fee is "
             f"{self.fee_bps} bps, quoted at {self.quoted_app_fee_usdc} USDC."),
            f"  This invoice expires at {self.expires_at}.",
            "",
            "Warnings:",
        ]
        lines += [f"  - {w}" for w in ins["warnings"]]
        return "\n".join(lines)


class InvoiceStore:
    """JSON file store. One file per invoice, written atomically."""

    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, invoice: Invoice) -> None:
        path = self.dir / f"{invoice.invoice_id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(asdict(invoice), indent=2), encoding="utf-8")
        tmp.replace(path)

    def get(self, invoice_id: str) -> Invoice:
        path = self.dir / f"{invoice_id}.json"
        if not path.exists():
            raise InvoiceError(f"unknown invoice {invoice_id}")
        return Invoice(**json.loads(path.read_text(encoding="utf-8")))

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.dir.glob("CLR-*.json"))


def new_invoice_id(now: datetime) -> str:
    return f"CLR-{now.strftime('%Y%m%d')}-{secrets.token_hex(3).upper()}"


def create_invoice(client: RelayClient, config: Config, store: InvoiceStore, *,
                   seller_id: str, seller_name: str, seller_wallet: str,
                   receive_chain_id: int, amount_usdc: str, job_ref: str,
                   refund_address: str, pay_from_chain_id: int,
                   buyer_id: str | None = None,
                   payer_address: str | None = None,
                   amount_mode: str = "exact_output") -> Invoice:
    """Create an invoice and its Relay deposit-address quote.

    The refund address is required and validated before Relay is called:
    no refund address, no payment instructions (spec section 3)."""
    if not job_ref:
        raise InvoiceError("a job reference is required: every payment traces to real work")
    _check_address(seller_wallet, "seller wallet")
    _check_address(refund_address, "refund address")
    if receive_chain_id not in RECEIVE_CHAINS:
        raise InvoiceError(f"sellers receive on {sorted(RECEIVE_CHAINS)} at launch, "
                           f"got chain {receive_chain_id}")
    if pay_from_chain_id not in USDC:
        raise InvoiceError(f"unsupported origin chain {pay_from_chain_id}")
    if payer_address:
        _check_address(payer_address, "payer address")
    config.require_quote_ready()
    recovery = config.effective_recovery_address

    now = datetime.now(timezone.utc)
    if amount_mode not in ("exact_output", "exact_input"):
        raise InvoiceError(f"unknown amount_mode {amount_mode!r}")
    # exact_output: the seller receives the exact invoice amount and the
    # buyer sends the computed input. exact_input: the buyer sends the
    # exact invoice amount and the seller receives the market fill. Some
    # routes (for example Base to BNB Chain USDC) only support deposit
    # addresses in exact_input mode; Relay rejects the other with a
    # "major tokens" error. The mode is printed on the invoice either way.
    quote = client.create_quote(
        user=payer_address or refund_address,
        recipient=seller_wallet,
        origin_chain_id=pay_from_chain_id,
        destination_chain_id=receive_chain_id,
        origin_currency=USDC[pay_from_chain_id],
        destination_currency=USDC[receive_chain_id],
        amount=to_base_units(amount_usdc),
        fee_recipient=config.fee_recipient, fee_bps=config.fee_bps,
        use_deposit_address=True,
        trade_type="EXACT_OUTPUT" if amount_mode == "exact_output" else "EXACT_INPUT",
        strict=True,
        refund_to=refund_address, recovery_address=recovery)
    deposit_address = extract_deposit_address(quote)
    if not deposit_address:
        raise InvoiceError("Relay quote returned no deposit address; invoice not issued")
    details = quote.get("details", {}) or {}
    fees = quote.get("fees", {}) or {}
    invoice = Invoice(
        invoice_id=new_invoice_id(now),
        job_ref=job_ref, seller_id=seller_id, seller_name=seller_name,
        seller_wallet=seller_wallet, receive_chain_id=receive_chain_id,
        amount_usdc=amount_usdc, fee_bps=config.fee_bps,
        quoted_app_fee_usdc=(fees.get("app") or {}).get("amountFormatted"),
        quoted_relayer_fee_usdc=(fees.get("relayer") or {}).get("amountFormatted"),
        pay_from_chain_id=pay_from_chain_id,
        amount_to_send_usdc=(amount_usdc if amount_mode == "exact_input"
                             else (details.get("currencyIn") or {}).get("amountFormatted")),
        amount_mode=amount_mode,
        expected_receive_usdc=((details.get("currencyOut") or {}).get("amountFormatted")
                               if amount_mode == "exact_input" else None),
        deposit_address=deposit_address,
        refund_address=refund_address, buyer_id=buyer_id,
        relay_request_id=quote.get("requestId"),
        status="waiting",
        created_at=now.isoformat(),
        expires_at=(now + timedelta(hours=EXPIRY_HOURS)).isoformat(),
    )
    store.save(invoice)
    from .ledger import append_event
    append_event(store.dir, "invoice_created", invoice_id=invoice.invoice_id,
                 job_ref=invoice.job_ref, seller_id=invoice.seller_id,
                 amount_usdc=invoice.amount_usdc,
                 relay_request_id=invoice.relay_request_id)
    return invoice
