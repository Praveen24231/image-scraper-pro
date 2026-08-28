import sys
import os
import json
import time

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath("image-scraper-pro/backend"))

from app import scrape_yandex
from pinterest_resource_scraper import extract_pinterest_resource_api
from pinterest_scraper import extract_pinterest_pin

def run_yandex_verification():
    print("\n" + "=" * 70)
    print("RUNNING YANDEX SCRAPER VERIFICATION SUITE")
    print("=" * 70)
    
    test_queries = [
        ("cats", "https://yandex.com/images/search?text=cats"),
        ("wallpaper", "https://yandex.com/images/search?text=wallpaper"),
        ("ferrari", "https://yandex.com/images/search?text=ferrari"),
    ]
    
    yandex_results = []
    
    for label, url in test_queries:
        t0 = time.time()
        print(f"\n[TEST YANDEX] Query: '{label}' | URL: {url}")
        urls = scrape_yandex("yandex.com", label, {}, max_pages=34, deep=True, max_images=600)
        elapsed = round(time.time() - t0, 2)
        
        # Verify deduplication
        unique_urls = set(urls)
        is_deduped = len(urls) == len(unique_urls)
        
        # Sample check
        sample_urls = urls[:3]
        
        res = {
            "query": label,
            "count": len(urls),
            "unique_count": len(unique_urls),
            "is_deduped": is_deduped,
            "elapsed_sec": elapsed,
            "exceeds_500": len(urls) >= 500,
            "sample_urls": sample_urls
        }
        yandex_results.append(res)
        print(f" -> Result: {len(urls)} images in {elapsed}s | Unique: {len(unique_urls)} | Exceeds 500: {res['exceeds_500']}")
        
    return yandex_results

def run_pinterest_verification():
    print("\n" + "=" * 70)
    print("RUNNING PINTEREST RELEVANCE & VOLUME VERIFICATION SUITE")
    print("=" * 70)
    
    test_pins = [
        ("Target User Pin (Boy Curly Haircut)", "https://in.pinterest.com/pin/980869993858369758/"),
        ("Pin 2 (Aesthetic Architecture / Room)", "https://in.pinterest.com/pin/1136033074757270594/"),
        ("Pin 3 (Nature / Landscape)", "https://in.pinterest.com/pin/1062075524624293007/")
    ]
    
    pinterest_results = []
    
    for label, pin_url in test_pins:
        t0 = time.time()
        print(f"\n[TEST PINTEREST] {label} | URL: {pin_url}")
        res = extract_pinterest_resource_api(pin_url, max_images=1000, min_target=300)
        elapsed = round(time.time() - t0, 2)
        
        images = res.get("images", [])
        unique_urls = set(img["url"] for img in images)
        is_deduped = len(images) == len(unique_urls)
        
        telemetry = res.get("telemetry", {})
        
        # Check first 5 items
        samples = [{"alt": img.get("alt", "")[:50], "url": img.get("url")} for img in images[:5]]
        
        pin_res = {
            "label": label,
            "url": pin_url,
            "success": res.get("success"),
            "count": len(images),
            "unique_count": len(unique_urls),
            "is_deduped": is_deduped,
            "reaches_300": len(images) >= 300,
            "elapsed_sec": elapsed,
            "telemetry": telemetry,
            "samples": samples
        }
        pinterest_results.append(pin_res)
        print(f" -> Result: {len(images)} images in {elapsed}s | Unique: {len(unique_urls)} | Reaches 300+: {pin_res['reaches_300']}")
        print(f" -> Telemetry: {telemetry}")
        print(f" -> Sample Titles:")
        for idx, s in enumerate(samples):
            safe_alt = s['alt'].encode('ascii', 'replace').decode('ascii')
            print(f"    [{idx+1}] {safe_alt}")
            
    return pinterest_results

if __name__ == "__main__":
    y_res = run_yandex_verification()
    p_res = run_pinterest_verification()
    
    print("\n" + "=" * 70)
    print("FINAL SUMMARY OF VERIFICATION RUN")
    print("=" * 70)
    print("Yandex Results:")
    print(json.dumps(y_res, indent=2))
    print("\nPinterest Results:")
    print(json.dumps(p_res, indent=2))
