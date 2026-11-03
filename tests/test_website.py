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

    def test_registry_acronym_domain_accepts_full_homepage_name(self):
        registry = {"navn": "Den Nationale Scene AS", "hjemmeside": "https://dns.no"}
        page = '<title>Den Nationale Scene</title><h1>Den Nationale Scene</h1>'
        result = crawl_verified_website("123456789", registry, FakeClient({"https://dns.no": page}), max_pages=1)
        self.assertIn("website.official", {c["field"] for c in result.claims})

    def test_registry_site_can_use_its_own_footer_number_with_brand_heading(self):
        page = '<h1>Our brand</h1><footer>Org nr 123 456 789</footer>'
        result = crawl_verified_website("123456789", REGISTRY, FakeClient({"https://example.no": page}), max_pages=1)
        self.assertIn("website.official", {c["field"] for c in result.claims})

    def test_social_platform_listing_is_not_company_owned_website(self):
        registry = {"navn": "Example Company AS", "hjemmeside": "https://www.facebook.com/examplecompany"}
        client = FakeClient({"https://www.facebook.com/examplecompany": '<h1>Example Company AS</h1>'})
        result = crawl_verified_website("123456789", registry, client, max_pages=1)
        self.assertFalse(result.claims)
        self.assertEqual(client.calls, [])

    def test_norwegian_letter_matches_registry_listed_domain(self):
        registry = {"navn": "AUTOBJØRN AS", "hjemmeside": "https://autobjorn.no"}
        pages = {"https://autobjorn.no": '<title>Autobjørn AS</title><h1>Autobjørn AS</h1>'}
        result = crawl_verified_website("123456789", registry, FakeClient(pages), max_pages=1)
        self.assertIn("website.official", {c["field"] for c in result.claims})

    def test_guessed_domain_needs_full_legal_name_or_exact_number(self):
        registry = {"navn": "ALSTRA AS"}
        accepted = crawl_verified_website("123456789", registry, FakeClient({"https://alstra.no": '<title>ALSTRA AS</title><h1>ALSTRA AS</h1>'}), max_pages=1)
        rejected = crawl_verified_website("123456789", registry, FakeClient({"https://alstra.no": '<title>ALSTRA Group</title><h1>ALSTRA Group</h1>'}), max_pages=1)
        self.assertIn("website.official", {c["field"] for c in accepted.claims})
        self.assertFalse(rejected.claims)

    def test_different_legal_name_on_same_domain_is_rejected(self):
        pages = {"https://example.no": '<title>Example Company Services AS</title><p>Example Company AS</p>'}
        result = crawl_verified_website("123456789", REGISTRY, FakeClient(pages), max_pages=1)
        self.assertFalse(result.claims)

    def test_company_title_cannot_override_another_company_heading(self):
        pages = {"https://example.no": '<title>Example Company AS</title><h1>Parent Services AS</h1><p>Example Company AS org 123 456 789</p>'}
        result = crawl_verified_website("123456789", REGISTRY, FakeClient(pages), max_pages=1)
        self.assertFalse(result.claims)

    def test_social_account_containing_company_name_is_not_exact(self):
        document = '''<script type="application/ld+json">{
          "@type":"Organization","name":"Example Company AS","url":"https://example.no",
          "sameAs":["https://www.linkedin.com/company/examplecompanygroup",
                    "https://www.linkedin.com/company/examplecompany"]
        }</script>'''
        fetch = Fetch("https://example.no", 200, document, document.encode(), "2026-10-15T00:00:00Z")
        claims = _structured_claims(fetch, "ev-1", "123456789", REGISTRY, "https://example.no/")
        self.assertEqual([c["value"] for c in claims if c["field"] == "public.social_profile"],
                         ["https://www.linkedin.com/company/examplecompany"])

    def test_verified_site_footer_yields_only_exact_company_social_account(self):
        home = '<title>Example Company AS</title><h1>Example Company AS</h1><p>Org nr 123 456 789</p><footer><a href="https://www.linkedin.com/company/examplecompany">LinkedIn</a><a href="https://www.linkedin.com/company/examplecompanygroup">Group</a><a href="https://facebook.com/webagency">Agency</a></footer>'
        result = crawl_verified_website("123456789", REGISTRY, FakeClient({"https://example.no": home}), max_pages=1)
        self.assertEqual([c["value"] for c in result.claims if c["field"] == "public.social_profile"], ["https://www.linkedin.com/company/examplecompany"])

    def test_footer_social_url_is_canonicalized_without_tracking_query(self):
        home = '<h1>Example Company AS</h1><footer>Org nr 123 456 789 <a href="https://www.instagram.com/examplecompany/?hl=nb">Instagram</a></footer>'
        result = crawl_verified_website("123456789", REGISTRY, FakeClient({"https://example.no": home}), max_pages=1)
        self.assertEqual([c["value"] for c in result.claims if c["field"] == "public.social_profile"], ["https://www.instagram.com/examplecompany"])

    def test_footer_social_accepts_exact_legal_name_with_as_suffix(self):
        home = '<h1>Example Company AS</h1><footer><a href="https://www.linkedin.com/company/example-company-as/">LinkedIn</a><a href="https://www.linkedin.com/company/example-company-group/">Group</a></footer>'
        result = crawl_verified_website("123456789", REGISTRY, FakeClient({"https://example.no": home}), max_pages=1)
        self.assertEqual([c["value"] for c in result.claims if c["field"] == "public.social_profile"], ["https://www.linkedin.com/company/example-company-as"])

    def test_dated_generic_article_on_company_press_page_is_news(self):
        home = '<h1>Example Company AS</h1><footer>Org nr 123 456 789</footer><a href="/press">Press</a>'
        listing = '<a href="/pressemelding-project/">Example Company announces a new project</a>'
        article = '<script type="application/ld+json">{"@type":"Article","headline":"Example Company announces a new project","mainEntityOfPage":{"@id":"https://example.no/pressemelding-project/"},"datePublished":"2026-10-01"}</script><h1>Example Company announces a new project</h1><div class="entry-content"><p>Example Company AS is opening a new project in Oslo.</p></div>'
        pages = {"https://example.no": home, "https://example.no/press": listing, "https://example.no/pressemelding-project/": article}
        result = crawl_verified_website("123456789", REGISTRY, FakeClient(pages), max_pages=4)
        self.assertEqual([c["value"]["url"] for c in result.claims if c["field"] == "public.activity_item"], ["https://example.no/pressemelding-project/"])

    def test_homepage_news_card_can_discover_dated_article(self):
        home = '<h1>Example Company AS</h1><footer>Org nr 123 456 789</footer><a class="post-card" href="/new-project/">Example Company opens a new project</a>'
        article = '<meta property="article:published_time" content="2026-10-01"><article><h1>Example Company opens a new project</h1><p>Example Company AS opened a new project in Oslo.</p></article>'
        pages = {"https://example.no": home, "https://example.no/new-project/": article}
        result = crawl_verified_website("123456789", REGISTRY, FakeClient(pages), max_pages=2)
        self.assertEqual([c["value"]["url"] for c in result.claims if c["field"] == "public.activity_item"], ["https://example.no/new-project/"])

    def test_dated_product_article_is_not_company_news(self):
        document = '<script type="application/ld+json">{"@type":"Article","headline":"Example Company launches widget","mainEntityOfPage":{"@id":"https://example.no/products/widget"},"datePublished":"2026-10-01"}</script><div class="entry-content">Example Company AS sells a widget.</div>'
        fetch = Fetch("https://example.no/products/widget", 200, document, document.encode(), "2026-10-15T00:00:00Z")
        self.assertFalse([c for c in _structured_claims(fetch, "ev-1", "123456789", REGISTRY, "https://example.no") if c["field"] == "public.activity_item"])

    def test_dated_blog_product_guide_is_not_company_news(self):
        url = "https://example.no/blogs/nyheter/granitt-kantstein-i-hagen"
        document = f'<script type="application/ld+json">{{"@type":"Article","headline":"Granitt kantstein: slik bruker du naturstein i hagen","mainEntityOfPage":{{"@id":"{url}"}},"datePublished":"2026-10-01"}}</script><article><h1>Granitt kantstein: slik bruker du naturstein i hagen</h1><p>Hos Example Company AS finner du kantstein.</p></article>'
        fetch = Fetch(url, 200, document, document.encode(), "2026-10-15T00:00:00Z")
        self.assertFalse([c for c in _structured_claims(fetch, "ev-1", "123456789", REGISTRY, "https://example.no", True) if c["field"] == "public.activity_item"])

    def test_homepage_news_cards_prioritize_company_event_over_generic_articles(self):
        home = '<h1>Example Company AS</h1><footer>Org nr 123 456 789</footer><a class="post-card" href="/generic-a/">How to choose a widget</a><a class="post-card" href="/generic-b/">Widget guide for beginners</a><a class="post-card" href="/example-company-partnership/">Example Company signs a partnership</a>'
        article = '<script type="application/ld+json">{"@type":"Article","headline":"Example Company signs a partnership","url":"https://example.no/example-company-partnership/","datePublished":"2026-10-01"}</script><article><h1>Example Company signs a partnership</h1><p>Example Company AS signed a partnership in Oslo.</p></article>'
        client = FakeClient({"https://example.no": home, "https://example.no/example-company-partnership/": article})
        result = crawl_verified_website("123456789", REGISTRY, client, max_pages=2)
        self.assertEqual([c["value"]["url"] for c in result.claims if c["field"] == "public.activity_item"], ["https://example.no/example-company-partnership/"])
        self.assertNotIn("https://example.no/generic-a/", client.calls)

    def test_verified_homepage_careers_link_is_fetched_and_published(self):
        home = '<h1>Example Company AS</h1><a href="/careers">Careers at Example Company</a>'
        careers = '<h1>Careers at Example Company AS</h1><p>Current openings are listed here.</p>'
        result = crawl_verified_website("123456789", REGISTRY, FakeClient({"https://example.no": home, "https://example.no/careers": careers}), max_pages=2)
        self.assertEqual([c["value"] for c in result.claims if c["field"] == "hiring.careers_page"], ["https://example.no/careers"])

    def test_dated_html_news_article_with_company_name_is_published(self):
        home = '<title>Example Company AS</title><h1>Example Company AS</h1><p>Org nr 123 456 789</p><a href="/news">News</a>'
        listing = '<a href="/news/contract">Example Company signs a new contract</a>'
        article = '<meta property="article:published_time" content="2026-10-01"><article><h1>Example Company signs a new contract</h1><p>Example Company has signed a contract today.</p></article>'
        pages = {"https://example.no": home, "https://example.no/news": listing, "https://example.no/news/contract": article}
        result = crawl_verified_website("123456789", REGISTRY, FakeClient(pages))
        self.assertEqual(len([c for c in result.claims if c["field"] == "public.activity_item"]), 1)

    def test_undated_html_news_article_is_withheld(self):
        home = '<title>Example Company AS</title><h1>Example Company AS</h1><p>Org nr 123 456 789</p><a href="/news">News</a>'
        listing = '<a href="/news/contract">Example Company signs a new contract</a>'
        article = '<article><h1>Example Company signs a new contract</h1><p>Example Company has signed a contract today.</p></article>'
        pages = {"https://example.no": home, "https://example.no/news": listing, "https://example.no/news/contract": article}
        result = crawl_verified_website("123456789", REGISTRY, FakeClient(pages))
        self.assertFalse([c for c in result.claims if c["field"] == "public.activity_item"])

    def test_article_update_time_is_not_publication_date(self):
        home = '<title>Example Company AS</title><h1>Example Company AS</h1><p>Org nr 123 456 789</p><a href="/news">News</a>'
        listing = '<a href="/news/contract">Example Company signs a new contract</a>'
        article = '<article><h1>Example Company signs a new contract</h1><time class="updated" datetime="2026-10-01">Updated</time><p>Example Company has signed a contract.</p></article>'
        pages = {"https://example.no": home, "https://example.no/news": listing, "https://example.no/news/contract": article}
        result = crawl_verified_website("123456789", REGISTRY, FakeClient(pages))
        self.assertFalse([c for c in result.claims if c["field"] == "public.activity_item"])

    def test_linked_page_redirect_outside_company_scope_is_ignored(self):
        class RedirectClient(FakeClient):
            def text(self, url):
                fetched = super().text(url)
                if url == "https://example.no/news":
                    return Fetch("https://parent.no/news", 200, '<h1>Parent news</h1><a href="mailto:parent@parent.no">Email</a>', b"parent news", "2026-10-15T00:00:00Z")
                return fetched

        pages = {"https://example.no": '<title>Example Company AS</title><h1>Example Company AS</h1><p>Org nr 123 456 789</p><a href="/news">News</a>'}
        result = crawl_verified_website("123456789", REGISTRY, RedirectClient(pages))
        fields = {claim["field"] for claim in result.claims}
        self.assertIn("website.official", fields)
        self.assertNotIn("public.activity_page", fields)
        self.assertNotIn("contact.email", fields)
        self.assertTrue(all(evidence["source_url"].startswith("https://example.no") for evidence in result.evidence))

    def test_homepage_redirect_to_parent_domain_is_not_verified(self):
        class RedirectClient(FakeClient):
            def text(self, url):
                body = '<title>Example Company AS</title><h1>Example Company AS</h1><p>Org nr 123 456 789</p>'
                return Fetch("https://parent.no/company/example", 200, body, body.encode(), "2026-10-15T00:00:00Z")

        result = crawl_verified_website("123456789", REGISTRY, RedirectClient({}), max_pages=1)
        self.assertFalse(result.claims)
        self.assertEqual(result.errors[0]["message"], "Homepage redirected to a different domain")

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
        self.assertEqual(_candidate_homepages({"navn": "Norsk Eksempel AS"}), ["https://norskeksempel.no", "https://norsk-eksempel.no", "https://norskeksempel.com"])
        self.assertEqual(_candidate_homepages({"navn": "Example AS", "hjemmeside": "example.no"}), ["https://example.no"])

    def test_wrong_first_discovery_candidate_does_not_block_exact_second_site(self):
        registry = {"navn": "Example Company AS"}
        pages = {"https://examplecompany.no": "<title>Other Company AS</title><h1>Other Company AS</h1>",
                 "https://example-company.no": "<title>Example Company AS</title><h1>Example Company AS</h1><p>Org nr 123 456 789</p>"}
        client = FakeClient(pages)
        result = crawl_verified_website("123456789", registry, client, max_pages=3)
        self.assertEqual([c["value"] for c in result.claims if c["field"] == "website.official"], ["https://example-company.no"])
        self.assertLessEqual(len(client.calls), 3)

    def test_large_batch_can_bound_unlisted_domain_discovery(self):
        registry = {"navn": "Example Company AS"}
        client = FakeClient({})
        result = crawl_verified_website("123456789", registry, client, max_pages=4, max_discovery_candidates=1)
        self.assertEqual(client.calls, ["https://examplecompany.no"])
        self.assertFalse(result.claims)

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
