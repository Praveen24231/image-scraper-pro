import time
import requests
import json

RENDER_URL = "https://image-scraper-pro.onrender.com"
TARGET_VERSION = "2.4-yandex-fix-pinterest-relevance"

def wait_for_render_deployment(max_wait_seconds=360):
    print(f"Monitoring Render production deployment at {RENDER_URL}...")
    print(f"Waiting for version: '{TARGET_VERSION}'...")
    
    t_start = time.time()
    last_status = None
    
    while time.time() - t_start < max_wait_seconds:
        try:
            r = requests.get(f"{RENDER_URL}/api/health", timeout=10)
            if r.status_code == 200:
                data = r.json()
                v = data.get("version")
                if v != last_status:
                    print(f"[{round(time.time() - t_start)}s] Production health status: {data}")
                    last_status = v
                if v == TARGET_VERSION:
                    print(f"\nSUCCESS: Render production deployment completed in {round(time.time() - t_start, 1)}s!")
                    print(f"Active version: {v}")
                    return True
            else:
                print(f"[{round(time.time() - t_start)}s] HTTP status: {r.status_code}")
        except Exception as e:
            print(f"[{round(time.time() - t_start)}s] Server updating / warming up... ({e})")
            
        time.sleep(8)
        
    print(f"Timeout after {max_wait_seconds}s waiting for deployment.")
    return False

if __name__ == "__main__":
    wait_for_render_deployment()
