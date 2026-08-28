import re
import json
import requests

def inspect_pin_page_data():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.pinterest.com/",
    }
    r = requests.get("https://in.pinterest.com/pin/980869993858369758/", headers=headers)
    html = r.text
    print(f"Status: {r.status_code}, Length: {len(html)}")
    
    # Check for script tags with json data (e.g. __PWS_DATA__ or relay data or initial data)
    scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    print(f"Total script tags: {len(scripts)}")
    
    for idx, s in enumerate(scripts):
        if "props" in s or "initialData" in s or "relay" in s or "Pin" in s or "Boys" in s or "980869993858369758" in s:
            print(f"\nScript [{idx}] (length {len(s)}):")
            # find keywords
            for kw in ["Boys", "Curly", "Haircut", "Blagues", "related", "grid_title"]:
                matches = [m.start() for m in re.finditer(kw, s, re.IGNORECASE)]
                if matches:
                    print(f"  Found '{kw}' at indices: {matches[:5]}")
                    for pos in matches[:2]:
                        snippet = s[max(0, pos-100):min(len(s), pos+200)]
                        print(f"    Snippet: {repr(snippet)}")

if __name__ == "__main__":
    inspect_pin_page_data()
