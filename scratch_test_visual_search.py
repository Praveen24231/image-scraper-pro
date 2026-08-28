import json
from playwright.sync_api import sync_playwright

def inspect_visual_search(pin_id):
    url = f"https://www.pinterest.com/pin/{pin_id}/visual-search/"
    print(f"Loading Visual Search: {url}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        
        resources = []
        def on_resp(res):
            if "/resource/" in res.url:
                resources.append(res.url)
        page.on("response", on_resp)
        
        page.goto(url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(3000)
        
        info = page.evaluate("""() => {
            const images = [];
            document.querySelectorAll('[data-test-id="pin"] img, [data-test-id="pinWrapper"] img, div[data-grid-item="true"] img, a[href*="/pin/"] img').forEach(img => {
                if (img.src && !img.src.includes('avatar') && !img.src.includes('75x75_RS')) {
                    images.push({
                        src: img.src,
                        alt: img.alt
                    });
                }
            });
            return {
                title: document.title,
                url: window.location.href,
                imagesFound: images.length,
                first10: images.slice(0, 10)
            };
        }""")
        print(f"Visual Search page result: {json.dumps(info, indent=2)}")
        print(f"Resources count: {len(resources)}")
        for r in resources[:10]:
            print(f" - {r[:120]}")
        browser.close()

if __name__ == "__main__":
    inspect_visual_search("980869993858369758")
