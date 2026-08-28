import requests

# Test the proxy download logic
def test_proxy():
    # A URL that might have a small version by default or resizing
    url = "https://townsquare.media/site/464/files/2018/12/GettyImages-931938782.jpg?w=1200"
    
    # Simulate the backend logic
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Referer': url
    }
    
    # 1. Without normalization
    resp1 = requests.get(url, headers=headers)
    print(f"Size with ?w=1200: {len(resp1.content)} bytes")
    
    # 2. With normalization (stripping ?w=)
    from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    if 'w' in qs: del qs['w']
    new_query = urlencode(qs, doseq=True)
    norm_url = urlunparse(parsed._replace(query=new_query))
    
    print(f"Normalized URL: {norm_url}")
    resp2 = requests.get(norm_url, headers=headers)
    print(f"Size normalized: {len(resp2.content)} bytes")

    # 3. Yandex CDN test
    ya_url_opt = "https://avatars.mds.yandex.net/get-images-cbir/2762254/20Xs0TD3cu1UhU5ClFu70w628/optimize"
    ya_url_orig = "https://avatars.mds.yandex.net/get-images-cbir/2762254/20Xs0TD3cu1UhU5ClFu70w628/orig"
    
    resp_ya1 = requests.get(ya_url_opt, headers=headers)
    resp_ya2 = requests.get(ya_url_orig, headers=headers)
    
    print(f"Yandex Optimize size: {len(resp_ya1.content)} bytes")
    print(f"Yandex Original size: {len(resp_ya2.content)} bytes")

if __name__ == "__main__":
    test_proxy()
