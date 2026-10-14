import unittest

from signalpost.sources import safe_public_url
from signalpost.sources import Fetch
from signalpost.website import PageParser, _candidate_homepages, _structured_claims, _verified


class WebsiteTests(unittest.TestCase):
    def test_private_network_is_rejected(self):
        with self.assertRaises(ValueError):
            safe_public_url("http://127.0.0.1/internal")

    def test_jsonld_adds_dated_activity_job_and_company_contact(self):
        document = '''<script type="application/ld+json">{
          "@graph": [
            {"@type":"Organization","telephone":"+47 22 33 44 55","email":"post@example.no","address":{"@type":"PostalAddress","streetAddress":"Main 1","postalCode":"0101","addressLocality":"Oslo"}},
            {"@type":"NewsArticle","headline":"New contract","url":"/news/contract","datePublished":"2026-10-01"},
            {"@type":"JobPosting","title":"Engineer","url":"/jobs/engineer","datePosted":"2026-10-02"}
          ]
        }</script>'''
        fetch = Fetch("https://example.no/", 200, document, document.encode(), "2026-10-15T00:00:00Z")
        claims = _structured_claims(fetch, "ev-1")
        fields = {claim["field"] for claim in claims}
        self.assertTrue({"contact.phone", "contact.email", "locations.company_reported", "public.activity_item", "hiring.job_posting"} <= fields)

    def test_missing_registry_site_gets_one_deterministic_discovery_candidate(self):
        self.assertEqual(_candidate_homepages({"navn": "Norsk Eksempel AS"}), ["https://norskeksempel.no", "https://norsk-eksempel.no"])
        self.assertEqual(_candidate_homepages({"navn": "Example AS", "hjemmeside": "example.no"}), ["https://example.no"])

    def test_exact_org_number_verifies_identity(self):
        ok, _ = _verified("EQUINOR ASA org.nr. 923 609 016", "923609016", {"navn": "EQUINOR ASA"})
        self.assertTrue(ok)

    def test_parser_collects_description_and_links(self):
        parser = PageParser()
        parser.feed('<meta name="description" content="Example company"><a href="/jobs">Open roles</a>')
        self.assertEqual(parser.meta_description, "Example company")
        self.assertEqual(parser.links, [("/jobs", "Open roles")])


if __name__ == "__main__":
    unittest.main()
