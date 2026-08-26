import uuid
import re
import io
import zipfile
import concurrent.futures
from html import unescape
from urllib.parse import urlparse, urlencode, parse_qs, unquote

import requests
import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from pinterest_scraper import extract_pinterest_pin
from pinterest_resource_scraper import extract_pinterest_resource_api


app = Flask(__name__, static_folder="static", static_url_path="")
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

# In-memory background jobs registry for progressive streaming
SCRAPE_JOBS = {}
SCRAPE_JOBS_LOCK = threading.Lock()

def start_job_cleanup_loop():
    """Periodically removes jobs older than 20 minutes to prevent memory leaks."""
    def cleanup():
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
IMGURL_PARAM_RE = re.compile(r'img_url=([^&"\'<>\s]+)')
CDN_RE     = re.compile(r'https://avatars\.mds\.yandex\.net/[^\s"\'<>\\,\)]+')


def canonicalize_yandex_url(url: str) -> str:
    """Normalizes Yandex image URLs, upgrades CDN thumbnails to full-res /orig, and strips tracking params."""
    if not url:
        return ""
    clean = url.replace("\\/", "/").strip()
    if "avatars.mds.yandex.net" in clean:
        raw = clean.split("?")[0]
        parts = raw.split("/")
        if len(parts) >= 5:
            if parts[-1] not in ("orig", "original"):
                parts[-1] = "orig"
            return "/".join(parts)
        return raw
    if "?" in clean:
        base, query = clean.split("?", 1)
        params = parse_qs(query)
        filtered_params = {k: v for k, v in params.items() if k not in ("nii", "pos", "rpt", "lr", "cst", "redircnt")}
        if filtered_params:
            return f"{base}?{urlencode(filtered_params, doseq=True)}"
        return base
    return clean


def extract_orig_urls(html: str) -> list:
    """Extract original image URLs from Yandex HTML (entity-decoded)."""
    if not html:
        return []

    decoded = unescape(html)
    seen = set()
    results = []

    # Primary: origUrl fields
    for m in ORIGURL_RE.finditer(decoded):
        url = canonicalize_yandex_url(m.group(1))
        if url not in seen and url.startswith("http"):
            seen.add(url)
            results.append(url)

    # Secondary: img_url parameters from dynamic serp image cards
    for m in IMGURL_PARAM_RE.finditer(decoded):
        raw_u = m.group(1)
        try:
            url = canonicalize_yandex_url(unquote(raw_u))
            if url not in seen and url.startswith("http"):
                seen.add(url)
                results.append(url)
        except Exception:
            pass

    # Tertiary: Yandex CDN thumbnails → upgrade to /orig
    for m in CDN_RE.finditer(decoded):
        upgraded = canonicalize_yandex_url(m.group(0))
        if upgraded not in seen and upgraded.startswith("http"):
            seen.add(upgraded)
            results.append(upgraded)

    return results


def build_yandex_url(domain: str, text: str, page: int, extra: dict) -> str:
    params = {"text": text, "p": page}
    params.update(extra)
    return f"https://{domain}/images/search?{urlencode(params)}"


def scrape_yandex_playwright(target_url: str, max_images: int = 2000, deep: bool = True) -> list:
    """Headless Chromium Playwright scraper for deep Yandex SERP extraction up to max_images."""
    from playwright.sync_api import sync_playwright
    print(f"[playwright] Launching Chromium browser for: {target_url[:80]} (target={max_images}, deep={deep})...")
    collected_urls = []
    seen = set()
    
    # Detailed pipeline counters
    metrics = {
        "raw_candidates": 0,
        "dom_img_urls": 0,
        "json_orig_urls": 0,
        "cdn_upgraded_urls": 0,
        "rejected_invalid": 0,
        "duplicates_removed": 0,
        "final_images": 0
    }
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                ]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=12000)
            except Exception as e:
                print(f"[playwright] Navigation notice: {e}")
            page.wait_for_timeout(800)

            def extract_batch():
                added = 0
                dom_urls = page.evaluate("""() => {
                    const urls = [];
                    document.querySelectorAll('a[href*="img_url="]').forEach(a => {
                        try {
                            const u = new URL(a.href);
                            const raw = u.searchParams.get('img_url');
                            if (raw) { urls.push(decodeURIComponent(raw)); }
                        } catch(e) {}
                    });
                    return urls;
                }""")
                for u in dom_urls:
                    metrics["raw_candidates"] += 1
                    metrics["dom_img_urls"] += 1
                    clean_u = canonicalize_yandex_url(u)
                    if not clean_u.startswith("http"):
                        metrics["rejected_invalid"] += 1
                        continue
                    if clean_u in seen:
                        metrics["duplicates_removed"] += 1
                        continue
                    seen.add(clean_u)
                    collected_urls.append(clean_u)
                    added += 1

                html = page.content()
                decoded = unescape(html)
                for m in ORIGURL_RE.finditer(decoded):
                    metrics["raw_candidates"] += 1
                    metrics["json_orig_urls"] += 1
                    u = canonicalize_yandex_url(m.group(1))
                    if not u.startswith("http"):
                        metrics["rejected_invalid"] += 1
                        continue
                    if u in seen:
                        metrics["duplicates_removed"] += 1
                        continue
                    seen.add(u)
                    collected_urls.append(u)
                    added += 1

                for m in CDN_RE.finditer(decoded):
                    metrics["raw_candidates"] += 1
                    upgraded = canonicalize_yandex_url(m.group(0))
                    metrics["cdn_upgraded_urls"] += 1
                    if upgraded in seen:
                        metrics["duplicates_removed"] += 1
                        continue
                    seen.add(upgraded)
                    collected_urls.append(upgraded)
                    added += 1

                return added

            # Initial extract
            extract_batch()

            if deep:
                t_scroll_start = time.time()
                max_scroll_time = 35.0
                consecutive_idle = 0
                scroll_count = 0
                
                while time.time() - t_scroll_start < max_scroll_time and len(collected_urls) < max_images:
                    scroll_count += 1
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(450)

                    # Click "show more" button if visible
                    page.evaluate("""() => {
                        const btn = document.querySelector('.more__button, .button_theme_action, .more__btn, [data-bem*="more"], .FetchList-MoreButton, .Button2_view_action');
                        if (btn && btn.offsetParent !== null) { btn.click(); }
                    }""")

                    added = extract_batch()
                    if added == 0:
                        consecutive_idle += 1
                        page.wait_for_timeout(350)
                        added = extract_batch()
                        if added > 0:
                            consecutive_idle = 0
                        elif consecutive_idle >= 4:
                            print(f"[playwright] End of SERP reached ({consecutive_idle} consecutive idle cycles at scroll {scroll_count})")
                            break
                    else:
                        consecutive_idle = 0

            browser.close()
            metrics["final_images"] = len(collected_urls[:max_images])
            print(f"[playwright] Pipeline report: raw={metrics['raw_candidates']}, dom={metrics['dom_img_urls']}, origUrl={metrics['json_orig_urls']}, cdn={metrics['cdn_upgraded_urls']}, dups_removed={metrics['duplicates_removed']}, final={metrics['final_images']}")
            print(f"[playwright] Successfully extracted {len(collected_urls[:max_images])} unique high-res images via Playwright")
    except Exception as e:
        print(f"[playwright] Error during rendering: {e}")
    return collected_urls[:max_images]


def _run_background_yandex_scrape(job_id: str, domain: str, text: str, extra: dict, target_count: int = 2000):
    """Background worker that queries multiple Yandex SERP pages and expands results up to target_count."""
    print(f"[job:{job_id}] Background scraper started for query '{text}' (target={target_count})")
    consecutive_empty = 0
    max_pages = 75
    batch_size = 5

    for batch_start in range(1, max_pages, batch_size):
        with SCRAPE_JOBS_LOCK:
            job = SCRAPE_JOBS.get(job_id)
            if not job or job.get("status") == "aborted":
                return
            if len(job["images"]) >= target_count:
                job["status"] = "completed"
                job["stop_reason"] = "TARGET_REACHED"
                job["updated_at"] = time.time()
                return

        page_indices = list(range(batch_start, min(batch_start + batch_size, max_pages)))
        
        def fetch_single_page(p_idx):
            p_url = build_yandex_url(domain, text, p_idx, extra)
            html = fetch_page(p_url, timeout=7)
            return extract_orig_urls(html)

        new_batch_urls = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=batch_size) as executor:
            page_results = executor.map(fetch_single_page, page_indices)
            for urls in page_results:
                for u in urls:
                    canon = canonicalize_yandex_url(u)
                    if canon.startswith("http"):
                        new_batch_urls.append(canon)

        added_in_batch = 0
        with SCRAPE_JOBS_LOCK:
            job = SCRAPE_JOBS.get(job_id)
            if not job:
                return
            for u in new_batch_urls:
                if u not in job["seen_urls"]:
                    job["seen_urls"].add(u)
                    job["images"].append({
                        "url": u,
                        "thumb": u,
                        "alt": text,
                        "width": "Original",
                        "height": "Original"
                    })
                    job["count"] = len(job["images"])
                    job["updated_at"] = time.time()
                    added_in_batch += 1
                    if len(job["images"]) >= target_count:
                        job["status"] = "completed"
                        job["stop_reason"] = "TARGET_REACHED"
                        print(f"[job:{job_id}] Target reached: {len(job['images'])} images")
                        return

        if added_in_batch == 0:
            consecutive_empty += 1
            if consecutive_empty >= 4:
                print(f"[job:{job_id}] SERP genuinely exhausted at page {batch_start + batch_size}")
                break
        else:
            consecutive_empty = 0

        time.sleep(0.2)

    with SCRAPE_JOBS_LOCK:
        job = SCRAPE_JOBS.get(job_id)
        if job and job["status"] != "completed":
            job["status"] = "completed"
            job["stop_reason"] = "ALL_PAGES_EXHAUSTED"
            job["updated_at"] = time.time()
            print(f"[job:{job_id}] Finished: collected {len(job['images'])} images")


def scrape_yandex(domain: str, text: str, extra: dict, max_pages=60, deep=True, max_images=2000) -> list:
    """Scrape up to max_images using multi-page pagination + deep extraction."""
    first_url = build_yandex_url(domain, text, 0, extra)
    seen = set()
    collected = []

    def add_urls(urls):
        added = 0
        for u in urls:
            clean_u = canonicalize_yandex_url(u)
            if clean_u.startswith("http") and clean_u not in seen:
                seen.add(clean_u)
                collected.append(clean_u)
                added += 1
        return added

    if deep:
        # Step 1: Initial page 0 extract
        p0_html = fetch_page(first_url, timeout=6)
        p0_urls = extract_orig_urls(p0_html)
        add_urls(p0_urls)

        # Step 2: Multi-page parallel pagination up to max_images (2000)
        target_count = max_images
        if len(collected) < target_count:
            page_indices = list(range(1, min(max_pages, 65)))
            
            def fetch_and_extract(p_idx):
                p_url = build_yandex_url(domain, text, p_idx, extra)
                html = fetch_page(p_url, timeout=7)
                return extract_orig_urls(html)

            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                results = executor.map(fetch_and_extract, page_indices)
                for res_urls in results:
                    add_urls(res_urls)
                    if len(collected) >= target_count:
                        break

        # Fallback to Playwright if initial requests were blocked
        if len(collected) < 30:
            pw_urls = scrape_yandex_playwright(first_url, max_images=max_images, deep=True)
            add_urls(pw_urls)

        return collected[:max_images]

    # Fast non-deep mode:
    urls = extract_orig_urls(fetch_page(first_url, timeout=6))
    if not urls:
        urls = scrape_yandex_playwright(first_url, max_images=30, deep=False)
    add_urls(urls)
    return collected[:max_images]


def parse_yandex_request(data: dict):
    """Parse and validate a Yandex scrape request. Returns (domain, text, extra) or raises."""
    url = data.get("url", "").strip()
    if not url:
        raise ValueError("URL is required")

    if not url.startswith("http://") and not url.startswith("https://"):
        if "yandex." in url:
            url = "https://" + url
        else:
            # User entered search query text directly
            return "yandex.com", url, {}

    u = urlparse(url)
    if "yandex" not in u.netloc and u.netloc:
        raise ValueError("Only Yandex Images URLs are supported. Example: https://yandex.com/images/search?text=cats")

    params = parse_qs(u.query)
    text = (params.get("text") or params.get("query") or params.get("q") or [""])[0].strip()
    if not text:
        text = "wallpaper"

    extra = {k: v[0] for k, v in params.items() if k not in ("text", "query", "q", "p", "format")}
    domain = u.netloc or "yandex.com"
    return domain, text, extra


@app.route("/")
def index():
    index_path = os.path.join(app.static_folder or "static", "index.html")
    accept = request.headers.get("Accept", "")
    if ("text/html" in accept or "application/json" not in accept) and os.path.exists(index_path):
        return send_file(index_path)
    return jsonify({
        "status": "online",
        "service": "Image Scraper Pro Cloud Backend",
        "version": "2.6-yandex-2000-progressive"
    }), 200


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "2.6-yandex-2000-progressive"})


@app.route("/api/scrape/start", methods=["POST", "OPTIONS"])
def api_scrape_start():
    """Starts a progressive Yandex scraping session: immediately returns Batch 1 and continues in background up to 2000 images."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json or {}
    try:
        domain, text, extra = parse_yandex_request(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    target_count = min(int(data.get("max_images", 2000)), 2000)
    job_id = str(uuid.uuid4())[:8]

    # Fast initial extract for instant 0-3s results
    first_url = build_yandex_url(domain, text, 0, extra)
    page0_html = fetch_page(first_url, timeout=5)
    page0_urls = extract_orig_urls(page0_html)
    
    initial_images = []
    seen = set()
    for u in page0_urls:
        canon = canonicalize_yandex_url(u)
        if canon.startswith("http") and canon not in seen:
            seen.add(canon)
            initial_images.append({
                "url": canon,
                "thumb": canon,
                "alt": text,
                "width": "Original",
                "height": "Original"
            })

    with SCRAPE_JOBS_LOCK:
        SCRAPE_JOBS[job_id] = {
            "job_id": job_id,
            "status": "scraping" if len(initial_images) < target_count else "completed",
            "images": list(initial_images),
            "seen_urls": set(seen),
            "count": len(initial_images),
            "target": target_count,
            "started_at": time.time(),
            "updated_at": time.time(),
            "stop_reason": None
        }

    # Start background expansion thread
    if len(initial_images) < target_count:
        t = threading.Thread(
            target=_run_background_yandex_scrape,
            args=(job_id, domain, text, extra, target_count),
            daemon=True
        )
        t.start()

    return jsonify({
        "job_id": job_id,
        "status": "scraping" if len(initial_images) < target_count else "completed",
        "count": len(initial_images),
        "target": target_count,
        "initial_images": initial_images
    }), 200


@app.route("/api/scrape/poll", methods=["GET", "OPTIONS"])
def api_scrape_poll():
    """Polls newly collected image batches from an active scraping job."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    job_id = request.args.get("job_id")
    offset = int(request.args.get("offset", 0))

    if not job_id:
        return jsonify({"error": "job_id is required"}), 400

    with SCRAPE_JOBS_LOCK:
        job = SCRAPE_JOBS.get(job_id)
        if not job:
            return jsonify({"error": "Job not found or expired", "status": "expired"}), 404

        all_images = job["images"]
        new_images = all_images[offset:]
        return jsonify({
            "job_id": job_id,
            "status": job["status"],
            "count": job["count"],
            "target": job["target"],
            "stop_reason": job.get("stop_reason"),
            "new_images": new_images,
            "next_offset": len(all_images)
        }), 200


@app.route("/api/pinterest/extract", methods=["POST", "OPTIONS"])
def api_pinterest_extract():
    """Extract high-resolution images from a Pinterest Pin URL using Resource API (with Playwright fallback)."""
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json or {}
    url = data.get("url", "").strip()
    max_images = int(data.get("max_images", 1000))
    min_target = int(data.get("min_target", 300))
    if not url:
        return jsonify({"success": False, "error": "Pinterest Pin URL is required"}), 400

    # Primary: Fast, lightweight native Pinterest JSON Resource API
    try:
        res = extract_pinterest_resource_api(url, max_images=max_images, min_target=min_target)
        if res.get("success") and len(res.get("images", [])) > 0:
            return jsonify(res), 200
    except Exception as e:
        print(f"[pinterest-api] Resource API extraction warning: {e}")

    # Fallback: Playwright / HTTP Pin Extractor
    res = extract_pinterest_pin(url, max_images=max_images, min_target=min_target)
    status_code = 200 if res.get("success") else 400
    return jsonify(res), status_code



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
    max_target = int(data.get("max_images", 1000 if deep else 30))
    try:
        urls = scrape_yandex(domain, text, extra, max_pages=max_pages, deep=deep, max_images=max_target)
        images = [{"url": u, "thumb": u, "alt": "", "width": "Original", "height": "Original"} for u in urls]
        print(f"[scrape] Found {len(images)} images for '{text}'")
        return jsonify({"images": images, "count": len(images)})
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
