"""Thin client for the Relay API.

The client takes an injectable transport so it can be tested without network
access and so different runtimes can supply the API key in their own way.
The default transport sends the key in the x-api-key header, as Relay
requires. Keys and headers are never logged or included in error messages.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Optional

# A transport takes (method, url, headers, body_bytes) and returns
# (status_code, parsed_json).
Transport = Callable[[str, str, dict, Optional[bytes]], tuple[int, dict]]


class RelayError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"Relay API error (HTTP {status}): {message}")
        self.status = status


def urllib_transport(method: str, url: str, headers: dict, body: Optional[bytes]) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError:
            parsed = {"message": raw[:300]}
        return exc.code, parsed


class RelayClient:
    def __init__(self, api_key: str | None, base_url: str = "https://api.relay.link",
                 transport: Transport | None = None):
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._transport = transport or urllib_transport

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["x-api-key"] = self._api_key
        payload = json.dumps(body).encode() if body is not None else None
        status, data = self._transport(method, self._base + path, headers, payload)
        if status >= 400:
            message = data.get("message") or data.get("error") or "unknown error"
            raise RelayError(status, str(message)[:300])
        return data

    def get_chains(self) -> list:
        return self._call("GET", "/chains").get("chains", [])

    def get_request_record(self, request_id: str) -> dict:
        """The verification record for one request: GET /requests/v3."""
        return self._call("GET", f"/requests/v3?requestId={request_id}")

    def get_intent_status(self, request_id: str) -> dict:
        """Current status of one request: GET /intents/status/v3."""
        return self._call("GET", f"/intents/status/v3?requestId={request_id}")

    def create_quote(self, *, user: str, recipient: str, origin_chain_id: int,
                     destination_chain_id: int, origin_currency: str,
                     destination_currency: str, amount: str, fee_recipient: str,
                     fee_bps: int, use_deposit_address: bool = False,
                     trade_type: str = "EXACT_INPUT", strict: bool = False,
                     refund_to: str | None = None,
                     recovery_address: str | None = None) -> dict:
        body = {
            "user": user,
            "recipient": recipient,
            "originChainId": origin_chain_id,
            "destinationChainId": destination_chain_id,
            "originCurrency": origin_currency,
            "destinationCurrency": destination_currency,
            "amount": amount,
            "tradeType": trade_type,
            "appFees": [{"recipient": fee_recipient, "fee": str(fee_bps)}],
            "useDepositAddress": use_deposit_address,
        }
        if use_deposit_address:
            body["strict"] = strict
            if refund_to:
                body["refundTo"] = refund_to
            if recovery_address:
                body["recoveryAddress"] = recovery_address
        return self._call("POST", "/quote/v2", body)
