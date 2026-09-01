import os
import sys
import asyncio
import uuid
import zipfile
import io
import requests
import httpx
import re
import json
import html
import hashlib
import threading
from collections import OrderedDict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse, parse_qs, urljoin, urlencode
from requests.utils import requote_uri

# Preserve Pinterest scrapers
from pinterest_scraper import extract_pinterest_pin
from pinterest_resource_scraper import extract_pinterest_resource_api

# Setup reusable connection-pooled session for ultra-fast downloads
session = requests.Session()
adapter = HTTPAdapter(
    pool_connections=256,
    pool_maxsize=256,
    max_retries=Retry(total=2, backoff_factor=0.2, status_forcelist=[500, 502, 503, 504])
)
session.mount('http://', adapter)
session.mount('https://', adapter)

# Fix Windows asyncio event loop policy for Playwright compatibility
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Safe print helper to prevent terminal encoding crashes on Windows
def safe_print(*args, **kwargs):
    import builtins
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = [str(arg).encode('ascii', errors='replace').decode('ascii') for arg in args]
        builtins.print(*safe_args, **kwargs)

MIN_IMAGE_DIMENSION = 400

def check_image_dimensions(image_bytes: bytes, min_dim=MIN_IMAGE_DIMENSION):
    """
    Returns (is_valid, width, height).
    is_valid is True if BOTH width >= min_dim AND height >= min_dim.
    """
    if not image_bytes:
        return False, 0, 0
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            w, h = img.size
            if w >= min_dim and h >= min_dim:
                return True, w, h
            return False, w, h
    except Exception:
        # If image format cannot be determined by PIL, allow if byte stream present
        return True, 0, 0

def normalize_url(url):
    if not url: return url
    if url.startswith('//'): url = 'https:' + url
    
    # 1. Yandex CDN URLs (avatars.mds.yandex.net)
    if 'avatars.mds.yandex.net' in url or 'get-shedevrum' in url:
        if '/get-' in url:
            parts = url.split('/')
            if len(parts) >= 6:
                last_part_full = parts[-1]
                last_part = last_part_full.split('?')[0]
                if last_part not in ['orig', 'original']:
                    parts[-1] = 'orig'
                    url = '/'.join(parts)
        elif '/get-shedevrum/' in url:
            if not url.endswith('/orig') and not '?' in url.split('/')[-1]:
                url = url.rstrip('/') + '/orig'

    # 2. Pinterest: /736x/ or /236x/ -> /originals/
    if 'pinimg.com' in url:
        if '/736x/' in url:
            url = url.replace('/736x/', '/originals/')
        elif '/236x/' in url:
            url = url.replace('/236x/', '/originals/')

    # 3. Strip common resizing query parameters
    try:
        from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        params_to_remove = ['w', 'h', 'width', 'height', 'size', 'quality', 'q', 'resize', 'fit', 'n']
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
        if '=' in url.split('/')[-1]:
            url = re.sub(r'=s\d+.*$', '=s0', url)
        else:
            url = re.sub(r'\/s\d+(-c)?\/', '/s4096/', url)

    return url

app = Flask(__name__, static_folder="../", static_url_path="")
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Expose-Headers"] = "Content-Disposition, Content-Length, X-Image-Width, X-Image-Height"
    return response

TEMP_DIR = "temp_downloads"
CACHE_DIR = os.path.join(TEMP_DIR, "cache")
for d in [TEMP_DIR, CACHE_DIR]:
    if not os.path.exists(d):
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass

class ImageCache:
    """Thread-safe fast in-memory LRU + disk image cache from friend's implementation."""
    def __init__(self, max_memory_items=300, cache_dir=CACHE_DIR):
        self.max_items = max_memory_items
        self.cache_dir = cache_dir
        self.lock = threading.Lock()
        self.memory_cache = OrderedDict()

    def _hash_key(self, url: str) -> str:
        return hashlib.sha256(url.encode('utf-8')).hexdigest()

    def get(self, url: str):
        key = self._hash_key(url)
        with self.lock:
            if key in self.memory_cache:
                self.memory_cache.move_to_end(key)
                return self.memory_cache[key]
        
        # Disk fallback
        disk_path = os.path.join(self.cache_dir, f"{key}.bin")
        meta_path = os.path.join(self.cache_dir, f"{key}.json")
        if os.path.exists(disk_path) and os.path.exists(meta_path):
            try:
                with open(disk_path, 'rb') as f:
                    content = f.read()
                with open(meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                entry = {
                    'content': content,
                    'content_type': meta.get('content_type', 'image/jpeg'),
                    'is_valid': meta.get('is_valid', True),
                    'width': meta.get('width', 0),
                    'height': meta.get('height', 0),
                    'ext': meta.get('ext', 'jpg')
                }
                with self.lock:
                    self.memory_cache[key] = entry
                    self.memory_cache.move_to_end(key)
                    if len(self.memory_cache) > self.max_items:
                        self.memory_cache.popitem(last=False)
                return entry
            except Exception:
                pass
        return None

    def put(self, url: str, content: bytes, content_type: str, is_valid: bool, width: int, height: int, ext: str):
        key = self._hash_key(url)
        entry = {
            'content': content,
            'content_type': content_type,
            'is_valid': is_valid,
            'width': width,
            'height': height,
            'ext': ext
        }
        with self.lock:
            self.memory_cache[key] = entry
            self.memory_cache.move_to_end(key)
            if len(self.memory_cache) > self.max_items:
                self.memory_cache.popitem(last=False)
        
        try:
            disk_path = os.path.join(self.cache_dir, f"{key}.bin")
            meta_path = os.path.join(self.cache_dir, f"{key}.json")
            with open(disk_path, 'wb') as f:
                f.write(content)
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump({'content_type': content_type, 'is_valid': is_valid, 'width': width, 'height': height, 'ext': ext}, f)
        except Exception:
            pass

image_cache = ImageCache()

def fetch_image_cached(url: str, min_dim=MIN_IMAGE_DIMENSION, timeout=12):
    """Fetches an image with thread-safe caching and Pillow validation."""
    if not url:
        return None, None, False, 0, 0, None, "Invalid URL"
    
    norm_url = normalize_url(url)
    cached = image_cache.get(norm_url)
    if cached:
        return cached['content'], cached['content_type'], cached['is_valid'], cached['width'], cached['height'], cached['ext'], None
    
    try:
        ascii_url = requote_uri(norm_url)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br'
        }
        if 'yandex' in ascii_url:
            headers['Referer'] = 'https://yandex.com/'
        elif 'wikimedia' in ascii_url or 'wikipedia' in ascii_url:
            headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ImageScraperPro/3.0'
        resp = session.get(ascii_url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return None, None, False, 0, 0, None, f"HTTP {resp.status_code}"
        
        content = resp.content
        content_type = resp.headers.get('Content-Type', 'image/jpeg').split(';')[0].strip()
        
        is_valid, w, h = check_image_dimensions(content, min_dim=min_dim)
        
        ext = norm_url.split('.')[-1].split('?')[0].lower()
        if not ext or len(ext) > 4 or not ext.isalnum():
            if 'png' in content_type: ext = 'png'
            elif 'webp' in content_type: ext = 'webp'
            elif 'avif' in content_type: ext = 'avif'
            else: ext = 'jpg'
            
        image_cache.put(norm_url, content, content_type, is_valid, w, h, ext)
        return content, content_type, is_valid, w, h, ext, None
    except Exception as e:
        return None, None, False, 0, 0, None, str(e)

SKIP_EXTENSIONS = {'.svg', '.ico', '.gif'}
SKIP_KEYWORDS = ['favicon', 'logo', 'icon', 'spinner', 'tracker', 'pixel',
                  'doubleclick', 'analytics', 'metrika', 'badge', 'spacer', 'captcha', '1x1']

def _is_countable_url(url: str) -> bool:
    if not url or url.startswith('data:'):
        return False
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    url_lower = url.lower()
    if any(kw in url_lower for kw in SKIP_KEYWORDS):
        return False
    return True

# Background streaming jobs registry
SCRAPE_JOBS = {}
SCRAPE_JOBS_LOCK = threading.Lock()

def start_job_cleanup_loop():
    def cleanup():
        import time
        while True:
            time.sleep(300)
            now = time.time()
            with SCRAPE_JOBS_LOCK:
                expired = [jid for jid, j in SCRAPE_JOBS.items() if now - j.get("started_at", now) > 1200]
                for jid in expired:
                    del SCRAPE_JOBS[jid]
    t = threading.Thread(target=cleanup, daemon=True)
    t.start()

start_job_cleanup_loop()

async def fast_count_images(url: str) -> dict:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    static_html = ''
    fetch_ok = False
    fetch_method = 'httpx'

    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=12) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            static_html = resp.text
            fetch_ok = True
    except Exception as e:
        safe_print(f"[count] httpx fetch failed: {e}")

    needs_browser = False
    if fetch_ok:
        quick_soup = BeautifulSoup(static_html, 'lxml') if 'lxml' in sys.modules else BeautifulSoup(static_html, 'html.parser')
        raw_img_count = len(quick_soup.find_all('img'))
        js_markers = ['__NEXT_DATA__', 'window.__INITIAL_STATE__', 'window.YM', '__reactFiber', 'ng-version', 'data-react']
        has_js_markers = any(m in static_html for m in js_markers)
        needs_browser = raw_img_count < 5 and has_js_markers
    else:
        needs_browser = True

    js_html = ''
    if needs_browser:
        fetch_method = 'playwright'
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                ctx = await browser.new_context(user_agent=headers['User-Agent'])
                page = await ctx.new_page()
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(2)
                js_html = await page.content()
                await browser.close()
        except Exception as e:
            safe_print(f"[count] Playwright fallback failed: {e}")

    html_to_parse = js_html if js_html else static_html
    if not html_to_parse:
        return {'total': 0, 'breakdown': {}, 'method': fetch_method, 'note': 'Could not fetch page'}

    soup = BeautifulSoup(html_to_parse, 'html.parser')
    base = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(url))

    seen = set()
    counts = {'img_src': 0, 'srcset': 0, 'data_src': 0, 'og_image': 0, 'link_href': 0, 'css_bg': 0}

    def add(src: str, bucket: str):
        if not src: return
        src = src.strip().split()[0]
        if src.startswith('//'): src = 'https:' + src
        elif src.startswith('/'): src = base + src
        if src in seen: return
        if _is_countable_url(src):
            seen.add(src)
            counts[bucket] += 1

    for tag in soup.find_all('img', src=True): add(tag['src'], 'img_src')
    for tag in soup.find_all(['img', 'source'], srcset=True):
        for part in tag['srcset'].split(','):
            add(part.strip().split()[0], 'srcset')
    for attr in ('data-src', 'data-original', 'data-lazy-src', 'data-lazy', 'data-echo', 'data-url', 'data-hi-res-src'):
        for tag in soup.find_all(attrs={attr: True}):
            add(tag[attr], 'data_src')
    for tag in soup.find_all('meta'):
        prop = tag.get('property', '') + tag.get('name', '')
        if 'image' in prop.lower():
            add(tag.get('content', ''), 'og_image')
    for tag in soup.find_all('a', href=True):
        href = tag['href']
        ext = urlparse(href).path.lower().split('.')[-1]
        if ext in ('jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tiff', 'avif'):
            add(href, 'link_href')
        qs = parse_qs(urlparse(href).query)
        img_url_val = (qs.get('img_url') or qs.get('url') or [])
        if img_url_val:
            add(unquote(img_url_val[0]), 'link_href')

    bg_pattern = re.compile(r'url\([\'"]?(https?://[^)\'"]+)[\'"]?\)', re.I)
    for tag in soup.find_all(style=True):
        for m in bg_pattern.finditer(tag['style']): add(m.group(1), 'css_bg')
    for style_tag in soup.find_all('style'):
        for m in bg_pattern.finditer(style_tag.get_text()): add(m.group(1), 'css_bg')

    total = len(seen)
    return {
        'total': total,
        'count': total,
        'breakdown': {k: v for k, v in counts.items() if v > 0},
        'method': fetch_method,
        'note': 'Browser render used' if needs_browser else 'Static HTML scan',
    }

async def auto_scroll_and_extract(page, accumulation_set, job_id=None, target_count=2000, max_scrolls=60):
    """Friend's scrolling loop with Show More button clicks and real-time DOM/state extraction."""
    last_count = 0
    no_change_count = 0

    for i in range(max_scrolls):
        if job_id:
            with SCRAPE_JOBS_LOCK:
                job = SCRAPE_JOBS.get(job_id)
                if not job or job.get("status") == "aborted":
                    break
                if len(job.get("images", [])) >= target_count:
                    break

        # Extract images and link attributes from DOM
        current_data = await page.evaluate("""
            () => {
                const results = [];
                const links = document.querySelectorAll('a[href*="img_url="], a[href*="url="], a.ImagesContentImage-Cover, a.serp-item__link, a.serp-item__item');
                links.forEach(a => {
                    let highRes = null;
                    try {
                        const href = a.href || a.getAttribute('href') || '';
                        const urlParams = new URL(href, window.location.origin).searchParams;
                        highRes = urlParams.get('img_url') || urlParams.get('url') || urlParams.get('image_url');
                    } catch(e) {}
                    const img = a.querySelector('img');
                    const src = highRes || img?.src || img?.getAttribute('data-src') || img?.getAttribute('data-original') || img?.getAttribute('data-lazy-src');
                    if (src) {
                        results.push({ 
                            url: src, 
                            alt: img?.alt || "", 
                            w: img?.naturalWidth || img?.width || 0,
                            h: img?.naturalHeight || img?.height || 0,
                            isHighRes: !!highRes 
                        });
                    }
                });

                document.querySelectorAll('[data-state], [data-bem]').forEach(el => {
                    const st = el.getAttribute('data-state') || el.getAttribute('data-bem');
                    if (st && (st.includes('origUrl') || st.includes('dups') || st.includes('img_url'))) {
                        results.push({ stateData: st });
                    }
                });

                return results;
            }
        """)
        
        for item in current_data:
            if 'url' in item:
                u = item['url']
                if u and not u.startswith('data:') and 'spacer.gif' not in u:
                    norm = normalize_url(u)
                    accumulation_set.add((norm, item.get('alt', ''), item.get('w', 0), item.get('h', 0)))
            elif 'stateData' in item:
                st = item['stateData']
                for m in re.finditer(r'"origUrl"\s*:\s*"([^"]+)"', st):
                    u = normalize_url(m.group(1).replace('\\/', '/'))
                    accumulation_set.add((u, 'Metadata State Asset', 0, 0))
                for m in re.finditer(r'"img_url"\s*:\s*"([^"]+)"', st):
                    u = normalize_url(m.group(1).replace('\\/', '/'))
                    accumulation_set.add((u, 'Metadata State Asset', 0, 0))

        # Scroll down and trigger lazy-loading
        await page.evaluate("window.scrollBy(0, 1500)")
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        
        # Click "Show more" / "Load more" button if visible
        try:
            more_selectors = [
                "button.FetchMore", ".more-button", ".serp-list__more",
                "button.button2_theme_action", "a.more-items",
                "button:has-text('Show more')", "button:has-text('More')",
                "button:has-text('Load more')", ".serp-loader", ".FetchList-MoreButton"
            ]
            for sel in more_selectors:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await asyncio.sleep(0.3)
                    break
        except Exception:
            pass

        await asyncio.sleep(0.25)

        curr_count = len(accumulation_set)
        if curr_count == last_count:
            no_change_count += 1
            if no_change_count >= 6 and i > 12:
                break
        else:
            no_change_count = 0
            last_count = curr_count

def parse_yandex_request(data: dict):
    url = data.get("url", "").strip()
    if not url:
        raise ValueError("URL is required")

    if not url.startswith("http://") and not url.startswith("https://"):
        if "yandex." in url:
            url = "https://" + url
        else:
            return "yandex.com", url, {}

    u = urlparse(url)
    params = parse_qs(u.query)
    text = (params.get("text") or params.get("query") or params.get("q") or [""])[0].strip()
    if not text:
        text = "wallpaper"

    extra = {k: v[0] for k, v in params.items() if k not in ("text", "query", "q", "p", "format")}
    domain = u.netloc or "yandex.com"
    return domain, text, extra

def build_yandex_url(domain: str, text: str, page: int, extra: dict) -> str:
    params = {"text": text, "p": page}
    params.update(extra)
    return f"https://{domain}/images/search?{urlencode(params)}"

async def scrape_images_core(url, autoscroll=True, max_images=2000, job_id=None):
    """
    Friend's complete Yandex scraping core:
    - Playwright single session with network response interception
    - dups metadata parsing (picks max W x H resolution)
    - DOM + state attribute extraction
    - Automatic pagination buffer continuation to reach up to 2,000 images
    """
    domain, text, extra = parse_yandex_request({"url": url})
    target_count = min(int(max_images), 2000)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = await context.new_page()

        accumulated_data = set()
        network_captured = set()

        # Network response interception (from friend's logic)
        async def handle_response(response):
            try:
                res_url = response.url
                if any(ext in res_url.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp', '.avif', 'avatars.mds.yandex.net']):
                    if '/i?id=' not in res_url and not any(kw in res_url.lower() for kw in SKIP_KEYWORDS):
                        network_captured.add((normalize_url(res_url), 'Network Resource', 0, 0))

                c_type = response.headers.get('content-type', '')
                if 'application/json' in c_type or 'text/plain' in c_type:
                    try:
                        text_resp = await response.text()
                        for m in re.finditer(r'"origUrl"\s*:\s*"([^"]+)"', text_resp):
                            u = normalize_url(m.group(1).replace('\\/', '/'))
                            network_captured.add((u, 'API Response Asset', 0, 0))
                        for m in re.finditer(r'"img_url"\s*:\s*"([^"]+)"', text_resp):
                            u = normalize_url(m.group(1).replace('\\/', '/'))
                            network_captured.add((u, 'API Response Asset', 0, 0))
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", handle_response)

        images = []
        seen_urls = set()

        def add_img(img_u, alt, w=0, h=0):
            if not img_u or img_u.startswith('data:'): return
            if 'avatars.mds.yandex.net' in img_u and '/i?id=' in img_u: return
            if img_u.split('?')[0].lower().endswith('.svg') or any(k in img_u.lower() for k in SKIP_KEYWORDS): return
            
            img_u = normalize_url(img_u)
            try:
                w_val = int(w) if w and w != 'Original' else 0
                h_val = int(h) if h and h != 'Original' else 0
            except Exception:
                w_val, h_val = 0, 0

            if w_val > 0 and h_val > 0:
                if w_val < MIN_IMAGE_DIMENSION or h_val < MIN_IMAGE_DIMENSION:
                    return

            if img_u in seen_urls: return
            seen_urls.add(img_u)

            item = {
                'url': img_u,
                'thumb': img_u,
                'alt': alt or text or 'Visual Asset',
                'width': w_val or 'Original',
                'height': h_val or 'Original',
                'area': w_val * h_val
            }
            images.append(item)

            if job_id:
                with SCRAPE_JOBS_LOCK:
                    jb = SCRAPE_JOBS.get(job_id)
                    if jb:
                        jb["images"].append(item)
                        jb["count"] = len(images)
                        jb["updated_at"] = asyncio.get_event_loop().time()

        pages_to_fetch = 45 if autoscroll and target_count > 50 else 1
        for p_idx in range(0, pages_to_fetch):
            if job_id:
                with SCRAPE_JOBS_LOCK:
                    jb = SCRAPE_JOBS.get(job_id)
                    if not jb or jb.get("status") == "aborted":
                        break
                    if len(images) >= target_count:
                        jb["status"] = "completed"
                        jb["stop_reason"] = "TARGET_REACHED"
                        break

            target_page_url = build_yandex_url(domain, text, p_idx, extra)
            try:
                await page.goto(target_page_url, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(0.3)

                if autoscroll:
                    await auto_scroll_and_extract(page, accumulated_data, job_id=job_id, target_count=target_count, max_scrolls=3)
                
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')

                # --- Metadata & dups multi-resolution parsing (Friend's logic) ---
                best_images = {}
                for is_encoded in [True, False]:
                    q = '&quot;' if is_encoded else '"'
                    pattern = rf'{q}id{q}\s*:\s*{q}([a-zA-Z0-9_-]+){q}.*?({q}origUrl{q}|{q}dups{q}|{q}img_url{q})'
                    for match in re.finditer(pattern, content):
                        img_id = match.group(1)
                        start_pos = match.start()
                        chunk = content[start_pos:start_pos+6000]
                        if is_encoded:
                            chunk = html.unescape(chunk)
                        try:
                            orig_m = re.search(r'"origUrl"\s*:\s*"(.*?)"', chunk)
                            dups_m = re.search(r'"dups"\s*:\s*\[(.*?)]', chunk)
                            w_m = re.search(r'"width"\s*:\s*(\d+)', chunk)
                            h_m = re.search(r'"height"\s*:\s*(\d+)', chunk)

                            cur_best = None
                            cur_w = int(w_m.group(1)) if w_m else 0
                            cur_h = int(h_m.group(1)) if h_m else 0

                            if orig_m:
                                cur_best = orig_m.group(1).replace('\\/', '/')
                            elif dups_m:
                                try:
                                    dups_json = json.loads("[" + dups_m.group(1) + "]")
                                    if dups_json:
                                        valid_dups = [d for d in dups_json if d.get('w', 0) >= MIN_IMAGE_DIMENSION and d.get('h', 0) >= MIN_IMAGE_DIMENSION]
                                        target_list = valid_dups if valid_dups else dups_json
                                        best_dup = max(target_list, key=lambda x: x.get('w', 0) * x.get('h', 0))
                                        cur_best = best_dup.get('url')
                                        cur_w = max(cur_w, best_dup.get('w', 0))
                                        cur_h = max(cur_h, best_dup.get('h', 0))
                                except Exception:
                                    pass

                            if cur_best:
                                cur_best = normalize_url(cur_best)
                                if img_id not in best_images or (cur_w * cur_h) > (best_images[img_id]['w'] * best_images[img_id]['h']):
                                    best_images[img_id] = {'url': cur_best, 'w': cur_w, 'h': cur_h}
                        except Exception:
                            continue

                for img_id, d in best_images.items():
                    add_img(d['url'], 'Highest Quality Asset', d['w'], d['h'])

                # Process accumulated scroll data
                for d in list(accumulated_data):
                    add_img(d[0], d[1], d[2] if len(d)>2 else 0, d[3] if len(d)>3 else 0)

                # Process network captured data
                for d in list(network_captured):
                    add_img(d[0], d[1])

                # Extract DOM links
                for link in soup.find_all('a', class_=['ImagesContentImage-Cover', 'serp-item__link', 'serp-item__item']):
                    try:
                        href = link.get('href')
                        if href and 'img_url=' in href:
                            img_u = parse_qs(urlparse(href).query).get('img_url', [None])[0]
                            if img_u: add_img(unquote(img_u), 'High Res Asset')
                    except Exception:
                        pass

                if len(images) >= target_count:
                    break

            except Exception as pe:
                safe_print(f"[scrape] Page {p_idx} warning: {pe}")

        await browser.close()
        return images[:target_count]

def _run_background_yandex_job(job_id: str, url: str, deep: bool, target_count: int):
    """Runs the friend's Yandex scraper asynchronously in a background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = loop.run_until_complete(scrape_images_core(url, autoscroll=deep, max_images=target_count, job_id=job_id))
    except Exception as e:
        safe_print(f"[job:{job_id}] Scraper thread exception: {e}")
    finally:
        loop.close()

    with SCRAPE_JOBS_LOCK:
        job = SCRAPE_JOBS.get(job_id)
        if job and job["status"] != "completed":
            job["status"] = "completed"
            job["stop_reason"] = "COMPLETED" if job.get("status") != "aborted" else "USER_STOPPED"
            safe_print(f"[job:{job_id}] Scrape job completed with {len(job['images'])} images.")

# --- ROUTES ---

@app.route("/")
def index():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    index_path = os.path.join(root_dir, "index.html")
    accept = request.headers.get("Accept", "")
    if ("text/html" in accept or "application/json" not in accept) and os.path.exists(index_path):
        return send_file(index_path)
    return jsonify({
        "status": "online",
        "service": "Image Scraper Pro Local Backend (Friend Reference Core)",
        "version": "3.0-friend-yandex-2000"
    }), 200

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "3.0-friend-yandex-2000"})

@app.route("/api/pinterest/extract", methods=["POST", "OPTIONS"])
def api_pinterest_extract():
    """Preserved Pinterest Resource & Pin extraction."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json or {}
    url = data.get("url", "").strip()
    max_images = int(data.get("max_images", 1000))
    min_target = int(data.get("min_target", 300))
    if not url:
        return jsonify({"success": False, "error": "Pinterest Pin URL is required"}), 400

    try:
        res = extract_pinterest_resource_api(url, max_images=max_images, min_target=min_target)
        if res.get("success") and len(res.get("images", [])) > 0:
            return jsonify(res), 200
    except Exception as e:
        safe_print(f"[pinterest-api] Resource API extraction warning: {e}")

    res = extract_pinterest_pin(url, max_images=max_images, min_target=min_target)
    status_code = 200 if res.get("success") else 400
    return jsonify(res), status_code

@app.route("/api/count", methods=["POST", "OPTIONS"])
def api_count():
    """Dual-mode count endpoint matching friend's fast_count_images."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    try:
        res = asyncio.run(fast_count_images(url))
        return jsonify(res)
    except Exception as e:
        safe_print(f"[api_count] Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/scrape/start", methods=["POST", "OPTIONS"])
def api_scrape_start():
    """Starts asynchronous streaming scrape job using friend's scraping core."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json or {}
    url = data.get("url", "").strip()
    deep = data.get("autoscroll", True)
    target_count = min(int(data.get("max_images", 2000 if deep else 30)), 2000)
    if not url:
        return jsonify({"error": "URL is required"}), 400

    job_id = str(uuid.uuid4())
    with SCRAPE_JOBS_LOCK:
        SCRAPE_JOBS[job_id] = {
            "job_id": job_id,
            "status": "running",
            "images": [],
            "seen_urls": set(),
            "count": 0,
            "target_count": target_count,
            "started_at": 0,
            "updated_at": 0,
            "stop_reason": None,
        }

    thread = threading.Thread(
        target=_run_background_yandex_job,
        args=(job_id, url, deep, target_count),
        daemon=True
    )
    thread.start()
    return jsonify({"job_id": job_id, "status": "running", "target": target_count})

@app.route("/api/scrape/status", methods=["GET", "OPTIONS"])
def api_scrape_status():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    job_id = request.args.get("job_id")
    since = int(request.args.get("since", 0))

    with SCRAPE_JOBS_LOCK:
        job = SCRAPE_JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        new_images = job["images"][since:]
        return jsonify({
            "status": job["status"],
            "images": new_images,
            "count": len(job["images"]),
            "stop_reason": job.get("stop_reason"),
            "target_count": job.get("target_count", 2000)
        })

@app.route("/api/scrape/stop", methods=["POST", "OPTIONS"])
def api_scrape_stop():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json or {}
    job_id = data.get("job_id") or request.args.get("job_id")
    with SCRAPE_JOBS_LOCK:
        job = SCRAPE_JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        job["status"] = "aborted"
        job["stop_reason"] = "USER_STOPPED"
        count = len(job["images"])

    return jsonify({"status": "aborted", "count": count, "message": f"Scraper stopped with {count} images."})

@app.route("/api/scrape", methods=["POST", "OPTIONS"])
def api_scrape():
    """Friend's direct synchronous scraping endpoint."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json or {}
    url = data.get("url", "").strip()
    deep = data.get("autoscroll", True)
    max_images = min(int(data.get("max_images", 2000 if deep else 30)), 2000)

    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        images = asyncio.run(scrape_images_core(url, autoscroll=deep, max_images=max_images))
        return jsonify({"images": images, "count": len(images)})
    except Exception as e:
        safe_print(f"[api_scrape] Error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/proxy_download", methods=["GET"])
def api_proxy_download():
    """Friend's cached proxy download endpoint with Pillow validation."""
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "URL is required"}), 400
    
    try:
        content, content_type, is_valid, w, h, ext, err = fetch_image_cached(url, min_dim=MIN_IMAGE_DIMENSION, timeout=12)
        if err or not content:
            return jsonify({"error": err or "Failed to fetch image"}), 500
        
        res = send_file(
            io.BytesIO(content),
            mimetype=content_type or "image/jpeg",
            as_attachment=False
        )
        res.headers["Cache-Control"] = "public, max-age=86400"
        if w > 0 and h > 0:
            res.headers["X-Image-Width"] = str(w)
            res.headers["X-Image-Height"] = str(h)
        return res
    except Exception as e:
        safe_print(f"Proxy download failed for {url}: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/download", methods=["POST", "OPTIONS"])
def api_download():
    """High-speed parallel ZIP download endpoint with ZIP_STORED and 64 worker threads."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json or {}
    urls = data.get("urls", [])
    min_dim = data.get("min_dimension", MIN_IMAGE_DIMENSION)
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    import concurrent.futures

    temp_zip_id = uuid.uuid4().hex
    temp_zip_path = os.path.join(TEMP_DIR, f"bulk_download_{temp_zip_id}.zip")
    zip_write_lock = threading.Lock()
    stats = {"success": 0, "skipped": 0, "failed": 0}

    with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_STORED) as zf:
        def process_url(url_index_tuple):
            index, u = url_index_tuple
            try:
                content, content_type, is_valid, w, h, ext, err = fetch_image_cached(u, min_dim=min_dim, timeout=8)
                if not is_valid and w > 0 and h > 0:
                    with zip_write_lock:
                        stats["skipped"] += 1
                    return
                if content:
                    filename = f"image_{index + 1:04d}_{uuid.uuid4().hex[:6]}.{ext or 'jpg'}"
                    with zip_write_lock:
                        zf.writestr(filename, content)
                        stats["success"] += 1
                else:
                    with zip_write_lock:
                        stats["failed"] += 1
            except Exception:
                with zip_write_lock:
                    stats["failed"] += 1

        indexed_urls = list(enumerate(urls))
        worker_count = min(64, max(len(urls), 8))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            list(executor.map(process_url, indexed_urls))

    # Background cleanup of temporary zip file after 10 minutes
    def cleanup_temp_zip(path):
        import time
        time.sleep(600)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
    threading.Thread(target=cleanup_temp_zip, args=(temp_zip_path,), daemon=True).start()

    return send_file(
        temp_zip_path,
        mimetype="application/zip",
        as_attachment=True,
        download_name="downloaded_images.zip"
    )

if __name__ == "__main__":
    safe_print("=" * 60)
    safe_print("  Image Scraper Pro (Friend's Core Engine) — http://localhost:5000")
    safe_print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False)
