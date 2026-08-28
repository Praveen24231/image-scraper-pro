import os
import requests
import time
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import re

def normalize_url(url):
    if not url: return url
    if url.startswith('//'): url = 'https:' + url
    
    # 1. Yandex CDN URLs (avatars.mds.yandex.net)
    if 'avatars.mds.yandex.net' in url or 'get-shedevrum' in url:
        if '/get-images-cbir/' in url:
            parts = url.split('/')
            if len(parts) >= 6:
                last_part = parts[-1].split('?')[0]
                if last_part != 'orig':
                    parts[-1] = 'orig'
                    url = '/'.join(parts).split('?')[0]
        elif '/get-shedevrum/' in url:
            if not url.endswith('/orig') and not '?' in url.split('/')[-1]:
                url = url.rstrip('/') + '/orig'

    # 2. Pinterest: /736x/ -> /originals/
    if 'pinimg.com' in url and '/736x/' in url:
        url = url.replace('/736x/', '/originals/')

    # 3. Strip common resizing query parameters
    try:
        from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        params_to_remove = ['w', 'h', 'width', 'height', 'size', 'quality', 'q', 'resize', 'fit']
        modified = False
        for p in params_to_remove:
            if p in qs:
                del qs[p]
                modified = True
        if modified:
            new_query = urlencode(qs, doseq=True)
            url = urlunparse(parsed._replace(query=new_query))
    except Exception:
        pass

    # 4. Google User Content
    if 'googleusercontent.com' in url:
        url = re.sub(r'\/s\d+(-c)?\/', '/s4096/', url)
    
    return url

# List of high-resolution image URLs from Yandex search
image_urls = [
    "https://c8.alamy.com/comp/2BFRKAK/cocaine-in-packet-isolated-on-white-2BFRKAK.jpg",
    "https://static2.bigstockphoto.com/2/7/1/large1500/172973141.jpg",
    "https://townsquare.media/site/464/files/2018/12/GettyImages-931938782.jpg?w=1200",
    "https://nypost.com/wp-content/uploads/sites/2/2016/12/coke.jpg?quality=75&w=1024",
    "https://static1.bigstockphoto.com/8/6/1/large1500/168718643.jpg",
    "https://c8.alamy.com/comp/2XCBY29/cocaine-in-plastic-packet-isolated-on-black-background-2XCBY29.jpg",
    "https://www.euractiv.com/wp-content/uploads/sites/2/2025/01/GettyImages-2173891902-1-scaled.jpg",
    "https://e3.365dm.com/21/01/1600x900/skynews-cocaine-southampton_5246508.jpg",
    "https://static2.bigstockphoto.com/3/7/1/large1500/173151941.jpg",
    "https://brainwavescience.com/wp-content/uploads/2024/05/shutterstock_2357248255_1-scaled.jpg",
    "https://pixel-shot.com/get_image/i-36629-0.JPG",
    "https://images.theconversation.com/files/659499/original/file-20250403-62-s967j5.jpg?w=1356",
    "https://ichef.bbci.co.uk/news/1536/cpsprodpb/3278/live/f4200b70-7ccf-11ef-b66d-034eed51208d.jpg.webp",
    "https://cdn.prod.website-files.com/6638f8a6eb6d568220f98b00/67c2c2178af8b1c85d307442_AdobeStock_508059680.jpeg",
    "https://ar.hibapress.com/wp-content/uploads/2025/07/Depositphotos_583141048_XL-1536x872.jpg",
    "https://pixel-shot.com/get_image/i-36632-0.JPG",
    "https://www.shutterstock.com/shutterstock/photos/1021284505/display_1500/stock-photo-cocaine-packets-being-weighted-1021284505.jpg",
    "https://e3.365dm.com/20/08/2048x1152/skynews-cocaine-drugs-gatwick-airport_5077896.jpg",
    "https://cdn.sanity.io/images/0vv8moc6/psychtimes/b870c894b0a52114acbdc1cf44552312792b880c-4534x3738.jpg",
    "https://pixel-shot.com/get_image/i-37320-0.JPG",
    "https://pixel-shot.com/get_image/i-36696-0.JPG",
    "https://www.futurity.org/wp/wp-content/uploads/2017/08/cocaine-bag-open_1600.jpg",
    "https://media.zenfs.com/en/ap.org/01d0212fb7c10d0b06865c2fdbf2e484",
    "https://f10.pmo.ee/M0xVKg-XfSYXdc-TFFT4oNJD2wo=/1442x0/filters:format(webp)/nginx/o/2019/11/12/12734973t1hdf3a.jpg",
    "https://ichef.bbci.co.uk/ace/standard/1600/cpsprodpb/2c57/live/fb7641a0-b450-11f0-84fc-23597f4c59b5.jpg",
    "https://media.wired.com/photos/6900a0f1725e504491c473c8/master/pass/GettyImages-2211312260.jpg",
    "https://thelasthouse.net/wp-content/uploads/2022/08/The-Last-House-Blog-3-What-are-the-Symptoms-of-Cocaine-Abuse.edited-scaled-1-2000x1125.jpg",
    "https://static2.bigstockphoto.com/5/4/3/large1500/345720454.jpg",
    "https://c8.alamy.com/comp/AEFX0E/cocaine-AEFX0E.jpg",
    "https://pixel-shot.com/get_image/i-36644-0.JPG"
]

download_dir = "downloads"
if not os.path.exists(download_dir):
    os.makedirs(download_dir)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
}

def download_image(args):
    url, index = args
    url = normalize_url(url)
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # Determine extension
        parsed_url = urlparse(url)
        path = parsed_url.path
        ext = os.path.splitext(path)[1]
        if not ext or len(ext) > 5:
            # Fallback
            if "jpg" in url.lower(): ext = ".jpg"
            elif "png" in url.lower(): ext = ".png"
            elif "webp" in url.lower(): ext = ".webp"
            else: ext = ".jpg"
        
        filename = f"cocaine_packet_{index:03d}{ext}"
        filepath = os.path.join(download_dir, filename)
        
        with open(filepath, 'wb') as f:
            f.write(response.content)
        print(f"Downloaded: {filename}")
    except Exception as e:
        print(f"Failed to download {url}: {e}")

if __name__ == "__main__":
    start_time = time.time()
    print(f"Starting parallel download of {len(image_urls)} images...")
    
    # Use 10 threads for multi-threaded downloading
    with ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(download_image, [(url, i) for i, url in enumerate(image_urls, 1)])
    
    end_time = time.time()
    print(f"Download complete in {end_time - start_time:.2f} seconds.")
