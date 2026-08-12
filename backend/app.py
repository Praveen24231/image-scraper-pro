"""
Fast Yandex Image Scraper Backend
- No Playwright/browser needed
- Scrapes via requests from your real IP (no captcha)
- 30 images/page × 34 pages = 1000+ images in parallel
- Run: python app.py
"""
import re
import io
import zipfile
import concurrent.futures
from html import unescape
from urllib.parse import urlparse, urlencode, parse_qs

import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

MAX_DOWNLOAD_URLS = 2000  # Safety cap to prevent memory exhaustion

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


import threading
import time

def start_keep_alive():
    """Background thread that pings Render health endpoint every 4 minutes to prevent sleep."""
    def ping_loop():
        time.sleep(10)
        while True:
            try:
                requests.get("https://image-scraper-pro.onrender.com/api/health", timeout=10)
                print("[keep-alive] Self-ping successful")
            except Exception as e:
                print(f"[keep-alive] Ping failed: {e}")
            time.sleep(240)  # Ping every 4 minutes (Render sleeps after 15m)

    t = threading.Thread(target=ping_loop, daemon=True)
    t.start()

start_keep_alive()


def fetch_page(url: str, timeout=6) -> str:
    """Fetch a Yandex Images page. Returns raw HTML or empty string."""
    try:
        r = SESSION.get(url, timeout=timeout, allow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[fetch] Failed {url[:80]}: {e}")
        return ""


ORIGURL_RE = re.compile(r'"origUrl"\s*:\s*"(https?[^"]+)"')
CDN_RE     = re.compile(r'https://avatars\.mds\.yandex\.net/[^\s"\'<>\\,\)]+')


def extract_orig_urls(html: str) -> list:
    """Extract original image URLs from Yandex HTML (entity-decoded)."""
    if not html:
        return []

    decoded = unescape(html)
    seen = set()
    results = []

    # Primary: origUrl fields
    for m in ORIGURL_RE.finditer(decoded):
        url = m.group(1).replace("\\/", "/")
        if url not in seen and url.startswith("http"):
            seen.add(url)
            results.append(url)

    # Fallback: Yandex CDN thumbnails → upgrade to /orig
    if len(results) < 5:
        for m in CDN_RE.finditer(decoded):
            raw = m.group(0).split("?")[0]
            parts = raw.split("/")
            if len(parts) >= 5:
                if parts[-1] not in ("orig", "original"):
                    parts[-1] = "orig"
                upgraded = "/".join(parts)
                if upgraded not in seen:
                    seen.add(upgraded)
                    results.append(upgraded)

    return results


def build_yandex_url(domain: str, text: str, page: int, extra: dict) -> str:
    params = {"text": text, "p": page}
    params.update(extra)
    return f"https://{domain}/images/search?{urlencode(params)}"


def scrape_yandex(domain: str, text: str, extra: dict, max_pages=34) -> list:
    """Scrape up to max_pages in high-speed parallel workers (16 threads)."""
    all_urls = []
    seen = set()

    def fetch_page_urls(page: int):
        url = build_yandex_url(domain, text, page, extra)
        html = fetch_page(url, timeout=6)
        return extract_orig_urls(html)

    # Page 0 first (fast initial result)
    page0 = fetch_page_urls(0)
    for u in page0:
        if u not in seen:
            seen.add(u)
            all_urls.append(u)

    if max_pages <= 1:
        return all_urls

    # Pages 1..max_pages in parallel (16 high-speed workers)
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(fetch_page_urls, p): p for p in range(1, max_pages)}
        for future in concurrent.futures.as_completed(futures):
            try:
                urls = future.result()
                for u in urls:
                    if u not in seen:
                        seen.add(u)
                        all_urls.append(u)
            except Exception:
                pass

    return all_urls


def parse_yandex_request(data: dict):
    """Parse and validate a Yandex scrape request. Returns (domain, text, extra) or raises."""
    url  = data.get("url", "").strip()
    if not url:
        raise ValueError("URL is required")
    u = urlparse(url)
    if "yandex" not in u.netloc:
        raise ValueError("Only Yandex Images URLs are supported")
    params = parse_qs(u.query)
    text   = (params.get("text") or params.get("query") or [""])[0].strip()
    if not text:
        raise ValueError("No search text found in URL. Example: https://yandex.com/images/search?text=cats")
    extra  = {k: v[0] for k, v in params.items() if k not in ("text", "p", "format")}
    domain = u.netloc
    return domain, text, extra


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/api/count", methods=["POST", "OPTIONS"])
def api_count():
    """Fast count — scrapes only page 0 and returns image count + breakdown."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json or {}
    try:
        domain, text, extra = parse_yandex_request(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        urls = scrape_yandex(domain, text, extra, max_pages=1)
        breakdown = {}
        for u in urls:
            ext = u.split(".")[-1].split("?")[0].lower()[:4]
            key = ext if ext in ("jpg", "jpeg", "png", "webp", "avif") else "other"
            breakdown[key] = breakdown.get(key, 0) + 1
        print(f"[count] {len(urls)} images for '{text}'")
        return jsonify({"count": len(urls), "breakdown": breakdown})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/scrape", methods=["POST", "OPTIONS"])
def api_scrape():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json or {}
    deep = data.get("autoscroll", True)

    try:
        domain, text, extra = parse_yandex_request(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    max_pages = 34 if deep else 1
    try:
        urls = scrape_yandex(domain, text, extra, max_pages=max_pages)
        images = [{"url": u, "thumb": u, "alt": "", "width": "Original", "height": "Original"} for u in urls]
        print(f"[scrape] Found {len(images)} images for '{text}'")
        return jsonify({"images": images})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download", methods=["POST", "OPTIONS"])
def api_download():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json or {}
    urls = data.get("urls", [])
    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    # Safety cap — prevent memory exhaustion from huge lists
    if len(urls) > MAX_DOWNLOAD_URLS:
        urls = urls[:MAX_DOWNLOAD_URLS]
        print(f"[download] Capped at {MAX_DOWNLOAD_URLS} URLs")

    dl_headers = {
        "User-Agent": HEADERS["User-Agent"],
        "Referer": "https://yandex.com/",
    }

    def download_one(indexed):
        idx, url = indexed
        try:
            r = SESSION.get(url, headers=dl_headers, timeout=15, stream=False)
            if r.status_code == 200 and len(r.content) > 500:
                ext = url.split(".")[-1].split("?")[0].lower()
                if ext not in ("jpg", "jpeg", "png", "webp", "avif", "bmp", "gif"):
                    ext = "jpg"
                return idx, r.content, ext
        except Exception:
            pass
        return idx, None, None

    memory_file = io.BytesIO()
    ok = 0
    print(f"[download] Starting ZIP of {len(urls)} images (12 workers)...")
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            for idx, content, ext in pool.map(download_one, enumerate(urls)):
                if content:
                    zf.writestr(f"image_{idx+1:04d}.{ext}", content)
                    ok += 1
                    if ok % 50 == 0:
                        print(f"[download] Packaged {ok}/{len(urls)}...")

    memory_file.seek(0)
    print(f"[download] Zipped {ok}/{len(urls)} images")
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name="yandex_images.zip",
    )


@app.route("/api/proxy_download")
def api_proxy_download():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Missing url"}), 400
    try:
        r = SESSION.get(url, headers={"Referer": "https://yandex.com/"}, timeout=15)
        r.raise_for_status()
        ct = r.headers.get("Content-Type", "image/jpeg")

        # Derive a clean filename from the URL
        path_part = url.split("?")[0].rstrip("/").split("/")[-1] or "image"
        if "." not in path_part[-5:]:
            ext = ct.split("/")[-1].split(";")[0].strip() or "jpg"
            path_part = f"{path_part}.{ext}"

        response = send_file(io.BytesIO(r.content), mimetype=ct)
        response.headers["Content-Disposition"] = f'attachment; filename="{path_part}"'
        return response
    except Exception as e:
        return jsonify({"error": str(e)}), 404


if __name__ == "__main__":
    print("=" * 60)
    print("  Yandex Image Scraper Backend — starting on port 5000")
    print("  Open: http://localhost:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False)
