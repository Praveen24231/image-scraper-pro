import asyncio
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse, parse_qs

def normalize_url(url):
    if not url: return url
    if url.startswith('//'): url = 'https:' + url
    
    if 'avatars.mds.yandex.net' in url or 'get-shedevrum' in url:
        if not url.endswith('/orig') and not '?' in url.split('/')[-1] and '/i?id=' not in url:
            url = url.rstrip('/') + '/orig'
            
    if 'pinimg.com' in url and '/736x/' in url:
        url = url.replace('/736x/', '/originals/')

    if '?x-oss-process=image' in url: url = url.split('?x-oss-process=')[0]
    
    if 'googleusercontent.com' in url:
        url = re.sub(r'\/s\d+(-c)?\/', '/s4096/', url)
    
    return url

async def test_yandex_scrape_v2(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')

        # Check for source image
        source_link = soup.find('a', class_='CbirItem-Link') or soup.find('a', class_='CbirHeader-Image')
        if source_link:
            href = source_link.get('href')
            print(f"FOUND SOURCE LINK: {href[:100]}...")
            if href and 'img_url=' in href:
                src = parse_qs(urlparse(href).query).get('img_url', [None])[0]
                print(f"EXTRACTED SOURCE IMG_URL: {normalize_url(unquote(src))}")

        # Check grid images
        links = soup.find_all('a', class_=['ImagesContentImage-Cover', 'serp-item__link'])
        print(f"FOUND {len(links)} grid links.")
        for i, link in enumerate(links[:5]):
            href = link.get('href')
            if href and 'img_url=' in href:
                img_url = parse_qs(urlparse(href).query).get('img_url', [None])[0]
                norm = normalize_url(unquote(img_url))
                print(f"Grid {i}: {norm[:100]}...")

        await browser.close()

if __name__ == "__main__":
    target_url = "https://yandex.com/images/search?tmpl_version=releases-frontend-images-v1.1750.0__77ab3d758063148f17d37f289cc6e905b94912bb&from=undefined&cbir_id=2762254%2F20Xs0TD3cu1UhU5ClFu70w628&cbir_page=similar&rpt=imageview&url=https%3A%2F%2Favatars.mds.yandex.net%2Fget-images-cbir%2F2762254%2F20Xs0TD3cu1UhU5ClFu70w628%2Forig&isize=large"
    asyncio.run(test_yandex_scrape_v2(target_url))
