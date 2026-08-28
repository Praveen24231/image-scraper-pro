import sys
import os
import json
import time

sys.path.insert(0, os.path.abspath("image-scraper-pro/backend"))

from pinterest_resource_scraper import extract_pinterest_resource_api

def run_pinterest_verification():
    print("\n" + "=" * 70)
    print("RUNNING PINTEREST RELEVANCE & VOLUME VERIFICATION SUITE")
    print("=" * 70)
    
    test_pins = [
        ("Target User Pin (Boy Curly Haircut)", "https://in.pinterest.com/pin/980869993858369758/"),
        ("Pin 2 (Honda Bike Old Model)", "https://in.pinterest.com/pin/1136033074757270594/"),
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
    p_res = run_pinterest_verification()
    print("\nPinterest Results JSON:")
    print(json.dumps(p_res, indent=2))
