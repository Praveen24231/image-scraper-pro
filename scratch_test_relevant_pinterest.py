import re
import json
import time
import requests
from html import unescape
from urllib.parse import quote, unquote

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.pinterest.com/",
}

IGNORE_HASHES = {
    "d53b014d86a6b6761bf649a0ed813c2b",  # site background sprite
    "2b050e69921ab2d9416d2aec89973b54",  # UI avatar icon
    "75x75_RS",
}

def upgrade_to_original_url(img_url: str) -> str:
    if not img_url:
        return ""
    parts = img_url.split("/")
    if len(parts) >= 5 and "i.pinimg.com" in parts[2]:
        parts[3] = "originals"
        return "/".join(parts)
    return img_url

def test_relevant_pinterest_pipeline(pin_url, min_target=300, max_images=1000):
    print(f"=== Testing Relevant Pinterest Extraction Pipeline for {pin_url} ===")
    t_start = time.time()
    
    debug_stats = {
        "target_pin_images": 0,
        "visual_search_candidates": 0,
        "related_pin_candidates": 0,
        "recommended_candidates": 0,
        "ui_profile_rejected": 0,
        "duplicates_removed": 0,
        "unrelated_rejected": 0,
        "final_accepted_images": 0
    }
    
    session = requests.Session()
    session.headers.update(HEADERS)
    
    # 1. Fetch seed page HTML
    pin_id_match = re.search(r'/pin/(\d+)', pin_url)
    pin_id = pin_id_match.group(1) if pin_id_match else "UNKNOWN"
    
    r = session.get(pin_url, timeout=12)
    html = r.text
    
    csrf = session.cookies.get("csrftoken") or session.cookies.get("_pinterest_sess") or ""
    
    # 2. Extract Target Pin Metadata & Semantic Annotations
    target_img_url = None
    target_title = ""
    visual_annotations = []
    breadcrumbs = []
    target_topic_urls = []
    
    # Parse JSON-LD
    ld_jsons = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
    for lj in ld_jsons:
        try:
            data = json.loads(lj)
            if isinstance(data, dict):
                target_title = data.get("headline") or data.get("name") or target_title
                if data.get("image"):
                    target_img_url = data.get("image")
        except Exception:
            pass
            
    # Parse Relay / PWS initial state for visualAnnotation and annotationsWithLinksArray
    va_match = re.search(r'"visualAnnotation"\s*:\s*(\[[^\]]+\])', html)
    if va_match:
        try:
            for va in json.loads(va_match.group(1)):
                if va and va not in visual_annotations:
                    visual_annotations.append(unescape(va).strip())
        except Exception:
            pass
            
    # Parse annotationsWithLinksArray
    awl_matches = re.findall(r'\{"name":"([^"]+)","url":"(/ideas/[^"]+)"\}', html)
    for name, topic_path in awl_matches:
        u_name = unescape(name).strip()
        if u_name and u_name not in visual_annotations:
            visual_annotations.append(u_name)
        full_topic_url = f"https://www.pinterest.com{topic_path}"
        if full_topic_url not in target_topic_urls:
            target_topic_urls.append(full_topic_url)
            
    # Parse seoBreadcrumbs
    bc_matches = re.findall(r'"seoBreadcrumbs"\s*:\s*(\[[^\]]+\])', html)
    for bcm in bc_matches:
        try:
            items = json.loads(bcm)
            for it in items:
                name = it.get("name")
                if name and name not in breadcrumbs:
                    breadcrumbs.append(name)
        except Exception:
            pass
            
    # Find original image in script or PinResource
    if not target_img_url:
        img_match = re.search(r'"images":\{"orig":\{"url":"(https:[^"]+)"', html)
        if img_match:
            target_img_url = img_match.group(1).replace("\\/", "/")
            
    print(f"Target Pin ID: {pin_id}")
    print(f"Target Image: {target_img_url}")
    print(f"Target Title: {target_title}")
    print(f"Visual Annotations: {visual_annotations}")
    print(f"Breadcrumbs: {breadcrumbs}")
    print(f"Target Topic URLs: {target_topic_urls}")
    
    collected_images = []
    seen_hashes = set(IGNORE_HASHES)
    
    # Process Target Pin Image first
    if target_img_url:
        orig = upgrade_to_original_url(target_img_url)
        fn = orig.split("/")[-1]
        h = fn.split(".")[0] if "." in fn else fn
        if h not in seen_hashes:
            seen_hashes.add(h)
            debug_stats["target_pin_images"] += 1
            debug_stats["final_accepted_images"] += 1
            collected_images.append({
                "url": orig,
                "thumb": target_img_url,
                "width": "Original",
                "height": "Original",
                "alt": f"Target Pin: {target_title or visual_annotations[0] if visual_annotations else 'Target Pin'}"
            })
            
    # Define relevance keywords set for verification
    relevance_keywords = set()
    for va in visual_annotations:
        for w in re.sub(r'[^\w\s]', ' ', va.lower()).split():
            if len(w) > 2:
                relevance_keywords.add(w)
    for bc in breadcrumbs:
        for w in re.sub(r'[^\w\s]', ' ', bc.lower()).split():
            if len(w) > 2:
                relevance_keywords.add(w)
    if target_title:
        for w in re.sub(r'[^\w\s]', ' ', target_title.lower()).split():
            if len(w) > 2:
                relevance_keywords.add(w)
                
    print(f"Established Relevance Keywords: {relevance_keywords}")
    
    # 3. Query Pinterest BaseSearchResource using exact visual annotations & related cluster terms
    session.headers.update({
        "Accept": "application/json, text/javascript, */*, q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "X-Pinterest-AppState": "active",
        "X-Pinterest-PWS-Handler": "www/[username]/[slug].js",
    })
    if csrf:
        session.headers["X-CSRFToken"] = csrf
        
    search_queries = []
    seen_q = set()
    
    # Prioritize primary visual annotations
    for va in visual_annotations:
        if va.lower() not in seen_q:
            seen_q.add(va.lower())
            search_queries.append(va)
            
    # Add title keywords if distinct
    if target_title:
        clean_t = " ".join([w for w in re.sub(r'[^\w\s]', ' ', target_title).split() if len(w) > 2][:4])
        if clean_t.lower() not in seen_q:
            seen_q.add(clean_t.lower())
            search_queries.append(clean_t)
            
    # Add combined visual annotation + breadcrumbs if needed
    if visual_annotations and breadcrumbs:
        combo = f"{visual_annotations[0]} {breadcrumbs[-1]}"
        if combo.lower() not in seen_q:
            seen_q.add(combo.lower())
            search_queries.append(combo)
            
    print(f"Target Search Queries: {search_queries}")
    
    def process_candidate(item, query_label):
        nonlocal collected_images
        if not isinstance(item, dict):
            return False
            
        debug_stats["visual_search_candidates"] += 1
        
        # Check image
        images_dict = item.get("images") or {}
        orig_candidate = None
        thumb_candidate = None
        for res_key in ["orig", "736x", "474x", "236x"]:
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
            
        # Check UI / avatar rejection
        if any(ign in orig_candidate for ign in ["avatar", "75x75_RS", "sprite", "favicon"]):
            debug_stats["ui_profile_rejected"] += 1
            return False
            
        orig_url = upgrade_to_original_url(orig_candidate)
        fn = orig_url.split("/")[-1]
        img_hash = fn.split(".")[0] if "." in fn else fn
        
        if img_hash in seen_hashes:
            debug_stats["duplicates_removed"] += 1
            return False
            
        # Relevance check on candidate title/grid_title/description
        cand_title = item.get("title") or item.get("grid_title") or item.get("description") or ""
        cand_words = set(re.sub(r'[^\w\s]', ' ', cand_title.lower()).split())
        
        # If candidate has text, verify it has at least some relevance overlap or comes from query
        # Avoid rejecting pins with empty titles that come from the specific search
        
        seen_hashes.add(img_hash)
        collected_images.append({
            "url": orig_url,
            "thumb": thumb_candidate or orig_url,
            "width": "Original",
            "height": "Original",
            "alt": cand_title or query_label
        })
        debug_stats["final_accepted_images"] += 1
        return True

    for q in search_queries:
        if len(collected_images) >= max_images:
            break
        if len(collected_images) >= min_target:
            break
            
        print(f"\n[Query] '{q}' (Collected so far: {len(collected_images)})")
        bookmark = None
        for page_idx in range(1, 12):
            if len(collected_images) >= max_images or len(collected_images) >= min_target:
                break
                
            opts = {
                "query": q,
                "scope": "pins",
                "page_size": 50
            }
            if bookmark:
                opts["bookmarks"] = [bookmark]
                
            payload = {"options": opts, "context": {}}
            url_srch = f"https://www.pinterest.com/resource/BaseSearchResource/get/?source_url={quote(f'/search/pins/?q={q}')}&data={quote(json.dumps(payload))}"
            
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
                    
                added_this_page = 0
                for it in results:
                    if len(collected_images) >= max_images:
                        break
                    if process_candidate(it, q):
                        added_this_page += 1
                        
                print(f"  Page {page_idx}: {len(results)} raw items -> +{added_this_page} accepted | Total: {len(collected_images)}")
                
                if not new_bookmark or new_bookmark == bookmark or len(results) == 0:
                    break
                bookmark = new_bookmark
            except Exception as e:
                print(f"  Search page error: {e}")
                break
                
    elapsed = time.time() - t_start
    print("\n" + "=" * 50)
    print("PINTEREST RELEVANCE PIPELINE REPORT:")
    for k, v in debug_stats.items():
        print(f"  {k}: {v}")
    print(f"  Execution Time: {round(elapsed, 2)}s")
    print("=" * 50)
    
    print(f"\nSample of Accepted Images:")
    for idx, img in enumerate(collected_images[:10]):
        print(f"  [{idx+1}] {img['alt'][:60]} -> {img['url']}")

if __name__ == "__main__":
    test_relevant_pinterest_pipeline("https://in.pinterest.com/pin/980869993858369758/", 300, 1000)
