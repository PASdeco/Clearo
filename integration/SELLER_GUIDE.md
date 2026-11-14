# Selling through Clearo: the seller guide

Clearo settles your sales across chains. You agree a job with a buyer,
Clearo issues the invoice, the buyer pays from whatever chain its money
sits on, and Clearo tells you the moment the payment is final on your
chain. Then you deliver. Clearo never holds your money or your keys.

## The two touches

There are only two integration points, and `examples/seller_quickstart.py`
in this folder is the whole thing as working code:

1. **Job agreed -> create an invoice.** `POST /invoices` with your seller
   profile, the job reference, the exact USDC amount, the buyer's refund
   address (required, on the chain the buyer pays from), and the chain the
   buyer pays from. Clearo returns the payment instructions: exact token
   contract, exact chain, exact amount to send, and a one-time deposit
   address. Hand those to the buyer exactly as issued.
2. **Payment final -> deliver.** Read `GET /invoices/<id>`, or receive the
   status from your own watcher. Deliver only when the status is
   `success`. Statuses: waiting, depositing, pending, submitted, success,
   failure, refund. Only `success` and `refund` are final. `failure` means
   still in flight, never "lost", and never a reason to deliver.

## Your profile and token

Your seller profile is yours: your seller id, display name, receiving
wallet, and the chain you receive USDC on (Base or BNB Chain at launch).
Clearo issues each seller a token; send it as the `X-Clearo-Token` header
when creating invoices. A token only creates invoices under its own
seller id. Your wallet keys never leave your system: buyers pay Relay's
deposit address, and Relay delivers to your wallet directly.

## The rules that protect you

- One invoice, one job, one deposit address. Never reuse an address.
- The buyer must state a refund address before instructions are issued.
  If a payment cannot complete, Relay returns it there automatically,
  minus gas.
- Clearo's fee is 25 bps of the invoice amount, printed on the invoice
  itself. No hidden charges, no minimum invoice.
- Check the invoice before delivering: amount and job reference are in
  the invoice record, and only a `success` status settles.

## Going live

Run the quickstart against your Clearo endpoint, issue a first invoice
for a small amount, pay it from a second wallet you control, and watch it
settle end to end. That dry run is the whole onboarding.
