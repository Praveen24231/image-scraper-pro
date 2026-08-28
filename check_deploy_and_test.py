import time
import requests
import json

RENDER_URL = "https://image-scraper-pro.onrender.com"
TARGET_VERSION = "2.4-yandex-fix-pinterest-relevance"

def wait_for_deploy(max_seconds=300):
    print(f"Waiting for Render production deployment '{TARGET_VERSION}' at {RENDER_URL}...")
    t0 = time.time()
    while time.time() - t0 < max_seconds:
        try:
            r = requests.get(f"{RENDER_URL}/api/health", timeout=10)
            if r.status_code == 200:
                v = r.json().get("version")
                print(f"[{round(time.time() - t0)}s] Live version: {v}")
                if v == TARGET_VERSION:
                    print(f"--> NEW DEPLOYMENT IS LIVE! (took {round(time.time() - t0)}s)")
                    return True
        except Exception as e:
            print(f"[{round(time.time() - t0)}s] Connecting... ({e})")
        time.sleep(6)
    return False

def test_production():
    print("\n" + "=" * 70)
    print("TESTING LIVE PRODUCTION ENDPOINTS ON RENDER")
    print("=" * 70)
    
    # 1. Test Health
    r_health = requests.get(f"{RENDER_URL}/api/health", timeout=10)
    print(f"\n[1] Health Check: {r_health.status_code} -> {r_health.json()}")
    
    # 2. Test Pinterest on Production
    print("\n[2] Testing Pinterest on Production...")
    target_pin = "https://in.pinterest.com/pin/980869993858369758/"
    t0 = time.time()
    r_pin = requests.post(
        f"{RENDER_URL}/api/pinterest/extract",
        json={"url": target_pin, "min_target": 300, "max_images": 1000},
        timeout=60
    )
    pin_elapsed = round(time.time() - t0, 2)
    print(f"Pinterest status: {r_pin.status_code} (took {pin_elapsed}s)")
    pin_data = r_pin.json()
    pin_images = pin_data.get("images", [])
    print(f"Total Pinterest Images Returned: {len(pin_images)}")
    print(f"Telemetry: {pin_data.get('telemetry')}")
    print("First 5 Images:")
    for idx, img in enumerate(pin_images[:5]):
        safe_alt = img.get("alt", "").encode("ascii", "replace").decode("ascii")
        print(f"  [{idx+1}] {safe_alt[:60]} -> {img.get('url')}")
        
    # 3. Test Yandex on Production
    print("\n[3] Testing Yandex on Production...")
    t0 = time.time()
    r_yan = requests.post(
        f"{RENDER_URL}/api/scrape",
        json={"url": "https://yandex.com/images/search?text=wallpaper", "autoscroll": True, "max_images": 600},
        timeout=60
    )
    yan_elapsed = round(time.time() - t0, 2)
    print(f"Yandex status: {r_yan.status_code} (took {yan_elapsed}s)")
    yan_data = r_yan.json()
    yan_images = yan_data.get("images", [])
    print(f"Total Yandex Images Returned: {len(yan_images)} (took {yan_elapsed}s)")
    print("First 3 Images:")
    for idx, img in enumerate(yan_images[:3]):
        print(f"  [{idx+1}] {img.get('url')[:100]}")
        
    print("\n" + "=" * 70)
    print("PRODUCTION TEST COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    if wait_for_deploy():
        test_production()
    else:
        print("Deployment check timed out. Running test anyway...")
        test_production()
