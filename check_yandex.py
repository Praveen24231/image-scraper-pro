import urllib.request, re

url = 'https://yandex.com/images/search?isize=large&text=bmw+m4'
req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
})
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        html = r.read().decode('utf-8', errors='ignore')

    p1 = re.findall(r'"url"\s*:\s*"(https?://[^"]+)"', html)
    img_urls = [u for u in p1 if any(x in u for x in ['avatars', 'yandex.net', 'im0-tub', 'im1-tub', 'sun9'])]

    print(f'HTML length: {len(html)}')
    print(f'Total url matches: {len(p1)}')
    print(f'Image-like urls: {len(img_urls)}')
    for u in img_urls[:8]:
        print(' ', u[:120])
except Exception as e:
    print(f'Error: {e}')
