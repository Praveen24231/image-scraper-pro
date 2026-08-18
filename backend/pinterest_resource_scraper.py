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
    Direct Pinterest JSON Resource API Extraction Pipeline with Strict Relevance:
    1. Parses seed Pin ID and initializes Pinterest session cookies.
    2. Extracts Target Pin original image, title, and native semantic annotations (visualAnnotation, seoBreadcrumbs, annotationsWithLinksArray).
    3. Establishes the Target Pin as reference Item #1.
    4. Derives highly targeted search queries strictly from the Pin's visual annotations.
    5. Progressively queries BaseSearchResource to gather up to 300+ relevant high-res images.
    6. Filters out UI sprites, avatars, and deduplicates across all resolutions.
    """
    t_start = time.time()
    url_type, pin_id = parse_pinterest_url(target_url)
    
    if pin_id == "UNKNOWN":
        return {
            "success": False,
            "error": "Invalid Pinterest Pin URL. Example: https://in.pinterest.com/pin/980869993858369758/",
            "images": [],
            "count": 0
        }

    session = requests.Session()
    session.headers.update(HEADERS)

    # 1. Fetch seed pin page HTML to extract SSR initial state & visual annotations
    target_img_url = None
    target_title = ""
    visual_annotations = []
    breadcrumbs = []
    target_topic_urls = []
    seed_page_url = f"https://www.pinterest.com/pin/{pin_id}/"
    
    try:
        r_init = session.get(seed_page_url, timeout=12)
        html_raw = r_init.text
        csrf = session.cookies.get("csrftoken") or session.cookies.get("_pinterest_sess") or ""
        if csrf:
            session.headers["X-CSRFToken"] = csrf
            
        # Parse JSON-LD
        ld_jsons = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_raw, re.DOTALL)
        for lj in ld_jsons:
            try:
                data = json.loads(lj)
                if isinstance(data, dict):
                    h = data.get("headline") or data.get("name")
                    if h:
                        target_title = unescape(str(h)).strip()
                    if data.get("image"):
                        target_img_url = data.get("image")
            except Exception:
                pass
                
        # Parse visualAnnotation array from initial Relay/PWS data
        va_match = re.search(r'"visualAnnotation"\s*:\s*(\[[^\]]+\])', html_raw)
        if va_match:
            try:
                for va in json.loads(va_match.group(1)):
                    clean_va = unescape(str(va)).strip()
                    if clean_va and clean_va not in visual_annotations:
                        visual_annotations.append(clean_va)
            except Exception:
                pass
                
        # Parse annotationsWithLinksArray
        awl_matches = re.findall(r'\{"name":"([^"]+)","url":"(/ideas/[^"]+)"\}', html_raw)
        for name, topic_path in awl_matches:
            u_name = unescape(name).strip()
            if u_name and u_name not in visual_annotations:
                visual_annotations.append(u_name)
            full_topic_url = f"https://www.pinterest.com{topic_path}"
            if full_topic_url not in target_topic_urls:
                target_topic_urls.append(full_topic_url)
                
        # Parse seoBreadcrumbs
        bc_matches = re.findall(r'"seoBreadcrumbs"\s*:\s*(\[[^\]]+\])', html_raw)
        for bcm in bc_matches:
            try:
                items = json.loads(bcm)
                for it in items:
                    name = it.get("name")
                    if name and name not in breadcrumbs:
                        breadcrumbs.append(unescape(str(name)).strip())
            except Exception:
                pass

        # Meta tags
        meta_titles = re.findall(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html_raw)
        for mt in meta_titles:
            c = unescape(mt).split("|")[0].strip()
            if c and not target_title:
                target_title = c

    except Exception as e:
        print(f"[pinterest-resource] Initial HTML fetch notice: {e}")

    # Telemetry and categorization counters
    telemetry = {
        "pin_id": pin_id,
        "pinterest_url_type": url_type,
        "target_pin_images": 0,
        "visual_search_candidates": 0,
        "related_pin_candidates": 0,
        "recommended_candidates": 0,
        "ui_profile_rejected": 0,
        "duplicates_removed": 0,
        "unrelated_rejected": 0,
        "final_accepted_images": 0,
        "queries_used": 0,
        "stop_reason": "UNKNOWN",
        "execution_time_sec": 0.0
    }

    collected_images = []
    seen_hashes = set(IGNORE_HASHES)

    # 2. Fetch seed pin details via PinResource if needed
    session.headers.update({
        "Accept": "application/json, text/javascript, */*, q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "X-Pinterest-AppState": "active",
        "X-Pinterest-PWS-Handler": "www/[username]/[slug].js",
    })

    pin_payload = {"options": {"id": pin_id, "field_set_key": "detailed"}, "context": {}}
    url_pin = f"https://www.pinterest.com/resource/PinResource/get/?source_url={quote(f'/pin/{pin_id}/')}&data={quote(json.dumps(pin_payload))}"
    
    try:
        r_pin = session.get(url_pin, timeout=10)
        if r_pin.status_code == 200:
            p_data = r_pin.json().get("resource_response", {}).get("data", {})
            t_pin = p_data.get("title") or p_data.get("grid_title") or p_data.get("description") or ""
            if t_pin and not target_title:
                target_title = unescape(str(t_pin)).strip()
            # Extract target image
            images_dict = p_data.get("images") or {}
            orig_obj = images_dict.get("orig") or images_dict.get("736x") or images_dict.get("474x")
            if orig_obj and isinstance(orig_obj, dict) and orig_obj.get("url"):
                target_img_url = orig_obj["url"]
    except Exception as e:
        print(f"[pinterest-resource] PinResource notice: {e}")

    # Establish Reference Target Pin as Item #1
    if target_img_url:
        orig = upgrade_to_original_url(target_img_url)
        fn = orig.split("/")[-1]
        h = fn.split(".")[0] if "." in fn else fn
        if h not in seen_hashes:
            seen_hashes.add(h)
            telemetry["target_pin_images"] += 1
            telemetry["final_accepted_images"] += 1
            collected_images.append({
                "url": orig,
                "thumb": target_img_url,
                "width": "Original",
                "height": "Original",
                "alt": f"Target Pin: {target_title or (visual_annotations[0] if visual_annotations else 'Target Pin')}"
            })

    def process_item(item, source_label=""):
        if not isinstance(item, dict):
            return False
        telemetry["visual_search_candidates"] += 1
        
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
            
        # Reject UI icons, sprites, avatars
        if any(ign in orig_candidate for ign in ["avatar", "75x75_RS", "sprite", "favicon"]):
            telemetry["ui_profile_rejected"] += 1
            return False

        orig_url = upgrade_to_original_url(orig_candidate)
        filename = orig_url.split("/")[-1]
        img_hash = filename.split(".")[0] if "." in filename else filename
        
        if img_hash in seen_hashes:
            telemetry["duplicates_removed"] += 1
            return False
            
        seen_hashes.add(img_hash)
        title = item.get("title") or item.get("grid_title") or item.get("description") or source_label or target_title
        
        collected_images.append({
            "url": orig_url,
            "thumb": thumb_candidate or orig_url,
            "width": "Original",
            "height": "Original",
            "alt": unescape(str(title)).strip()
        })
        telemetry["final_accepted_images"] += 1
        return True

    # 3. Build strictly targeted search queries based on visual annotations and breadcrumbs
    search_queries = []
    seen_q = set()

    for va in visual_annotations:
        if va.lower() not in seen_q:
            seen_q.add(va.lower())
            search_queries.append(va)

    if target_title:
        clean_t = " ".join([w for w in re.sub(r'[^\w\s]', ' ', target_title).split() if len(w) > 2][:4])
        if clean_t.lower() not in seen_q:
            seen_q.add(clean_t.lower())
            search_queries.append(clean_t)

    if visual_annotations and breadcrumbs:
        combo = f"{visual_annotations[0]} {breadcrumbs[-1]}"
        if combo.lower() not in seen_q:
            seen_q.add(combo.lower())
            search_queries.append(combo)

    # Fallback to general title if no visual annotations exist
    if not search_queries:
        if target_title:
            search_queries.append(target_title)
        else:
            search_queries.append("aesthetic photography")

    telemetry["queries_used"] = len(search_queries)

    # 4. Progressively paginate BaseSearchResource across visual annotation queries
    stop_reason = "UNKNOWN"
    for q in search_queries:
        if len(collected_images) >= max_images:
            stop_reason = "MAX_REACHED"
            break
        if len(collected_images) >= min_target:
            stop_reason = "TARGET_REACHED"
            break
            
        bookmark = None
        for page_idx in range(1, 14):
            if len(collected_images) >= max_images or len(collected_images) >= min_target:
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
                print(f"[pinterest-resource] BaseSearchResource warning on '{q}': {e}")
                break

    elapsed = time.time() - t_start
    if stop_reason == "UNKNOWN":
        if len(collected_images) >= max_images:
            stop_reason = "MAX_REACHED"
        elif len(collected_images) >= min_target:
            stop_reason = "TARGET_REACHED"
        else:
            stop_reason = "ALL_QUERIES_EXHAUSTED"

    telemetry["stop_reason"] = stop_reason
    telemetry["execution_time_sec"] = round(elapsed, 2)
    telemetry["unique_images"] = len(collected_images)

    print(f"[pinterest-resource] Pipeline complete: {len(collected_images)} relevant images collected in {telemetry['execution_time_sec']}s (stop={stop_reason})")

    return {
        "success": len(collected_images) > 0,
        "source": "pinterest",
        "source_url": target_url,
        "count": len(collected_images),
        "images": collected_images[:max_images],
        "telemetry": telemetry
    }
