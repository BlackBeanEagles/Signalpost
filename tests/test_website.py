import unittest

from signalpost.sources import safe_public_url
from signalpost.website import PageParser, _verified


class WebsiteTests(unittest.TestCase):
    def test_private_network_is_rejected(self):
        with self.assertRaises(ValueError):
            safe_public_url("http://127.0.0.1/internal")

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
