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

- `clearo/invoices.py` is the invoice engine described above.

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
