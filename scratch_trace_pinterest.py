import json
from playwright.sync_api import sync_playwright

def trace_pinterest_page(pin_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        page = context.new_page()
        
        resources_called = []
        def on_response(response):
            u = response.url
            if "/resource/" in u:
                try:
                    data = response.json()
                    resources_called.append({
                        "url": u.split("?")[0],
                        "status": response.status,
                        "resource_name": u.split("/resource/")[1].split("/")[0] if "/resource/" in u else "",
                        "item_count": len(data.get("resource_response", {}).get("data", [])) if isinstance(data.get("resource_response", {}).get("data"), list) else (1 if data.get("resource_response", {}).get("data") else 0)
                    })
                except Exception:
                    pass
        page.on("response", on_response)
        
        print(f"Loading {pin_url}...")
        page.goto(pin_url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(3000)
        
        # Check DOM structure for main pin vs related pins
        dom_structure = page.evaluate("""() => {
            // Find main pin container
            const mainPinImg = document.querySelector('[data-test-id="pin-closeup-image"] img, [data-test-id="closeup-image"] img, div[data-test-id="pin"] img, [data-test-id="main-pin"] img');
            
            // Find related pins / grid items
            const gridPins = [];
            document.querySelectorAll('[data-test-id="pin"], [data-test-id="pinWrapper"], div[data-grid-item="true"]').forEach(el => {
                const img = el.querySelector('img');
                const titleEl = el.querySelector('[title], [aria-label]');
                const link = el.querySelector('a[href*="/pin/"]');
                if (img && img.src) {
                    gridPins.push({
                        src: img.src,
                        alt: img.alt,
                        link: link ? link.href : null
                    });
                }
            });
            
            return {
                mainPinImg: mainPinImg ? mainPinImg.src : null,
                mainPinAlt: mainPinImg ? mainPinImg.alt : null,
                gridPinsCount: gridPins.length,
                first5GridPins: gridPins.slice(0, 5)
            };
        }""")
        print(f"DOM Structure: {json.dumps(dom_structure, indent=2)}")
        
        # Scroll once to see what resources are fetched
        print("Scrolling down...")
        page.evaluate("window.scrollBy(0, 2500)")
        page.wait_for_timeout(3000)
        
        print(f"\nPinterest Resources intercepted ({len(resources_called)} total):")
        for r in resources_called:
            print(f" - {r['resource_name']}: status={r['status']}, items={r['item_count']}")
            
        browser.close()

if __name__ == "__main__":
    trace_pinterest_page("https://in.pinterest.com/pin/980869993858369758/")
