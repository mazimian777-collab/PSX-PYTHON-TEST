"""
FULL ROLLOUT - PSX Historical Data ko GitHub Actions se fetch kar ke
Cloudflare Worker ke /pushhistorical endpoint par POST karta hai.

(Update) Pehle yeh sirf 3 companies (MARI, SAZEW, MEBL) tak TEST MODE mein
mehdood tha. Test kaamyab hone ke baad, ab yeh poori WATCHLIST (100 companies,
psx-bot-worker.js ke andar wali WATCHLIST se hoobahoo li gayi hai) ke liye
chalta hai. Yeh script:

- Sirf GitHub Actions ke apne "workflow_dispatch" (manual button) se chalti hai.
  Koi schedule/cron abhi shamil NAHI kiya gaya - jab tak aap khud manually
  "Run workflow" na dabayein, yeh khud ba khud kabhi nahi chalegi.
- Existing Historical Import Queue, Cloudflare Worker ke baaki kisi bhi
  function/feature ko CHHOOTI NAHI - sirf naye /pushhistorical endpoint ko
  ek normal HTTP client ki tarah, ek ek company ke liye, wafqe (delay) ke
  sath call karti hai (taake PSX par ek dum bohot saari requests na jayein).
- Shared secret kabhi print/log NAHI karti - sirf ek GitHub Actions Secret
  (environment variable) se padhti hai.
- Har company independent hai: agar koi ek fail ho (jaise PSX temporarily
  block kar de), to baaki companies par koi asar nahi parta - script chalti
  rehti hai aur aakhir mein saaf report deti hai ke kitni kaamyab hui,
  kitni nakaam.

IMPORTANT (aap ne yeh 2 cheezein set karni hain, is script mein koi secret
khud se nahi likha gaya):
  1. Neeche PSX_WORKER_BASE_URL ko apne Cloudflare Worker ke asal URL se
     replace karein. Yeh URL koi secret nahi hai (sirf domain hai), is liye
     seedha yahan likha ja sakta hai.
  2. GitHub repo mein Settings -> Secrets and variables -> Actions mein
     "PUSH_HISTORICAL_SECRET" naam ka secret bana kar wahi value rakhein jo
     Cloudflare Worker Secret "PUSH_HISTORICAL_SECRET" mein bhi set hai
     (dono taraf EXACT same value honi chahiye).
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
PSX_WORKER_BASE_URL = "https://psxai-bot.mazimian777.workers.dev"

# ---- Poori WATCHLIST (100 companies) - psx-bot-worker.js ke WATCHLIST array se ----
ALL_SYMBOLS = [
    "ABL", "ABOT", "AGP", "AHCL", "AICL", "AIRLINK", "AKBL", "APL", "ATLH", "ATRL",
    "BAFL", "BAHL", "BNWM", "BOP", "BWCL", "CHCC", "CNERGY", "COLG", "CPHL", "DCR",
    "DGKC", "EFERT", "ENGROH", "FABL", "FATIMA", "FCCL", "FFC", "FFL", "FHAM", "GADT",
    "GAL", "GHGL", "GHNI", "GLAXO", "HALEON", "HBL", "HCAR", "HGFA", "HINOON", "HMB",
    "HUBC", "HUMNL", "IBFL", "ILP", "INDU", "INIL", "ISL", "JDWS", "JVDC", "KAPCO",
    "KEL", "KOHC", "KTML", "LCI", "LOTCHEM", "LUCK", "MARI", "MCB", "MEBL", "MEHT",
    "MLCF", "MTL", "MUREB", "NATF", "NBP", "NESTLE", "NML", "NPL", "OGDC", "PABC",
    "PAEL", "PAKT", "PGLC", "PIBTL", "PIOC", "PKGS", "POL", "POWER", "PPL", "PSEL",
    "PSO", "PSX", "PTC", "RMPL", "SAZEW", "SCBPL", "SEARL", "SHFA", "SNGP", "SRVI",
    "SSGC", "SSOM", "SYS", "TGL", "THALL", "TPLRF1", "TRG", "UBL", "UPFL", "YOUW",
]

TIMEOUT_SECONDS = 20
DELAY_BETWEEN_SYMBOLS_SECONDS = 8  # PSX par wafqa rakhne ke liye (100 companies, is liye thora zyada rakha)


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


def run_test_for_symbol(symbol, secret, index, total):
    print("=" * 60)
    print("[" + str(index) + "/" + str(total) + "] PSX -> /pushhistorical")
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

    total = len(ALL_SYMBOLS)
    results = {}
    for i, symbol in enumerate(ALL_SYMBOLS):
        if i > 0:
            print("\n")
            time.sleep(DELAY_BETWEEN_SYMBOLS_SECONDS)
        results[symbol] = run_test_for_symbol(symbol, secret, i + 1, total)

    success_symbols = [s for s, ok in results.items() if ok]
    failed_symbols = [s for s, ok in results.items() if not ok]

    print("\n" + "=" * 60)
    print("FINAL SUMMARY:")
    print("Total: " + str(total) + " | Kaamyab: " + str(len(success_symbols)) + " | Nakaam: " + str(len(failed_symbols)))
    if failed_symbols:
        print("\nYeh companies nakaam hui (baad mein dobara try ki ja sakti hain):")
        print(", ".join(failed_symbols))
    print("=" * 60)

    # (Design choice) Agar kam az kam kuch companies kaamyab hui hain, to poori
    # run ko "Failure" mark nahi karte - kyunke 100 companies mein se kuch ka
    # PSX se temporarily fail hona normal hai (bilkul jaisa existing Import
    # Queue mein bhi hota hai). Sirf tab "Failure" dikhate hain jab BILKUL
    # koi bhi company kaamyab na ho - yeh nishaani hai ke koi bunyadi masla
    # hai (jaise secret galat, ya Worker down).
    if len(success_symbols) == 0:
        sys.exit(1)


if __name__ == "__main__":
    run_test()
