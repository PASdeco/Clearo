#!/usr/bin/env python3
"""Relay chains health check. No API key needed.
GET https://api.relay.link/chains
Prints a plain summary and saves a JSON snapshot if --save is passed.
"""
import json, sys, urllib.request
from datetime import datetime, timezone

URL = "https://api.relay.link/chains"

def main():
    save = "--save" in sys.argv
    with urllib.request.urlopen(URL, timeout=20) as r:
        data = json.load(r)
    chains = data.get("chains", [])
    disabled = [c["name"] for c in chains if c.get("disabled")]
    lagging = [c["name"] for c in chains if c.get("blockProductionLagging")]
    no_deposit = [c["name"] for c in chains if not c.get("depositEnabled")]
    print(f"chains_total: {len(chains)}")
    print(f"disabled: {len(disabled)} {disabled if disabled else ''}")
    print(f"block_production_lagging: {len(lagging)} {lagging if lagging else ''}")
    print(f"deposit_disabled: {len(no_deposit)} {no_deposit if no_deposit else ''}")
    if save:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = f"data/chains-{ts}.json"
        with open(path, "w") as f:
            json.dump({"checked_at_utc": ts, "count": len(chains),
                       "disabled": disabled, "lagging": lagging,
                       "deposit_disabled": no_deposit,
                       "names": [c["name"] for c in chains]}, f, indent=2)
        print(f"saved: {path}")

if __name__ == "__main__":
    main()
