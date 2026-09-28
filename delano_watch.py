#!/usr/bin/env python3
"""
Delano Original Gamer restock watcher.

Setup (once):
    pip install playwright requests
    playwright install chromium
    Install the ntfy app on your phone and subscribe to NTFY_TOPIC below.

Run:
    python delano_watch.py --debug   # first run: prints what it sees per size
    python delano_watch.py           # normal run, alerts only on a change

Schedule (Mac/Linux, every 15 min):  crontab -e
    */15 * * * * /usr/bin/python3 /path/to/delano_watch.py >> /tmp/delano.log 2>&1
"""
import argparse
import json
import pathlib
import re

import requests
from playwright.sync_api import sync_playwright

URL = "https://www.delanobats.com/original-gamer"
WATCH = ['31"', '32"']                        # sizes you care about
NTFY_TOPIC = "delano-restock-CHANGE-ME-8472"  # make this unguessable
STATE = pathlib.Path(__file__).with_name("delano_state.json")
SOLD_OUT = re.compile(r"sold\s*out|out\s*of\s*stock|unavailable|notify", re.I)


def check(debug=False):
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("button[aria-label^='Size ']", timeout=45000)
        body = page.inner_text("body")
        results["tbd_banner"] = bool(re.search(r"restock dates are TBD", body, re.I))

        for size in WATCH:
            btn = page.locator(f'button[aria-label^=\'Size {size}\']').first
            if btn.count() == 0:
                results[size] = False
                if debug:
                    print(f"{size}: size button not found")
                continue

            label = btn.get_attribute("aria-label") or ""
            disabled = btn.is_disabled()
            in_stock = not disabled and not SOLD_OUT.search(label)
            results[size] = in_stock
            if debug:
                print(f"{size}: label='{label}' disabled={disabled} -> in_stock={in_stock}")

        browser.close()
    return results


def notify(msg):
    requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=msg.encode(),
                  headers={"Title": "Delano restock", "Click": URL, "Priority": "high"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--test", action="store_true", help="just send a test push")
    ap.add_argument("--simulate", action="store_true",
                    help="pretend 31\" restocked to test the full alert path")
    args = ap.parse_args()

    if args.test:
        notify("Test alert from delano_watch.py. Notifications are working.")
        print("Test push sent.")
        return

    try:
        now = check(args.debug)
    except Exception as e:
        print("Check failed, skipping this run:", str(e).splitlines()[0])
        return
    prev = json.loads(STATE.read_text()) if STATE.exists() else {}

    if args.simulate:
        now[WATCH[0]] = True
        prev[WATCH[0]] = False

    alerts = [f'{s} is back in stock' for s in WATCH if now.get(s) and not prev.get(s)]
    if prev.get("tbd_banner") and not now["tbd_banner"]:
        alerts.append('"Restock dates are TBD" note was removed from the page')

    if alerts:
        notify("\n".join(alerts))
    print(now, "| alerts:", alerts or "none")
    if not args.simulate:
        STATE.write_text(json.dumps(now))


if __name__ == "__main__":
    main()
