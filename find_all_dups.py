import asyncio
import json
from playwright.async_api import async_playwright

async def get_all_dups(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        
        # This script tries to find 'dups' anywhere in window
        all_images_data = await page.evaluate("""
            () => {
                const results = [];
                
                // 1. Check data-state on Root
                try {
                    const root = document.querySelector('.Root');
                    if (root) {
                        const state = JSON.parse(root.getAttribute('data-state'));
                        // Deep search for dups in state
                        const findDups = (obj) => {
                            if (!obj) return;
                            if (obj.dups && Array.isArray(obj.dups)) {
                                results.push(obj);
                            }
                            if (typeof obj === 'object') {
                                Object.values(obj).forEach(findDups);
                            }
                        };
                        findDups(state);
                    }
                } catch(e) {}
                
                // 2. Check reactBus or other global structures
                try {
                    if (window.Ya && window.Ya.reactBus) {
                         // Some internal Yandex structure search here...
                    }
                } catch(e) {}

                return results;
            }
        """)
        
        await browser.close()
        return all_images_data

if __name__ == "__main__":
    target_url = "https://yandex.com/images/search?text=high+resolution+wallpaper"
    data = asyncio.run(get_all_dups(target_url))
    print(f"Found {len(data)} items with dups via JS.")
    if data:
        # Sort by resolution and print
        item = data[0]
        dups = sorted(item.get('dups', []), key=lambda x: x.get('w',0)*x.get('h',0), reverse=True)
        print(f"Best dup: {dups[0].get('w')}x{dups[0].get('h')} -> {dups[0].get('url')}")
