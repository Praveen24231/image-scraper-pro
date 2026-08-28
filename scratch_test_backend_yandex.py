import time
import re
from html import unescape
from urllib.parse import unquote
from playwright.sync_api import sync_playwright

ORIGURL_RE = re.compile(r'"origUrl"\s*:\s*"(https?[^"]+)"')
IMGURL_PARAM_RE = re.compile(r'img_url=([^&"\'<>\s]+)')
CDN_RE     = re.compile(r'https://avatars\.mds\.yandex\.net/[^\s"\'<>\\,\)]+')

def test_current_backend_yandex(target_url, max_images=1000, deep=True):
    print(f"=== Testing current backend Yandex logic for {target_url} ===")
    collected_urls = []
    seen = set()
    
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
            page.goto(target_url, wait_until="domcontentloaded", timeout=7000)
        except Exception as e:
            print(f"goto exception: {e}")
        page.wait_for_timeout(600)

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
                clean_u = u.replace("\\/", "/")
                if clean_u not in seen and clean_u.startswith("http"):
                    seen.add(clean_u)
                    collected_urls.append(clean_u)
                    added += 1

            html = page.content()
            decoded = unescape(html)
            for m in ORIGURL_RE.finditer(decoded):
                u = m.group(1).replace("\\/", "/")
                if u not in seen and u.startswith("http"):
                    seen.add(u)
                    collected_urls.append(u)
                    added += 1

            for m in CDN_RE.finditer(decoded):
                raw = m.group(0).split("?")[0]
                parts = raw.split("/")
                if len(parts) >= 5:
                    if parts[-1] not in ("orig", "original"):
                        parts[-1] = "orig"
                    upgraded = "/".join(parts)
                    if upgraded not in seen:
                        seen.add(upgraded)
                        collected_urls.append(upgraded)
                        added += 1

            return added

        init_added = extract_batch()
        print(f"Initial extract batch added: {init_added} (Total: {len(collected_urls)})")

        if deep:
            t_scroll_start = time.time()
            scroll_count = 0
            while time.time() - t_scroll_start < 12.0 and len(collected_urls) < max_images:
                scroll_count += 1
                page.evaluate("window.scrollBy(0, 15000)")
                page.wait_for_timeout(200)

                # Click "show more" button if visible
                page.evaluate("""() => {
                    const btn = document.querySelector('.more__button, .button_theme_action, .more__btn, [data-bem*="more"]');
                    if (btn && btn.offsetParent !== null) { btn.click(); }
                }""")

                added = extract_batch()
                print(f"Scroll {scroll_count}: added {added}, total {len(collected_urls)}, elapsed {round(time.time() - t_scroll_start, 2)}s")
                if added == 0 and time.time() - t_scroll_start > 5.0:
                    print(f"Premature break triggered at scroll {scroll_count}! time={round(time.time() - t_scroll_start, 2)}s")
                    break

        browser.close()
        print(f"Final collected count: {len(collected_urls)}")

if __name__ == "__main__":
    test_current_backend_yandex("https://yandex.com/images/search?text=cats", 1000, True)
