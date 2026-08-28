import asyncio
import json
import re
from playwright.async_api import async_playwright

async def extract_yandex_json(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        
        # Try to find JSON in script tags
        scripts = await page.evaluate("""
            () => {
                const results = [];
                const scripts = document.querySelectorAll('script');
                scripts.forEach(s => {
                    const content = s.textContent;
                    if (content.includes('App.data') || content.includes('PAGE_DATA') || content.includes('dups')) {
                        results.push(content.substring(0, 500)); // Just a snippet
                    }
                });
                return results;
            }
        """)
        
        # Also try to extract data-bem from serp-item if it's a grid
        bem_items = await page.evaluate("""
            () => {
                const items = document.querySelectorAll('.serp-item');
                if (items.length > 0) {
                    return items[0].getAttribute('data-bem');
                }
                return null;
            }
        """)
        
        await browser.close()
        return scripts, bem_items

if __name__ == "__main__":
    target_url = "https://yandex.com/images/search?text=high+resolution+wallpaper"
    scripts, bem = asyncio.run(extract_yandex_json(target_url))
    
    print("--- Scripts Snippets ---")
    for s in scripts:
        print(s)
        print("-" * 10)
        
    print("--- First BEM ---")
    print(bem)
