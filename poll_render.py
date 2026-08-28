import time
import requests

RENDER_URL = "https://image-scraper-pro.onrender.com"
TARGET_VERSION = "2.4-yandex-fix-pinterest-relevance"

t0 = time.time()
while time.time() - t0 < 180:
    try:
        r = requests.get(f"{RENDER_URL}/api/health", timeout=10)
        if r.status_code == 200:
            v = r.json().get("version")
            print(f"[{round(time.time() - t0)}s] Live version: {v}")
            if v == TARGET_VERSION:
                print("==> SUCCESS: NEW DEPLOYMENT IS LIVE!")
                break
    except Exception as e:
        print(f"[{round(time.time() - t0)}s] Connecting... ({e})")
    time.sleep(8)
