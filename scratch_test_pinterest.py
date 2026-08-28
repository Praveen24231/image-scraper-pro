import re
import json
import requests
from html import unescape
from urllib.parse import quote, unquote

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.pinterest.com/",
}

def inspect_pinterest(pin_url):
    print(f"=== Inspecting Pinterest URL: {pin_url} ===")
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # 1. Fetch seed pin page HTML
    r = session.get(pin_url, timeout=15)
    html = r.text
    print(f"Status: {r.status_code}, HTML length: {len(html)}")
    
    # Check CSRF / session
    csrf = session.cookies.get("csrftoken") or session.cookies.get("_pinterest_sess") or ""
    print(f"CSRF token found: {bool(csrf)}")
    
    # 2. Extract Pin ID
    pin_id_match = re.search(r'/pin/(\d+)', pin_url)
    pin_id = pin_id_match.group(1) if pin_id_match else None
    print(f"Pin ID: {pin_id}")
    
    # 3. Check JSON-LD
    ld_jsons = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    print(f"JSON-LD blocks found: {len(ld_jsons)}")
    for idx, lj in enumerate(ld_jsons):
        try:
            data = json.loads(lj)
            print(f"JSON-LD [{idx}]: type={data.get('@type')}, name={data.get('name')}, headline={data.get('headline')}, image={data.get('image')}")
        except Exception as e:
            print(f"JSON-LD [{idx}] parse error: {e}")
            
    # 4. Check og: meta tags
    og_title = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html)
    og_desc = re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html)
    og_img = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
    print(f"og:title: {og_title.group(1) if og_title else None}")
    print(f"og:desc: {og_desc.group(1) if og_desc else None}")
    print(f"og:image: {og_img.group(1) if og_img else None}")
    
    # 5. Check PinResource API
    session.headers.update({
        "Accept": "application/json, text/javascript, */*, q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "X-Pinterest-AppState": "active",
        "X-Pinterest-PWS-Handler": "www/[username]/[slug].js",
    })
    if csrf:
        session.headers["X-CSRFToken"] = csrf
        
    pin_payload = {"options": {"id": pin_id, "field_set_key": "detailed"}, "context": {}}
    url_pin = f"https://www.pinterest.com/resource/PinResource/get/?source_url={quote(f'/pin/{pin_id}/')}&data={quote(json.dumps(pin_payload))}"
    
    r_pin = session.get(url_pin, timeout=10)
    print(f"PinResource status: {r_pin.status_code}")
    if r_pin.status_code == 200:
        p_json = r_pin.json()
        p_data = p_json.get("resource_response", {}).get("data", {})
        print(f"PinResource keys: {list(p_data.keys())[:10]}")
        print(f"Pin Title: {p_data.get('title')}")
        print(f"Pin Grid Title: {p_data.get('grid_title')}")
        print(f"Pin Description: {p_data.get('description')}")
        print(f"Pin Domain: {p_data.get('domain')}")
        print(f"Pin Visual Search / Related data available?")
        
        # Check visuals / related resources
        images = p_data.get("images", {})
        print(f"Pin Images available keys: {list(images.keys())}")
        orig_img = images.get("orig", {}).get("url")
        print(f"Target Pin Original Image URL: {orig_img}")
        
    # 6. Check Related Pins / Visual Search Resource endpoints on Pinterest!
    # Does Pinterest have RelatedPinFeedResource or VisualSearchResource?
    related_payload = {"options": {"pin_id": pin_id, "field_set_key": "grid_item"}, "context": {}}
    url_rel = f"https://www.pinterest.com/resource/RelatedPinFeedResource/get/?source_url={quote(f'/pin/{pin_id}/')}&data={quote(json.dumps(related_payload))}"
    r_rel = session.get(url_rel, timeout=10)
    print(f"RelatedPinFeedResource status: {r_rel.status_code}")
    if r_rel.status_code == 200:
        rel_data = r_rel.json().get("resource_response", {}).get("data", [])
        print(f"RelatedPinFeedResource items returned: {len(rel_data)}")
        if rel_data:
            print(f"First related item title: {rel_data[0].get('title')}, grid_title: {rel_data[0].get('grid_title')}")
            
    # Check PinVisualSearchResource / VisualSearchResource
    vs_payload = {"options": {"pin_id": pin_id, "crop": {"x": 0, "y": 0, "w": 1, "h": 1}}, "context": {}}
    url_vs = f"https://www.pinterest.com/resource/PinVisualSearchResource/get/?source_url={quote(f'/pin/{pin_id}/visual-search/')}&data={quote(json.dumps(vs_payload))}"
    r_vs = session.get(url_vs, timeout=10)
    print(f"PinVisualSearchResource status: {r_vs.status_code}")
    if r_vs.status_code == 200:
        vs_data = r_vs.json().get("resource_response", {}).get("data", {})
        results = vs_data.get("results", []) if isinstance(vs_data, dict) else vs_data
        print(f"PinVisualSearchResource items returned: {len(results)}")
        if results:
            print(f"First visual search item: {results[0].get('title')}")

if __name__ == "__main__":
    inspect_pinterest("https://in.pinterest.com/pin/980869993858369758/")
