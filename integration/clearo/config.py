"""Clearo service configuration.

Every value comes from the environment. The Relay API key is server-side
only: it is read from RELAY_API_KEY, never stored in this repository, and
never logged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    relay_api_base: str = "https://api.relay.link"
    relay_api_key: str | None = None
    fee_bps: int = 25
    fee_recipient: str | None = None
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        fee_bps_raw = os.environ.get("CLEARO_FEE_BPS", "25")
        try:
            fee_bps = int(fee_bps_raw)
        except ValueError as exc:
            raise ConfigError(f"CLEARO_FEE_BPS must be an integer, got {fee_bps_raw!r}") from exc
        if not 0 < fee_bps <= 1000:
            raise ConfigError("CLEARO_FEE_BPS must be between 1 and 1000 basis points")
        return cls(
            relay_api_base=os.environ.get("RELAY_API_BASE", "https://api.relay.link").rstrip("/"),
            relay_api_key=os.environ.get("RELAY_API_KEY") or None,
            fee_bps=fee_bps,
            fee_recipient=os.environ.get("CLEARO_FEE_RECIPIENT") or None,
            log_level=os.environ.get("CLEARO_LOG_LEVEL", "INFO").upper(),
        )

    def require_quote_ready(self) -> None:
        missing = []
        if not self.relay_api_key:
            missing.append("RELAY_API_KEY")
        if not self.fee_recipient:
            missing.append("CLEARO_FEE_RECIPIENT")
        if missing:
            raise ConfigError("Missing required configuration: " + ", ".join(missing))

    def public_summary(self) -> dict:
        """Configuration summary safe to print: no secrets, ever."""
        return {
            "relay_api_base": self.relay_api_base,
            "relay_api_key_set": bool(self.relay_api_key),
            "fee_bps": self.fee_bps,
            "fee_recipient_set": bool(self.fee_recipient),
            "log_level": self.log_level,
        }
