import asyncio
import json
from playwright.async_api import async_playwright

async def get_serp_data(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)  # Wait for dynamic content
        
        # Extract data from serp-item elements
        # Usually Yandex uses div.serp-item and data-bem attribute
        items_data = await page.evaluate("""
            () => {
                const results = [];
                const items = document.querySelectorAll('.serp-item');
                items.forEach(item => {
                    const dataBem = item.getAttribute('data-bem');
                    if (dataBem) {
                        try {
                            const parsed = JSON.parse(dataBem);
                            results.push(parsed);
                        } catch(e) {}
                    }
                });
                return results;
            }
        """)
        
        await browser.close()
        return items_data

if __name__ == "__main__":
    target_url = "https://yandex.com/images/search?text=high+resolution+wallpaper"
    data = asyncio.run(get_serp_data(target_url))
    if data:
        print(f"Found {len(data)} items with data-bem")
        # Print the first one's structure
        import pprint
        pprint.pprint(data[0])
    else:
        print("No items found with data-bem")
