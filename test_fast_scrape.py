import httpx
import re
import html
import json
from bs4 import BeautifulSoup

def fast_scrape(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    r = httpx.get(url, headers=headers, follow_redirects=True, timeout=15)
    content = r.text
    
    images = []
    seen = set()
    
    # 1. Extract origUrl from JSON (both unescaped & html-escaped)
    for text_to_search in [content, html.unescape(content)]:
        for m in re.finditer(r'"origUrl"\s*:\s*"([^"]+)"', text_to_search):
            img_url = m.group(1).replace('\\/', '/')
            if img_url not in seen and img_url.startswith('http'):
                seen.add(img_url)
                images.append({'url': img_url, 'alt': 'Highest Quality Asset', 'width': 'Original', 'height': 'Original', 'area': 999999})
                
        for m in re.finditer(r'"url"\s*:\s*"([^"]+)"', text_to_search):
            img_url = m.group(1).replace('\\/', '/')
            if img_url not in seen and img_url.startswith('http') and ('avatars.mds.yandex.net' in img_url or 'pinimg.com' in img_url or 'unsplash' in img_url or 'wallpaper' in img_url):
                if not any(k in img_url.lower() for k in ['favicon', 'logo', 'icon', 'spinner']):
                    seen.add(img_url)
                    images.append({'url': img_url, 'alt': 'Search Asset', 'width': 'Original', 'height': 'Original', 'area': 100000})

    # 2. Extract DOM <img> tags
    soup = BeautifulSoup(content, 'html.parser')
    for img in soup.find_all('img'):
        src = img.get('src') or img.get('data-src') or img.get('data-original')
        if src and src.startswith('//'): src = 'https:' + src
        if src and src.startswith('http') and src not in seen:
            if not any(k in src.lower() for k in ['favicon', 'logo', 'icon', 'spinner', 'pixel', 'tracker']):
                seen.add(src)
                images.append({'url': src, 'alt': img.get('alt', ''), 'width': 'Original', 'height': 'Original', 'area': 1000})
                
    return images

if __name__ == '__main__':
    res = fast_scrape('https://yandex.com/images/search?text=ferrari')
    print(f"Total extracted: {len(res)}")
    for item in res[:5]:
        print(" -", item['url'])
