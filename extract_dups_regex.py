import re
import json
import requests

def extract_dups(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    }
    r = requests.get(url, headers=headers)
    content = r.text
    
    # Look for script tags or data attributes containing dups
    # Usually it's in a big JSON blob
    # We can try to find all strings that look like a dups array start: "dups":[{
    
    found_urls = []
    
    # This regex is broad but should find the dups array
    matches = re.finditer(r'"dups":\[(.*?)]', content)
    for match in matches:
        try:
            # Reconstruct part of the JSON to parse it
            raw_dups = match.group(0)
            parsed = json.loads("{" + raw_dups + "}")
            dups = parsed['dups']
            
            # Find the best dup
            if dups:
                best = max(dups, key=lambda x: x.get('w', 0) * x.get('h', 0))
                found_urls.append({
                    'url': best.get('url'),
                    'w': best.get('w'),
                    'h': best.get('h')
                })
        except:
            continue
            
    return found_urls

if __name__ == "__main__":
    url = "https://yandex.com/images/search?text=high+resolution+wallpaper"
    urls = extract_dups(url)
    print(f"Found {len(urls)} high-res URLs via regex.")
    for u in urls[:5]:
        print(f"{u['w']}x{u['h']} -> {u['url'][:100]}")
