"""Clearo settlement service.

Clearo issues invoices for agent-to-agent work, routes the payment through
Relay, watches it to finality, verifies the fee, and only then signals the
seller to deliver. Clearo is non-custodial: it never holds funds or keys.
"""

__version__ = "0.1.0"
