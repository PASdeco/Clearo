"""Clearo service entry point.

Phase A scope: start cleanly, report configuration without secrets, confirm
the Relay connection, and pull a quote through Clearo's own client code.
Later phases add the invoice engine, the watcher and fee verification.

Usage:
    python -m clearo.service health
    python -m clearo.service chains
    python -m clearo.service quote --amount 0.50 --user 0x... --recipient 0x...
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys

from . import __version__
from .config import Config, ConfigError
from .relay_client import RelayClient, RelayError

# USDC contracts for the chains Clearo launches on.
USDC = {
    8453: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",   # Base
    42161: "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",  # Arbitrum
    56: "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",     # BNB Chain
}


def build_client(config: Config, transport=None) -> RelayClient:
    return RelayClient(config.relay_api_key, config.relay_api_base, transport=transport)


def to_base_units(amount_usdc: str) -> str:
    value = float(amount_usdc)
    if value <= 0:
        raise ValueError("amount must be greater than zero")
    return str(int(round(value * 1_000_000)))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="clearo", description="Clearo settlement service")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health", help="print version and configuration summary")
    sub.add_parser("chains", help="list the chains Relay currently supports (count only)")
    quote_p = sub.add_parser("quote", help="pull a quote through the Clearo client (spends nothing)")
    quote_p.add_argument("--amount", required=True, help="amount in USDC, e.g. 0.50")
    quote_p.add_argument("--user", required=True)
    quote_p.add_argument("--recipient", required=True)
    quote_p.add_argument("--from-chain", type=int, default=8453)
    quote_p.add_argument("--to-chain", type=int, default=42161)
    inv = sub.add_parser("invoice", help="invoice engine commands")
    inv_sub = inv.add_subparsers(dest="invoice_command", required=True)
    create_p = inv_sub.add_parser("create", help="create an invoice and its deposit address")
    create_p.add_argument("--seller-id", required=True)
    create_p.add_argument("--seller-name", required=True)
    create_p.add_argument("--seller-wallet", required=True)
    create_p.add_argument("--receive-chain", type=int, required=True)
    create_p.add_argument("--amount", required=True, help="exact USDC the seller receives")
    create_p.add_argument("--job-ref", required=True)
    create_p.add_argument("--refund-address", required=True,
                          help="buyer refund address on the origin chain (required)")
    create_p.add_argument("--pay-from-chain", type=int, required=True)
    create_p.add_argument("--buyer-id")
    create_p.add_argument("--payer-address")
    show_p = inv_sub.add_parser("show", help="show an invoice's payment instructions")
    show_p.add_argument("--id", required=True)
    watch_p = sub.add_parser("watch", help="poll Relay once for every open invoice")
    sub.add_parser("serve", help="run the webhook and status HTTP server").add_argument(
        "--port", type=int, default=8080)
    args = parser.parse_args(argv)

    try:
        config = Config.from_env()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(level=config.log_level,
                        format="%(asctime)s %(levelname)s clearo %(message)s")
    client = build_client(config)

    if args.command == "serve":
        from .invoices import InvoiceStore
        from .server import serve
        serve(InvoiceStore(os.environ.get("CLEARO_DATA_DIR", "data")), args.port)
        return 0
    if args.command == "watch":
        from .invoices import InvoiceStore
        from .watcher import poll_all
        results = poll_all(client, InvoiceStore(os.environ.get("CLEARO_DATA_DIR", "data")))
        print(json.dumps(results, indent=2))
        return 0

    try:
        if args.command == "health":
            print(json.dumps({"service": "clearo", "version": __version__,
                              "config": config.public_summary()}, indent=2))
            return 0
        if args.command == "chains":
            chains = client.get_chains()
            print(json.dumps({"chains_supported": len(chains)}))
            return 0
        if args.command == "quote":
            config.require_quote_ready()
            quote = client.create_quote(
                user=args.user, recipient=args.recipient,
                origin_chain_id=args.from_chain, destination_chain_id=args.to_chain,
                origin_currency=USDC[args.from_chain],
                destination_currency=USDC[args.to_chain],
                amount=to_base_units(args.amount),
                fee_recipient=config.fee_recipient, fee_bps=config.fee_bps)
            fees = quote.get("fees", {})
            print(json.dumps({
                "request_id": quote.get("requestId"),
                "app_fee_usdc": (fees.get("app") or {}).get("amountFormatted"),
                "relayer_fee_usdc": (fees.get("relayer") or {}).get("amountFormatted"),
                "amount_out_usdc": (quote.get("details", {}).get("currencyOut") or {}).get("amountFormatted"),
            }, indent=2))
            return 0
        if args.command == "invoice":
            from .invoices import InvoiceStore, create_invoice, InvoiceError
            store = InvoiceStore(os.environ.get("CLEARO_DATA_DIR", "data"))
            if args.invoice_command == "create":
                invoice = create_invoice(
                    client, config, store,
                    seller_id=args.seller_id, seller_name=args.seller_name,
                    seller_wallet=args.seller_wallet,
                    receive_chain_id=args.receive_chain, amount_usdc=args.amount,
                    job_ref=args.job_ref, refund_address=args.refund_address,
                    pay_from_chain_id=args.pay_from_chain, buyer_id=args.buyer_id,
                    payer_address=args.payer_address)
                print(invoice.instructions_text())
                print()
                print(json.dumps({"invoice_id": invoice.invoice_id,
                                  "status": invoice.status,
                                  "relay_request_id": invoice.relay_request_id}, indent=2))
                return 0
            invoice = store.get(args.id)
            print(json.dumps(invoice.payment_instructions(), indent=2))
            return 0
    except (ConfigError, RelayError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
