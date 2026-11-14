"""Clearo seller quickstart: the whole integration, in one file.

This is what an outside seller copies. It talks to a running Clearo
service over plain HTTP, standard library only, no Clearo internals.

    export CLEARO_API_BASE=http://localhost:8080
    export CLEARO_SELLER_TOKEN=<the token Clearo issued this seller>

    python seller_quickstart.py create --job-ref job-123 --amount 12.50 \
        --buyer-refund-address 0xBuyerRefund... --pay-from-chain 56
    python seller_quickstart.py status --id CLR-20261114-XXXXXX

Creating an invoice returns the payment instructions to hand to the
buyer. Poll the status; when it reads "success" the payment is final and
the seller delivers. Only "success" and "refund" are final states.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

API_BASE = os.environ.get("CLEARO_API_BASE", "http://localhost:8080").rstrip("/")
TOKEN = os.environ.get("CLEARO_SELLER_TOKEN", "")
SELLER = {
    "id": os.environ.get("CLEARO_SELLER_ID", "my-seller"),
    "name": os.environ.get("CLEARO_SELLER_NAME", "My Seller"),
    "wallet": os.environ.get("CLEARO_SELLER_WALLET", ""),
    "receive_chain_id": int(os.environ.get("CLEARO_SELLER_RECEIVE_CHAIN", "8453")),
}


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API_BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json",
                                          "X-Clearo-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def create_invoice(job_ref: str, amount_usdc: str, buyer_refund_address: str,
                   pay_from_chain_id: int, buyer_id: str | None = None) -> dict:
    return call("POST", "/invoices", {
        "seller": SELLER, "job_ref": job_ref, "amount_usdc": amount_usdc,
        "buyer_refund_address": buyer_refund_address,
        "pay_from_chain_id": pay_from_chain_id, "buyer_id": buyer_id})


def get_invoice(invoice_id: str) -> dict:
    return call("GET", f"/invoices/{invoice_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clearo seller quickstart")
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("create")
    c.add_argument("--job-ref", required=True)
    c.add_argument("--amount", required=True)
    c.add_argument("--buyer-refund-address", required=True)
    c.add_argument("--pay-from-chain", type=int, required=True)
    c.add_argument("--buyer-id")
    s = sub.add_parser("status")
    s.add_argument("--id", required=True)
    args = parser.parse_args()
    if args.command == "create":
        result = create_invoice(args.job_ref, args.amount, args.buyer_refund_address,
                                args.pay_from_chain, args.buyer_id)
    else:
        result = get_invoice(args.id)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
