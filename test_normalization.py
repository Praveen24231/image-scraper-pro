import re
from urllib.parse import urlparse, parse_qs, urlunparse

def normalize_url(url):
    if not url: return url
    if url.startswith('//'): url = 'https:' + url
    
    # 1. Yandex CDN URLs (avatars.mds.yandex.net)
    if 'avatars.mds.yandex.net' in url or 'get-shedevrum' in url:
        # Pattern: .../get-images-cbir/123/abc/suffix
        if '/get-images-cbir/' in url:
            parts = url.split('/')
            # if suffix exists
            if len(parts) >= 6:
                # Replace last part if it's not 'orig'
                if parts[-1].split('?')[0] != 'orig':
                    parts[-1] = 'orig'
                    url = '/'.join(parts).split('?')[0]
        elif '/i?id=' in url:
            # Thumbnail patterns often look like /i?id=...&n=13
            # Usually we want to keep them or find if there's a better one,
            # but usually 'img_url' in search result is better.
            pass
        elif not url.endswith('/orig') and not '?' in url.split('/')[-1]:
            url = url.rstrip('/') + '/orig'

    # 2. Pinterest
    if 'pinimg.com' in url and '/736x/' in url:
        url = url.replace('/736x/', '/originals/')

    # 3. Strip common resizing parameters from any URL
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    
    # Common resize/quality params to remove
    params_to_remove = ['w', 'h', 'width', 'height', 'size', 'quality', 'q', 'resize', 'fit']
    modified = False
    for p in params_to_remove:
        if p in qs:
            del qs[p]
            modified = True
            
    if modified:
        # Rebuild query string
        from urllib.parse import urlencode
        new_query = urlencode(qs, doseq=True)
        url = urlunparse(parsed._replace(query=new_query))

    # 4. Google User Content
    if 'googleusercontent.com' in url:
        url = re.sub(r'\/s\d+(-c)?\/', '/s4096/', url)
    
    return url

test_urls = [
    "https://avatars.mds.yandex.net/get-images-cbir/2762254/20Xs0TD3cu1UhU5ClFu70w628/optimize",
    "https://avatars.mds.yandex.net/get-images-cbir/2762254/20Xs0TD3cu1UhU5ClFu70w628/orig",
    "https://static2.bigstockphoto.com/2/7/1/large1500/172973141.jpg?w=1024",
    "https://townsquare.media/site/464/files/2018/12/GettyImages-931938782.jpg?w=1200&h=800",
    "https://nypost.com/wp-content/uploads/sites/2/2016/12/coke.jpg?quality=75&w=1024",
    "https://i.pinimg.com/736x/ab/cd/ef.jpg",
    "https://lh3.googleusercontent.com/pw/AM-JKLX/s200/photo.jpg"
]

for u in test_urls:
    print(f"Original: {u}")
    print(f"Normalized: {normalize_url(u)}")
    print("-" * 20)
