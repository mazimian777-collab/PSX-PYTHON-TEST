"""
TEST MODE - PSX Historical Data ko GitHub Actions se fetch kar ke
Cloudflare Worker ke naye /pushhistorical endpoint par POST karta hai.

Maqsad: sirf 3 companies (MARI, SAZEW, MEBL) par yeh naya bridge test karna -
poori 100 companies par abhi NAHI chalana. Yeh script:

- Sirf GitHub Actions ke apne "workflow_dispatch" (manual button) se chalti hai.
- Existing Historical Import Queue, Cloudflare Worker ke baaki kisi bhi
  function/feature ko CHHOOTI NAHI - sirf naye /pushhistorical endpoint ko
  ek normal HTTP client ki tarah call karti hai.
- Shared secret kabhi print/log NAHI karti - sirf ek GitHub Actions Secret
  (environment variable) se padhti hai.

IMPORTANT (aap ne yeh 2 cheezein set karni hain, is script mein koi secret
khud se nahi likha gaya):
  1. Neeche PSX_WORKER_BASE_URL ko apne Cloudflare Worker ke asal URL se
     replace karein PSX_WORKER_BASE_URL = "https://psxai-bot.mazimian777.workers.dev"
     Yeh URL koi secret nahi hai (sirf domain hai), is liye seedha yahan
     likha ja sakta hai.
  2. GitHub repo mein Settings -> Secrets and variables -> Actions -> naya
     secret bana kar naam "PUSH_HISTORICAL_SECRET" rakhein aur value woh
     rakhein jo aap Cloudflare Worker Secret "PUSH_HISTORICAL_SECRET" mein
     bhi set karenge (dono taraf EXACT same value honi chahiye).
"""

import os
import sys
import time

try:
    import requests
except ImportError:
    print("FATAL: 'requests' library install nahi hai. Workflow file mein "
          "'pip install requests' step check karein.")
    sys.exit(1)

# ---- Step 1: Yahan apna asal Cloudflare Worker URL likhein (secret nahi hai) ----
PSX_WORKER_BASE_URL = "https://REPLACE-WITH-YOUR-WORKER-URL.workers.dev"

TEST_SYMBOLS = ["MARI", "SAZEW", "MEBL"]
TIMEOUT_SECONDS = 20
DELAY_BETWEEN_SYMBOLS_SECONDS = 5


def fetch_psx_history(symbol):
    """PSX se raw historical data fetch karta hai. Koi KV/Worker code yahan nahi hai -
    yeh bilkul wahi seedha GET request hai jo pehle wale isolated test mein kaamyab hua tha."""
    url = "https://dps.psx.com.pk/timeseries/eod/" + symbol
    response = requests.get(url, timeout=TIMEOUT_SECONDS)
    return response


def push_to_worker(symbol, rows, secret):
    """Naye /pushhistorical endpoint ko POST karta hai. 'secret' kabhi print nahi hota."""
    push_url = PSX_WORKER_BASE_URL.rstrip("/") + "/pushhistorical"
    payload = {
        "symbol": symbol,
        "data": rows,
        "secret": secret,
    }
    response = requests.post(push_url, json=payload, timeout=TIMEOUT_SECONDS)
    return response


def run_test_for_symbol(symbol, secret):
    print("=" * 60)
    print("PSX -> /pushhistorical TEST MODE")
    print("Symbol: " + symbol)
    print("-" * 60)

    # Step A: PSX se data fetch karein
    try:
        psx_resp = fetch_psx_history(symbol)
    except requests.exceptions.Timeout:
        print("RESULT: FAIL - PSX se data lete waqt Timeout ho gaya.")
        return False
    except requests.exceptions.RequestException as err:
        print("RESULT: FAIL - PSX se data lete waqt error: " + type(err).__name__)
        return False

    print("PSX Fetch - HTTP Status: " + str(psx_resp.status_code))

    if psx_resp.status_code != 200:
        print("RESULT: FAIL - PSX ne HTTP " + str(psx_resp.status_code) + " diya, isliye push nahi kiya jaa sakta.")
        return False

    try:
        data = psx_resp.json()
    except ValueError:
        print("RESULT: FAIL - PSX ka response valid JSON nahi tha.")
        return False

    rows = None
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        rows = data["data"]
    elif isinstance(data, list):
        rows = data

    if not rows:
        print("RESULT: FAIL - PSX response mein 'data' rows nahi milin.")
        return False

    print("PSX se " + str(len(rows)) + " historical rows mile.")

    # Step B: /pushhistorical endpoint ko POST karein
    try:
        push_resp = push_to_worker(symbol, rows, secret)
    except requests.exceptions.Timeout:
        print("RESULT: FAIL - Worker ko POST karte waqt Timeout ho gaya.")
        return False
    except requests.exceptions.RequestException as err:
        print("RESULT: FAIL - Worker ko POST karte waqt error: " + type(err).__name__)
        return False

    print("Worker Push - HTTP Status: " + str(push_resp.status_code))

    try:
        push_body = push_resp.json()
    except ValueError:
        push_body = None

    if push_resp.status_code == 200 and push_body and push_body.get("success"):
        print("RESULT: KAAMYABI - " + symbol + " ka data Worker mein save ho gaya (" +
              str(push_body.get("days")) + " din).")
        return True
    else:
        error_text = push_body.get("error") if push_body else push_resp.text[:300]
        print("RESULT: FAIL - Worker ne mana kar diya. Wajah: " + str(error_text))
        return False


def run_test():
    secret = os.environ.get("PUSH_HISTORICAL_SECRET")
    if not secret:
        print("FATAL: PUSH_HISTORICAL_SECRET environment variable set nahi hai. "
              "GitHub Actions Secret 'PUSH_HISTORICAL_SECRET' workflow mein pass ho raha hai ya nahi, check karein.")
        sys.exit(1)

    if "REPLACE-WITH-YOUR-WORKER-URL" in PSX_WORKER_BASE_URL:
        print("FATAL: PSX_WORKER_BASE_URL abhi tak placeholder hai. Script ke upar "
              "wali line mein apna asal Cloudflare Worker URL likhein.")
        sys.exit(1)

    results = {}
    for i, symbol in enumerate(TEST_SYMBOLS):
        if i > 0:
            print("\n")
            time.sleep(DELAY_BETWEEN_SYMBOLS_SECONDS)
        results[symbol] = run_test_for_symbol(symbol, secret)

    print("\n" + "=" * 60)
    print("FINAL SUMMARY:")
    for symbol, ok in results.items():
        print(symbol + ": " + ("KAAMYAB" if ok else "NAKAAM"))
    print("=" * 60)

    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    run_test()
