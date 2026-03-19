import json
import math
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from app.services.csv_service import write_csv
from app.utils.browser import create_chrome_driver
from app.utils.normalize import normalize_text


CURRENT_YEAR = datetime.now().year

STATES_TO_CITIES = {
    "punjab": ["Ludhiana", "Amritsar", "Jalandhar", "Patiala", "Bathinda", "Mohali", "Hoshiarpur"],
    "maharashtra": ["Mumbai", "Pune", "Nagpur", "Thane", "Nashik", "Aurangabad"],
    "gujarat": ["Ahmedabad", "Surat", "Vadodara", "Rajkot"],
    "delhi": ["Delhi"],
    "haryana": ["Gurgaon", "Faridabad", "Panchkula"],
    "uttar pradesh": ["Lucknow", "Kanpur", "Noida", "Agra"],
}

ALLOWED_NEARBY = {
    "delhi": {"delhi", "new delhi", "noida", "greater noida", "ghaziabad", "faridabad", "gurgaon", "gurugram"},
    "mumbai": {"mumbai"},
    "pune": {"pune"},
    "bangalore": {"bangalore", "bengaluru"},
    "hyderabad": {"hyderabad"},
    "chennai": {"chennai"},
    "kolkata": {"kolkata"},
    "gurgaon": {"gurgaon", "gurugram"},
}

COMMERCIAL_KEYWORDS = {
    "commercial",
    "office",
    "corporate",
    "workspace",
    "workspaces",
    "retail",
    "showroom",
    "mall",
    "hospitality",
    "hotel",
    "restaurant",
    "cafeteria",
    "institutional",
    "fitout",
    "fit-out",
    "turnkey",
    "contracting",
    "commercial interior",
    "commercial interiors",
    "office interior",
    "office interiors",
    "store design",
    "shop design",
}

GST_PATTERNS = [
    r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b",
    r"\bGSTIN[:\s\-]*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b",
    r"\bGST(?:\s*No\.?|\s*Number|\s*Registration)?[:\s\-]*([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b",
]


def _norm(s: str) -> str:
    return normalize_text(s or "").lower()


def normalize_keyword_typos(keyword: str) -> str:
    k = _norm(keyword)

    replacements = {
        "contracter": "contractor",
        "contracters": "contractors",
        "labour": "labor",
        "labours": "labors",
        "eletrician": "electrician",
        "electritian": "electrician",
        "plumbers": "plumber",
        "carpenters": "carpenter",
        "architects": "architect",
    }

    for wrong, correct in replacements.items():
        k = k.replace(wrong, correct)

    return normalize_text(k)


def extract_from_jsonld(html: str):
    matches = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html or "",
        re.S | re.I,
    )
    for block in matches:
        try:
            j = json.loads(block)
            if isinstance(j, list):
                for item in j:
                    if isinstance(item, dict) and (item.get("name") or item.get("@type")):
                        return item
                if j:
                    return j[0]
            if isinstance(j, dict):
                return j
        except Exception:
            continue
    return None


def extract_phone_from_html(html: str) -> str:
    if not html:
        return ""

    raw_matches = re.findall(r"(?:\+91[-\s]?)?[6-9]\d{9}", html)
    cleaned = []

    for p in raw_matches:
        digits = re.sub(r"\D", "", p)
        if digits.startswith("91") and len(digits) > 10:
            digits = digits[-10:]
        if len(digits) == 10 and digits[0] in "6789":
            cleaned.append(digits)

    return cleaned[0] if cleaned else ""


def extract_possible_rating_values(text: str) -> List[float]:
    if not text:
        return []
    values = []
    for m in re.finditer(r"(?<!\d)([0-9](?:\.[0-9])?)(?!\d)", text):
        try:
            val = float(m.group(1))
            if 0.0 < val <= 5.0:
                values.append(val)
        except Exception:
            continue
    return values


def extract_possible_review_values(text: str) -> List[int]:
    if not text:
        return []
    values = []
    for m in re.finditer(r"([0-9][0-9,]{0,6})", text):
        try:
            val = int(m.group(1).replace(",", ""))
            if 0 <= val <= 100000:
                values.append(val)
        except Exception:
            continue
    return values


def parse_rating_and_reviews(text: str) -> tuple[float, int]:
    if not text:
        return 0.0, 0

    lower = text.lower()
    rating = 0.0
    reviews = 0

    rating_patterns = [
        r"([0-5](?:\.[0-9])?)\s*(?:/5|out of 5|star|stars)",
        r"rating[:\s]*([0-5](?:\.[0-9])?)",
    ]
    for pat in rating_patterns:
        m = re.search(pat, lower, re.I)
        if m:
            try:
                val = float(m.group(1))
                if 0 < val <= 5:
                    rating = val
                    break
            except Exception:
                pass

    review_patterns = [
        r"([0-9][0-9,]*)\s*(?:review|reviews|vote|votes|rating count)",
        r"reviews?[:\s]*([0-9][0-9,]*)",
    ]
    for pat in review_patterns:
        m = re.search(pat, lower, re.I)
        if m:
            try:
                reviews = int(m.group(1).replace(",", ""))
                break
            except Exception:
                pass

    if rating == 0.0:
        candidates = extract_possible_rating_values(text)
        if candidates:
            rating = max(candidates)

    if reviews == 0:
        candidates = extract_possible_review_values(text)
        plausible = [x for x in candidates if x > 5]
        if plausible:
            reviews = max(plausible)

    if rating > 5:
        rating = 0.0

    return rating, reviews


def keyword_variants(keyword: str) -> List[str]:
    base = normalize_keyword_typos(keyword)
    words = set(base.split())

    synonym_map = {
        "architect": ["architect", "architects", "architecture", "architectural", "architect firm"],
        "plumber": ["plumber", "plumbers", "plumbing", "sanitary", "pipe fitting", "pipefitting"],
        "electric": ["electric", "electrical", "electrician", "electricians", "wiring", "electrical contractor"],
        "electrician": ["electrician", "electricians", "electrical", "wiring", "electrical contractor"],
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
        "electric contractor": ["electric contractor", "electrical contractor", "electrician", "electrical work"],
        "plumber": ["plumber", "plumbing contractor", "sanitary contractor"],
        "carpenter": ["carpenter", "woodwork contractor", "modular carpenter"],
    }

    for phrase, items in phrase_expansions.items():
        if phrase in base:
            expanded.update(items)

    return sorted(x for x in expanded if x)


def extract_gst_number(text: str) -> str:
    if not text:
        return ""
    upper = text.upper()
    for pattern in GST_PATTERNS:
        m = re.search(pattern, upper, re.I)
        if m:
            if m.groups():
                return m.group(1).strip()
            return m.group(0).strip()
    return ""


def extract_established_year(text: str) -> Optional[int]:
    if not text:
        return None

    patterns = [
        r"(?:since|established in|estd\.?|founded in|started in)\s*(19[6-9][0-9]|20[0-2][0-9])",
        r"\b(19[6-9][0-9]|20[0-2][0-9])\b",
    ]

    for pat in patterns:
        matches = re.findall(pat, text, re.I)
        for year_str in matches:
            try:
                year = int(year_str)
                if 1960 <= year <= CURRENT_YEAR:
                    return year
            except Exception:
                continue

    return None


def extract_experience_years(text: str) -> int:
    if not text:
        return 0

    patterns = [
        r"([0-9]{1,2})\+?\s*(?:years|yrs)\s*(?:of\s*)?(?:experience|exp)",
        r"experience[:\s]*([0-9]{1,2})\+?\s*(?:years|yrs)?",
        r"([0-9]{1,2})\+?\s*(?:years|yrs)\s*in\s*business",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            try:
                years = int(m.group(1))
                if 0 <= years <= 80:
                    return years
            except Exception:
                pass

    est_year = extract_established_year(text)
    if est_year:
        years = CURRENT_YEAR - est_year
        if 0 <= years <= 80:
            return years

    return 0


def extract_commercial_score(text: str) -> tuple[int, str]:
    if not text:
        return 0, ""

    lower = _norm(text)
    matched = []

    for term in COMMERCIAL_KEYWORDS:
        if term in lower:
            matched.append(term)

    unique_matched = sorted(set(matched))
    return len(unique_matched), ", ".join(unique_matched)


def has_5_plus_years(experience_years: int) -> bool:
    return experience_years >= 5


def relevance_score(name: str, company_name: str, category_text: str, city_text: str, keyword: str, city: str) -> int:
    keyword = normalize_keyword_typos(keyword)

    name_l = _norm(name)
    company_l = _norm(company_name)
    category_l = _norm(category_text)
    city_l = _norm(city_text)
    keyword_l = _norm(keyword)
    city_target = _norm(city)

    variants = keyword_variants(keyword_l)
    combined = f"{name_l} {company_l} {category_l}"

    score = 0

    if keyword_l and keyword_l in name_l:
        score += 70
    if keyword_l and keyword_l in company_l:
        score += 35
    if keyword_l and keyword_l in category_l:
        score += 45

    for word in variants:
        if word in name_l:
            score += 18
        if word in company_l:
            score += 10
        if word in category_l:
            score += 12

    keyword_words = [w for w in keyword_l.split() if len(w) > 2]
    matched_words = sum(1 for w in keyword_words if w in combined)
    score += matched_words * 12

    if city_target and city_target in city_l:
        score += 20

    return score


def final_score(
    relevance: int,
    rating: float,
    reviews: int,
    gst_found: bool,
    experience_years: int,
    commercial_score: int,
) -> float:
    gst_component = 50000.0 if gst_found else 0.0
    exp_component = 10000.0 if experience_years >= 5 else experience_years * 100.0
    commercial_component = commercial_score * 1500.0
    relevance_component = relevance * 100.0
    rating_component = rating * 20.0
    review_component = min(reviews, 500) / 20.0

    return gst_component + exp_component + commercial_component + relevance_component + rating_component + review_component


def safe_find_text(parent, selectors: List[tuple]) -> str:
    for by, sel in selectors:
        try:
            el = parent.find_element(by, sel)
            text = el.text.strip()
            if text:
                return text
        except Exception:
            continue
    return ""


def set_location_via_ui(driver, city_name: str) -> bool:
    driver.get("https://www.justdial.com")
    time.sleep(0.5)

    xpath_candidates = [
        "//input[@id='srch_loc']",
        "//input[contains(@placeholder,'Search') and @type='text']",
        "//input[contains(@aria-label,'location') or contains(@aria-label,'Location')][@type='text']",
        "//input[contains(@class,'loc') and @type='text']",
        "//div[contains(@class,'fld loc')]//input",
    ]

    for xp in xpath_candidates:
        try:
            el = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xp)))
            try:
                el.click()
            except Exception:
                driver.execute_script("arguments[0].click();", el)

            try:
                el.send_keys(Keys.CONTROL, "a")
                el.send_keys(Keys.DELETE)
            except Exception:
                pass

            el.clear()
            el.send_keys(city_name)
            time.sleep(0.35)

            suggestions_xp = (
                "//ul[contains(@class,'searchlist')]/li | "
                "//ul[contains(@class,'srch_lst')]/li | "
                "//div[contains(@class,'autocomplete')]/div"
            )
            try:
                suggestions = WebDriverWait(driver, 1.5).until(
                    EC.visibility_of_any_elements_located((By.XPATH, suggestions_xp))
                )
                if suggestions:
                    suggestions[0].click()
                    time.sleep(0.45)
                    return True
            except TimeoutException:
                el.send_keys(Keys.ENTER)
                time.sleep(0.3)
                return True
        except Exception:
            continue

    return False


def set_location_cookie(driver, city_name: str) -> bool:
    try:
        driver.get("https://www.justdial.com")
        time.sleep(0.25)
        driver.add_cookie({"name": "main_city", "value": city_name, "domain": ".justdial.com", "path": "/"})
        return True
    except Exception:
        return False


def open_search_page(driver, city: str, keyword: str):
    keyword = normalize_keyword_typos(keyword)
    search_url = f"https://www.justdial.com/{city.replace(' ', '-')}/{keyword.replace(' ', '-')}"
    driver.get(search_url)
    WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
    time.sleep(0.6)


def infer_city_from_text(text: str, fallback_city: str) -> str:
    t = _norm(text)
    for city in [
        "greater noida", "delhi", "new delhi", "faridabad", "gurgaon", "gurugram", "ghaziabad", "noida",
        "mumbai", "pune", "hyderabad", "chennai", "kolkata", "bangalore", "bengaluru"
    ]:
        if city in t:
            return city
    return _norm(fallback_city)


def city_match(candidate_city_text: str, target_city: str) -> bool:
    target = _norm(target_city)
    allowed = ALLOWED_NEARBY.get(target, {target})
    candidate_city = infer_city_from_text(candidate_city_text, target)
    return candidate_city in allowed


def collect_listing_candidates(driver, keyword: str, city: str, target: int, max_time: int) -> List[Dict[str, Any]]:
    keyword = normalize_keyword_typos(keyword)

    start = time.time()
    no_new = 0
    last_count = 0

    wanted_candidates = min(max(target * 4, 12), 35)
    candidates: Dict[str, Dict[str, Any]] = {}

    while (time.time() - start) < max_time and len(candidates) < wanted_candidates and no_new < 4:
        anchors = driver.find_elements(By.XPATH, "//a[contains(@href,'_BZDET')]")

        for a in anchors:
            try:
                href = (a.get_attribute("href") or "").split("?")[0]
                if not href or href in candidates:
                    continue

                try:
                    card = a.find_element(By.XPATH, "./ancestor::li[1]")
                except Exception:
                    try:
                        card = a.find_element(By.XPATH, "./ancestor::div[contains(@class,'resultbox') or contains(@class,'cntanr')][1]")
                    except Exception:
                        card = a

                card_text = normalize_text(card.text)
                title = normalize_text(a.text)

                if not title:
                    title = safe_find_text(
                        card,
                        [
                            (By.CSS_SELECTOR, "h2"),
                            (By.CSS_SELECTOR, "h3"),
                            (By.XPATH, ".//*[self::h2 or self::h3][1]"),
                        ],
                    )

                rating, reviews = parse_rating_and_reviews(card_text)

                locality = ""
                locality_match = re.search(r"in\s+([A-Za-z0-9 ,\-]+)", title, re.I)
                if locality_match:
                    locality = locality_match.group(1).strip()

                city_text = locality or card_text or city
                if not city_match(city_text, city):
                    continue

                rel_score = relevance_score(title, "", card_text, city_text, keyword, city)
                if rel_score < 40:
                    continue

                candidate = {
                    "profile_url": href,
                    "business_name": title,
                    "company_name": "",
                    "category_text": card_text,
                    "city_text": city_text,
                    "rating": rating,
                    "reviews": reviews,
                    "source": "justdial",
                    "relevance_score": rel_score,
                }

                commercial_score, commercial_match = extract_commercial_score(card_text + " " + title)
                candidate["commercial_score"] = commercial_score
                candidate["commercial_match"] = commercial_match
                candidate["gst_found"] = False
                candidate["gst_number"] = ""
                candidate["experience_years"] = 0
                candidate["established_year"] = ""

                candidate["final_score"] = final_score(
                    candidate["relevance_score"],
                    candidate["rating"],
                    candidate["reviews"],
                    candidate["gst_found"],
                    candidate["experience_years"],
                    candidate["commercial_score"],
                )

                candidates[href] = candidate
            except Exception:
                continue

        current_count = len(candidates)
        if current_count == last_count:
            no_new += 1
        else:
            no_new = 0
        last_count = current_count

        if len(candidates) >= wanted_candidates:
            break

        try:
            next_el = None
            next_candidates = driver.find_elements(
                By.XPATH,
                "//a[contains(@rel,'next') or contains(translate(text(),'NEXT','next'),'next') or contains(@class,'next')]",
            )
            for el in next_candidates:
                try:
                    if el.is_displayed():
                        next_el = el
                        break
                except Exception:
                    continue

            if next_el:
                try:
                    next_el.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", next_el)
                time.sleep(0.8)
                continue
        except Exception:
            pass

        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass
        time.sleep(0.5)

    ranked = sorted(
        candidates.values(),
        key=lambda x: (x["final_score"], x["rating"], x["reviews"]),
        reverse=True,
    )
    return ranked


def extract_profile_rows(
    driver,
    ranked_candidates: List[Dict[str, Any]],
    keyword: str,
    city: str,
    target: int,
    headless: bool,
    progress_callback: Optional[Callable[[int, int, Optional[str]], None]] = None,
) -> List[dict]:
    keyword = normalize_keyword_typos(keyword)

    gst_rows = []
    fallback_rows = []

    seen_gst_phones = set()
    seen_gst_names = set()
    seen_fb_phones = set()
    seen_fb_names = set()

    generic_site_names = {"justdial", "just dial", "jd"}
    generic_company_words = {
        "architects", "plumbers", "contractors", "interior designers", "designers",
        "consultants", "builders", "factory", "services", "shop", "store", "company", "agency"
    }

    def is_generic_name(n: str) -> bool:
        if not n:
            return True
        s = n.strip().lower()
        if s in generic_site_names:
            return True
        if len(s) < 3:
            return True
        if s in generic_company_words:
            return True
        return False

    shortlisted = ranked_candidates[: max(target * 5, 25)]
    total_to_process = len(shortlisted)

    if progress_callback:
        progress_callback(0, total_to_process, "Justdial scraping started")

    for idx, candidate in enumerate(shortlisted, start=1):
        if len(gst_rows) >= target:
            if progress_callback:
                progress_callback(idx - 1, total_to_process, f"Justdial processed {idx - 1}/{total_to_process}")
            break

        url = candidate["profile_url"]

        try:
            html = None
            attempts = 0

            while attempts < 2 and not html:
                attempts += 1
                try:
                    driver.get(url)
                    try:
                        WebDriverWait(driver, 4).until(
                            EC.any_of(
                                EC.presence_of_element_located((By.CSS_SELECTOR, 'script[type="application/ld+json"]')),
                                EC.presence_of_element_located((By.TAG_NAME, "h1")),
                                EC.presence_of_element_located((By.TAG_NAME, "body")),
                            )
                        )
                    except Exception:
                        pass
                    html = driver.page_source
                except WebDriverException:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = create_chrome_driver(headless=headless)
                    time.sleep(0.6)

            if not html:
                if progress_callback:
                    progress_callback(idx, total_to_process, f"Justdial processed {idx}/{total_to_process}")
                continue

            visible_text = normalize_text(html)
            jld = extract_from_jsonld(html)

            name = candidate.get("business_name", "")
            company_name = ""
            phone = ""
            address = ""
            parsed_city = city
            website = ""
            rating = candidate.get("rating", 0.0)
            reviews = candidate.get("reviews", 0)

            if jld:
                name = jld.get("name") or name
                company_name = jld.get("alternateName") or ""
                brand = jld.get("brand") or jld.get("publisher") or None
                if isinstance(brand, dict):
                    company_name = company_name or brand.get("name") or ""
                elif isinstance(brand, str):
                    company_name = company_name or brand

                phone = jld.get("telephone") or ""
                adr = jld.get("address") or {}
                if isinstance(adr, dict):
                    street = adr.get("streetAddress", "")
                    locality = adr.get("addressLocality", "")
                    parsed_city = adr.get("addressRegion", "") or parsed_city
                    address = ", ".join([p for p in [street, locality] if p])
                website = jld.get("url") or ""

                aggregate = jld.get("aggregateRating") or {}
                if isinstance(aggregate, dict):
                    jsonld_rating, jsonld_reviews = parse_rating_and_reviews(
                        f"{aggregate.get('ratingValue', '')} {aggregate.get('ratingCount', '')}"
                    )
                    if jsonld_rating:
                        rating = jsonld_rating
                    if jsonld_reviews:
                        reviews = jsonld_reviews

            if is_generic_name(name):
                try:
                    title = driver.title or ""
                    if title:
                        candidate_name = re.split(r"[-|:—]", title)[0].strip()
                        candidate_name = re.sub(r"\bJustdial\b", "", candidate_name, flags=re.I).strip(" -|,")
                        if candidate_name and not is_generic_name(candidate_name):
                            name = candidate_name
                except Exception:
                    pass

            if is_generic_name(name):
                try:
                    h1 = driver.find_element(By.TAG_NAME, "h1")
                    h1txt = h1.text.strip()
                    if h1txt and not is_generic_name(h1txt):
                        name = h1txt
                except Exception:
                    pass

            if not company_name:
                try:
                    company_candidates = driver.find_elements(
                        By.CSS_SELECTOR,
                        '[class*="company"], [class*="brand"], [class*="company-name"], '
                        '[class*="brand-name"], [itemprop="brand"], [itemprop="alternateName"]',
                    )
                    phone_pattern = re.compile(r"\+?91[-\s]?[0-9]{10}|(?<!\d)(?:[6-9][0-9]{9})(?!\d)")
                    for c in company_candidates:
                        text = c.text.strip()
                        if not text or len(text) < 3:
                            continue
                        if phone_pattern.search(text) or re.fullmatch(r"[0-9\s\-()+]{6,}", text):
                            continue
                        if text.lower() in {"justdial", "this page isn’t working", (name or "").lower()}:
                            continue
                        company_name = text
                        break
                except Exception:
                    pass

            if not phone:
                try:
                    tel_el = driver.find_element(By.CSS_SELECTOR, 'a[href^="tel:"]')
                    phone = tel_el.get_attribute("href").replace("tel:", "")
                except Exception:
                    phone = extract_phone_from_html(html or "")

            if not address:
                try:
                    addr = driver.find_element(By.TAG_NAME, "address")
                    address = addr.text.strip()
                except Exception:
                    try:
                        meta = driver.find_element(By.CSS_SELECTOR, 'meta[name="address"]')
                        address = meta.get_attribute("content") or ""
                    except Exception:
                        try:
                            p = driver.find_element(By.CSS_SELECTOR, ".jd-locality, .locality, .address")
                            address = p.text.strip()
                        except Exception:
                            pass

            if rating > 5:
                rating = 0.0
            if reviews < 0:
                reviews = 0

            normalized_name = normalize_text(name)
            normalized_company = normalize_text(company_name)
            normalized_address = normalize_text(address)

            phone_candidates = re.findall(r"(?:\+91[-\s]?)?[6-9]\d{9}", phone or "")
            normalized_phone = ""

            for candidate_phone in phone_candidates:
                digits = re.sub(r"\D", "", candidate_phone)
                if digits.startswith("91") and len(digits) > 10:
                    digits = digits[-10:]
                if len(digits) == 10 and digits[0] in "6789":
                    normalized_phone = digits
                    break

            if not normalized_phone:
                digits = re.sub(r"\D", "", phone or "")
                if digits.startswith("91") and len(digits) > 10:
                    digits = digits[-10:]
                if len(digits) == 10 and digits[0] in "6789":
                    normalized_phone = digits
                else:
                    normalized_phone = ""

            if normalized_phone and len(normalized_phone) != 10:
                if progress_callback:
                    progress_callback(idx, total_to_process, f"Justdial processed {idx}/{total_to_process}")
                continue
            if not normalized_name:
                if progress_callback:
                    progress_callback(idx, total_to_process, f"Justdial processed {idx}/{total_to_process}")
                continue

            row_city = infer_city_from_text(f"{parsed_city} {address} {name}", city)
            if not city_match(row_city, city):
                if progress_callback:
                    progress_callback(idx, total_to_process, f"Justdial processed {idx}/{total_to_process}")
                continue

            combined_text = _norm(f"{normalized_name} {normalized_company} {normalized_address} {visible_text}")
            keyword_ok = any(v in combined_text for v in keyword_variants(keyword))
            if not keyword_ok:
                if progress_callback:
                    progress_callback(idx, total_to_process, f"Justdial processed {idx}/{total_to_process}")
                continue

            gst_number = extract_gst_number(html + " " + normalized_address + " " + normalized_company + " " + normalized_name)
            gst_found = bool(gst_number)

            experience_source_text = " ".join([
                html,
                normalized_name,
                normalized_company,
                normalized_address,
            ])
            established_year = extract_established_year(experience_source_text)
            experience_years = extract_experience_years(experience_source_text)

            commercial_score, commercial_match = extract_commercial_score(experience_source_text)

            computed_final_score = final_score(
                candidate.get("relevance_score", 0),
                rating,
                reviews,
                gst_found,
                experience_years,
                commercial_score,
            )

            row = {
                "business_name": normalized_name,
                "company_name": normalized_company,
                "phone": normalized_phone,
                "address": normalized_address,
                "city": _norm(city),
                "category": normalize_text(keyword),
                "website": normalize_text(website),
                "rating": f"{rating:.1f}" if rating else "",
                "reviews": str(reviews) if reviews else "",
                "gst_found": "yes" if gst_found else "no",
                "gst_number": gst_number,
                "established_year": str(established_year) if established_year else "",
                "experience_years": str(experience_years) if experience_years else "",
                "has_5_plus_years": "yes" if has_5_plus_years(experience_years) else "no",
                "commercial_score": str(commercial_score),
                "commercial_match": commercial_match,
                "selection_type": "gst_priority" if gst_found else "fallback_non_gst",
                "source_url": url,
                "source": "justdial",
                "relevance_score": candidate.get("relevance_score", 0),
                "final_score": round(computed_final_score, 2),
            }

            if gst_found:
                if normalized_phone and normalized_phone in seen_gst_phones:
                    if progress_callback:
                        progress_callback(idx, total_to_process, f"Justdial processed {idx}/{total_to_process}")
                    continue
                if normalized_name and normalized_name.lower() in seen_gst_names:
                    if progress_callback:
                        progress_callback(idx, total_to_process, f"Justdial processed {idx}/{total_to_process}")
                    continue
                if normalized_phone:
                    seen_gst_phones.add(normalized_phone)
                if normalized_name:
                    seen_gst_names.add(normalized_name.lower())
                gst_rows.append(row)
            else:
                if normalized_phone and normalized_phone in seen_fb_phones:
                    if progress_callback:
                        progress_callback(idx, total_to_process, f"Justdial processed {idx}/{total_to_process}")
                    continue
                if normalized_name and normalized_name.lower() in seen_fb_names:
                    if progress_callback:
                        progress_callback(idx, total_to_process, f"Justdial processed {idx}/{total_to_process}")
                    continue
                if normalized_phone:
                    seen_fb_phones.add(normalized_phone)
                if normalized_name:
                    seen_fb_names.add(normalized_name.lower())
                fallback_rows.append(row)

        except Exception:
            pass

        if progress_callback:
            progress_callback(idx, total_to_process, f"Justdial processed {idx}/{total_to_process}")

    gst_rows = sorted(
        gst_rows,
        key=lambda x: (
            x.get("has_5_plus_years") == "yes",
            int(x.get("commercial_score") or 0),
            float(x["final_score"]) if str(x.get("final_score", "")).strip() else 0.0,
            float(x["rating"]) if str(x.get("rating", "")).strip() else 0.0,
            int(str(x["reviews"]).replace(",", "")) if str(x.get("reviews", "")).strip() else 0,
        ),
        reverse=True,
    )

    fallback_rows = sorted(
        fallback_rows,
        key=lambda x: (
            x.get("has_5_plus_years") == "yes",
            int(x.get("commercial_score") or 0),
            float(x["final_score"]) if str(x.get("final_score", "")).strip() else 0.0,
            float(x["rating"]) if str(x.get("rating", "")).strip() else 0.0,
            int(str(x["reviews"]).replace(",", "")) if str(x.get("reviews", "")).strip() else 0,
        ),
        reverse=True,
    )

    final_rows = gst_rows[:target]
    if len(final_rows) < target:
        remaining = target - len(final_rows)
        final_rows.extend(fallback_rows[:remaining])

    return final_rows[:target]


def collect_profile_candidates(driver, city: str, keyword: str, target: int, max_time: int) -> List[Dict[str, Any]]:
    keyword = normalize_keyword_typos(keyword)

    city_key = _norm(city)
    all_candidates: List[Dict[str, Any]] = []

    if city_key in STATES_TO_CITIES:
        cities = STATES_TO_CITIES[city_key]
        per_city_target = max(6, math.ceil(target * 1.5 / max(1, len(cities))))
        per_city_time = max(12, math.ceil(max_time / max(1, len(cities))))
        for ci in cities:
            ok = set_location_via_ui(driver, ci)
            if not ok:
                set_location_cookie(driver, ci)

            open_search_page(driver, ci, keyword)
            city_candidates = collect_listing_candidates(driver, keyword, ci, per_city_target, per_city_time)
            all_candidates.extend(city_candidates)
    else:
        ok = set_location_via_ui(driver, city)
        if not ok:
            set_location_cookie(driver, city)

        open_search_page(driver, city, keyword)
        all_candidates = collect_listing_candidates(driver, keyword, city, target, max_time)

    dedup: Dict[str, Dict[str, Any]] = {}
    for c in all_candidates:
        url = c["profile_url"]
        existing = dedup.get(url)
        if not existing or c["final_score"] > existing["final_score"]:
            dedup[url] = c

    ranked = sorted(
        dedup.values(),
        key=lambda x: (x["final_score"], x["rating"], x["reviews"]),
        reverse=True,
    )
    return ranked


def run_justdial_scraper(
    keyword: str,
    city: str,
    max_results: int,
    max_time: int,
    headless: bool,
    output_file: Path,
    progress_callback: Optional[Callable[[int, int, Optional[str]], None]] = None,
) -> int:
    keyword = normalize_keyword_typos(keyword)

    driver = create_chrome_driver(headless=headless)
    try:
        ranked_candidates = collect_profile_candidates(
            driver=driver,
            city=city,
            keyword=keyword,
            target=max_results,
            max_time=max_time,
        )

        rows = extract_profile_rows(
            driver=driver,
            ranked_candidates=ranked_candidates,
            keyword=keyword,
            city=city,
            target=max_results,
            headless=headless,
            progress_callback=progress_callback,
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
            "gst_found",
            "gst_number",
            "established_year",
            "experience_years",
            "has_5_plus_years",
            "commercial_score",
            "commercial_match",
            "selection_type",
            "source_url",
            "source",
            "relevance_score",
            "final_score",
        ]
        total_rows = write_csv(output_file, headers, rows)

        if progress_callback:
            shortlisted_count = len(ranked_candidates[: max(max_results * 5, 25)])
            progress_callback(shortlisted_count, shortlisted_count, "Justdial scraping completed")

        return total_rows
    finally:
        try:
            driver.quit()
        except Exception:
            pass