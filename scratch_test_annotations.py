import re
import json
import requests
from urllib.parse import quote

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*, q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "X-Pinterest-AppState": "active",
    "X-Pinterest-PWS-Handler": "www/[username]/[slug].js",
    "Referer": "https://www.pinterest.com/",
}

def test_annotation_extraction():
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # 1. Fetch seed page HTML
    url = "https://in.pinterest.com/pin/980869993858369758/"
    r = session.get(url, timeout=10)
    html = r.text
    
    # Extract script tag with Relay / PWS data
    annotations = []
    breadcrumbs = []
    target_img = None
    
    # Find visualAnnotation
    va_match = re.search(r'"visualAnnotation"\s*:\s*(\[[^\]]+\])', html)
    if va_match:
        try:
            annotations = json.loads(va_match.group(1))
        except Exception:
            pass
            
    # Find seoBreadcrumbs
    bc_matches = re.findall(r'"seoBreadcrumbs"\s*:\s*(\[[^\]]+\])', html)
    for bcm in bc_matches:
        try:
            items = json.loads(bcm)
            for it in items:
                if it.get("name"):
                    breadcrumbs.append(it["name"])
        except Exception:
            pass
            
    orig_match = re.search(r'https?://i\.pinimg\.com/originals/[0-9a-f/]+\.(?:jpg|png|webp)', html)
    if orig_match:
        target_img = orig_match.group(0)
        
    print(f"Target Image: {target_img}")
    print(f"Annotations: {annotations}")
    print(f"Breadcrumbs: {breadcrumbs}")
    
    # 2. Query BaseSearchResource using the target pin's actual visual annotations!
    # e.g., "Boys Curly Haircut"
    query = annotations[0] if annotations else "Boys Curly Haircut"
    print(f"\nQuerying BaseSearchResource with: '{query}'")
    
    opts = {
        "query": query,
        "scope": "pins",
        "page_size": 50
    }
    srch_payload = {"options": opts, "context": {}}
    url_srch = f"https://www.pinterest.com/resource/BaseSearchResource/get/?source_url={quote(f'/search/pins/?q={query}')}&data={quote(json.dumps(srch_payload))}"
    
    r_srch = session.get(url_srch, timeout=10)
    print(f"Search status: {r_srch.status_code}")
    if r_srch.status_code == 200:
        data = r_srch.json().get("resource_response", {}).get("data", {})
        results = data.get("results", []) if isinstance(data, dict) else data
        print(f"Results returned: {len(results)}")
        for idx, it in enumerate(results[:5]):
            title = it.get("title") or it.get("grid_title") or it.get("description")
            img = it.get("images", {}).get("orig", {}).get("url") or it.get("images", {}).get("736x", {}).get("url")
            print(f" Item [{idx+1}]: Title='{title}', Img={img}")

if __name__ == "__main__":
    test_annotation_extraction()
