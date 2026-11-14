#!/usr/bin/env python3
"""Relay quote/v2 template. DOES NOT execute anything.
Requires RELAY_API_KEY and RELAY_APP_FEE_RECIPIENT in the environment.
Verified 2026-11-12 from Relay docs:
- POST /quote/v2 requires x-api-key on every request since 2026-10-02.
- App fees are in bps of the input amount, recipient must be an EVM address.
- App fees accrue off chain in USDC and are claimed later, not paid in real time.
- Verify collection with GET /requests/v3 (x-api-key required) and
  GET /app-fees/{wallet}/balances. Note: /requests/v2 retires 2026-11-24.
This file only builds and prints the request body. Sending is a separate,
explicit step we will add after the key exists and we agree the test route.
"""
import os, sys, json

def build_quote(user, recipient, origin_chain, dest_chain,
                origin_currency, dest_currency, amount):
    fee_bps = os.environ.get("RELAY_APP_FEE_BPS", "25")
    fee_recipient = os.environ.get("RELAY_APP_FEE_RECIPIENT", "")
    if not fee_recipient:
        raise SystemExit("RELAY_APP_FEE_RECIPIENT is not set. Stop.")
    return {
        "user": user,
        "recipient": recipient,
        "originChainId": origin_chain,
        "destinationChainId": dest_chain,
        "originCurrency": origin_currency,
        "destinationCurrency": dest_currency,
        "amount": str(amount),
        "tradeType": "EXACT_INPUT",
        "appFees": [{"recipient": fee_recipient, "fee": str(fee_bps)}],
        # Set True only for the payment link flow where the payer
        # sends a plain transfer to a deposit address.
        "useDepositAddress": False,
    }

if __name__ == "__main__":
    if not os.environ.get("RELAY_API_KEY"):
        raise SystemExit("RELAY_API_KEY is not set. Create the App in the Relay Dashboard first, then store the key securely. Do not paste it in chat.")
    print("Template ready. No request sent. Wire a real test route only after Phase 0 is complete.")
