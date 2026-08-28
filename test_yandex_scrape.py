import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse, parse_qs

async def test_yandex_scrape(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5) # Wait for images to load
        
        # Try to extract via JS evaluate first
        js_images = await page.evaluate("""
            () => {
                const results = [];
                const links = document.querySelectorAll('a.ImagesContentImage-Cover, a.serp-item__link');
                links.forEach(a => {
                    const href = a.getAttribute('href');
                    let imgUrl = null;
                    if (href && href.includes('img_url=')) {
                        const params = new URLSearchParams(href.split('?')[1]);
                        imgUrl = params.get('img_url');
                    }
                    const img = a.querySelector('img');
                    const src = img ? img.src : null;
                    results.push({
                        imgUrl: imgUrl,
                        src: src,
                        alt: img ? img.alt : ''
                    });
                });
                return results;
            }
        """)
        
        print(f"JS found {len(js_images)} potential images.")
        for i, item in enumerate(js_images[:5]):
            print(f"Item {i}: imgUrl={item['imgUrl']}, src={item['src']}")

        content = await page.content()
        await browser.close()
        
        soup = BeautifulSoup(content, 'html.parser')
        bs_links = soup.find_all('a', class_='ImagesContentImage-Cover')
        print(f"BS4 found {len(bs_links)} links with ImagesContentImage-Cover")
        
        for link in bs_links[:5]:
            href = link.get('href')
            print(f"Href: {href[:100]}...")

if __name__ == "__main__":
    target_url = "https://yandex.com/images/search?tmpl_version=releases-frontend-images-v1.1750.0__77ab3d758063148f17d37f289cc6e905b94912bb&from=undefined&cbir_id=2762254%2F20Xs0TD3cu1UhU5ClFu70w628&cbir_page=similar&rpt=imageview&url=https%3A%2F%2Favatars.mds.yandex.net%2Fget-images-cbir%2F2762254%2F20Xs0TD3cu1UhU5ClFu70w628%2Forig&isize=large"
    asyncio.run(test_yandex_scrape(target_url))
