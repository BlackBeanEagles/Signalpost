import unittest

from signalpost.sources import safe_public_url
from signalpost.sources import Fetch
from signalpost.website import PageParser, _candidate_homepages, _structured_claims, _verified, crawl_verified_website


REGISTRY = {"navn": "Example Company AS", "hjemmeside": "https://example.no", "telefon": "22334455"}


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def text(self, url):
        self.calls.append(url)
        body = self.pages.get(url)
        if body is None:
            return Fetch(url, 404, None, b"", "2026-10-15T00:00:00Z")
        return Fetch(url, 200, body, body.encode(), "2026-10-15T00:00:00Z")


class WebsiteTests(unittest.TestCase):
    def test_private_network_is_rejected(self):
        with self.assertRaises(ValueError):
            safe_public_url("http://127.0.0.1/internal")

    def test_jsonld_requires_company_identity_and_article_publication_date(self):
        document = '''<script type="application/ld+json">{
          "@graph": [
            {"@type":"Organization","name":"Example Company AS","url":"https://example.no","telephone":"+47 22 33 44 55","email":"post@example.no","sameAs":["https://www.linkedin.com/company/examplecompany","https://www.linkedin.com/company/examplegroup"],"address":{"@type":"PostalAddress","streetAddress":"Main 1","postalCode":"0101","addressLocality":"Oslo"}},
            {"@type":"https://schema.org/NewsArticle","headline":"Example Company signs a new contract","url":"/news/contract","datePublished":"2026-10-01","description":"Example Company has signed a new contract","publisher":{"name":"Example Company AS"}},
            {"@type":"NewsArticle","headline":"Product overview navigation","url":"/products","dateModified":"2026-10-01"},
            {"@type":"JobPosting","title":"Engineer","url":"/jobs/engineer","datePosted":"2026-10-02","hiringOrganization":{"name":"Example Company AS"}}
          ]
        }</script>'''
        fetch = Fetch("https://example.no/news/contract", 200, document, document.encode(), "2026-10-15T00:00:00Z")
        claims = _structured_claims(fetch, "ev-1", "123456789", REGISTRY, "https://example.no/")
        fields = {claim["field"] for claim in claims}
        self.assertTrue({"contact.phone", "contact.email", "locations.company_reported", "public.activity_item", "hiring.job_posting", "public.social_profile"} <= fields)
        self.assertEqual([c["value"] for c in claims if c["field"] == "public.social_profile"], ["https://www.linkedin.com/company/examplecompany"])
        self.assertEqual(len([c for c in claims if c["field"] == "public.activity_item"]), 1)

    def test_parent_homepage_cannot_become_subsidiary_site(self):
        pages = {"https://example.no": '<title>Parent Group</title><h1>Parent Group</h1><a href="/contact">Contact</a>',
                 "https://example.no/contact": "Example Company AS org 123 456 789"}
        result = crawl_verified_website("123456789", REGISTRY, FakeClient(pages))
        self.assertFalse(result.claims)
        self.assertEqual(result.errors[0]["message"], "ambiguous identity")

    def test_registry_listed_brand_site_can_verify_without_footer_number(self):
        pages = {"https://example.no": '<title>Example Company</title><h1>Welcome to Example Company</h1>'}
        result = crawl_verified_website("123456789", REGISTRY, FakeClient(pages), max_pages=1)
        self.assertIn("website.official", {c["field"] for c in result.claims})

    def test_different_legal_name_on_same_domain_is_rejected(self):
        pages = {"https://example.no": '<title>Example Company Services AS</title><p>Example Company AS</p>'}
        result = crawl_verified_website("123456789", REGISTRY, FakeClient(pages), max_pages=1)
        self.assertFalse(result.claims)

    def test_footer_social_and_news_menu_are_not_published(self):
        home = '<title>Example Company AS</title><h1>Example Company AS</h1><p>Org nr 123 456 789</p><a href="https://facebook.com/parentgroup">Facebook</a><a href="/news">News</a>'
        news = '<h1>News</h1><a href="/news/#skip-to-content">Skip to the content</a><a href="/products">Product overview</a><a href="/news/contract">Example Company signs a new contract</a>'
        article = '<script type="application/ld+json">{"@type":"NewsArticle","headline":"Example Company signs a new contract","url":"/news/contract","datePublished":"2026-10-01","publisher":{"name":"Example Company AS"}}</script><main>Example Company has signed a new contract.</main>'
        pages = {"https://example.no": home, "https://example.no/news": news, "https://example.no/products": "Products", "https://example.no/news/contract": article}
        client = FakeClient(pages)
        result = crawl_verified_website("123456789", REGISTRY, client)
        self.assertFalse([c for c in result.claims if c["field"] == "public.social_profile"])
        activity = [c["value"] for c in result.claims if c["field"] == "public.activity_item"]
        self.assertEqual(activity, [{"title": "Example Company signs a new contract", "url": "https://example.no/news/contract", "published_at": "2026-10-01"}])
        self.assertFalse(any("#" in call for call in client.calls))

    def test_company_subsection_excludes_group_news_and_jobs(self):
        registry = {**REGISTRY, "hjemmeside": "https://group.no/companies/example"}
        home = '<title>Example Company AS</title><h1>Example Company AS</h1><p>Org nr 123 456 789</p><a href="/news">Group news</a><a href="/jobs">Group jobs</a>'
        pages = {"https://group.no/companies/example": home,
                 "https://group.no/news": '<h1>Group news</h1>',
                 "https://group.no/jobs": '<h1>Group jobs</h1>'}
        result = crawl_verified_website("123456789", registry, FakeClient(pages))
        fields = {claim["field"] for claim in result.claims}
        self.assertIn("website.official", fields)
        self.assertNotIn("public.activity_page", fields)
        self.assertNotIn("hiring.careers_page", fields)

    def test_updated_feed_date_and_unrelated_article_do_not_count_as_news(self):
        document = '''<script type="application/ld+json">{
          "@graph":[
            {"@type":"NewsArticle","headline":"Parent Group acquires a business","url":"/news/parent","datePublished":"2026-10-01","description":"Parent Group acquires another business"},
            {"@type":"NewsArticle","headline":"Example Company opens new site","url":"/news/parent","dateModified":"2026-10-02","description":"Example Company opens a site"}
          ]}</script><main>Parent Group acquires another business.</main>'''
        fetch = Fetch("https://example.no/news/parent", 200, document, document.encode(), "2026-10-15T00:00:00Z")
        claims = _structured_claims(fetch, "ev-1", "123456789", REGISTRY, "https://example.no/")
        self.assertFalse([c for c in claims if c["field"] == "public.activity_item"])

    def test_dated_article_from_news_card_is_published(self):
        home = '<title>Example Company AS</title><h1>Example Company AS</h1><a href="/news">News</a>'
        listing = '<a class="news-card" href="/new-contract/">Example Company signs a new contract</a><a href="/products">Product overview</a>'
        article = '<script type="application/ld+json">{"@type":"Article","headline":"Example Company signs a new contract","mainEntityOfPage":"/new-contract/","datePublished":"2026-10-01T08:00:00+00:00"}</script><main>Example Company has signed a new contract.</main>'
        pages = {"https://example.no": home, "https://example.no/news": listing, "https://example.no/new-contract/": article}
        result = crawl_verified_website("123456789", REGISTRY, FakeClient(pages))
        items = [c["value"] for c in result.claims if c["field"] == "public.activity_item"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://example.no/new-contract/")

    def test_missing_registry_site_gets_one_deterministic_discovery_candidate(self):
        self.assertEqual(_candidate_homepages({"navn": "Norsk Eksempel AS"}), ["https://norskeksempel.no", "https://norsk-eksempel.no"])
        self.assertEqual(_candidate_homepages({"navn": "Example AS", "hjemmeside": "example.no"}), ["https://example.no"])

    def test_exact_org_number_verifies_identity(self):
        ok, _ = _verified("EQUINOR ASA org.nr. 923 609 016", "923609016", {"navn": "EQUINOR ASA"}, heading="EQUINOR ASA")
        self.assertTrue(ok)

    def test_parser_collects_description_and_links(self):
        parser = PageParser()
        parser.feed('<meta name="description" content="Example company"><script>var irrelevant=123456789;</script><a href="/jobs">Open roles</a>')
        self.assertEqual(parser.meta_description, "Example company")
        self.assertEqual(parser.links, [("/jobs", "Open roles")])
        self.assertNotIn("123456789", parser.text)


if __name__ == "__main__":
    unittest.main()
