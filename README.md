# Clearo

Clearo is settlement infrastructure for AI agent commerce, built on Relay.

A seller agent issues an invoice. A buyer agent pays in USDC from any supported chain. Relay moves the payment across chains, the seller receives USDC on its own chain, and the seller agent is notified when the payment is final so it can release the order.

Website: https://getclearo.netlify.app

## Product facts

- Non-custodial: Clearo never holds buyer or seller funds.
- Fee: 0.25% per settlement, shown on the invoice before payment.
- Minimum invoice: 12 USDC.
- Launch settlement: USDC on Base and BNB Chain.
- One invoice uses one deposit address. A refund address is required before payment.

## Repository layout

- `website/` contains the public product website.
- `integration/` contains the Relay integration starter code.
- `brand/` contains the Clearo symbol, lockups and wordmark in SVG form.

## Status

The product website is live. The Relay integration is in setup: the Clearo Relay App and API access come before the first live settlement proof.
