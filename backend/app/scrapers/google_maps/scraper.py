import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Callable, Optional
from urllib.parse import urlparse

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from app.services.csv_service import write_csv
from app.utils.browser import create_chrome_driver
from app.utils.normalize import normalize_text


COMMERCIAL_KEYWORDS = {
    "commercial",
    "office",
    "corporate",
    "workspace",
    "workspaces",
    "retail",
    "showroom",
    "fitout",
    "fit-out",
    "turnkey",
    "contracting",
    "contractor",
    "electrical contractor",
    "electric contractor",
    "industrial",
    "installation",
    "maintenance",
    "wiring",
    "panel",
    "repair",
    "service",
    "electrical work",
    "electrical services",
    "interior",
    "interiors",
    "architecture",
    "architectural",
    "design build",
    "design-build",
    "renovation",
    "execution",
}

NEGATIVE_KEYWORDS = {
    "school",
    "institute",
    "academy",
    "college",
    "training",
    "course",
    "classes",
    "university",
    "coaching",
}

ALLOWED_NEARBY = {
    "delhi": {"delhi", "new delhi", "noida", "greater noida", "ghaziabad", "faridabad", "gurgaon", "gurugram"},
    "mumbai": {"mumbai"},
    "pune": {"pune"},
    "bangalore": {"bangalore", "bengaluru"},
    "bengaluru": {"bangalore", "bengaluru"},
    "hyderabad": {"hyderabad"},
    "chennai": {"chennai"},
    "kolkata": {"kolkata"},
    "gurgaon": {"gurgaon", "gurugram"},
    "gurugram": {"gurgaon", "gurugram"},
    "jaipur": {"jaipur"},
    "noida": {"noida", "greater noida", "delhi", "new delhi", "ghaziabad"},
    "ghaziabad": {"ghaziabad", "delhi", "new delhi", "noida"},
    "faridabad": {"faridabad", "delhi", "new delhi", "noida", "gurgaon", "gurugram"},
}

PHONE_REGEX = re.compile(r"(?:\+?91[-\s]?)?[6-9]\d{9}")

STRICT_REVIEW_PATTERNS = [
    re.compile(r"([0-9][0-9,]{0,5})\s+reviews?\b", re.I),
    re.compile(r"\b([0-9][0-9,]{0,5})\s+Google reviews?\b", re.I),
    re.compile(r"\b([0-9][0-9,]{0,5})\s+ratings?\b", re.I),
    re.compile(r"\(([0-9][0-9,]{0,5})\)", re.I),
]
STRICT_RATING_PATTERNS = [
    re.compile(r"\b([0-5](?:\.[0-9])?)\s*stars?\b", re.I),
    re.compile(r"\b([0-5](?:\.[0-9])?)\s*/\s*5\b", re.I),
    re.compile(r"\brating[:\s]*([0-5](?:\.[0-9])?)\b", re.I),
]

CITY_TOKENS = (
    "greater noida", "new delhi", "delhi", "faridabad", "gurgaon", "gurugram", "ghaziabad", "noida",
    "mumbai", "pune", "hyderabad", "chennai", "kolkata", "bangalore", "bengaluru", "jaipur",
)

ADDRESS_JUNK_EXACT = {
    "directions",
    "online appointments",
    "online estimates",
    "open",
    "closed",
}

ADDRESS_INVALID_EXACT = {
    "directions",
    "online appointments",
    "online estimates",
    "open",
    "closed",
    "restaurants",
    "restaurant",
    "hotels",
    "hotel",
    "services",
    "service",
    "plumber",
    "electrician",
}

ADDRESS_JUNK_CONTAINS = (
    "best architect",
    "very professional",
    "cheers to",
    "smashing it",
    "one of the best",
    "as they say",
    "stars",
    "reviews",
)

ADDRESS_HINT_TOKENS = (
    "road", "rd", "street", "st", "sector", "block", "phase", "market",
    "nagar", "colony", "area", "floor", "plot", "tower", "marg", "circle", "chowk",
)

NOISY_NAME_PHRASES = (
    "service all electrical work",
    "all electrical work",
    "24 hour service",
    "24 hours service",
    "24x7 service",
    "best service",
    "call now",
    "online service",
    "home service",
)

TITLE_SELECTORS = [
    (By.CSS_SELECTOR, ".fontHeadlineSmall"),
    (By.XPATH, ".//div[contains(@class,'fontHeadlineSmall')]"),
    (By.XPATH, ".//div[@role='heading']"),
]

DETAIL_NAME_SELECTORS = [
    (By.XPATH, "//h1"),
    (By.CSS_SELECTOR, "h1.DUwDvf"),
]

WEBSITE_SELECTORS = [
    (By.XPATH, "//a[contains(@data-item-id,'authority')]"),
    (By.XPATH, "//a[contains(@aria-label,'Website')]"),
]

ADDRESS_SELECTORS = [
    (By.XPATH, "//button[@data-item-id='address']//div[contains(@class,'fontBodyMedium')]"),
    (By.XPATH, "//button[@data-item-id='address']"),
    (By.XPATH, "//button[contains(@aria-label,'Address')]"),
]


def _norm(s: str) -> str:
    return normalize_text(s or "").lower()


def debug_log(message: str):
    print(f"[GMAPS] {message}")


def save_debug_artifacts(driver, label: str):
    try:
        debug_dir = Path("/app/app/storage/outputs/debug")
        debug_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        png_path = debug_dir / f"{label}_{timestamp}.png"
        html_path = debug_dir / f"{label}_{timestamp}.html"

        driver.save_screenshot(str(png_path))
        html_path.write_text(driver.page_source or "", encoding="utf-8")

        debug_log(f"Saved screenshot: {png_path}")
        debug_log(f"Saved html dump: {html_path}")
    except Exception as e:
        debug_log(f"Failed to save debug artifacts for {label}: {e}")


def normalize_keyword_typos(keyword: str) -> str:
    k = _norm(keyword)
    replacements = {
        "contracter": "contractor",
        "contracters": "contractors",
        "labour": "labor",
        "labours": "labors",
        "eletrician": "electrician",
        "electritian": "electrician",
        "electrcian": "electrician",
        "plumbers": "plumber",
        "carpenters": "carpenter",
        "architects": "architect",
    }
    for wrong, correct in replacements.items():
        k = k.replace(wrong, correct)
    return normalize_text(k)


def keyword_variants(keyword: str) -> List[str]:
    base = normalize_keyword_typos(keyword)
    words = set(base.split())

    synonym_map = {
        "architect": ["architect", "architects", "architecture", "architectural", "architect firm"],
        "plumber": ["plumber", "plumbers", "plumbing", "sanitary", "pipe fitting", "pipefitting", "sanitary contractor"],
        "electric": ["electric", "electrical", "electrician", "electricians", "wiring", "electrical contractor", "electrical work"],
        "electrician": ["electrician", "electricians", "electrical", "wiring", "electrical contractor", "electric repair", "electrical service"],
        "contractor": ["contractor", "contractors", "contracter", "contracters"],
        "interior": ["interior", "interiors", "designer", "designers", "interior designer", "interior designers"],
        "builder": ["builder", "builders", "construction", "contractor", "contractors"],
        "furniture": ["furniture", "furnishing", "furnishers", "dealer", "dealers"],
        "designer": ["designer", "designers", "design", "designing"],
        "commercial": ["commercial", "office", "corporate", "retail", "showroom", "workspace", "fitout", "fit-out"],
        "carpenter": ["carpenter", "carpenters", "woodwork", "wood working", "joinery", "furniture carpenter"],
        "labor": ["labor", "labour", "labor contractor", "labour contractor", "manpower", "workforce", "labor supplier", "labour supplier", "manpower supplier"],
        "manpower": ["manpower", "workforce", "labor", "labour", "staffing", "labor supplier", "labour supplier"],
    }

    expanded = set(words)
    for w in list(words):
        if w in synonym_map:
            expanded.update(synonym_map[w])

    expanded.add(base)

    phrase_expansions = {
        "labor contractor": ["labor contractor", "labour contractor", "manpower supplier", "manpower contractor", "labor supplier", "labour supplier"],
        "electric contractor": ["electric contractor", "electrical contractor", "electrician", "electrical work", "electrical service"],
        "plumber": ["plumber", "plumbing contractor", "sanitary contractor"],
        "carpenter": ["carpenter", "woodwork contractor", "modular carpenter"],
    }

    for phrase, items in phrase_expansions.items():
        if phrase in base:
            expanded.update(items)

    return sorted(x for x in expanded if x)


def infer_city_from_text(text: str, fallback_city: str) -> str:
    t = _norm(text)
    for city in CITY_TOKENS:
        if city in t:
            return city
    return _norm(fallback_city)


def city_match(candidate_city_text: str, target_city: str) -> bool:
    target = _norm(target_city)
    allowed = ALLOWED_NEARBY.get(target, {target})
    candidate_city = infer_city_from_text(candidate_city_text, target)
    return candidate_city in allowed


def clean_business_name(name: str, keyword: str = "") -> str:
    text = normalize_text(name or "")
    if not text:
        return ""

    text = text.replace("|", " ")
    text = re.sub(r"\s{2,}", " ", text).strip()

    lowered = text.lower()
    for phrase in NOISY_NAME_PHRASES:
        idx = lowered.find(phrase)
        if idx > 0:
            text = text[:idx].strip(" -|,")
            lowered = text.lower()

    if keyword:
        kw = _norm(keyword)
        if text.lower() == kw:
            return ""

    return normalize_text(text)


def extract_commercial_score(text: str) -> tuple[int, str]:
    if not text:
        return 0, ""

    lower = _norm(text)
    matched = [term for term in COMMERCIAL_KEYWORDS if term in lower]
    unique_matched = sorted(set(matched))
    return len(unique_matched), ", ".join(unique_matched)


def extract_scoped_commercial_score(*parts: str) -> tuple[int, str]:
    scoped_text = " ".join(normalize_text(p or "") for p in parts if p).strip()
    if not scoped_text:
        return 0, ""
    return extract_commercial_score(scoped_text)


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""

    matches = PHONE_REGEX.findall(phone)
    for p in matches:
        digits = re.sub(r"\D", "", p)
        if digits.startswith("91") and len(digits) > 10:
            digits = digits[-10:]
        if len(digits) == 10 and digits[0] in "6789":
            return digits

    digits = re.sub(r"\D", "", phone)
    if digits.startswith("91") and len(digits) > 10:
        digits = digits[-10:]
    if len(digits) == 10 and digits[0] in "6789":
        return digits

    return ""


def normalize_website(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if "google.com" in url or "/maps/place/" in url:
        return ""
    return url.rstrip("/")


def website_domain(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().strip()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def website_quality_score(url: str) -> int:
    domain = website_domain(url)
    if not domain:
        return 0
    if "facebook.com" in domain or "instagram.com" in domain:
        return 1
    if "wa.me" in domain or "whatsapp" in domain:
        return 1
    if "odoo.com" in domain or "blogspot.com" in domain or "wordpress.com" in domain or "wixsite.com" in domain:
        return 1
    if "." not in domain or "gmail.com" in domain:
        return 0
    return 2


def is_negative_business(text: str) -> bool:
    t = _norm(text)
    return any(word in t for word in NEGATIVE_KEYWORDS)


def address_quality_score(address: str, city: str) -> int:
    if not address:
        return 0

    a = _norm(address)
    if a in ADDRESS_JUNK_EXACT:
        return 0
    if any(bad in a for bad in ADDRESS_JUNK_CONTAINS):
        return 0

    score = 0
    if "," in address:
        score += 2
    if any(tok in a for tok in ADDRESS_HINT_TOKENS):
        score += 2
    if any(ch.isdigit() for ch in address):
        score += 1
    if _norm(city) in a:
        score += 1
    if len(address.strip()) >= 12:
        score += 1
    return score


def is_valid_address(address: str, city: str) -> bool:
    if not address:
        return False

    a = _norm(address)
    if a in ADDRESS_INVALID_EXACT:
        return False
    if len(a.split()) <= 1:
        return False

    return address_quality_score(address, city) > 0


def parse_rating_and_reviews_strict(text: str) -> tuple[float, int]:
    if not text:
        return 0.0, 0

    lower = text.lower()
    rating = 0.0
    reviews = 0

    for pat in STRICT_RATING_PATTERNS:
        m = pat.search(lower)
        if m:
            try:
                val = float(m.group(1))
                if 0 < val <= 5:
                    rating = val
                    break
            except Exception:
                pass

    for pat in STRICT_REVIEW_PATTERNS:
        m = pat.search(lower)
        if m:
            try:
                val = int(m.group(1).replace(",", ""))
                if 0 <= val <= 5000:
                    reviews = val
                    break
            except Exception:
                pass

    return rating, reviews


def parse_rating_reviews_from_card(container_text: str, aria_label: str) -> tuple[float, int]:
    rating, reviews = parse_rating_and_reviews_strict(aria_label or "")

    if rating == 0.0:
        rating, _ = parse_rating_and_reviews_strict(container_text or "")

    if reviews == 0 and aria_label:
        _, reviews = parse_rating_and_reviews_strict(aria_label)

    return rating, reviews


def extract_phone_from_text_lines(text: str) -> str:
    if not text:
        return ""

    for line in (line.strip() for line in text.split("\n") if line.strip()):
        if "review" in line.lower():
            continue
        phone = normalize_phone(line)
        if phone:
            return phone
    return ""


def maps_relevance_score(
    business_name: str,
    category_text: str,
    detail_text: str,
    keyword: str,
    city: str,
    website: str,
) -> int:
    keyword = normalize_keyword_typos(keyword)

    name_l = _norm(business_name)
    category_l = _norm(category_text)
    detail_l = _norm(detail_text)
    website_l = _norm(website)
    keyword_l = _norm(keyword)
    combined = f"{name_l} {category_l} {detail_l} {website_l}"

    variants = keyword_variants(keyword_l)
    score = 0

    if keyword_l and keyword_l in name_l:
        score += 80
    if keyword_l and keyword_l in category_l:
        score += 40
    if keyword_l and keyword_l in detail_l:
        score += 18

    for word in variants:
        if word in name_l:
            score += 18
        if word in category_l:
            score += 12
        if word in detail_l:
            score += 6

    keyword_words = [w for w in keyword_l.split() if len(w) > 2]
    matched_words = sum(1 for w in keyword_words if w in combined)
    score += matched_words * 8

    if city_match(detail_text, city):
        score += 18

    score += website_quality_score(website) * 8

    if is_negative_business(combined):
        score -= 120

    return score


def maps_final_score(
    relevance: int,
    rating: float,
    reviews: int,
    has_phone: bool,
    website_quality: int,
    commercial_score: int,
    address_score: int,
) -> float:
    relevance_component = relevance * 100.0
    rating_component = rating * 25.0
    review_component = min(reviews, 500) * 0.5
    phone_component = 220.0 if has_phone else 0.0
    website_component = website_quality * 80.0
    commercial_component = commercial_score * 90.0
    address_component = address_score * 35.0

    return (
        relevance_component
        + rating_component
        + review_component
        + phone_component
        + website_component
        + commercial_component
        + address_component
    )


def _safe_text(parent, selectors: List[tuple]) -> str:
    for by, selector in selectors:
        try:
            el = parent.find_element(by, selector)
            text = el.text.strip()
            if text:
                return text
        except Exception:
            continue
    return ""


def _safe_attr(parent, selectors: List[tuple], attr: str) -> str:
    for by, selector in selectors:
        try:
            el = parent.find_element(by, selector)
            value = el.get_attribute(attr)
            if value:
                return value
        except Exception:
            continue
    return ""


def open_maps_search(driver, keyword: str, city: str):
    query = f"{keyword} in {city}"
    url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
    debug_log(f"Opening Maps search: {url}")
    driver.get(url)

    WebDriverWait(driver, 20).until(
        EC.any_of(
            EC.presence_of_element_located((By.XPATH, "//div[@role='feed']")),
            EC.presence_of_element_located((By.XPATH, "//a[contains(@href,'/maps/place/')]")),
        )
    )
    time.sleep(3)

    debug_log(f"Current URL after open: {driver.current_url}")
    debug_log(f"Page title: {driver.title}")

    try:
        body_text = normalize_text(driver.find_element(By.TAG_NAME, "body").text)
        debug_log(f"Body preview: {body_text[:1000]}")
        low = body_text.lower()

        suspicious_terms = [
            "sorry, something went wrong",
            "unusual traffic",
            "detected unusual traffic",
            "sign in",
            "before you continue",
            "captcha",
            "access denied",
        ]
        if any(term in low for term in suspicious_terms):
            debug_log("Suspicious / blocked page detected on maps search open")
            save_debug_artifacts(driver, "gmaps_search_suspicious")
    except Exception as e:
        debug_log(f"Failed to capture body preview after search open: {e}")


def scroll_results_feed(driver, wanted_candidates: int, max_time: int):
    start = time.time()
    no_change = 0
    prev_unique_count = 0
    iteration = 0

    debug_log(f"Starting feed scroll | wanted_candidates={wanted_candidates} max_time={max_time}")

    while time.time() - start < max_time:
        iteration += 1
        anchors = driver.find_elements(By.XPATH, "//a[contains(@href,'/maps/place/')]")
        unique_hrefs = set()

        for a in anchors:
            try:
                href = (a.get_attribute("href") or "").split("&authuser=")[0]
                if href:
                    unique_hrefs.add(href)
            except Exception:
                continue

        unique_count = len(unique_hrefs)
        debug_log(
            f"Scroll iteration={iteration} elapsed={round(time.time() - start, 1)}s "
            f"anchors={len(anchors)} unique_hrefs={unique_count}"
        )

        if iteration == 1 and unique_count == 0:
            debug_log(f"No place anchors found on first iteration. URL={driver.current_url} title={driver.title}")
            save_debug_artifacts(driver, "gmaps_zero_anchors")
            try:
                body_text = normalize_text(driver.find_element(By.TAG_NAME, "body").text)
                debug_log(f"Maps body preview: {body_text[:1200]}")
            except Exception as e:
                debug_log(f"Failed reading maps body preview: {e}")

        if unique_count >= wanted_candidates:
            debug_log("Wanted candidates reached during scroll")
            break

        try:
            feed = driver.find_element(By.XPATH, "//div[@role='feed']")
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", feed)
            debug_log("Scrolled results feed")
        except Exception:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            debug_log("Scrolled window instead of feed")

        time.sleep(2.2)

        if unique_count == prev_unique_count:
            no_change += 1
        else:
            no_change = 0

        prev_unique_count = unique_count

        if no_change >= 4:
            debug_log("Stopping scroll due to no new results")
            break


def collect_listing_candidates(
    driver,
    keyword: str,
    city: str,
    max_results: int,
    max_time: int,
) -> List[Dict[str, Any]]:
    keyword = normalize_keyword_typos(keyword)
    city_norm = normalize_text(city)
    category_norm = normalize_text(keyword)

    wanted_candidates = min(max(max_results * 4, 12), 40)
    debug_log(
        f"Collecting listing candidates | city={city} keyword={keyword} "
        f"max_results={max_results} max_time={max_time} wanted_candidates={wanted_candidates}"
    )

    scroll_results_feed(driver, wanted_candidates=wanted_candidates, max_time=max_time)

    candidates: Dict[str, Dict[str, Any]] = {}

    anchors = driver.find_elements(By.XPATH, "//a[contains(@href,'/maps/place/')]")
    debug_log(f"Total place anchors after scroll: {len(anchors)}")

    for a in anchors:
        try:
            href = (a.get_attribute("href") or "").split("&authuser=")[0]
            if not href or href in candidates:
                continue

            try:
                container = a.find_element(By.XPATH, "./ancestor::*[@role='article'][1]")
            except Exception:
                try:
                    container = a.find_element(By.XPATH, "./ancestor::div[contains(@class,'Nv2PK')][1]")
                except Exception:
                    container = a

            raw_title = _safe_text(container, TITLE_SELECTORS)
            if not raw_title:
                raw_title = normalize_text(a.text)

            title = clean_business_name(raw_title, keyword=keyword)
            if not title:
                continue

            container_text = normalize_text(container.text or "")

            role_img = None
            try:
                role_img = container.find_element(By.XPATH, ".//*[@role='img']")
            except Exception:
                pass

            aria_label = role_img.get_attribute("aria-label") if role_img else ""
            rating, reviews = parse_rating_reviews_from_card(container_text, aria_label)

            phone = extract_phone_from_text_lines(container_text)

            website = ""
            try:
                for lnk in container.find_elements(By.TAG_NAME, "a"):
                    lhref = lnk.get_attribute("href") or ""
                    if lhref and "google.com" not in lhref and "/maps/place/" not in lhref:
                        website = normalize_website(lhref)
                        if website:
                            break
            except Exception:
                pass

            possible_address = ""
            for line in (x.strip() for x in container_text.split("\n") if x.strip()):
                if is_valid_address(line, city):
                    possible_address = line

            relevance = maps_relevance_score(
                business_name=title,
                category_text=container_text,
                detail_text=container_text,
                keyword=keyword,
                city=city,
                website=website,
            )

            if relevance < 35:
                continue

            if is_negative_business(f"{title} {container_text}"):
                continue

            commercial_score, commercial_match = extract_scoped_commercial_score(title, container_text, website)
            addr_score = address_quality_score(possible_address, city)
            wq = website_quality_score(website)

            candidate = {
                "profile_url": href,
                "business_name": title,
                "company_name": "",
                "phone": phone,
                "address": normalize_text(possible_address),
                "city": city_norm,
                "category": category_norm,
                "website": website,
                "rating": rating,
                "reviews": reviews,
                "source_url": href,
                "source": "google_maps",
                "raw_card_text": container_text,
                "relevance_score": relevance,
                "commercial_score": commercial_score,
                "commercial_match": commercial_match,
                "address_quality_score": addr_score,
                "website_quality_score": wq,
            }

            candidate["final_score"] = maps_final_score(
                relevance=relevance,
                rating=rating,
                reviews=reviews,
                has_phone=bool(phone),
                website_quality=wq,
                commercial_score=commercial_score,
                address_score=addr_score,
            )

            candidates[href] = candidate
        except Exception:
            continue

    ranked = sorted(
        candidates.values(),
        key=lambda x: (x["final_score"], x["rating"], x["reviews"]),
        reverse=True,
    )

    debug_log(f"Candidate collection complete. Ranked candidates={len(ranked)}")
    if ranked:
        debug_log(
            "Top candidates preview: "
            + str(
                [
                    {
                        "name": x.get("business_name"),
                        "score": x.get("final_score"),
                        "rating": x.get("rating"),
                        "reviews": x.get("reviews"),
                    }
                    for x in ranked[:5]
                ]
            )
        )

    return ranked[: max(max_results * 3, 15)]


def extract_detail_phone(driver, body_text: str) -> str:
    try:
        for el in driver.find_elements(By.XPATH, "//a[starts-with(@href,'tel:')]"):
            href = el.get_attribute("href") or ""
            phone = normalize_phone(href)
            if phone:
                return phone
    except Exception:
        pass

    try:
        for el in driver.find_elements(By.XPATH, "//button[contains(@data-item-id,'phone')]"):
            txt = (
                el.text
                or el.get_attribute("aria-label")
                or el.get_attribute("data-item-id")
                or ""
            ).strip()
            phone = normalize_phone(txt)
            if phone:
                return phone
    except Exception:
        pass

    try:
        for el in driver.find_elements(By.XPATH, "//*[@aria-label]"):
            aria = (el.get_attribute("aria-label") or "").strip()
            aria_l = aria.lower()
            if "phone" in aria_l or "call" in aria_l:
                phone = normalize_phone(aria)
                if phone:
                    return phone
    except Exception:
        pass

    for line in (x.strip() for x in body_text.split("\n") if x.strip()):
        if "review" in line.lower():
            continue
        phone = normalize_phone(line)
        if phone:
            return phone

    return ""


def extract_detail_address(driver, body_text: str, city: str) -> str:
    for by, sel in ADDRESS_SELECTORS:
        try:
            for el in driver.find_elements(by, sel):
                txt = (el.text or el.get_attribute("aria-label") or "").strip()
                txt = normalize_text(txt)
                if is_valid_address(txt, city):
                    return txt
        except Exception:
            continue

    for line in (x.strip() for x in body_text.split("\n") if x.strip()):
        if is_valid_address(line, city):
            return normalize_text(line)

    return ""


def is_row_city_valid(row: Dict[str, Any], city: str) -> bool:
    address_text = row.get("address", "") or ""
    source_url = row.get("source_url", "") or ""
    raw_text = row.get("raw_card_text", "") or ""

    if address_text and city_match(address_text, city):
        return True

    combined_fallback = f"{source_url} {raw_text}"
    return city_match(combined_fallback, city)


def click_and_extract_details(driver, candidate: Dict[str, Any], city: str) -> Dict[str, Any]:
    row = dict(candidate)
    url = candidate.get("profile_url", "")
    debug_log(f"Opening detail page: {url}")

    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.any_of(
                EC.presence_of_element_located((By.XPATH, "//h1")),
                EC.presence_of_element_located((By.TAG_NAME, "body")),
            )
        )
        time.sleep(4)

        debug_log(f"Detail page URL: {driver.current_url}")
        debug_log(f"Detail page title: {driver.title}")

        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(@data-item-id,'phone')]"))
            )
        except Exception:
            pass

        body_el = driver.find_element(By.TAG_NAME, "body")
        body_text = body_el.text or ""

        if not body_text.strip():
            debug_log(f"Empty body text on detail page: {url}")
            save_debug_artifacts(driver, "gmaps_detail_empty_body")

        try:
            body_el.click()
            time.sleep(1)
        except Exception:
            pass

        try:
            driver.execute_script("window.scrollBy(0, 300);")
            time.sleep(1)
        except Exception:
            pass

        body_text = body_el.text or ""
        debug_log(f"Detail body preview: {normalize_text(body_text)[:1200]}")

        business_name = _safe_text(driver, DETAIL_NAME_SELECTORS)
        if business_name:
            cleaned = clean_business_name(business_name, keyword=row.get("category", ""))
            if cleaned:
                row["business_name"] = cleaned

        website = _safe_attr(driver, WEBSITE_SELECTORS, "href")
        website = normalize_website(website) or row.get("website", "")
        row["website"] = website

        phone = extract_detail_phone(driver, body_text)
        if phone:
            row["phone"] = phone

        address = extract_detail_address(driver, body_text, city)
        if address:
            row["address"] = address

        row["source_url"] = driver.current_url or row.get("source_url", url)

        detail_rating, detail_reviews = parse_rating_reviews_from_card(body_text, body_text)
        if not row.get("rating") and detail_rating:
            row["rating"] = detail_rating
        if not row.get("reviews") and detail_reviews:
            row["reviews"] = detail_reviews

        business_name_val = row.get("business_name", "")
        address_val = row.get("address", "")
        raw_card_text = row.get("raw_card_text", "")
        website_val = row.get("website", "")

        combined_text = " ".join([business_name_val, address_val, raw_card_text, website_val])

        row["relevance_score"] = maps_relevance_score(
            business_name=business_name_val,
            category_text=raw_card_text,
            detail_text=combined_text,
            keyword=row.get("category", ""),
            city=city,
            website=website_val,
        )

        commercial_score, commercial_match = extract_scoped_commercial_score(
            business_name_val,
            raw_card_text,
            website_val,
            address_val,
        )
        row["commercial_score"] = commercial_score
        row["commercial_match"] = commercial_match
        row["address_quality_score"] = address_quality_score(address_val, city)
        row["website_quality_score"] = website_quality_score(website_val)
        row["has_phone"] = "yes" if row.get("phone") else "no"
        row["has_website"] = "yes" if website_val else "no"

        row["final_score"] = maps_final_score(
            relevance=int(row.get("relevance_score", 0) or 0),
            rating=float(row.get("rating", 0) or 0),
            reviews=int(row.get("reviews", 0) or 0),
            has_phone=bool(row.get("phone")),
            website_quality=int(row.get("website_quality_score", 0) or 0),
            commercial_score=int(row.get("commercial_score", 0) or 0),
            address_score=int(row.get("address_quality_score", 0) or 0),
        )

        debug_log(
            f"Accepted detail row | name={row.get('business_name')} phone={row.get('phone')} "
            f"address={row.get('address')} rating={row.get('rating')} reviews={row.get('reviews')} "
            f"final_score={row.get('final_score')}"
        )
    except Exception as e:
        debug_log(f"Detail extraction error for {url}: {e}")
        save_debug_artifacts(driver, "gmaps_detail_error")

        row["has_phone"] = "yes" if row.get("phone") else "no"
        row["has_website"] = "yes" if row.get("website") else "no"
        row["address_quality_score"] = address_quality_score(row.get("address", ""), city)
        row["website_quality_score"] = website_quality_score(row.get("website", ""))
        row["final_score"] = maps_final_score(
            relevance=int(row.get("relevance_score", 0) or 0),
            rating=float(row.get("rating", 0) or 0),
            reviews=int(row.get("reviews", 0) or 0),
            has_phone=bool(row.get("phone")),
            website_quality=int(row.get("website_quality_score", 0) or 0),
            commercial_score=int(row.get("commercial_score", 0) or 0),
            address_score=int(row.get("address_quality_score", 0) or 0),
        )

    return row


def dedupe_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_by_url: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        url = (row.get("source_url") or "").strip()
        if not url:
            continue
        row_score = float(row.get("final_score", 0) or 0)
        existing = best_by_url.get(url)
        if not existing or row_score > float(existing.get("final_score", 0) or 0):
            best_by_url[url] = row

    stage1 = list(best_by_url.values())

    best_by_name_city: Dict[str, Dict[str, Any]] = {}
    for row in stage1:
        key = f"{_norm(row.get('business_name', ''))}|{_norm(row.get('city', ''))}"
        row_score = float(row.get("final_score", 0) or 0)
        existing = best_by_name_city.get(key)
        if not existing or row_score > float(existing.get("final_score", 0) or 0):
            best_by_name_city[key] = row

    stage2 = list(best_by_name_city.values())

    best_by_domain_or_name: Dict[str, Dict[str, Any]] = {}
    for row in stage2:
        domain = website_domain(row.get("website", ""))
        key = domain if domain else f"{_norm(row.get('business_name', ''))}|{_norm(row.get('city', ''))}"
        row_score = float(row.get("final_score", 0) or 0)
        existing = best_by_domain_or_name.get(key)
        if not existing or row_score > float(existing.get("final_score", 0) or 0):
            best_by_domain_or_name[key] = row

    return list(best_by_domain_or_name.values())


def run_google_maps_scraper(
    keyword: str,
    city: str,
    max_results: int,
    max_time: int,
    headless: bool,
    output_file: Path,
    progress_callback: Optional[Callable[[int, int, Optional[str]], None]] = None,
) -> int:
    keyword = normalize_keyword_typos(keyword)
    city_norm = normalize_text(city)
    category_norm = normalize_text(keyword)

    debug_log(
        f"Run started | keyword={keyword} city={city} max_results={max_results} "
        f"max_time={max_time} headless={headless}"
    )

    driver = create_chrome_driver(headless=headless)

    try:
        open_maps_search(driver, keyword, city)

        ranked_candidates = collect_listing_candidates(
            driver=driver,
            keyword=keyword,
            city=city,
            max_results=max_results,
            max_time=max_time,
        )

        debug_log(f"Ranked candidates collected: {len(ranked_candidates)}")
        if not ranked_candidates:
            debug_log("No ranked candidates found. Saving diagnostics.")
            save_debug_artifacts(driver, "gmaps_no_ranked_candidates")

        detailed_rows: List[Dict[str, Any]] = []
        shortlisted = ranked_candidates[: max(max_results * 2, 12)]
        total_to_process = len(shortlisted)

        debug_log(f"Shortlisted candidates for detail extraction: {total_to_process}")

        if progress_callback:
            progress_callback(0, total_to_process, "Google Maps scraping started")

        for idx, candidate in enumerate(shortlisted, start=1):
            row = click_and_extract_details(driver, candidate, city)

            combined_for_validation = " ".join(
                [
                    row.get("business_name", ""),
                    row.get("address", ""),
                    row.get("raw_card_text", ""),
                    row.get("website", ""),
                ]
            )

            if not is_negative_business(combined_for_validation):
                if is_row_city_valid(row, city):
                    if int(row.get("relevance_score", 0) or 0) >= 35:
                        detailed_rows.append(row)
                    else:
                        debug_log(f"Rejected row due to low relevance: {row.get('business_name')}")
                else:
                    debug_log(f"Rejected row due to city mismatch: {row.get('business_name')}")
            else:
                debug_log(f"Rejected negative business row: {row.get('business_name')}")

            if progress_callback:
                progress_callback(
                    idx,
                    total_to_process,
                    f"Google Maps processed {idx}/{total_to_process}",
                )

        debug_log(f"Detailed rows before dedupe: {len(detailed_rows)}")

        deduped = dedupe_rows(detailed_rows)
        debug_log(f"Rows after dedupe: {len(deduped)}")

        ranked_final = sorted(
            deduped,
            key=lambda x: (
                float(x.get("final_score", 0) or 0),
                float(x.get("rating", 0) or 0),
                int(x.get("reviews", 0) or 0),
            ),
            reverse=True,
        )

        final_rows = ranked_final[:max_results]
        debug_log(f"Final selected rows: {len(final_rows)}")

        if not final_rows:
            debug_log("No final rows after ranking. Saving diagnostics.")
            save_debug_artifacts(driver, "gmaps_no_final_rows")

        export_rows = []
        for row in final_rows:
            rating_val = row.get("rating")
            reviews_val = row.get("reviews")
            export_rows.append(
                {
                    "business_name": normalize_text(row.get("business_name", "")),
                    "company_name": normalize_text(row.get("company_name", "")),
                    "phone": normalize_text(row.get("phone", "")),
                    "address": normalize_text(row.get("address", "")),
                    "city": normalize_text(row.get("city", city_norm)),
                    "category": normalize_text(row.get("category", category_norm)),
                    "website": normalize_text(row.get("website", "")),
                    "rating": f"{float(rating_val or 0):.1f}" if rating_val else "",
                    "reviews": str(int(reviews_val or 0)) if reviews_val else "",
                    "has_phone": row.get("has_phone", "no"),
                    "has_website": row.get("has_website", "no"),
                    "website_quality_score": str(int(row.get("website_quality_score", 0) or 0)),
                    "commercial_score": str(int(row.get("commercial_score", 0) or 0)),
                    "commercial_match": row.get("commercial_match", ""),
                    "address_quality_score": str(int(row.get("address_quality_score", 0) or 0)),
                    "relevance_score": str(int(row.get("relevance_score", 0) or 0)),
                    "final_score": str(round(float(row.get("final_score", 0) or 0), 2)),
                    "source_url": row.get("source_url", ""),
                    "source": "google_maps",
                }
            )

        headers = [
            "business_name",
            "company_name",
            "phone",
            "address",
            "city",
            "category",
            "website",
            "rating",
            "reviews",
            "has_phone",
            "has_website",
            "website_quality_score",
            "commercial_score",
            "commercial_match",
            "address_quality_score",
            "relevance_score",
            "final_score",
            "source_url",
            "source",
        ]

        total_rows = write_csv(output_file, headers, export_rows)
        debug_log(f"CSV written: {output_file} | total_rows={total_rows}")

        if progress_callback:
            progress_callback(total_to_process, total_to_process, "Google Maps scraping completed")

        return total_rows
    finally:
        try:
            driver.quit()
        except Exception:
            pass