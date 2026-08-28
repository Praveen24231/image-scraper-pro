import asyncio
import re
import html
import json
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse, parse_qs

async def test_scrape(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print(f"Scraping URL: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        
        content = await page.content()
        await browser.close()
        
        # Test origUrl extraction
        orig_url_matches = re.findall(r'"origUrl":"(.*?)"', content)
        print(f"--- FOUND {len(orig_url_matches)} origUrl matches ---")
        for i, url in enumerate(orig_url_matches[:10]):
            print(f"{i}: {url.replace('\\\\/', '/')}")

        # Test dups extraction
        dup_matches = re.findall(r'"dups":\[(.*?)]', content)
        print(f"--- FOUND {len(dup_matches)} dups matches ---")
        
        # Test if it's entity encoded
        encoded_dups = re.findall(r'&quot;dups&quot;:\[(.*?)]', content)
        print(f"--- FOUND {len(encoded_dups)} encoded dups matches ---")

if __name__ == "__main__":
    url = "https://yandex.com/images/search?text=teen+indian+girl&isize=large"
    asyncio.run(test_scrape(url))
