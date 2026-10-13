import hashlib
import html.parser
import re
import urllib.parse
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .sources import Fetch, HttpClient


KEYWORDS = ("contact", "kontakt", "about", "om-oss", "careers", "karriere", "jobb", "jobs", "news", "aktuelt", "nyheter")
SOCIAL_HOSTS = {"linkedin.com", "www.linkedin.com", "facebook.com", "www.facebook.com", "instagram.com", "www.instagram.com", "youtube.com", "www.youtube.com"}


class PageParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text: list[str] = []
        self.links: list[tuple[str, str]] = []
        self.meta_description = ""
        self._href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self._href = values["href"]
            self._link_text = []
        if tag == "meta" and (values.get("name") or values.get("property") or "").casefold() in {"description", "og:description"} and values.get("content"):
            self.meta_description = values["content"].strip()

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join(self._link_text).strip()))
            self._href = None
            self._link_text = []

    def handle_data(self, data):
        cleaned = " ".join(data.split())
        if cleaned:
            self.text.append(cleaned)
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


def _tokens(value: Any) -> list[str]:
    ascii_text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().casefold()
    ignored = {"as", "asa", "enk", "ans", "da", "sa", "nuf", "ba", "a", "s", "ab", "norway", "norge"}
    return [token for token in re.findall(r"[a-z0-9]+", ascii_text) if token not in ignored and len(token) >= 2]


def _verified(text: str, orgnr: str, registry: dict[str, Any]) -> tuple[bool, str]:
    compact = _digits(text)
    if orgnr in compact:
        return True, f"Page displays organisation number {orgnr}."
    folded_tokens = set(_tokens(text))
    name_tokens = _tokens(registry.get("navn"))
    phone = _digits(registry.get("telefon"))
    postal = str((registry.get("forretningsadresse") or {}).get("postnummer") or "")
    corroborated = (len(phone) >= 8 and phone[-8:] in compact) or (postal and postal in text)
    matched_weight = sum(len(token) for token in name_tokens if token in folded_tokens)
    total_weight = sum(len(token) for token in name_tokens) or 1
    host = (urllib.parse.urlparse(str(registry.get("hjemmeside") or "") if "://" in str(registry.get("hjemmeside") or "") else "https://" + str(registry.get("hjemmeside") or "")).hostname or "").casefold()
    domain_stem = host.removeprefix("www.").split(".", 1)[0].replace("-", "")
    strongest = max(name_tokens, key=len, default="")
    strong_name_match = matched_weight / total_weight >= 0.75
    strong_domain_match = len(strongest) >= 5 and strongest in domain_stem and matched_weight / total_weight >= 0.5
    if strong_name_match and (corroborated or strong_domain_match):
        return True, "Page matches the legal-name tokens and either official contact data or the registry-listed domain."
    return False, "Website lacks sufficient exact-entity proof."


def _ev(fetch: Fetch, proof: str) -> dict[str, Any]:
    return {"id": f"ev-website-{fetch.sha256[:16]}", "source_url": fetch.url, "source_class": "company_owned", "retrieved_at": fetch.retrieved_at, "content_sha256": fetch.sha256, "claim_span": proof, "extraction_method": "signalpost.company_site.v1"}


def crawl_verified_website(orgnr: str, registry: dict[str, Any], client: HttpClient, max_pages: int = 5) -> WebsiteResult:
    result = WebsiteResult()
    supplied = str(registry.get("hjemmeside") or "").strip()
    if not supplied:
        return result
    home = supplied if "://" in supplied else "https://" + supplied
    try:
        first = client.text(home)
    except Exception as exc:
        result.errors.append({"module": "website", "message": type(exc).__name__})
        return result
    if first.status != 200 or not isinstance(first.body, str):
        result.errors.append({"module": "website", "message": first.error or f"HTTP {first.status}"})
        return result
    base_host = (urllib.parse.urlparse(first.url).hostname or "").casefold().removeprefix("www.")
    parser = PageParser(); parser.feed(first.body)
    pages = [(first, parser)]
    candidates = []
    for href, label in parser.links:
        absolute = urllib.parse.urljoin(first.url, href)
        parsed = urllib.parse.urlparse(absolute)
        if (parsed.hostname or "").casefold().removeprefix("www.") == base_host and any(word in (parsed.path + " " + label).casefold() for word in KEYWORDS):
            clean = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
            if clean not in candidates:
                candidates.append(clean)
    def priority(url: str) -> int:
        value = urllib.parse.urlparse(url).path.casefold()
        groups = (("career", "karriere", "jobb", "jobs"), ("news", "aktuelt", "nyheter"), ("contact", "kontakt"), ("about", "om-oss"))
        return next((index for index, words in enumerate(groups) if any(word in value for word in words)), len(groups))
    for url in sorted(candidates, key=priority)[: max(0, max_pages - 1)]:
        fetch = client.text(url)
        if fetch.status == 200 and isinstance(fetch.body, str):
            page = PageParser(); page.feed(fetch.body); pages.append((fetch, page))
    verified, proof = _verified(" ".join(" ".join(page.text) for _, page in pages), orgnr, registry)
    if not verified:
        result.errors.append({"module": "website", "message": "ambiguous identity", "detail": proof})
        return result
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
        if any(word in path for word in ("career", "karriere", "jobb", "jobs")):
            result.claims.append({"key": f"hiring.careers_page:{hashlib.sha256(fetch.url.encode()).hexdigest()[:12]}", "field": "hiring.careers_page", "value": fetch.url, "availability": "available", "confidence": 0.98, "evidence_ids": [ev["id"]]})
        if any(word in path for word in ("news", "aktuelt", "nyheter")):
            result.claims.append({"key": f"public.activity_page:{hashlib.sha256(fetch.url.encode()).hexdigest()[:12]}", "field": "public.activity_page", "value": fetch.url, "availability": "available", "confidence": 0.98, "evidence_ids": [ev["id"]]})
        for href, _label in page.links:
            absolute = urllib.parse.urljoin(fetch.url, href); parsed = urllib.parse.urlparse(absolute)
            field = value = None
            if parsed.scheme == "mailto": field, value = "contact.email", absolute.removeprefix("mailto:").split("?", 1)[0]
            elif parsed.scheme == "tel": field, value = "contact.phone", absolute.removeprefix("tel:")
            elif (parsed.hostname or "").casefold() in SOCIAL_HOSTS: field, value = "public.social_profile", absolute
            elif any(word in parsed.path.casefold() for word in ("/job/", "/jobs/", "/stilling", "/ledige-stillinger")) and 4 <= len(_label.strip()) <= 160:
                field, value = "hiring.job_posting", {"title": _label.strip(), "url": absolute}
            if field and value:
                identity = value if isinstance(value, str) else value["url"]
                if identity not in seen:
                    seen.add(identity); result.claims.append({"key": f"{field}:{hashlib.sha256(identity.encode()).hexdigest()[:12]}", "field": field, "value": value, "availability": "available", "confidence": 0.95, "evidence_ids": [ev["id"]]})
    return result

