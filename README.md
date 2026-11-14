# Clearo

**Settle agent payments across any chain.**

Clearo is settlement infrastructure for agent-to-agent commerce, built on [Relay](https://relay.link). A seller agent issues an invoice. A buyer agent pays in USDC from the chain where its funds sit. Relay moves and converts the payment, the seller receives USDC on its own chain, and the moment the payment is final the seller agent is notified and can release delivery.

- Website: https://clearo.pxxlspace.cv
- Seller API: https://clearo-i0gr.onrender.com
- Seller guide: [integration/SELLER_GUIDE.md](integration/SELLER_GUIDE.md)

## How it works

1. **Invoice.** The seller creates an invoice through the Clearo API. Clearo returns machine-readable payment instructions: the exact token contract, the exact chain, the exact amount, and a one-time deposit address generated for that invoice alone.
2. **Pay.** The buyer checks the invoice against the agreed job and pays with a plain transfer from its own wallet. No wallet connection to Clearo, and no keys are shared at any point.
3. **Move.** Relay detects the deposit and fills on the seller's chain. The seller receives USDC on the chain it chose.
4. **Release.** When Relay reports the payment final, Clearo verifies the fee against the quote and signals the seller to deliver. Only a final `success` counts as settled.

Clearo is non-custodial. It never holds funds and never holds private keys: the buyer pays Relay's deposit address, Relay delivers directly to the seller's wallet, and Clearo keeps the record.

## For sellers

Selling through Clearo takes two touches, covered in the [seller guide](integration/SELLER_GUIDE.md):

- Create an invoice with `POST /invoices`, authenticated with your seller token, and hand the payment instructions to the buyer exactly as issued.
- Deliver when `GET /invoices/<id>` reports `success`. Only `success` and `refund` are final; every other status means the payment is still in flight.

The whole integration is one copyable file: [integration/examples/seller_quickstart.py](integration/examples/seller_quickstart.py). A seller token is issued per seller; ask the operator for yours.

## Pricing

- Clearo fee: **0.25% (25 bps)** per settlement, printed on the invoice before payment.
- No subscription, no minimum invoice amount, no custody fees.
- Relay's network cost is quoted separately on every invoice, so the quoted and actual fee can be checked line by line after settlement.

## Rules that protect both sides

- One invoice, one job, one deposit address. A deposit address is never reused.
- A buyer refund address is required before payment instructions are issued. If a payment cannot complete in a refundable way, Relay returns it to that address automatically, minus gas.
- Pay the exact token, on the exact chain, to the exact address on the invoice. A deposit in the wrong token may be unrecoverable.
- Invoices expire 24 hours after they are issued.

## Repository layout

- `website/` — the public product website.
- `integration/` — the Clearo service (Python, standard library only), the seller guide, and the seller quickstart example.
- `brand/` — the Clearo symbol, lockups, and wordmark in SVG.
- `render.yaml` — the deployment blueprint for the hosted service.

## Status

Clearo is live. The service is deployed and reachable at the seller API address above, settlement webhooks are registered with Relay, and the first settlements have completed end to end with fees verified against Relay's records to the digit. The public API runs on a free hosting tier and may take up to a minute to answer after an idle period.

Settlement currency at launch is USDC, with sellers receiving on Base or BNB Chain.

---

Built on Relay. Clearo is operated independently of Relay.
