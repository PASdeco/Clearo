"""Relay request statuses, in Clearo's plain words (spec section 5).

waiting, depositing, pending, submitted, success, failure, refund.
Only success and refund are final. Failure is NOT final: a failed fill can
retry or move to refund, so an invoice in failure stays open and watched.
Status never moves backwards, and a final status is never overwritten.
"""
from __future__ import annotations

ORDER = ["waiting", "depositing", "pending", "submitted", "success"]
KNOWN = set(ORDER) | {"failure", "refund"}
FINAL = {"success", "refund"}


def is_final(status: str) -> bool:
    return status in FINAL


def can_transition(current: str, new: str) -> bool:
    """Whether an invoice in `current` may move to `new`.

    Rules: final states are sticky; failure may be reported from any open
    state and an invoice may leave failure back into the forward flow or to
    refund; otherwise movement is forward-only along ORDER. Unknown Relay
    statuses never change an invoice."""
    if new not in KNOWN:
        return False
    if current in FINAL:
        return False
    if new == current:
        return False
    if new == "refund":
        return True
    if current == "failure":
        return new in ORDER or new == "refund"
    if new == "failure":
        return True
    if current == "expired":
        return False
    return ORDER.index(new) > ORDER.index(current)
