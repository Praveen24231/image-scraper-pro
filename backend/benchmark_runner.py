import sys
import os
import time
from html import unescape
import re
from urllib.parse import unquote

ORIGURL_RE = re.compile(r'"origUrl"\s*:\s*"(https?[^"]+)"')
IMGURL_PARAM_RE = re.compile(r'img_url=([^&"\'<>\s]+)')
CDN_RE = re.compile(r'https://avatars\.mds\.yandex\.net/[^\s"\'<>\\,\)]+')

def canonicalize(u):
    if not u or not u.startswith("http"):
        return ""
    clean = u.replace("\\/", "/").replace("\\\\", "").strip()
    if "avatars.mds.yandex.net" in clean:
        raw = clean.split("?")[0]
        parts = raw.split("/")
        if len(parts) >= 5:
            if parts[-1] not in ("orig", "original"):
                parts[-1] = "orig"
            return "/".join(parts)
        return raw
    if "?" in clean:
        base = clean.split("?")[0]
        ext = base.split(".")[-1].lower()
        if ext in ("jpg", "jpeg", "png", "webp", "avif"):
            return base
    return clean

def run_benchmark():
    from playwright.sync_api import sync_playwright
    t0 = time.time()
    seen = set()
    collected = []
    milestones = {}
    total_discovered_raw = 0
    invalid_removed = 0
    duplicates_removed = 0
    pages_processed = 0
    scroll_cycles = 0

    print("==================================================", flush=True)
    print("      LOCAL YANDEX 2,000 IMAGE SCRAPER BENCHMARK ", flush=True)
    print("==================================================", flush=True)
    print(f"Target: 2,000 Unique Images", flush=True)
    print(f"Query:  nature", flush=True)
    print(f"URL:    https://yandex.com/images/search?text=nature", flush=True)
    print("--------------------------------------------------", flush=True)

    with sync_playwright() as p:
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

        def extract_from_page(pg):
            nonlocal total_discovered_raw, invalid_removed, duplicates_removed
            new_urls = []
            
            # 1. DOM links
            dom_urls = pg.evaluate("""() => {
                const urls = [];
                document.querySelectorAll('a[href*="img_url="]').forEach(a => {
                    try {
                        const u = new URL(a.href);
                        const raw = u.searchParams.get('img_url');
                        if (raw) urls.push(decodeURIComponent(raw));
                    } catch(e) {}
                });
                return urls;
            }""")
            for u in dom_urls:
                total_discovered_raw += 1
                c = canonicalize(u)
                if not c:
                    invalid_removed += 1
                    continue
                if c in seen:
                    duplicates_removed += 1
                    continue
                seen.add(c)
                new_urls.append(c)

            # 2. HTML origUrl JSON and CDN patterns
            html = pg.content()
            decoded = unescape(html)
            for m in ORIGURL_RE.finditer(decoded):
                total_discovered_raw += 1
                c = canonicalize(m.group(1))
                if not c:
                    invalid_removed += 1
                    continue
                if c in seen:
                    duplicates_removed += 1
                    continue
                seen.add(c)
                new_urls.append(c)

            for m in CDN_RE.finditer(decoded):
                total_discovered_raw += 1
                c = canonicalize(m.group(0))
                if not c:
                    invalid_removed += 1
                    continue
                if c in seen:
                    duplicates_removed += 1
                    continue
                seen.add(c)
                new_urls.append(c)

            return new_urls

        max_target = 2000
        stop_reason = ""

        for p_idx in range(0, 50):
            p_url = f"https://yandex.com/images/search?text=nature&p={p_idx}"
            pages_processed += 1
            try:
                page.goto(p_url, wait_until="domcontentloaded", timeout=12000)
                page.wait_for_timeout(250)
                
                batch = extract_from_page(page)
                collected.extend(batch)
                
                # Check first result milestone
                el = time.time() - t0
                if "first_result" not in milestones and len(collected) > 0:
                    milestones["first_result"] = el
                    print(f"First result:      {el:.2f}s ({len(collected)} images ready)", flush=True)

                # Scroll down 3 times per page to trigger lazy-loaded image batches
                for s in range(3):
                    scroll_cycles += 1
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(200)
                    batch2 = extract_from_page(page)
                    collected.extend(batch2)

                count = len(collected)
                el = time.time() - t0
                print(f"Page {p_idx:02d} processed: {count} unique images ({el:.2f}s)", flush=True)

                for m in [50, 100, 250, 500, 750, 1000, 1500, 2000]:
                    if m not in milestones and count >= m:
                        milestones[m] = el
                        print(f"  >>> MILESTONE {m:4d} images: {el:.2f}s", flush=True)

                if count >= max_target:
                    stop_reason = f"Target {max_target} reached successfully"
                    break
            except Exception as e:
                print(f"Page {p_idx} notice: {e}", flush=True)

        if not stop_reason:
            stop_reason = "Completed all pages / SERP boundary reached"

        browser.close()

    total_time = time.time() - t0
    final_count = len(collected)
    orig_count = sum(1 for u in collected if "orig" in u or not any(x in u for x in ["get-images-similar-mtab", "thumb", "avatars.mds.yandex.net/get-images-cbir"]))

    print("\n==================================================", flush=True)
    print("                FINAL BENCHMARK REPORT            ", flush=True)
    print("==================================================", flush=True)
    print(f"First result:      {milestones.get('first_result', 0):.2f}s", flush=True)
    for m in [50, 100, 250, 500, 750, 1000, 1500, 2000]:
        t_val = milestones.get(m)
        if t_val is not None:
            print(f"{m:4d} images:        {t_val:.2f}s", flush=True)
        else:
            print(f"{m:4d} images:        Not reached", flush=True)

    print("\nMETRICS:", flush=True)
    print(f"Total discovered:               {total_discovered_raw}", flush=True)
    print(f"Unique valid images:            {final_count}", flush=True)
    print(f"High-resolution/original images:{orig_count}", flush=True)
    print(f"Duplicates removed:             {duplicates_removed}", flush=True)
    print(f"Invalid URLs removed:           {invalid_removed}", flush=True)
    print(f"Pages processed:                {pages_processed}", flush=True)
    print(f"Scroll cycles:                  {scroll_cycles}", flush=True)
    print(f"Total execution time:           {total_time:.2f}s", flush=True)
    print(f"Average images/second:          {final_count / max(total_time, 0.1):.1f} imgs/sec", flush=True)
    print(f"Final stop reason:              {stop_reason}", flush=True)
    print("==================================================", flush=True)

if __name__ == "__main__":
    run_benchmark()
