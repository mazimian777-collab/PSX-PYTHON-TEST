import sys
import time

try:
    import requests
except ImportError:
    print("FATAL: 'requests' library install nahi hai.")
    sys.exit(1)

TEST_SYMBOLS = ["SAZEW", "MEBL"]
TIMEOUT_SECONDS = 20


def run_test_for_symbol(symbol):
    url = "https://dps.psx.com.pk/timeseries/eod/" + symbol

    print("=" * 60)
    print("PSX Historical Endpoint - Isolated GitHub Actions Test")
    print("=" * 60)
    print("Symbol: " + symbol)
    print("URL: " + url)
    print("-" * 60)

    start_time = time.time()

    try:
        response = requests.get(url, timeout=TIMEOUT_SECONDS)
    except requests.exceptions.Timeout as err:
        elapsed = time.time() - start_time
        print("RESULT: FAIL (Timeout)")
        print("Elapsed Time: {:.2f}s".format(elapsed))
        print("Error Message: " + str(err))
        return
    except requests.exceptions.RequestException as err:
        elapsed = time.time() - start_time
        print("RESULT: FAIL (Connection/Request Error)")
        print("Elapsed Time: {:.2f}s".format(elapsed))
        print("Error Type: " + type(err).__name__)
        print("Error Message: " + str(err))
        return

    elapsed = time.time() - start_time

    print("HTTP Status: " + str(response.status_code))
    print("Response Time: {:.3f}s".format(elapsed))
    print("Final URL: " + response.url)
    print("Content-Type: " + str(response.headers.get("Content-Type", "(moujood nahi)")))
    print("-" * 60)

    body_text = response.text or ""
    print("Response Body - pehle 500 characters:")
    print(body_text[:500])
    print("-" * 60)

    if response.status_code == 200:
        try:
            data = response.json()
            rows = None
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                rows = data["data"]
            elif isinstance(data, list):
                rows = data

            if rows and len(rows) > 0:
                print("JSON Parse: OK")
                print("Historical rows mile: " + str(len(rows)))
                print("Pehli row (sample): " + str(rows[0]))
                print("=" * 60)
                print("GitHub Actions se " + symbol + " ka PSX Historical Data kaamyabi se mil gaya.")
            else:
                print("=" * 60)
                print("GitHub Actions se " + symbol + " ke liye 200 OK mila, magar data array khali hai.")
        except ValueError as err:
            print("Parse Error: " + str(err))
            print("=" * 60)
            print("GitHub Actions se " + symbol + " ke liye 200 OK mila, magar JSON parse nahi hua.")
    elif response.status_code == 520:
        print("=" * 60)
        print("GitHub Actions se bhi " + symbol + " ke liye PSX Historical Endpoint 520 de raha hai.")
    else:
        print("=" * 60)
        print("GitHub Actions se " + symbol + " ke liye HTTP " + str(response.status_code) + " mila.")


def run_test():
    for i, symbol in enumerate(TEST_SYMBOLS):
        if i > 0:
            print("\n")
        run_test_for_symbol(symbol)


if __name__ == "__main__":
    run_test()
