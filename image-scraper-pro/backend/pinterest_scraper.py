"""
Pinterest Pin URL + Visual Search + Related Pins Scraper Module
Extracts high-resolution images for Normal Pins & Visual Search URLs via Playwright Chromium.
Does NOT modify or touch Yandex scraper logic.
"""
import re
import json
from html import unescape
from urllib.parse import quote, urlparse
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.pinterest.com/",
}

# Matches standard pins (/pin/12345/) and visual search pins (/pin/12345/visual-search/...)
PIN_URL_RE = re.compile(
    r'https?://(?:[a-z0-9\-]+\.)?pinterest\.(?:com|[a-z]{2,3}(?:\.[a-z]{2})?)/pin/(?:[a-zA-Z0-9_\-]+/)?(\d+)',
    re.IGNORECASE
)
PIN_IT_RE = re.compile(r'https?://pin\.it/[a-zA-Z0-9_\-]+', re.IGNORECASE)

# Static UI site assets / icons / avatars to ignore
IGNORE_HASHES = {
    "d53b014d86a6b6761bf649a0ed813c2b",  # site background sprite
    "2b050e69921ab2d9416d2aec89973b54",  # UI avatar icon
}


def is_valid_pinterest_url(url: str) -> bool:
    """Validate if given string is a valid Pinterest Pin URL, Visual Search URL, or pin.it short link."""
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if PIN_URL_RE.search(url) or PIN_IT_RE.search(url):
        return True
    return False


def parse_pinterest_url(url_str: str):
    """
    Extract Pin ID and detect URL type (NORMAL_PIN vs VISUAL_SEARCH).
    """
    url_str = url_str.strip()
    pin_id_match = PIN_URL_RE.search(url_str)
    pin_id = pin_id_match.group(1) if pin_id_match else "UNKNOWN"
    
    if "/visual-search" in url_str.lower():
        return "VISUAL_SEARCH", pin_id
    elif pin_id != "UNKNOWN":
        return "NORMAL_PIN", pin_id
    return "UNKNOWN", pin_id


def get_original_image_candidate(img_url: str) -> str:
    """Convert any pinimg thumbnail URL (/736x/, /474x/, /236x/, /1200x/) to /originals/ candidate."""
    if not img_url:
        return ""
    parts = img_url.split("/")
    if len(parts) >= 5 and "i.pinimg.com" in parts[2]:
        parts[3] = "originals"
        return "/".join(parts)
    return img_url


# Crawling configuration defaults
DEFAULT_MIN_TARGET = 300
DEFAULT_MAX_IMAGES = 1000
MAX_TOPIC_PAGES = 12
MAX_SCROLLS_PER_TOPIC = 6
PAGE_TIMEOUT_MS = 25000


def scrape_pinterest_hybrid_playwright(target_url: str, min_target: int = DEFAULT_MIN_TARGET, max_images: int = DEFAULT_MAX_IMAGES):
    """
    Playwright Chromium browser automation engine:
    1. Opens seed Pin (or resolves Visual Search to seed Pin ID).
    2. Extracts main Pin image & metadata.
    3. Dynamically discovers related /ideas/... topic cluster URLs from the Pin page.
    4. Crawls discovered /ideas/... topic pages with progressive scrolling to collect high-res images.
    5. Deduplicates by image hash and stops when target (min 300) / max (1000) is reached or topics exhausted.
    """
    url_type, pin_id = parse_pinterest_url(target_url)
    print(f"\n{'=' * 60}")
    print(f"[playwright-pinterest] Starting Extraction | Type: {url_type} | Pin ID: {pin_id}")
    print(f"URL: {target_url}")
    print(f"Target: min={min_target}, max={max_images}")
    print(f"{'=' * 60}")

    collected_images = []
    seen_hashes = set(IGNORE_HASHES)
    duplicates_removed = 0
    main_title = "Pinterest Image"
    main_pin_images_count = 0
    discovered_topic_urls = []
    total_raw_found = 0
    final_page_url = target_url
    stop_reason = "UNKNOWN"

    def process_image_url(raw_u, alt_text=""):
        nonlocal duplicates_removed, total_raw_found
        total_raw_found += 1
        if len(collected_images) >= max_images:
            return False

        orig = get_original_image_candidate(raw_u)
        path_parts = orig.split("/")
        img_filename = path_parts[-1] if path_parts else orig
        img_hash = img_filename.split(".")[0] if "." in img_filename else img_filename

        if img_hash in seen_hashes:
            duplicates_removed += 1
            return False

        seen_hashes.add(img_hash)
        collected_images.append({
            "url": orig,
            "thumb": raw_u,
            "width": "Original",
            "height": "Original",
            "alt": alt_text or main_title
        })
        return True

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080}
            )
            page = context.new_page()

            network_images = set()
            def handle_response(response):
                res_u = response.url
                if "i.pinimg.com" in res_u:
                    network_images.add(res_u)

            page.on("response", handle_response)

            # STEP 1 & 2: Load Seed Pin Closeup Page
            seed_pin_url = f"https://www.pinterest.com/pin/{pin_id}/" if pin_id != "UNKNOWN" else target_url
            print(f"\n[STEP 1] Loading Seed Pin Page: {seed_pin_url}")
            try:
                page.goto(seed_pin_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                page.wait_for_timeout(2500)
                final_page_url = page.url

                html_initial = page.content()

                # Extract headline/title
                ld_jsons = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html_initial, re.DOTALL)
                for lj in ld_jsons:
                    try:
                        data = json.loads(lj)
                        if isinstance(data, dict):
                            headline = data.get("headline") or data.get("name") or data.get("articleBody")
                            if headline:
                                main_title = unescape(str(headline)).strip()
                    except Exception:
                        pass

                # Process seed page images
                init_matches = re.findall(r'https?://i\.pinimg\.com/[0-9a-z_x/]+/[0-9a-f/]+\.(?:jpg|png|webp)', html_initial, re.IGNORECASE)
                for m in init_matches:
                    process_image_url(m, main_title)

                # Single scroll on seed page for lazy elements
                page.evaluate("window.scrollBy(0, 2000)")
                page.wait_for_timeout(1000)
                seed_rendered = page.content()
                for m in set(re.findall(r'https?://i\.pinimg\.com/[0-9a-z_x/]+/[0-9a-f/]+\.(?:jpg|png|webp)', seed_rendered, re.IGNORECASE)).union(network_images):
                    process_image_url(m, main_title)

                main_pin_images_count = len(collected_images)
                safe_title = main_title.encode("ascii", "replace").decode("ascii")
                print(f"MAIN PIN IMAGES: {main_pin_images_count} (Title: '{safe_title}')")

                # STEP 3: Discover specific /ideas/... topic cluster links from Pin's native annotations
                target_annotations = []
                va_match = re.search(r'"visualAnnotation"\s*:\s*(\[[^\]]+\])', html_initial)
                if va_match:
                    try:
                        for va in json.loads(va_match.group(1)):
                            clean_va = unescape(str(va)).strip()
                            if clean_va and clean_va not in target_annotations:
                                target_annotations.append(clean_va)
                    except Exception:
                        pass

                # Extract specific topic URLs from target Pin's annotationsWithLinksArray
                awl_matches = re.findall(r'\{"name":"([^"]+)","url":"(/ideas/[^"]+)"\}', html_initial)
                seen_topics = set()
                for name, topic_path in awl_matches:
                    u_name = unescape(name).strip()
                    if u_name and u_name not in target_annotations:
                        target_annotations.append(u_name)
                    full_href = f"https://www.pinterest.com{topic_path}".split("?")[0].rstrip("/") + "/"
                    if full_href not in seen_topics:
                        seen_topics.add(full_href)
                        discovered_topic_urls.append(full_href)

                print(f"RELATED TARGET TOPIC LINKS FOUND: {len(discovered_topic_urls)}")
                for idx, t_url in enumerate(discovered_topic_urls[:10]):
                    print(f"  Topic [{idx+1}]: {t_url}")

            except Exception as e:
                print(f"[playwright-pinterest] Warning on seed pin: {e}")

            # STEP 4, 5, 6, 7 & 8: Crawl discovered /ideas/ topic pages
            topics_to_crawl = discovered_topic_urls[:MAX_TOPIC_PAGES]
            for t_idx, topic_url in enumerate(topics_to_crawl):
                if len(collected_images) >= max_images:
                    stop_reason = "MAX_REACHED"
                    break
                if len(collected_images) >= min_target and t_idx >= 3:
                    stop_reason = "TARGET_REACHED"
                    break

                topic_start_count = len(collected_images)
                raw_topic_count = 0
                print(f"\nTOPIC {t_idx + 1}/{len(topics_to_crawl)}:")
                print(f"URL = {topic_url}")

                try:
                    page.goto(topic_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
                    page.wait_for_timeout(2000)

                    topic_html = page.content()
                    topic_matches = re.findall(r'https?://i\.pinimg\.com/[0-9a-z_x/]+/[0-9a-f/]+\.(?:jpg|png|webp)', topic_html, re.IGNORECASE)
                    raw_topic_count += len(topic_matches)

                    for m in set(topic_matches).union(network_images):
                        if len(collected_images) >= max_images:
                            break
                        process_image_url(m, f"Topic: {topic_url.split('/')[4] if len(topic_url.split('/')) > 4 else main_title}")

                    # Progressive scrolling on topic page
                    no_new_scrolls = 0
                    for s in range(1, MAX_SCROLLS_PER_TOPIC + 1):
                        if len(collected_images) >= max_images:
                            break
                        prev_cnt = len(collected_images)
                        page.evaluate("window.scrollBy(0, 2000)")
                        page.wait_for_timeout(1000)

                        s_html = page.content()
                        s_matches = re.findall(r'https?://i\.pinimg\.com/[0-9a-z_x/]+/[0-9a-f/]+\.(?:jpg|png|webp)', s_html, re.IGNORECASE)
                        raw_topic_count += len(s_matches)

                        for m in set(s_matches).union(network_images):
                            if len(collected_images) >= max_images:
                                break
                            process_image_url(m, "Related Topic Image")

                        new_images_in_scroll = len(collected_images) - prev_cnt
                        if new_images_in_scroll == 0:
                            no_new_scrolls += 1
                            if no_new_scrolls >= 2:
                                break
                        else:
                            no_new_scrolls = 0

                    new_unique_from_topic = len(collected_images) - topic_start_count
                    print(f"Images found = {raw_topic_count}")
                    print(f"New unique images = {new_unique_from_topic} (Total Unique now: {len(collected_images)})")

                except Exception as te:
                    print(f"Warning crawling topic {topic_url}: {te}")

            # STEP 9: Search fallback if min_target not reached and title is available
            if len(collected_images) < min_target and main_title and main_title != "Pinterest Image" and main_title != "Pinterest":
                clean_query = re.sub(r'[^\w\s]', ' ', main_title).strip()
                if clean_query:
                    search_url = f"https://www.pinterest.com/search/pins/?q={quote(clean_query)}"
                    print(f"\n[FALLBACK SEARCH] Target {min_target} not reached yet ({len(collected_images)} collected).")
                    print(f"Searching: {search_url}")
                    try:
                        page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_timeout(2000)
                        for scroll in range(1, 8):
                            if len(collected_images) >= min_target or len(collected_images) >= max_images:
                                break
                            prev_cnt = len(collected_images)
                            page.evaluate("window.scrollBy(0, 2000)")
                            page.wait_for_timeout(1000)
                            s_html = page.content()
                            s_matches = re.findall(r'https?://i\.pinimg\.com/[0-9a-z_x/]+/[0-9a-f/]+\.(?:jpg|png|webp)', s_html, re.IGNORECASE)
                            for m in set(s_matches).union(network_images):
                                process_image_url(m, f"Search: {clean_query}")
                            print(f"Search scroll {scroll}: +{len(collected_images) - prev_cnt} images (Total: {len(collected_images)})")
                    except Exception as se:
                        print(f"Search fallback exception: {se}")

            browser.close()

        if stop_reason == "UNKNOWN":
            if len(collected_images) >= max_images:
                stop_reason = "MAX_REACHED"
            elif len(collected_images) >= min_target:
                stop_reason = "TARGET_REACHED"
            elif len(discovered_topic_urls) > 0 and len(discovered_topic_urls) <= MAX_TOPIC_PAGES:
                stop_reason = "ALL_TOPICS_EXHAUSTED"
            else:
                stop_reason = "NO_NEW_RESULTS"

        telemetry = {
            "pinterest_url_type": url_type,
            "pin_id": pin_id,
            "main_pin_images": main_pin_images_count,
            "topics_discovered": len(discovered_topic_urls),
            "topics_crawled": min(len(discovered_topic_urls), MAX_TOPIC_PAGES),
            "total_raw_found": total_raw_found,
            "duplicates_removed": duplicates_removed,
            "unique_images": len(collected_images),
            "stop_reason": stop_reason
        }

        print("\n" + "=" * 60)
        print(f"PIN ID: {pin_id}")
        print(f"MAIN PIN IMAGES: {main_pin_images_count}")
        print(f"RELATED /ideas/ LINKS FOUND: {len(discovered_topic_urls)}")
        print(f"TOTAL RAW IMAGES: {total_raw_found}")
        print(f"DUPLICATES REMOVED: {duplicates_removed}")
        print(f"TOTAL UNIQUE IMAGES: {len(collected_images)}")
        print(f"STOP REASON: {stop_reason}")
        print("=" * 60 + "\n")

        return collected_images, telemetry, final_page_url

    except Exception as e:
        print(f"[playwright-pinterest] Error during render: {e}")
        telemetry = {
            "pinterest_url_type": url_type,
            "pin_id": pin_id,
            "main_pin_images": 0,
            "topics_discovered": 0,
            "topics_crawled": 0,
            "total_raw_found": 0,
            "duplicates_removed": 0,
            "unique_images": 0,
            "stop_reason": "ERROR"
        }
        return [], telemetry, target_url


def scrape_pin_page_http_fallback(session: requests.Session, target_url: str):
    """Fast HTTP fallback if Playwright is unavailable."""
    try:
        r = session.get(target_url, timeout=8, allow_redirects=True)
        if r.status_code != 200 or "/pin/" not in r.url:
            return [], r.url
        html = r.text

        images_found = []
        title = "Pinterest Image"
        ld_jsons = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
        for lj in ld_jsons:
            try:
                data = json.loads(lj)
                if isinstance(data, dict):
                    headline = data.get("headline") or data.get("name") or data.get("articleBody")
                    if headline:
                        title = unescape(str(headline)).strip()
                    img = data.get("image") or data.get("contentUrl")
                    if isinstance(img, str) and img.startswith("http"):
                        images_found.append((img, title))
            except Exception:
                pass

        pinimg_matches = re.findall(r'https?://i\.pinimg\.com/[0-9a-z_x/]+/[0-9a-f/]+\.(?:jpg|png|webp)', html, re.IGNORECASE)
        for p_img in pinimg_matches:
            images_found.append((p_img, "Pinterest Image"))

        return images_found, r.url
    except Exception:
        return [], target_url


def extract_pinterest_pin(pin_url: str, max_images: int = DEFAULT_MAX_IMAGES, min_target: int = DEFAULT_MIN_TARGET, timeout: int = 30) -> dict:
    """
    Extract Normal Pin or Visual Search Pin images up to max_images (min target 300).
    Crawls dynamic /ideas/ topic clusters to expand results.
    Stops gracefully when target/max is reached or no more accessible images are available.
    """
    url = pin_url.strip()
    if not is_valid_pinterest_url(url):
        return {
            "success": False,
            "error": "Invalid Pinterest URL. Examples:\n- https://in.pinterest.com/pin/1136033074757270594/\n- https://in.pinterest.com/pin/1136033074757270594/visual-search/",
            "images": [],
            "count": 0
        }

    url_type, pin_id = parse_pinterest_url(url)

    # Primary: Playwright Chromium browser scraper with /ideas/ topic cluster crawling
    collected_images, telemetry, final_url = scrape_pinterest_hybrid_playwright(url, min_target=min_target, max_images=max_images)

    # Fallback: Fast HTTP session if Playwright returned 0 images
    if not collected_images:
        session = requests.Session()
        session.headers.update(HEADERS)
        fallback_imgs, final_url = scrape_pin_page_http_fallback(session, url)

        seen_hashes = set(IGNORE_HASHES)
        for raw_u, alt in fallback_imgs:
            orig = get_original_image_candidate(raw_u)
            path_parts = orig.split("/")
            img_filename = path_parts[-1] if path_parts else orig
            img_hash = img_filename.split(".")[0] if "." in img_filename else img_filename

            if img_hash not in seen_hashes:
                seen_hashes.add(img_hash)
                collected_images.append({
                    "url": orig,
                    "thumb": raw_u,
                    "width": "Original",
                    "height": "Original",
                    "alt": alt
                })

        telemetry["unique_images"] = len(collected_images)

    if not collected_images:
        return {
            "success": False,
            "error": "Unable to extract images from this Pinterest link. Please verify the URL and try again.",
            "images": [],
            "count": 0,
            "telemetry": telemetry
        }

    return {
        "success": True,
        "source": "pinterest",
        "source_url": final_url or url,
        "count": len(collected_images),
        "telemetry": telemetry,
        "images": collected_images[:max_images]
    }

