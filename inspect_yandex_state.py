import asyncio
import json
from playwright.async_api import async_playwright

async def extract_yandex_state(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        print(f"Navigating to {url}...")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)
        
        # Extract data-state from div.Root
        state_json = await page.evaluate("""
            () => {
                const root = document.querySelector('.Root.Root_inited');
                if (root) {
                    return root.getAttribute('data-state');
                }
                return null;
            }
        """)
        
        await browser.close()
        return state_json

if __name__ == "__main__":
    target_url = "https://yandex.com/images/search?text=high+resolution+wallpaper"
    state = asyncio.run(extract_yandex_state(target_url))
    
    if state:
        try:
            data = json.loads(state)
            print("Successfully parsed data-state JSON.")
            # Let's save it to a file for inspection
            with open("yandex_state.json", "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print("Saved to yandex_state.json")
            
            # Check for dups in the first item
            # Path might be: data['serpData']['items']['models'][0]['dups']
            # or data['initialState']['serpData']...
            
            items = data.get('serpData', {}).get('items', {}).get('models', [])
            if not items:
                # Try initialState
                items = data.get('initialState', {}).get('serpData', {}).get('items', {}).get('models', [])
            
            if items:
                print(f"Found {len(items)} items in models.")
                first_item = items[0]
                print("First item keys:", first_item.keys())
                dups = first_item.get('dups', [])
                print(f"First item has {len(dups)} dups.")
                if dups:
                    for d in dups:
                        print(f"Dup: {d.get('w')}x{d.get('h')} -> {d.get('url')[:100]}...")
            else:
                print("Could not find items in models.")
        except Exception as e:
            print(f"Error parsing JSON: {e}")
            # print(state[:1000])
    else:
        print("Could not find data-state attribute.")
