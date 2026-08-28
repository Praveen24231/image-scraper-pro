import time
import re
from html import unescape
from urllib.parse import unquote
from playwright.sync_api import sync_playwright

ORIGURL_RE = re.compile(r'"origUrl"\s*:\s*"(https?[^"]+)"')
IMGURL_PARAM_RE = re.compile(r'img_url=([^&"\'<>\s]+)')
CDN_RE = re.compile(r'https://avatars\.mds\.yandex\.net/[^\s"\'<>\\,\)]+')

def test_robust_yandex_scrape(target_url, max_images=1000, max_time=35.0):
    print(f"=== Testing Robust Yandex Scraper for {target_url} (target={max_images}) ===")
    collected_urls = []
    seen = set()
    
    # Categorization debug counters as requested by user
    debug_counters = {
        "raw_candidates": 0,
        "dom_img_urls": 0,
        "json_orig_urls": 0,
        "cdn_upgraded_urls": 0,
        "rejected_invalid": 0,
        "rejected_thumbnail": 0,
        "duplicates_removed": 0,
        "final_images": 0
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        page.goto(target_url, wait_until="domcontentloaded", timeout=12000)
        page.wait_for_timeout(800)

        def extract_batch():
            added = 0
            # 1. Extract from DOM links with img_url parameter (highest quality original source)
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
                debug_counters["raw_candidates"] += 1
                debug_counters["dom_img_urls"] += 1
                clean_u = u.replace("\\/", "/")
                if not clean_u.startswith("http"):
                    debug_counters["rejected_invalid"] += 1
                    continue
                if clean_u in seen:
                    debug_counters["duplicates_removed"] += 1
                    continue
                seen.add(clean_u)
                collected_urls.append(clean_u)
                added += 1

            # 2. Extract origUrl from JSON / script tags in DOM
            html = page.content()
            decoded = unescape(html)
            for m in ORIGURL_RE.finditer(decoded):
                debug_counters["raw_candidates"] += 1
                debug_counters["json_orig_urls"] += 1
                u = m.group(1).replace("\\/", "/")
                if not u.startswith("http"):
                    debug_counters["rejected_invalid"] += 1
                    continue
                if u in seen:
                    debug_counters["duplicates_removed"] += 1
                    continue
                seen.add(u)
                collected_urls.append(u)
                added += 1

            # 3. Yandex CDN images (avatars.mds.yandex.net) -> upgrade to /orig
            for m in CDN_RE.finditer(decoded):
                debug_counters["raw_candidates"] += 1
                raw = m.group(0).split("?")[0]
                parts = raw.split("/")
                if len(parts) >= 5:
                    if parts[-1] not in ("orig", "original"):
                        parts[-1] = "orig"
                    upgraded = "/".join(parts)
                    debug_counters["cdn_upgraded_urls"] += 1
                    if upgraded in seen:
                        debug_counters["duplicates_removed"] += 1
                        continue
                    seen.add(upgraded)
                    collected_urls.append(upgraded)
                    added += 1

            return added

        init_added = extract_batch()
        print(f"Initial extract: +{init_added} (Total: {len(collected_urls)})")

        t_start = time.time()
        consecutive_idle = 0
        scroll_count = 0

        while time.time() - t_start < max_time and len(collected_urls) < max_images:
            scroll_count += 1
            # Scroll down smoothly to trigger infinite scroll
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            page.wait_for_timeout(450)

            # Click "Show more" / "Fetch more" button if visible
            page.evaluate("""() => {
                const btn = document.querySelector('.more__button, .button_theme_action, .more__btn, [data-bem*="more"], .FetchList-MoreButton, .Button2_view_action');
                if (btn && btn.offsetParent !== null) { btn.click(); }
            }""")

            added = extract_batch()
            if added == 0:
                consecutive_idle += 1
                # Wait a bit longer to allow dynamic fetch
                page.wait_for_timeout(350)
                added = extract_batch()
                if added > 0:
                    consecutive_idle = 0
                elif consecutive_idle >= 4:
                    print(f"Stopping: 4 consecutive idle scrolls with no new images at scroll {scroll_count}")
                    break
            else:
                consecutive_idle = 0

            if scroll_count % 3 == 0 or len(collected_urls) >= max_images:
                print(f"Scroll {scroll_count}: +{added} added | Total: {len(collected_urls)} | Elapsed: {round(time.time() - t_start, 1)}s")

        browser.close()
        
    debug_counters["final_images"] = len(collected_urls[:max_images])
    print("\n" + "=" * 50)
    print("YANDEX PIPELINE DEBUG REPORT:")
    for k, v in debug_counters.items():
        print(f"  {k}: {v}")
    print("=" * 50)
    return collected_urls[:max_images]

if __name__ == "__main__":
    test_robust_yandex_scrape("https://yandex.com/images/search?text=wallpaper", 600, 30.0)
