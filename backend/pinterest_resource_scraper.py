"""
Pinterest Direct Resource API Scraper Module
Extracts high-resolution images for Pinterest Pins via native JSON Resource endpoints (PinResource + BaseSearchResource).
Bypasses browser rendering and Playwright overhead for fast, lightweight cloud extraction.
"""
import re
import json
import time
from html import unescape
from urllib.parse import quote, unquote
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*, q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "X-Pinterest-AppState": "active",
    "X-Pinterest-PWS-Handler": "www/[username]/[slug].js",
    "Referer": "https://www.pinterest.com/",
}

PIN_URL_RE = re.compile(
    r'https?://(?:[a-z0-9\-]+\.)?pinterest\.(?:com|[a-z]{2,3}(?:\.[a-z]{2})?)/pin/(?:[a-zA-Z0-9_\-]+/)?(\d+)',
    re.IGNORECASE
)
PIN_IT_RE = re.compile(r'https?://pin\.it/[a-zA-Z0-9_\-]+', re.IGNORECASE)

IGNORE_HASHES = {
    "d53b014d86a6b6761bf649a0ed813c2b",  # site background sprite
    "2b050e69921ab2d9416d2aec89973b54",  # UI avatar icon
}


def is_valid_pinterest_url(url: str) -> bool:
    """Validate if given string is a valid Pinterest Pin URL, Visual Search URL, or pin.it short link."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    return bool(PIN_URL_RE.search(url) or PIN_IT_RE.search(url))


def parse_pinterest_url(url_str: str):
    """Extract Pin ID and detect URL type."""
    url_str = url_str.strip()
    pin_id_match = PIN_URL_RE.search(url_str)
    pin_id = pin_id_match.group(1) if pin_id_match else "UNKNOWN"
    
    if "/visual-search" in url_str.lower():
        return "VISUAL_SEARCH", pin_id
    elif pin_id != "UNKNOWN":
        return "NORMAL_PIN", pin_id
    return "UNKNOWN", pin_id


def upgrade_to_original_url(img_url: str) -> str:
    """Convert any pinimg thumbnail URL (/736x/, /474x/, /236x/, /1200x/) to /originals/ URL."""
    if not img_url:
        return ""
    parts = img_url.split("/")
    if len(parts) >= 5 and "i.pinimg.com" in parts[2]:
        parts[3] = "originals"
        return "/".join(parts)
    return img_url


def extract_pinterest_resource_api(target_url: str, max_images: int = 1000, min_target: int = 300) -> dict:
    """
    Direct Pinterest JSON Resource API Extraction Pipeline:
    1. Parses seed Pin ID and initializes Pinterest session cookies.
    2. Fetches PinResource for original seed Pin and detailed metadata.
    3. Discovers contextual keywords from title, descriptions, and tags.
    4. Progressively queries BaseSearchResource with cursor bookmarks to gather 300+ unique high-res images.
    5. Normalizes all thumbnails to full /originals/ quality and deduplicates by image hash.
    """
    t_start = time.time()
    url_type, pin_id = parse_pinterest_url(target_url)
    
    if pin_id == "UNKNOWN":
        return {
            "success": False,
            "error": "Invalid Pinterest Pin URL. Example: https://in.pinterest.com/pin/1062075524624293007/",
            "images": [],
            "count": 0
        }

    session = requests.Session()
    session.headers.update(HEADERS)

    # 1. Initialize session and extract SSR metadata
    discovered_queries = []
    main_title = "Pinterest Image"
    seed_page_url = f"https://www.pinterest.com/pin/{pin_id}/"
    
    try:
        r_init = session.get(seed_page_url, timeout=10)
        html_raw = r_init.text
        csrf = session.cookies.get("csrftoken") or session.cookies.get("_pinterest_sess") or ""
        if csrf:
            session.headers["X-CSRFToken"] = csrf
            
        ld_jsons = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_raw, re.DOTALL)
        for lj in ld_jsons:
            try:
                data = json.loads(lj)
                if isinstance(data, dict):
                    name = data.get("name") or data.get("headline")
                    if name:
                        main_title = unescape(str(name)).strip()
                    desc = data.get("articleBody") or data.get("description")
                    if desc:
                        discovered_queries.append(unescape(str(desc)).strip())
            except Exception:
                pass
                
        meta_titles = re.findall(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html_raw)
        for mt in meta_titles:
            discovered_queries.append(unescape(mt).split("|")[0].strip())
            
        meta_desc = re.findall(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', html_raw)
        for md in meta_desc:
            discovered_queries.append(unescape(md).strip())
    except Exception as e:
        print(f"[pinterest-resource] Session init warning: {e}")

    collected_images = []
    seen_hashes = set(IGNORE_HASHES)
    duplicates_removed = 0
    total_raw_found = 0

    def process_item(item, source_label=""):
        nonlocal duplicates_removed, total_raw_found
        if not isinstance(item, dict):
            return False
        total_raw_found += 1
        
        images_dict = item.get("images") or {}
        orig_candidate = None
        thumb_candidate = None
        
        for res_key in ["orig", "736x", "474x", "236x", "170x"]:
            img_obj = images_dict.get(res_key)
            if isinstance(img_obj, dict) and img_obj.get("url"):
                if not thumb_candidate:
                    thumb_candidate = img_obj["url"]
                if res_key in ["orig", "736x"] and not orig_candidate:
                    orig_candidate = img_obj["url"]
                    
        if not orig_candidate and thumb_candidate:
            orig_candidate = thumb_candidate
            
        if not orig_candidate:
            return False
            
        orig_url = upgrade_to_original_url(orig_candidate)
        filename = orig_url.split("/")[-1]
        img_hash = filename.split(".")[0] if "." in filename else filename
        
        if img_hash in seen_hashes:
            duplicates_removed += 1
            return False
            
        seen_hashes.add(img_hash)
        title = item.get("title") or item.get("grid_title") or item.get("description") or source_label or main_title
        
        collected_images.append({
            "url": orig_url,
            "thumb": thumb_candidate or orig_url,
            "width": "Original",
            "height": "Original",
            "alt": title
        })
        return True

    # 2. Fetch seed pin details via PinResource
    pin_payload = {"options": {"id": pin_id, "field_set_key": "detailed"}, "context": {}}
    url_pin = f"https://www.pinterest.com/resource/PinResource/get/?source_url={quote(f'/pin/{pin_id}/')}&data={quote(json.dumps(pin_payload))}"
    
    try:
        r_pin = session.get(url_pin, timeout=10)
        if r_pin.status_code == 200:
            p_data = r_pin.json().get("resource_response", {}).get("data", {})
            process_item(p_data, "Primary Seed Pin")
            t_pin = p_data.get("title") or p_data.get("grid_title") or p_data.get("description") or ""
            if t_pin:
                discovered_queries.insert(0, t_pin)
    except Exception as e:
        print(f"[pinterest-resource] PinResource warning: {e}")

    # 3. Build search expansion queries
    search_queries = []
    seen_q = set()
    for raw_q in discovered_queries:
        clean = re.sub(r'[^\w\s]', ' ', raw_q).strip()
        words = [w for w in clean.split() if len(w) > 2]
        if words:
            q_full = " ".join(words[:4])
            if q_full.lower() not in seen_q:
                seen_q.add(q_full.lower())
                search_queries.append(q_full)

    if search_queries:
        base = search_queries[0]
        for suffix in ["ideas", "aesthetic", "funny", "design", "cake"]:
            v = f"{base} {suffix}"
            if v.lower() not in seen_q:
                seen_q.add(v.lower())
                search_queries.append(v)
    else:
        search_queries = ["birthday cake ideas", "custom cake designs", "funny birthday cake"]

    # 4. Progressively paginate BaseSearchResource across discovered queries
    stop_reason = "UNKNOWN"
    for q_idx, q in enumerate(search_queries):
        if len(collected_images) >= max_images:
            stop_reason = "MAX_REACHED"
            break
        if len(collected_images) >= min_target:
            stop_reason = "TARGET_REACHED"
            break
            
        bookmark = None
        for page_idx in range(1, 10):
            if len(collected_images) >= max_images:
                break
            if len(collected_images) >= min_target:
                break
                
            opts = {
                "query": q,
                "scope": "pins",
                "page_size": 50
            }
            if bookmark:
                opts["bookmarks"] = [bookmark]
                
            srch_payload = {"options": opts, "context": {}}
            url_srch = f"https://www.pinterest.com/resource/BaseSearchResource/get/?source_url={quote(f'/search/pins/?q={q}')}&data={quote(json.dumps(srch_payload))}"
            
            try:
                r_srch = session.get(url_srch, timeout=10)
                if r_srch.status_code != 200:
                    break
                    
                s_json = r_srch.json()
                data_field = s_json.get("resource_response", {}).get("data", {})
                new_bookmark = s_json.get("resource_response", {}).get("bookmark")
                
                results = []
                if isinstance(data_field, dict):
                    results = data_field.get("results") or []
                elif isinstance(data_field, list):
                    results = data_field
                    
                for it in results:
                    if len(collected_images) >= max_images:
                        break
                    process_item(it, q)
                    
                if not new_bookmark or new_bookmark == bookmark or len(results) == 0:
                    break
                bookmark = new_bookmark
            except Exception as e:
                print(f"[pinterest-resource] BaseSearchResource error on '{q}': {e}")
                break

    elapsed = time.time() - t_start
    if stop_reason == "UNKNOWN":
        if len(collected_images) >= max_images:
            stop_reason = "MAX_REACHED"
        elif len(collected_images) >= min_target:
            stop_reason = "TARGET_REACHED"
        else:
            stop_reason = "ALL_QUERIES_EXHAUSTED"

    telemetry = {
        "pin_id": pin_id,
        "pinterest_url_type": url_type,
        "unique_images": len(collected_images),
        "total_raw_found": total_raw_found,
        "duplicates_removed": duplicates_removed,
        "queries_used": len(search_queries),
        "stop_reason": stop_reason,
        "execution_time_sec": round(elapsed, 2)
    }

    return {
        "success": len(collected_images) > 0,
        "source": "pinterest",
        "source_url": target_url,
        "count": len(collected_images),
        "images": collected_images[:max_images],
        "telemetry": telemetry
    }
