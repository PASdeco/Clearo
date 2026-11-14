# Clearo integration

Code that connects a product to Clearo and Relay.

## The Clearo service (`clearo/`)

The settlement service itself, in Python (standard library only):

- `clearo/config.py` reads configuration from the environment. The Relay
  API key comes from `RELAY_API_KEY` and stays server-side; the service fee
  defaults to 25 bps (`CLEARO_FEE_BPS`) and the fee recipient is set with
  `CLEARO_FEE_RECIPIENT`.
- `clearo/relay_client.py` is a thin Relay API client (chains and quotes in
  this phase) with an injectable transport for testing.
- `clearo/service.py` is the entry point:
  - `python -m clearo.service health` prints version and a secret-free
    configuration summary.
  - `python -m clearo.service chains` reports how many chains Relay
    currently supports.
  - `python -m clearo.service quote --amount 0.50 --user 0x... --recipient 0x...`
    pulls a live quote through the service's own client. A quote spends
    nothing and signs nothing.
  - `python -m clearo.service invoice create --seller-id ... --seller-name ... --seller-wallet 0x... --receive-chain 8453 --amount 0.50 --job-ref ... --refund-address 0x... --pay-from-chain 56`
    creates an invoice: Clearo requests a strict, one-time deposit address
    from Relay (exact output, refund and recovery addresses set), stores the
    invoice under `CLEARO_DATA_DIR`, and prints the payment instructions.
    The buyer's refund address is required; without it no instructions are
    issued. Sellers receive on Base or BNB Chain at launch.
  - `python -m clearo.service invoice show --id CLR-...` prints an
    invoice's machine-readable payment instructions: exact token contract,
    exact chain, exact amount to send, the deposit address, expiry, and the
    payer warnings (wrong token, one-time address, blocked platforms).

- `clearo/invoices.py` is the invoice engine described above. Invoices
  carry an amount mode: `exact_output` (the seller receives the exact
  invoice amount; the buyer sends the computed input) by default, or
  `exact_input` (the buyer sends the exact invoice amount; the seller
  receives the market fill, quoted as an estimate). Some routes only
  support deposit addresses in one mode, so the mode is chosen per route
  and printed on the invoice.
- `examples/seller_quickstart.py` is the seller integration as one
  copyable file (plain HTTP, no Clearo internals), and `SELLER_GUIDE.md`
  is the seller-facing guide. Sellers run both themselves.
- `POST /invoices` on the HTTP surface lets a plugged-in seller create an
  invoice over HTTP, authenticated per seller with `CLEARO_SELLER_TOKENS`
  (a JSON map of seller id to token, sent as the `X-Clearo-Token` header).
- `python -m clearo.service watch` polls Relay once for every open invoice
  and applies any status change. `python -m clearo.service serve --port 8080`
  runs the HTTP surface: `POST /webhooks/relay` for Relay webhooks,
  `GET /invoices/<id>` for an invoice's status and instructions, and
  `GET /health`.

## Watching settlements (`clearo/status.py`, `clearo/webhooks.py`, `clearo/watcher.py`)

- Relay statuses: waiting, depositing, pending, submitted, success,
  failure, refund. Only success and refund are final. Failure is not final:
  the invoice stays open and watched. Status never moves backwards and a
  final status is never overwritten.
- Webhooks are verified with HMAC-SHA256 over "<timestamp>.<body>" against
  every active App key (key rotation safe) before they are believed.
  Unsigned or tampered deliveries are rejected with 401.
- Events are matched to invoices by deposit address first and request ID
  second, because Relay may regenerate the request ID that owns a fill.
- Polling (`GET /intents/status/v3`) runs as backup to webhooks, with the
  same transition rules. Invoices that pass their 24 hour expiry unpaid are
  closed as expired by the watcher.

## Fee verification and the ledger (`clearo/verification.py`, `clearo/ledger.py`)

- `python -m clearo.service verify --id CLR-...` checks one final invoice's
  app fee against Relay's record on `GET /requests/v3`: quoted against
  actual, compared as exact decimals. Outcomes: match, not_collected (a
  quoted fee at or under $0.025 that Relay did not collect; informational),
  mismatch (flagged in the ledger the same day), unavailable (no Relay
  record yet; nothing is claimed).
- `python -m clearo.service reconcile` verifies every final invoice and
  totals the accrual book: the sum of actual fees across verified records,
  the figure a Relay fee balance must agree with before any claim.
- Every real event (invoice created, status change, fee verified, fee
  mismatch) is appended to `settlement-ledger.jsonl` in the data directory.
  The ledger is append-only and is the book published numbers must match.

## Plugging in a seller (`clearo/seller.py`)

A seller plugs in with two automatic touches: when it agrees a job it
calls the bridge and Clearo issues the invoice; when Clearo reports the
payment final, the bridge writes a delivery release for that job, exactly
once, and only on success. A refunded or unpaid invoice releases nothing.
Buyers never plug in: they receive payment instructions and pay from their
own wallet.

- `python -m clearo.service seller invoice --job-ref ... --amount 0.50 --buyer-refund-address 0x... --pay-from-chain 56`
  issues an invoice under the seller profile (`CLEARO_SELLER_ID`,
  `CLEARO_SELLER_NAME`, `CLEARO_SELLER_WALLET`, `CLEARO_SELLER_RECEIVE_CHAIN`).
- `python -m clearo.service seller release-check` releases delivery for
  every final-paid invoice of that seller. The webhook server also runs a
  release pass after each verified event.
- Releases are written to `deliveries.jsonl` in the data directory for the
  seller's own runner to act on, and recorded in the settlement ledger.

Run it with `pip install .` from this folder (provides the `clearo`
command), or directly with `PYTHONPATH=. python -m clearo.service ...`.

## Quote body example (`quote-request.json`)

The reference request body for `POST /quote/v2` with the Clearo app fee
attached and a one-time deposit address requested. `relay-client.mjs` shows
the same call from JavaScript for integrators who work in Node.

Rules that apply to every integration:

- Relay API keys are server-side only, sent in the `x-api-key` header, and
  never shipped to a browser or a mobile app.
- Invoices always set a buyer refund address and a recovery address before
  payment instructions are issued.
- Only a final `success` status from Relay counts as settled.

## Deployment

The service deploys from the `render.yaml` blueprint at the repository
root (Render, Python runtime, root directory `integration`). The start
command is `clearo serve --port $PORT`; the health check is
`GET /health`. Configuration is environment only:

- `RELAY_API_KEY` (secret): the Relay app key, used for quotes, status
  and request records, and as the webhook signing key fallback.
- `RELAY_WEBHOOK_KEYS` (secret, optional): comma separated signing keys
  during Relay key rotation.
- `CLEARO_FEE_BPS`, `CLEARO_FEE_RECIPIENT`, `CLEARO_RECOVERY_ADDRESS`:
  the app fee and the addresses it settles to.
- `CLEARO_DATA_DIR`: the invoice store and settlement ledger directory.
- `CLEARO_SELLER_TOKENS` (secret, optional): JSON map of seller id to
  access token for the self-serve `POST /invoices` surface.

After deployment, register the public webhook endpoint
(`https://<service-host>/webhooks/relay`) in the Relay app settings so
settlement events arrive as signed webhooks; polling remains the backup.
