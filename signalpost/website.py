import hashlib
import html.parser
import json
import re
import urllib.parse
import unicodedata
from datetime import date, datetime
from dataclasses import dataclass, field
from typing import Any

from .identity import is_valid_orgnr
from .sources import Fetch, HttpClient


KEYWORDS = ("contact", "kontakt", "about", "om-oss", "careers", "karriere", "jobb", "jobs", "news", "aktuelt", "nyheter", "blog", "press")
SOCIAL_HOSTS = {"linkedin.com", "www.linkedin.com", "facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com", "youtube.com", "www.youtube.com"}
COMMON_PATHS = ("/kontakt", "/contact", "/om-oss", "/about", "/karriere", "/careers", "/jobb", "/jobs", "/aktuelt", "/nyheter", "/news")


class PageParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.footer_links: list[str] = []
        self.news_links: list[str] = []
        self.meta_description = ""
        self.title: list[str] = []
        self.headings: list[str] = []
        self._title_depth = 0
        self._heading_depth = 0
        self._ignored_depth = 0
        self._footer_depth = 0
        self._href_in_footer = False
        self.published_dates: list[str] = []
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth += 1
        if tag == "footer":
            self._footer_depth += 1
        if tag == "title":
            self._title_depth += 1
        if tag == "h1":
            self._heading_depth += 1
        if tag == "a" and values.get("href"):
            self._href = values["href"]
            self._href_in_footer = self._footer_depth > 0
            self._link_text = []
            if re.search(r"(?:siste-nytt|news|nyhet|article|post-card|post-item)", str(values.get("class") or ""), re.I):
                self.news_links.append(values["href"])
        if tag == "meta" and (values.get("name") or values.get("property") or "").casefold() in {"description", "og:description"} and values.get("content"):
            self.meta_description = values["content"].strip()
        if tag == "meta" and (values.get("property") or values.get("name") or "").casefold() in {"article:published_time", "datepublished"} and values.get("content"):
            self.published_dates.append(values["content"].strip())
        if tag == "time" and values.get("datetime") and ((values.get("itemprop") or "").casefold() == "datepublished" or re.search(r"publish|post-date|entry-date", str(values.get("class") or ""), re.I)):
            self.published_dates.append(values["datetime"].strip())

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self._ignored_depth = max(0, self._ignored_depth - 1)
        if tag == "footer":
            self._footer_depth = max(0, self._footer_depth - 1)
        if tag == "title":
            self._title_depth = max(0, self._title_depth - 1)
        if tag == "h1":
            self._heading_depth = max(0, self._heading_depth - 1)
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._link_text).strip()))
            if self._href_in_footer:
                self.footer_links.append(self._href)
            self._href = None
            self._link_text = []
            self._href_in_footer = False

    def handle_data(self, data):
        if self._ignored_depth:
            return
        cleaned = " ".join(data.split())
        if cleaned:
            self.text.append(cleaned)
            if self._title_depth:
                self.title.append(cleaned)
            if self._heading_depth:
                self.headings.append(cleaned)
            if self._href:
                self._link_text.append(cleaned)


@dataclass
class WebsiteResult:
    claims: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    snapshots: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def _digits(value: Any) -> str:
    return "".join(re.findall(r"\d", str(value or "")))


def _ascii(value: Any) -> str:
    value = str(value or "").casefold().replace("ø", "o").replace("æ", "ae").replace("å", "a")
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()


def _tokens(value: Any) -> list[str]:
    ascii_text = _ascii(value)
    ignored = {"as", "asa", "enk", "ans", "da", "sa", "nuf", "ba", "a", "s", "ab", "norway", "norge"}
    return [token for token in re.findall(r"[a-z0-9]+", ascii_text) if token not in ignored and len(token) >= 2]


def _candidate_homepages(registry: dict[str, Any]) -> list[str]:
    supplied = str(registry.get("hjemmeside") or "").strip()
    if supplied:
        candidate = supplied if "://" in supplied else "https://" + supplied
        if (urllib.parse.urlparse(candidate).hostname or "").casefold() in SOCIAL_HOSTS:
            return []
        return [candidate]
    tokens = _tokens(registry.get("navn"))
    compact = "".join(tokens)
    hyphenated = "-".join(tokens)
    # Guessed hostnames are discovery only; publication still requires exact-entity
    # proof, and crawl_verified_website caps all outbound candidate requests.
    if not 3 <= len(compact) <= 63:
        return []
    candidates = [f"https://{compact}.no"]
    if hyphenated != compact and len(hyphenated) <= 63:
        candidates.append(f"https://{hyphenated}.no")
    candidates.append(f"https://{compact}.com")
    return candidates


def _name_match(text: str, name: str) -> bool:
    expected = _tokens(name)
    actual = set(_tokens(text))
    return bool(expected) and sum(len(word) for word in expected if word in actual) / sum(map(len, expected)) >= 0.75


def _other_legal_name(heading: str, name: str) -> bool:
    expected = _tokens(name)
    words = re.findall(r"[a-z0-9]+", _ascii(heading))
    suffixes = [i for i, word in enumerate(words) if word in {"as", "asa"}]
    return bool(expected and suffixes and words[max(0, suffixes[-1] - len(expected)):suffixes[-1]] != expected)


def _site_numbers(text: str, orgnr: str) -> set[str]:
    distinct = set()
    for match in re.finditer(r"(?<!\d)\d(?:[\s.\-]*\d){8}(?!\d)", text):
        digits = _digits(match.group())
        context = text[max(0, match.start() - 35):match.start()].casefold()
        if digits == orgnr or (is_valid_orgnr(digits) and re.search(r"(?:org(?:anis(?:ation|asjon))?\.?\s*(?:nr|number|nummer)?|mva|vat)\W*$", context)):
            distinct.add(digits)
    return distinct


def _verified(text: str, orgnr: str, registry: dict[str, Any], heading: str = "", site_url: str = "", homepage_text: str = "") -> tuple[bool, str]:
    # A footer can list many subsidiaries. A number there cannot establish that the
    # whole site belongs to one of them when the page presents another identity.
    name = str(registry.get("navn") or "")
    heading_matches = _name_match(heading, name)
    homepage_has_org = orgnr in _site_numbers(homepage_text, orgnr)
    if not heading or not (heading_matches or homepage_has_org):
        return False, "Homepage title/heading does not identify this legal entity."
    if re.search(r"\b(?:group|konsern|konsernet)\b", heading.casefold()) and not re.search(r"\b(?:group|konsern)\b", str(registry.get("navn") or "").casefold()):
        return False, "Homepage presents a parent group rather than this entity."
    if _other_legal_name(heading, str(registry.get("navn") or "")):
        return False, "Homepage names a different legal company."
    distinct = _site_numbers(text, orgnr)
    if len(distinct) > 1:
        return False, "Homepage identifies multiple legal entities."
    if orgnr in distinct:
        if not heading_matches and not registry.get("hjemmeside"):
            host = (urllib.parse.urlparse(site_url).hostname or "").casefold().removeprefix("www.")
            if host.split(".", 1)[0].replace("-", "") != "".join(_tokens(name)):
                return False, "Discovered domain does not match the company identity."
        return True, f"Page displays organisation number {orgnr}."
    if distinct:
        return False, "Homepage displays another organisation number."
    if registry.get("hjemmeside") and site_url:
        expected = _tokens(name)
        actual = _tokens(heading)
        full_name = bool(expected) and any(actual[index:index + len(expected)] == expected for index in range(len(actual) - len(expected) + 1))
        if full_name:
            return True, "Homepage displays the full company name on its registry-listed site."
    if not registry.get("hjemmeside") and site_url:
        legal_words = re.findall(r"[a-z0-9]+", _ascii(registry.get("navn")))
        heading_words = re.findall(r"[a-z0-9]+", _ascii(heading))
        domain_stem = (urllib.parse.urlparse(site_url).hostname or "").casefold().removeprefix("www.").split(".", 1)[0].replace("-", "")
        compact = "".join(_tokens(registry.get("navn")))
        exact_legal_name = any(heading_words[index:index + len(legal_words)] == legal_words for index in range(len(heading_words) - len(legal_words) + 1))
        if len(compact) >= 5 and domain_stem == compact and exact_legal_name and legal_words[-1:] in (["as"], ["asa"]):
            return True, "Exact legal name and matching discovered domain agree."
    folded_tokens = set(_tokens(heading or text))
    name_tokens = _tokens(registry.get("navn"))
    matched_weight = sum(len(token) for token in name_tokens if token in folded_tokens)
    total_weight = sum(len(token) for token in name_tokens) or 1
    host = (urllib.parse.urlparse(str(registry.get("hjemmeside") or "") if "://" in str(registry.get("hjemmeside") or "") else "https://" + str(registry.get("hjemmeside") or "")).hostname or "").casefold()
    domain_stem = host.removeprefix("www.").split(".", 1)[0].replace("-", "")
    strongest = max(name_tokens, key=len, default="")
    strong_name_match = matched_weight / total_weight >= 0.75
    strong_domain_match = len(strongest) >= 5 and strongest in domain_stem and matched_weight / total_weight >= 0.5
    if strong_name_match and strong_domain_match:
        return True, "Homepage identity and registry-listed domain agree."
    return False, "Website lacks sufficient exact-entity proof."


def _ev(fetch: Fetch, proof: str) -> dict[str, Any]:
    return {"id": f"ev-website-{fetch.sha256[:16]}", "source_url": fetch.url, "source_class": "company_owned", "retrieved_at": fetch.retrieved_at, "content_sha256": fetch.sha256, "claim_span": proof, "extraction_method": "signalpost.company_site.v1"}


def _jsonld_nodes(document: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    pattern = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            nodes.append(value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for match in pattern.finditer(document):
        try:
            walk(json.loads(match.group(1).strip()))
        except (json.JSONDecodeError, TypeError):
            continue
    return nodes


def _same_host(left: str, right: str) -> bool:
    return (urllib.parse.urlparse(left).hostname or "").casefold().removeprefix("www.") == (urllib.parse.urlparse(right).hostname or "").casefold().removeprefix("www.")


def _in_site_scope(url: str, home: str) -> bool:
    if not _same_host(url, home):
        return False
    prefix = urllib.parse.urlparse(home).path.rstrip("/")
    path = urllib.parse.urlparse(url).path.rstrip("/")
    return not prefix or path == prefix or path.startswith(prefix + "/")


def _company_social_account(url: str, registry: dict[str, Any]) -> bool:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or (parsed.hostname or "").casefold() not in SOCIAL_HOSTS:
        return False
    account = parsed.path.rstrip("/").rsplit("/", 1)[-1].lstrip("@")
    slug = re.sub(r"[^a-z0-9]", "", _ascii(account))
    name_tokens = _tokens(registry.get("navn"))
    return bool(any(len(word) >= 4 for word in name_tokens) and slug == "".join(name_tokens))


def _canonical_social_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), "", "", ""))


def _exact_organization(node: Any, orgnr: str, registry: dict[str, Any], site: str) -> bool:
    if not isinstance(node, dict):
        return False
    name = node.get("legalName") or node.get("name") or ""
    if _tokens(name) != _tokens(registry.get("navn")) or not _tokens(name):
        return False
    identifier = node.get("taxID") or node.get("vatID") or node.get("identifier")
    if isinstance(identifier, dict):
        identifier = identifier.get("value")
    if identifier and orgnr not in _digits(identifier):
        return False
    url = node.get("url")
    return not url or _in_site_scope(urllib.parse.urljoin(site, str(url)), site)


def _published_date(value: Any, retrieved_at: str) -> str | None:
    if not isinstance(value, str) or not re.match(r"^\d{4}-\d{2}-\d{2}(?:$|T)", value):
        return None
    try:
        published = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        retrieved = date.fromisoformat(retrieved_at[:10])
    except ValueError:
        return None
    return value if published <= retrieved else None


def _article_body(document: str) -> str:
    sections = re.findall(r"<(?:article|main)\b[^>]*>(.*?)</(?:article|main)>", document, re.I | re.S)
    sections += re.findall(r"<(?:div|section)\b[^>]*class=[\"'][^\"']*(?:entry-content|post-content|article-content|content__body)[^\"']*[\"'][^>]*>(.*?)</(?:div|section)>", document, re.I | re.S)
    cleaned = []
    for section in sections[:4]:
        section = re.sub(r"<(?:script|style)\b[^>]*>.*?</(?:script|style)>", " ", section, flags=re.I | re.S)
        cleaned.append(html.unescape(re.sub(r"<[^>]+>", " ", section)))
    return " ".join(cleaned)[:50000]


def _structured_claims(fetch: Fetch, evidence_id: str, orgnr: str, registry: dict[str, Any], site: str, from_news_listing: bool = False) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(field: str, value: Any, confidence: float = 0.97) -> None:
        identity = json.dumps(value, ensure_ascii=False, sort_keys=True) if not isinstance(value, str) else value
        marker = (field, identity)
        if not value or marker in seen:
            return
        seen.add(marker)
        claims.append({"key": f"{field}:{hashlib.sha256(identity.encode()).hexdigest()[:12]}", "field": field, "value": value, "availability": "available", "confidence": confidence, "evidence_ids": [evidence_id]})

    for node in _jsonld_nodes(str(fetch.body or "")):
        raw_type = node.get("@type")
        kinds = {str(item).rstrip("/").rsplit("/", 1)[-1] for item in (raw_type if isinstance(raw_type, list) else [raw_type]) if item}
        if kinds & {"Organization", "Corporation", "LocalBusiness", "Store", "ProfessionalService"} and _exact_organization(node, orgnr, registry, site):
            add("contact.phone", node.get("telephone"))
            add("contact.email", str(node.get("email") or "").removeprefix("mailto:"))
            address = node.get("address")
            if isinstance(address, dict) and any(address.get(key) for key in ("streetAddress", "postalCode", "addressLocality")):
                add("locations.company_reported", {key: address.get(key) for key in ("streetAddress", "postalCode", "addressLocality", "addressCountry") if address.get(key)})
            same_as = node.get("sameAs")
            for url in same_as if isinstance(same_as, list) else [same_as]:
                if _company_social_account(str(url or ""), registry):
                    add("public.social_profile", _canonical_social_url(str(url)))
        if kinds & {"NewsArticle", "BlogPosting", "PressRelease", "Article"}:
            headline = node.get("headline") or node.get("name")
            url = node.get("url") or node.get("mainEntityOfPage") or node.get("@id")
            if isinstance(url, dict):
                url = url.get("@id")
            parsed_url = urllib.parse.urlparse(urllib.parse.urljoin(fetch.url, str(url or "")))
            absolute = urllib.parse.urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, "", "", ""))
            article_path = urllib.parse.urlparse(absolute).path.casefold()
            article_path_ok = any(word in article_path for word in ("news", "nyheter", "aktuelt", "article", "artikkel", "blog", "press"))
            published = _published_date(node.get("datePublished"), fetch.retrieved_at)
            article_text = " ".join(str(node.get(key) or "") for key in ("articleBody", "description", "about"))
            about_company = _name_match(article_text + " " + _article_body(str(fetch.body or "")), str(registry.get("navn") or ""))
            if headline and len(str(headline).strip()) >= 12 and url and published and (article_path_ok or from_news_listing) and _in_site_scope(absolute, site) and absolute.rstrip("/") == fetch.url.rstrip("/") and about_company:
                add("public.activity_item", {"title": str(headline)[:300], "url": absolute, "published_at": published})
        if "JobPosting" in kinds:
            title = node.get("title") or node.get("name")
            url = node.get("url") or fetch.url
            if title and _exact_organization(node.get("hiringOrganization"), orgnr, registry, site) and _in_site_scope(urllib.parse.urljoin(fetch.url, str(url)), site):
                add("hiring.job_posting", {"title": str(title)[:200], "url": urllib.parse.urljoin(fetch.url, str(url)), "published_at": node.get("datePosted"), "valid_through": node.get("validThrough")})
    return claims


def _html_article_claim(fetch: Fetch, page: PageParser, registry: dict[str, Any]) -> dict[str, Any] | None:
    article = re.search(r"<article\b[^>]*>(.*?)</article>", str(fetch.body or ""), re.I | re.S)
    if not article:
        return None
    content = PageParser(); content.feed(article.group(1))
    title = " ".join(content.headings or page.headings).strip()
    published = next((_published_date(value, fetch.retrieved_at) for value in content.published_dates + page.published_dates if _published_date(value, fetch.retrieved_at)), None)
    if not published or len(title) < 12 or not _name_match(" ".join(content.text), str(registry.get("navn") or "")):
        return None
    value = {"title": title[:300], "url": fetch.url, "published_at": published}
    identity = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return {"key": f"public.activity_item:{hashlib.sha256(identity.encode()).hexdigest()[:12]}", "field": "public.activity_item", "value": value, "availability": "available", "confidence": 0.95}


def crawl_verified_website(orgnr: str, registry: dict[str, Any], client: HttpClient, max_pages: int = 5, max_discovery_candidates: int = 3) -> WebsiteResult:
    result = WebsiteResult()
    home_candidates = _candidate_homepages(registry)
    if not registry.get("hjemmeside"):
        home_candidates = home_candidates[:max_discovery_candidates]
    if not home_candidates:
        return result
    attempts = 0

    def fetch_page(url: str) -> Fetch | None:
        nonlocal attempts
        if attempts >= max_pages:
            return None
        attempts += 1
        return client.text(url)

    first = None
    last_error = None
    parser = None
    for home in home_candidates:
        try:
            candidate = fetch_page(home)
        except Exception as exc:
            last_error = type(exc).__name__
            continue
        if candidate is None:
            break
        if candidate.status == 200 and isinstance(candidate.body, str) and _same_host(candidate.url, home):
            candidate_parser = PageParser(); candidate_parser.feed(candidate.body)
            candidate_heading = " ".join(candidate_parser.headings)
            candidate_title = " ".join(candidate_parser.title)
            displayed = candidate_heading if _name_match(candidate_heading, str(registry.get("navn") or "")) else candidate_title
            homepage_has_org = orgnr in _site_numbers(" ".join(candidate_parser.text), orgnr)
            if not (_name_match(displayed, str(registry.get("navn") or "")) or homepage_has_org) or _other_legal_name(candidate_heading, str(registry.get("navn") or "")):
                last_error = "ambiguous identity"
                continue
            first = candidate
            parser = candidate_parser
            break
        last_error = "Homepage redirected to a different domain" if candidate.status == 200 and not _same_host(candidate.url, home) else candidate.error or f"HTTP {candidate.status}"
    if first is None:
        result.errors.append({"module": "website", "message": last_error or "No candidate website responded"})
        return result
    assert parser is not None
    primary_heading = " ".join(parser.headings)
    title = " ".join(parser.title)
    heading = primary_heading if _name_match(primary_heading, str(registry.get("navn") or "")) or not title else title
    homepage_has_org = orgnr in _site_numbers(" ".join(parser.text), orgnr)
    if re.search(r"\b(?:group|konsern|konsernet)\b", primary_heading.casefold()) or _other_legal_name(primary_heading, str(registry.get("navn") or "")) or not (_name_match(heading, str(registry.get("navn") or "")) or homepage_has_org):
        result.errors.append({"module": "website", "message": "ambiguous identity", "detail": "Homepage does not identify the exact company."})
        return result
    pages = [(first, parser)]
    candidates = []
    for href, label in parser.links:
        absolute = urllib.parse.urljoin(first.url, href)
        parsed = urllib.parse.urlparse(absolute)
        if _in_site_scope(absolute, first.url) and any(word in (parsed.path + " " + label).casefold() for word in KEYWORDS):
            clean = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
            if clean not in candidates:
                candidates.append(clean)
    # Many small-company sites omit useful navigation from the homepage or render it with
    # JavaScript. Probe a bounded set of conventional same-origin paths; publication still
    # requires the exact-entity gate below and a successful page response.
    common_path_limit = max(0, max_pages - (2 if parser.news_links else 1))
    for path in COMMON_PATHS:
        if len(candidates) >= common_path_limit:
            break
        guessed = urllib.parse.urljoin(first.url.rstrip("/") + "/", path.lstrip("/"))
        if guessed not in candidates:
            candidates.append(guessed)
    def priority(url: str) -> int:
        value = urllib.parse.urlparse(url).path.casefold()
        groups = (("career", "karriere", "jobb", "jobs"), ("news", "aktuelt", "nyheter", "blog", "press"), ("contact", "kontakt"), ("about", "om-oss"))
        return next((index for index, words in enumerate(groups) if any(word in value for word in words)), len(groups))
    for url in sorted(candidates, key=priority)[: max(0, min(2, max_pages - 1))]:
        fetch = fetch_page(url)
        if fetch is None:
            break
        if fetch.status == 200 and isinstance(fetch.body, str) and _in_site_scope(fetch.url, first.url):
            page = PageParser(); page.feed(fetch.body); pages.append((fetch, page))
    verified, proof = _verified(" ".join(" ".join(page.text) for _, page in pages), orgnr, registry, heading=heading, site_url=first.url, homepage_text=" ".join(parser.text))
    if not verified:
        result.errors.append({"module": "website", "message": "ambiguous identity", "detail": proof})
        return result
    # News listing links are only discovery candidates. Never publish them as news
    # until an article page supplies its own publication date and company context.
    article_urls: set[str] = set()
    for fetch, page in list(pages):
        if attempts >= max_pages:
            break
        news_listing_path = any(word in urllib.parse.urlparse(fetch.url).path.casefold() for word in ("news", "aktuelt", "nyheter", "blog", "press"))
        if not news_listing_path and not (fetch.url == first.url and page.news_links):
            continue
        for href, label in [(href, "News article") for href in page.news_links] + page.links:
            if attempts >= max_pages:
                break
            parsed_article = urllib.parse.urlparse(urllib.parse.urljoin(fetch.url, href))
            absolute = urllib.parse.urlunparse((parsed_article.scheme, parsed_article.netloc, parsed_article.path, "", "", ""))
            path = parsed_article.path.casefold()
            in_news_path = any(word in path for word in ("news", "aktuelt", "nyheter", "article", "artikkel", "blog", "press"))
            listed_article = href in page.news_links
            if not _in_site_scope(absolute, first.url) or not (in_news_path or listed_article) or not (12 <= len(label.strip()) <= 240) or path in {"", "/"} or any(word in path for word in ("category", "kategori", "tag", "author", "kontakt", "contact", "privacy", "cookie")):
                continue
            if any(absolute.rstrip("/") == existing.url.rstrip("/") for existing, _ in pages):
                continue
            article = fetch_page(absolute)
            if article is None:
                break
            if article.status == 200 and isinstance(article.body, str) and _in_site_scope(article.url, first.url):
                article_page = PageParser(); article_page.feed(article.body)
                pages.append((article, article_page))
                article_urls.add(article.url)
    for url in sorted(candidates, key=priority):
        if attempts >= max_pages:
            break
        if any(url.rstrip("/") == existing.url.rstrip("/") for existing, _ in pages):
            continue
        fetch = fetch_page(url)
        if fetch is None:
            break
        if fetch.status == 200 and isinstance(fetch.body, str) and _in_site_scope(fetch.url, first.url):
            page = PageParser(); page.feed(fetch.body); pages.append((fetch, page))
    evidence_by_url = {}
    for fetch, _ in pages:
        ev = _ev(fetch, proof); evidence_by_url[fetch.url] = ev; result.evidence.append(ev)
        result.snapshots.append({"source_url": fetch.url, "retrieved_at": fetch.retrieved_at, "content_sha256": fetch.sha256, "status": fetch.status})
    first_ev = result.evidence[0]
    result.claims.append({"key": "website.official", "field": "website.official", "value": first.url, "availability": "available", "confidence": 1.0, "evidence_ids": [first_ev["id"]]})
    if 20 <= len(parser.meta_description) <= 1000:
        result.claims.append({"key": "website.description", "field": "website.description", "value": parser.meta_description, "availability": "available", "confidence": 0.98, "evidence_ids": [first_ev["id"]]})
    seen = set()
    for fetch, page in pages:
        ev = evidence_by_url[fetch.url]; path = urllib.parse.urlparse(fetch.url).path.casefold()
        structured = _structured_claims(fetch, ev["id"], orgnr, registry, first.url, fetch.url in article_urls)
        result.claims.extend(structured)
        if fetch.url in article_urls and not any(claim["field"] == "public.activity_item" for claim in structured):
            article_claim = _html_article_claim(fetch, page, registry)
            if article_claim:
                article_claim["evidence_ids"] = [ev["id"]]
                result.claims.append(article_claim)
        for href in page.footer_links:
            absolute = urllib.parse.urljoin(fetch.url, href)
            if _company_social_account(absolute, registry):
                account_url = _canonical_social_url(absolute)
                result.claims.append({"key": f"public.social_profile:{hashlib.sha256(account_url.encode()).hexdigest()[:12]}", "field": "public.social_profile", "value": account_url, "availability": "available", "confidence": 0.95, "evidence_ids": [ev["id"]]})
        if any(word in path for word in ("career", "karriere", "jobb", "jobs")):
            result.claims.append({"key": f"hiring.careers_page:{hashlib.sha256(fetch.url.encode()).hexdigest()[:12]}", "field": "hiring.careers_page", "value": fetch.url, "availability": "available", "confidence": 0.98, "evidence_ids": [ev["id"]]})
        if any(word in path for word in ("news", "aktuelt", "nyheter", "blog", "press")):
            result.claims.append({"key": f"public.activity_page:{hashlib.sha256(fetch.url.encode()).hexdigest()[:12]}", "field": "public.activity_page", "value": fetch.url, "availability": "available", "confidence": 0.98, "evidence_ids": [ev["id"]]})
        for href, _label in page.links:
            absolute = urllib.parse.urljoin(fetch.url, href); parsed = urllib.parse.urlparse(absolute)
            field = value = None
            if parsed.scheme == "mailto": field, value = "contact.email", absolute.removeprefix("mailto:").split("?", 1)[0]
            elif parsed.scheme == "tel": field, value = "contact.phone", absolute.removeprefix("tel:")
            if field and value:
                identity = value if isinstance(value, str) else value["url"]
                if identity not in seen:
                    seen.add(identity); result.claims.append({"key": f"{field}:{hashlib.sha256(identity.encode()).hexdigest()[:12]}", "field": field, "value": value, "availability": "available", "confidence": 0.95, "evidence_ids": [ev["id"]]})
    deduplicated: dict[str, dict[str, Any]] = {}
    for claim in result.claims:
        deduplicated.setdefault(str(claim.get("key")), claim)
    result.claims = list(deduplicated.values())
    return result

