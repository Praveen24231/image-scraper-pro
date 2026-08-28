import asyncio
from playwright.async_api import async_playwright

async def test_lexica():
    url = "https://lexica.art/?q=eyJpZCI6ImY1ZTU1ZDMyLWZhMGEtNDc0NC04NWRlLTFjMTc1MjM5ZjY3YiIsInVybCI6Imh0dHBzOi8vaW1hZ2VkZWxpdmVyeS5uZXQvbVBtU0dvck9ucjRPelViMGhSYnJ3QS83NGU5YTI4Zi00NGFmLTRkOTUtODZlYi1iNmIxYjk0ODE5MDAvdGlueT90eXBlPS5qcGciLCJ3aWR0aCI6NzM2LCJoZWlnaHQiOjEzMDgsInRpbWVzdGFtcCI6MTc3NTYzNjAxNTkzNH0%3D"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print(f"Navigating to {url}")
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        # Count initial images
        images = await page.query_selector_all("img")
        print(f"Initial images count: {len(images)}")
        
        # Take a screenshot to see what's there
        await page.screenshot(path="lexica_start.png")
        
        # Scroll and accumulate
        all_image_urls = set()
        
        for i in range(10):
            # Get current images
            current_images = await page.evaluate("""
                () => Array.from(document.querySelectorAll('img')).map(img => img.src)
            """)
            for src in current_images:
                if src and not src.startswith("data:"):
                    all_image_urls.add(src)
            
            print(f"Step {i}: Total accumulated: {len(all_image_urls)}")
            
            # Scroll down
            await page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            await asyncio.sleep(1)
            
        print(f"Final accumulated count: {len(all_image_urls)}")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_lexica())
