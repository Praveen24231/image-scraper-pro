import sys
import os
import time
from html import unescape
import re
from urllib.parse import unquote

ORIGURL_RE = re.compile(r'"origUrl"\s*:\s*"(https?[^"]+)"')
IMGURL_PARAM_RE = re.compile(r'img_url=([^&"\'<>\s]+)')
CDN_RE = re.compile(r'https://avatars\.mds\.yandex\.net/[^\s"\'<>\\,\)]+')

def is_valid_real_image(url: str) -> bool:
    """Filters out icons, avatars, sprites, UI elements, broken URLs."""
    if not url or not url.startswith("http"):
        return False
    # Filter UI assets, avatars, tracking sprites
    lower = url.lower()
    invalid_patterns = [
        "yastatic.net", "favicon", "sprite", "icon-", "avatar", 
        "get-images-cbir", "get-images-similar-mtab", "ui-", "logo",
        "captcha", "1x1.png", "pixel.gif"
    ]
    if any(p in lower for p in invalid_patterns):
        return False
    return True

def canonicalize_url(url: str) -> str:
    """Upgrades thumbnails to full original resolution and strips tracking queries."""
    if not url or not url.startswith("http"):
        return ""
    clean = url.replace("\\/", "/").replace("\\\\", "").strip()
    
    # If Yandex CDN, upgrade to /orig
    if "avatars.mds.yandex.net" in clean:
        raw = clean.split("?")[0]
        parts = raw.split("/")
        if len(parts) >= 5:
            if parts[-1] not in ("orig", "original"):
                parts[-1] = "orig"
            return "/".join(parts)
        return raw

    # If direct image with query params, keep clean base URL
    if "?" in clean:
        base = clean.split("?")[0]
        ext = base.split(".")[-1].lower()
        if ext in ("jpg", "jpeg", "png", "webp", "avif"):
            return base
    return clean

def run_backend_debug(target_query="nature", max_target=2000):
    from playwright.sync_api import sync_playwright
    print("==================================================", flush=True)
    print("      BACKEND YANDEX SCRAPER DIRECT DEBUG TEST    ", flush=True)
    print("==================================================", flush=True)
    print(f"Target Query:     {target_query}", flush=True)
    print(f"Max Images Target:{max_target}", flush=True)
    print(f"Deep Scrape:      ON (autoscroll=True)", flush=True)
    print("--------------------------------------------------", flush=True)

    t0 = time.time()
    seen = set()
    collected_urls = []
    milestones = {}
    
    total_discovered = 0
    total_duplicates = 0
    total_invalid = 0
    pages_processed = 0
    scroll_cycles = 0

    with sync_playwright() as p:
        print("[backend] Launching persistent Chromium instance...", flush=True)
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )

        def route_filter(route):
            req = route.request
            if req.resource_type in ["font", "media"]:
                route.abort()
            elif any(x in req.url for x in ["mc.yandex.ru", "an.yandex.ru", "clck.yandex.ru", "stat.yandex.ru"]):
                route.abort()
            else:
                route.continue_()

        page = context.new_page()
        page.route("**/*", route_filter)

        def extract_batch():
            nonlocal total_discovered, total_duplicates, total_invalid
            new_batch = []
            
            # 1. DOM links
            dom_links = page.evaluate("""() => {
                const arr = [];
                document.querySelectorAll('a[href*="img_url="]').forEach(a => {
                    try {
                        const u = new URL(a.href);
                        const raw = u.searchParams.get('img_url');
                        if (raw) arr.push(decodeURIComponent(raw));
                    } catch(e) {}
                });
                return arr;
            }""")
            for u in dom_links:
                total_discovered += 1
                if not is_valid_real_image(u):
                    total_invalid += 1
                    continue
                canon = canonicalize_url(u)
                if not canon:
                    total_invalid += 1
                    continue
                if canon in seen:
                    total_duplicates += 1
                    continue
                seen.add(canon)
                new_batch.append(canon)

            # 2. Page HTML JSON origUrls
            html = page.content()
            decoded = unescape(html)
            for m in ORIGURL_RE.finditer(decoded):
                total_discovered += 1
                raw = m.group(1)
                if not is_valid_real_image(raw):
                    total_invalid += 1
                    continue
                canon = canonicalize_url(raw)
                if not canon:
                    total_invalid += 1
                    continue
                if canon in seen:
                    total_duplicates += 1
                    continue
                seen.add(canon)
                new_batch.append(canon)

            # 3. Yandex CDN upgraded to /orig
            for m in CDN_RE.finditer(decoded):
                total_discovered += 1
                raw = m.group(0)
                if not is_valid_real_image(raw):
                    total_invalid += 1
                    continue
                canon = canonicalize_url(raw)
                if not canon:
                    total_invalid += 1
                    continue
                if canon in seen:
                    total_duplicates += 1
                    continue
                seen.add(canon)
                new_batch.append(canon)

            return new_batch

        stop_reason = ""

        for p_idx in range(0, 50):
            pages_processed += 1
            p_url = f"https://yandex.com/images/search?text={target_query}&p={p_idx}"
            print(f"\n==================== PAGE {p_idx} ====================", flush=True)
            print(f"URL: {p_url}", flush=True)

            try:
                page.goto(p_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_timeout(300)

                # Initial page extraction
                b0 = extract_batch()
                collected_urls.extend(b0)
                high_res_0 = sum(1 for u in collected_urls if "orig" in u or any(u.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]))
                print(f"  [PAGE {p_idx} - INITIAL LOAD] Added: +{len(b0)} | Total Unique: {len(collected_urls)} | High-Res: {high_res_0}", flush=True)

                # Check milestones
                cur_len = len(collected_urls)
                el = time.time() - t0
                for m in [50, 100, 250, 500, 750, 1000, 1500, 2000]:
                    if m not in milestones and cur_len >= m:
                        milestones[m] = el
                        print(f"    ⭐ MILESTONE {m} IMAGES REACHED: {el:.2f}s", flush=True)

                if cur_len >= max_target:
                    stop_reason = f"Target {max_target} reached at Page {p_idx} Initial Load"
                    break

                # 3 Progressive Scrolls per page
                for s in range(1, 4):
                    scroll_cycles += 1
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(250)
                    bs = extract_batch()
                    collected_urls.extend(bs)
                    cur_len = len(collected_urls)
                    el = time.time() - t0
                    high_res_s = sum(1 for u in collected_urls if "orig" in u or any(u.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]))
                    print(f"  [PAGE {p_idx} - SCROLL {s}] Added: +{len(bs)} | Total Unique: {cur_len} | High-Res: {high_res_s}", flush=True)

                    for m in [50, 100, 250, 500, 750, 1000, 1500, 2000]:
                        if m not in milestones and cur_len >= m:
                            milestones[m] = el
                            print(f"    ⭐ MILESTONE {m} IMAGES REACHED: {el:.2f}s", flush=True)

                    if cur_len >= max_target:
                        stop_reason = f"Target {max_target} reached at Page {p_idx} Scroll {s}"
                        break

                if cur_len >= max_target:
                    break

            except Exception as e:
                print(f"[PAGE {p_idx} ERROR]: {e}", flush=True)

        if not stop_reason:
            stop_reason = "Completed all pages / SERP boundary reached"

        browser.close()

    total_time = time.time() - t0
    final_unique = len(collected_urls)
    final_high_res = sum(1 for u in collected_urls if "orig" in u or any(u.endswith(ext) for ext in [".jpg", ".jpeg", ".png", ".webp"]))

    print("\n==================================================", flush=True)
    print("           FINAL BACKEND BENCHMARK REPORT         ", flush=True)
    print("==================================================", flush=True)
    for m in [50, 100, 250, 500, 1000, 1500, 2000]:
        t_val = milestones.get(m)
        if t_val is not None:
            print(f"First {m:4d} images: {t_val:.2f} seconds", flush=True)
        else:
            print(f"First {m:4d} images: Not reached", flush=True)

    print("\nFINAL METRICS:", flush=True)
    print(f"Discovered:         {total_discovered}", flush=True)
    print(f"Unique:             {final_unique}", flush=True)
    print(f"Valid:              {final_unique}", flush=True)
    print(f"High-resolution:    {final_high_res}", flush=True)
    print(f"Duplicates removed: {total_duplicates}", flush=True)
    print(f"Invalid removed:    {total_invalid}", flush=True)
    print(f"Pages processed:    {pages_processed}", flush=True)
    print(f"Scroll cycles:      {scroll_cycles}", flush=True)
    print(f"Total time:         {total_time:.2f} seconds", flush=True)
    print(f"Images/second:      {final_unique / max(total_time, 0.1):.1f} imgs/sec", flush=True)
    print(f"Stop reason:        {stop_reason}", flush=True)
    print("==================================================", flush=True)

if __name__ == "__main__":
    run_backend_debug("nature", 2000)
