import os
import sys
import asyncio
import uuid
import zipfile
import io
import requests
import httpx
import re
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse, parse_qs, urljoin
from requests.utils import requote_uri

# Fix Windows asyncio event loop policy for Playwright compatibility
# Without this, Playwright crashes on Windows with "no running event loop" errors
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

def run_async(coro):
    """Run an async coroutine safely in a brand-new event loop.
    Flask routes are synchronous; Playwright needs its own fresh loop on Windows.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# Safe print helper to prevent terminal encoding crashes on Windows (cp1252/charmap)
def print(*args, **kwargs):
    import builtins
    try:
        builtins.print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = [str(arg).encode('ascii', errors='replace').decode('ascii') for arg in args]
        builtins.print(*safe_args, **kwargs)

def normalize_url(url):
    if not url: return url
    if url.startswith('//'): url = 'https:' + url
    
    # 1. Yandex CDN URLs (avatars.mds.yandex.net)
    if 'avatars.mds.yandex.net' in url or 'get-shedevrum' in url:
        # Standard pattern: .../get-XXX/123/abc/suffix
        if '/get-' in url:
            parts = url.split('/')
            if len(parts) >= 6:
                # The last part is the size/optimization (e.g., 'small', '300x300', 'orig')
                last_part_full = parts[-1]
                # Remove any query parameters from the last part
                last_part = last_part_full.split('?')[0]
                
                # Check if it's already original or if it's a known size that can be upgraded
                if last_part not in ['orig', 'original']:
                    # We can safely replace the last part with 'orig' for most Yandex 'get-' services
                    parts[-1] = 'orig'
                    url = '/'.join(parts)
        elif '/get-shedevrum/' in url:
            if not url.endswith('/orig') and not '?' in url.split('/')[-1]:
                url = url.rstrip('/') + '/orig'

    # 2. Pinterest: /736x/ -> /originals/
    if 'pinimg.com' in url:
        if '/736x/' in url:
            url = url.replace('/736x/', '/originals/')
        elif '/236x/' in url:
            url = url.replace('/236x/', '/originals/')

    # 3. Strip common resizing query parameters from any source URL
    try:
        from urllib.parse import urlparse, parse_qs, urlunparse, urlencode
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        
        # Common resize/quality params to remove
        params_to_remove = ['w', 'h', 'width', 'height', 'size', 'quality', 'q', 'resize', 'fit', 'n']
        modified = False
        for p in params_to_remove:
            if p in qs:
                # Only remove if it's not a critical ID param (usually single letter or short)
                # But 'w' and 'h' are almost always sizes.
                del qs[p]
                modified = True
        
        if modified:
            new_query = urlencode(qs, doseq=True)
            url = urlunparse(parsed._replace(query=new_query))
    except Exception:
        pass

    # 4. Google User Content
    if 'googleusercontent.com' in url:
        # Upgrade =s900 or =s400 to =s0 (original) or a large size
        if '=' in url.split('/')[-1]:
            url = re.sub(r'=s\d+.*$', '=s0', url)
        else:
            url = re.sub(r'\/s\d+(-c)?\/', '/s4096/', url)

    return url

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

# Directory for temporary downloads
TEMP_DIR = "temp_downloads"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

# ---------------------------------------------------------------------------
# Fast Image Counter — httpx (no browser) + optional Playwright fallback
# ---------------------------------------------------------------------------
SKIP_EXTENSIONS = {'.svg', '.ico', '.gif'}
SKIP_KEYWORDS = ['favicon', 'logo', 'icon', 'spinner', 'tracker', 'pixel',
                  'doubleclick', 'analytics', 'metrika', 'badge', 'spacer']

def _is_countable_url(url: str) -> bool:
    """Return True if url looks like a real image (not a UI chrome asset)."""
    if not url or url.startswith('data:'):
        return False
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
        return False
    url_lower = url.lower()
    if any(kw in url_lower for kw in SKIP_KEYWORDS):
        return False
    return True

async def fast_count_images(url: str) -> dict:
    """
    Phase 1 — httpx (no browser, fast ~1-3 s):
      Fetches raw HTML and counts every img src / srcset / data-* src / og:image.
    Phase 2 — Playwright fallback (only if page appears JS-rendered):
      Launches browser with NO scrolling, grabs DOM after initial load.
    Returns a dict with counts broken down by source type.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }

    static_html = ''
    fetch_ok     = False
    fetch_method = 'httpx'

    # ── Phase 1: fast static fetch ──────────────────────────────────────────
    try:
        async with httpx.AsyncClient(headers=headers, follow_redirects=True,
                                     timeout=12) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            static_html = resp.text
            fetch_ok = True
    except Exception as e:
        print(f"[count] httpx fetch failed: {e}")

    # ── Detect JS-rendered pages (very few imgs in raw HTML) ────────────────
    needs_browser = False
    if fetch_ok:
        quick_soup = BeautifulSoup(static_html, 'lxml')
        raw_img_count = len(quick_soup.find_all('img'))
        # Heuristic: if <5 imgs and page has heavy JS markers → needs browser
        js_markers = ['__NEXT_DATA__', 'window.__INITIAL_STATE__',
                      'window.YM', '__reactFiber', 'ng-version', 'data-react']
        has_js_markers = any(m in static_html for m in js_markers)
        needs_browser = raw_img_count < 5 and has_js_markers
    else:
        needs_browser = True   # fetch failed entirely → try browser

    # ── Phase 2: Playwright (no scroll, just initial DOM) ───────────────────
    js_html = ''
    if needs_browser:
        fetch_method = 'playwright'
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                ctx = await browser.new_context(
                    user_agent=headers['User-Agent'])
                page = await ctx.new_page()
                await page.goto(url, wait_until='domcontentloaded', timeout=30000)
                await asyncio.sleep(2)   # let initial JS settle
                js_html = await page.content()
                await browser.close()
        except Exception as e:
            print(f"[count] Playwright fallback failed: {e}")

    html_to_parse = js_html if js_html else static_html
    if not html_to_parse:
        return {'total': 0, 'breakdown': {}, 'method': fetch_method,
                'note': 'Could not fetch page'}

    soup = BeautifulSoup(html_to_parse, 'lxml')
    base = '{uri.scheme}://{uri.netloc}'.format(uri=urlparse(url))

    seen   = set()
    counts = {'img_src': 0, 'srcset': 0, 'data_src': 0,
              'og_image': 0, 'link_href': 0, 'css_bg': 0}

    def add(src: str, bucket: str):
        if not src:
            return
        src = src.strip().split()[0]   # handle srcset descriptors
        if src.startswith('//'):
            src = 'https:' + src
        elif src.startswith('/'):
            src = base + src
        if src in seen:
            return
        if _is_countable_url(src):
            seen.add(src)
            counts[bucket] += 1

    # img[src]
    for tag in soup.find_all('img', src=True):
        add(tag['src'], 'img_src')

    # img[srcset]  /  source[srcset]
    for tag in soup.find_all(['img', 'source'], srcset=True):
        for part in tag['srcset'].split(','):
            candidate = part.strip().split()[0]
            add(candidate, 'srcset')

    # data-src / data-original / data-lazy-src (lazy-load patterns)
    for attr in ('data-src', 'data-original', 'data-lazy-src',
                 'data-lazy', 'data-echo', 'data-url'):
        for tag in soup.find_all(attrs={attr: True}):
            add(tag[attr], 'data_src')

    # og:image / twitter:image meta tags
    for tag in soup.find_all('meta'):
        prop = tag.get('property', '') + tag.get('name', '')
        if 'image' in prop.lower():
            add(tag.get('content', ''), 'og_image')

    # <a href="..."> wrapping images (Yandex / Pinterest style)
    for tag in soup.find_all('a', href=True):
        href = tag['href']
        # only count if the link itself looks like an image file
        ext = urlparse(href).path.lower().split('.')[-1]
        if ext in ('jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'tiff', 'avif'):
            add(href, 'link_href')
        # also extract img_url query param (Yandex)
        qs = parse_qs(urlparse(href).query)
        img_url_val = (qs.get('img_url') or [])
        if img_url_val:
            add(unquote(img_url_val[0]), 'link_href')

    # Inline CSS background-image: url(...)
    bg_pattern = re.compile(r'url\([\'"]?(https?://[^)\'"]+)[\'"]?\)', re.I)
    for tag in soup.find_all(style=True):
        for m in bg_pattern.finditer(tag['style']):
            add(m.group(1), 'css_bg')
    # Also scan <style> blocks
    for style_tag in soup.find_all('style'):
        for m in bg_pattern.finditer(style_tag.get_text()):
            add(m.group(1), 'css_bg')

    total = len(seen)
    return {
        'total':     total,
        'breakdown': {k: v for k, v in counts.items() if v > 0},
        'method':    fetch_method,
        'note':      'Browser render used' if needs_browser else 'Static HTML scan',
    }

@app.route('/api/count', methods=['POST'])
def api_count():
    """Fast image count endpoint — returns total + breakdown in ~2-5 s."""
    data = request.json or {}
    url  = data.get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    try:
        result = run_async(fast_count_images(url))
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

async def auto_scroll(page, accumulation_set, max_scrolls=15):
    last_height = await page.evaluate("document.body.scrollHeight")
    
    for i in range(max_scrolls):
        # JS evaluation to find both thumbnails and high-res links
        current_data = await page.evaluate("""
            () => {
                const results = [];
                // Target links that usually wrap gallery images
                const links = document.querySelectorAll('a[href*="img_url="], a.ImagesContentImage-Cover, a.serp-item__link');
                links.forEach(a => {
                    let highRes = null;
                    try {
                        const urlParams = new URL(a.href, window.location.origin).searchParams;
                        highRes = urlParams.get('img_url');
                    } catch(e) {}
                    const img = a.querySelector('img');
                    if (img || highRes) {
                        results.push({ 
                            url: highRes || img?.src, 
                            alt: img?.alt || "", 
                            isHighRes: !!highRes 
                        });
                    }
                });

                // Also get all images not inside those links
                const allImgs = document.querySelectorAll('img');
                allImgs.forEach(img => {
                    if (!img.closest('a[href*="img_url="]')) {
                        results.push({ url: img.src, alt: img.alt || "", isHighRes: false });
                    }
                });
                return results;
            }
        """)
        
        for item in current_data:
            url = item['url']
            if url and not url.startswith('data:') and not 'spacer.gif' in url:
                # Add normalized URL
                norm_url = normalize_url(url)
                accumulation_set.add((norm_url, item['alt'], item['isHighRes']))

        await page.evaluate("window.scrollBy(0, window.innerHeight * 1.5)")
        await asyncio.sleep(1.0)
        
        # Click the "Show more" button if it appears to allow infinite scroll to resume
        try:
            button_selector = 'button.FetchListButton-Button, .FetchListButton-Button, .more-button'
            button_loc = page.locator(button_selector)
            if await button_loc.is_visible():
                print("[auto_scroll] Found 'Show more' button, clicking it...")
                await button_loc.click()
                await asyncio.sleep(1.5)  # Wait for new content to load
        except Exception as e:
            pass

        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height and i > 5: break
        last_height = new_height

async def scrape_images(url, autoscroll=True):
    async with async_playwright() as p:
        # Use a real-looking user agent
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        accumulated_data = set() # Store (url, alt) tuples
        
        try:
            print(f"Scraping URL: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Initial wait
            await asyncio.sleep(2)
            
            if autoscroll:
                await auto_scroll(page, accumulated_data, max_scrolls=45)
            else:
                await page.evaluate("window.scrollTo(0, 800)") 
                await asyncio.sleep(2)
        except Exception as e:
            print(f"Page load/scroll failed: {e}")
        
        # Final extraction from DOM content
        content = await page.content()
        await browser.close()
        
        soup = BeautifulSoup(content, 'html.parser')
        images = []
        seen_urls = set()

        # Helper to add image if unique and high quality
        def add_img(url, alt, w=0, h=0):
            if not url or url.startswith('data:'): return
            
            # Skip low-res Yandex search grid thumbnails
            if 'avatars.mds.yandex.net' in url and '/i?id=' in url:
                return
                
            # Skip SVGs, web icons, tracking pixels, or standard small logos
            if url.split('?')[0].endswith('.svg') or any(k in url.lower() for k in ['favicon', '/tracker', 'pixel.gif', 'doubleclick', 'google-analytics', 'yandex.ru/metrika', 'logo', 'spinner', 'icon']):
                return
                
            url = normalize_url(url)
            
            # Try to convert w/h to int
            try:
                w_val = int(w) if w and w != 'Original' else 0
                h_val = int(h) if h and h != 'Original' else 0
            except:
                w_val, h_val = 0, 0

            # Deduplication: if we already have this URL, don't add again
            if url in seen_urls: return
            seen_urls.add(url)
            
            images.append({
                'url': url, 
                'alt': alt, 
                'width': w_val or 'Original', 
                'height': h_val or 'Original',
                'area': w_val * h_val
            })

        # --- Yandex Metadata Extraction (Highest Resolution) ---
        import html
        import json
        
        # Dictionary to store best version of each image ID: {id: {url, w, h, alt}}
        best_images = {}

        # 1. Search for JSON-like objects in the content (often entity encoded)
        # We look for "id":"..." and "origUrl":"..." or "dups":[...]
        # Pattern to find items that look like image metadata objects
        # They usually start with {"id":"..." or &quot;id&quot;:&quot;...
        
        # Try both encoded and unencoded
        for is_encoded in [True, False]:
            q = '&quot;' if is_encoded else '"'
            # Look for ID and then either origUrl or dups within a reasonable range
            # Yandex items are usually within a few thousand characters
            pattern = rf'{q}id{q}\s*:\s*{q}([a-f0-9]{{32}}){q}.*?({q}origUrl{q}|{q}dups{q})'
            matches = re.finditer(pattern, content)
            
            for match in matches:
                img_id = match.group(1)
                start_pos = match.start()
                # Find the boundaries of this object (approximate)
                # Usually it's inside {...}
                # We'll take a chunk and try to find the complete JSON
                chunk = content[start_pos:start_pos+5000]
                
                # Unescape if needed
                if is_encoded:
                    chunk = html.unescape(chunk)
                
                # Try to find a valid JSON object starting from {
                # Since we started at "id", let's backtrack to find {
                # Or just construct a minimal JSON if we can find the keys
                
                try:
                    # Simple extraction: find origUrl and dimensions directly if JSON parsing is too hard
                    orig_match = re.search(r'"origUrl":"(.*?)"', chunk)
                    dups_match = re.search(r'"dups":\[(.*?)]', chunk)
                    w_match = re.search(r'"width":(\d+)', chunk)
                    h_match = re.search(r'"height":(\d+)', chunk)
                    
                    current_best_url = None
                    current_w = int(w_match.group(1)) if w_match else 0
                    current_h = int(h_match.group(1)) if h_match else 0
                    
                    if orig_match:
                        current_best_url = orig_match.group(1).replace('\\/', '/')
                    elif dups_match:
                        try:
                            dups_json = json.loads("[" + dups_match.group(1) + "]")
                            if dups_json:
                                best_dup = max(dups_json, key=lambda x: x.get('w', 0) * x.get('h', 0))
                                current_best_url = best_dup.get('url')
                                current_w = max(current_w, best_dup.get('w', 0))
                                current_h = max(current_h, best_dup.get('h', 0))
                        except: pass
                    
                    if current_best_url:
                        # Normalize early
                        current_best_url = normalize_url(current_best_url)
                        
                        if img_id not in best_images:
                            best_images[img_id] = {'url': current_best_url, 'w': current_w, 'h': current_h}
                        else:
                            # Keep the one with larger area
                            old = best_images[img_id]
                            if (current_w * current_h) > (old['w'] * old['h']):
                                best_images[img_id] = {'url': current_best_url, 'w': current_w, 'h': current_h}
                except: continue

        # Add the best versions found from metadata
        for img_id, data in best_images.items():
            add_img(data['url'], 'Highest Quality Asset', data['w'], data['h'])
        
        print(f"Extracted {len(best_images)} unique high-res images from metadata.")

        # 0. Check the target URL itself for a source image (CBIR)
        try:
            parsed_target = urlparse(url)
            target_qs = parse_qs(parsed_target.query)
            img_url_vals = target_qs.get('img_url') or target_qs.get('url') or []
            source_search_url = img_url_vals[0] if img_url_vals else None
            if source_search_url:
                add_img(unquote(source_search_url), 'Search Source (Original)')
        except: pass

        # 0.1 Specifically look for CBIR/Source image in DOM
        try:
            source_link = soup.find('a', class_='CbirItem-Link') or soup.find('a', class_='CbirHeader-Image')
            if source_link:
                href = source_link.get('href')
                if href and 'img_url=' in href:
                    src = parse_qs(urlparse(href).query).get('img_url', [None])[0]
                    if src: add_img(unquote(src), 'Source Image (High Res)')
                else:
                    img = source_link.find('img')
                    if img: add_img(img.get('src'), 'Source Image')
        except: pass

        # 1. Process accumulated images (captured during scroll)
        # These are usually links with img_url params
        for data in list(accumulated_data):
            url, alt = data[0], data[1]
            # Skip low-res Yandex thumbnails captured during scrolling
            if 'avatars.mds.yandex.net' in url and '/i?id=' in url:
                continue
            add_img(url, alt)

        # 2. Extract from final DOM (BS4) - especially links
        for link in soup.find_all('a', class_=['ImagesContentImage-Cover', 'serp-item__link', 'serp-item__item']):
            try:
                href = link.get('href')
                if href and 'img_url=' in href:
                    img_url = parse_qs(urlparse(href).query).get('img_url', [None])[0]
                    if img_url:
                        add_img(unquote(img_url), 'High Res Asset')
            except: pass

        # 3. Fallback: all images (Filter out small ones if possible)
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-original')
            if not src: continue
            
            # Skip common UI icons or very small thumbnails
            if 'icon' in src.lower() or 'logo' in src.lower() or 'spinner' in src.lower(): continue
            
            # If it's a Yandex thumbnail, we prefer the metadata version
            if 'avatars.mds.yandex.net' in src and '/i?id=' in src:
                # Skip thumbnail fallbacks since we extract high-res equivalents from metadata
                continue
                
            add_img(src, img.get('alt', ''))
        
        print(f"Total unique images found: {len(images)}")
        return images

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/api/scrape', methods=['POST'])
def api_scrape():
    data = request.json
    url = data.get('url')
    autoscroll = data.get('autoscroll', True)
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    try:
        images = run_async(scrape_images(url, autoscroll=autoscroll))
        return jsonify({'images': images})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/proxy_download', methods=['GET'])
def api_proxy_download():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    
    try:
        # URL encode to avoid unicode header issues
        ascii_url = requote_uri(url)
        # Fetch the image through the backend to bypass CORS
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Referer': ascii_url
        }
        response = requests.get(ascii_url, headers=headers, timeout=15, stream=True)
        response.raise_for_status()
        
        # Determine content type and suggested filename
        content_type = response.headers.get('Content-Type', 'image/jpeg')
        
        return send_file(
            io.BytesIO(response.content),
            mimetype=content_type,
            as_attachment=False # Browser will handle download with its own filename or our 'a' tag attribute
        )
    except Exception as e:
        print(f"Proxy download failed for {url}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.json
    urls = data.get('urls', [])
    if not urls:
        return jsonify({'error': 'No URLs provided'}), 400
    
    import concurrent.futures
    
    def download_image(url_index_tuple):
        index, url = url_index_tuple
        try:
            # URL encode to avoid unicode header issues
            ascii_url = requote_uri(url)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Referer': ascii_url
            }
            response = requests.get(ascii_url, headers=headers, timeout=12)
            if response.status_code == 200:
                ext = url.split('.')[-1].split('?')[0].lower()
                if not ext or len(ext) > 4 or not ext.isalnum():
                    ext = 'jpg'
                return index, response.content, ext
        except Exception as e:
            print(f"Parallel fetch failed for {url}: {e}")
        return index, None, None

    indexed_urls = list(enumerate(urls))
    downloaded_data = {}
    
    # Run requests concurrently using up to 12 workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        results = executor.map(download_image, indexed_urls)
        for index, content, ext in results:
            if content:
                downloaded_data[index] = (content, ext)

    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for index, url in indexed_urls:
            if index in downloaded_data:
                content, ext = downloaded_data[index]
                filename = f"image_{index + 1}_{uuid.uuid4().hex[:6]}.{ext}"
                zf.writestr(filename, content)
                
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='downloaded_images.zip'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)
