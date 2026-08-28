import time
import re
from html import unescape
from urllib.parse import urlparse, parse_qs, unquote
from playwright.sync_api import sync_playwright

def inspect_yandex(query="wallpaper", max_images=600):
    url = f"https://yandex.com/images/search?text={query}"
    print(f"=== Inspecting Yandex for query: {query} ===")
    print(f"URL: {url}")
    
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
        
        # Track network requests
        network_urls = []
        def handle_response(response):
            if "search" in response.url or "images" in response.url or "json" in response.url:
                network_urls.append(response.url)
        page.on("response", handle_response)
        
        print("Navigating...")
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(2000)
        
        # Check initial state / data-state
        data_state_info = page.evaluate("""() => {
            const root = document.querySelector('.Root');
            const dataState = root ? root.getAttribute('data-state') : null;
            let modelsCount = 0;
            if (dataState) {
                try {
                    const parsed = JSON.parse(dataState);
                    const items = parsed?.serpData?.items?.models || parsed?.initialState?.serpData?.items?.models || [];
                    modelsCount = items.length;
                } catch(e) {}
            }
            return {
                hasRoot: !!root,
                hasDataState: !!dataState,
                dataStateLen: dataState ? dataState.length : 0,
                modelsCount: modelsCount,
                serpItemsCount: document.querySelectorAll('.serp-item, .ImagesContentImage-Cover, a[href*="img_url="]').length
            };
        }""")
        print(f"Initial State Info: {data_state_info}")
        
        # Let's see what happens as we scroll
        raw_candidates_seen = set()
        dom_history = []
        
        t_start = time.time()
        scroll_count = 0
        while scroll_count < 30 and len(raw_candidates_seen) < max_images:
            scroll_count += 1
            
            # Extract current items from DOM
            batch = page.evaluate("""() => {
                const urls = [];
                // 1. img_url from links
                document.querySelectorAll('a[href*="img_url="]').forEach(a => {
                    try {
                        const u = new URL(a.href);
                        const raw = u.searchParams.get('img_url');
                        if (raw) urls.push({type: 'img_url', url: decodeURIComponent(raw)});
                    } catch(e) {}
                });
                
                // 2. data-bem or data-state
                document.querySelectorAll('[data-bem]').forEach(el => {
                    const bem = el.getAttribute('data-bem');
                    if (bem && bem.includes('http')) {
                        // check if has image urls
                    }
                });
                
                // 3. <img> tags
                document.querySelectorAll('.serp-item img, .ImagesContentImage img').forEach(img => {
                    if (img.src) urls.push({type: 'img_src', url: img.src});
                });
                
                // 4. check if button "Next page" or "More images" exists
                const moreBtn = document.querySelector('.more__button, .button_theme_action, .more__btn, [data-bem*="more"], .FetchList-MoreButton, .Button2_view_action');
                let moreBtnText = moreBtn ? (moreBtn.innerText || moreBtn.textContent) : null;
                
                return {
                    items: urls,
                    serpItemCount: document.querySelectorAll('.serp-item, .ImagesContentImage-Cover').length,
                    hasMoreBtn: !!moreBtn,
                    moreBtnText: moreBtnText,
                    scrollHeight: document.body.scrollHeight,
                    scrollTop: window.scrollY
                };
            }""")
            
            # HTML regex search
            html = page.content()
            orig_urls = re.findall(r'"origUrl"\s*:\s*"(https?[^"]+)"', html)
            
            for item in batch["items"]:
                raw_candidates_seen.add(item["url"])
            for u in orig_urls:
                raw_candidates_seen.add(u.replace("\\/", "/"))
                
            print(f"Scroll {scroll_count}: DOM SerpItems={batch['serpItemCount']}, Total Unique Raw Seen={len(raw_candidates_seen)}, ScrollHeight={batch['scrollHeight']}, HasMoreBtn={batch['hasMoreBtn']} ({batch['moreBtnText']})")
            
            # Scroll down
            page.evaluate("window.scrollBy(0, 5000)")
            page.wait_for_timeout(500)
            
            # Click more button if present
            if batch['hasMoreBtn']:
                page.evaluate("""() => {
                    const moreBtn = document.querySelector('.more__button, .button_theme_action, .more__btn, [data-bem*="more"], .FetchList-MoreButton, .Button2_view_action');
                    if (moreBtn && moreBtn.offsetParent !== null) moreBtn.click();
                }""")
                page.wait_for_timeout(800)
                
            if scroll_count % 5 == 0:
                print(f"  --> At scroll {scroll_count}, elapsed: {round(time.time() - t_start, 1)}s, raw unique: {len(raw_candidates_seen)}")
                
        print(f"\nFinal raw candidates seen: {len(raw_candidates_seen)}")
        browser.close()

if __name__ == "__main__":
    inspect_yandex("cats", 600)
