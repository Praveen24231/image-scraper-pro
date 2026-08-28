import requests

print("=== CHECKING HEALTH ENDPOINTS ===")
try:
    r_cloud = requests.get("https://image-scraper-pro.onrender.com/api/health", timeout=10)
    print(f"Cloud (Render): {r_cloud.status_code} -> {r_cloud.json()}")
except Exception as e:
    print(f"Cloud error: {e}")

try:
    r_local = requests.get("http://localhost:5000/api/health", timeout=5)
    print(f"Local: {r_local.status_code} -> {r_local.json()}")
except Exception as e:
    print(f"Local (not running or offline): {e}")
