import unittest

from signalpost.identity import InvalidOrganizationNumber, assert_same_entity, is_valid_orgnr, normalize_orgnr


class IdentityTests(unittest.TestCase):
    def test_valid_orgnr(self):
        self.assertTrue(is_valid_orgnr("923609016"))
        self.assertEqual(normalize_orgnr("923 609 016"), "923609016")

    def test_invalid_orgnr(self):
        self.assertFalse(is_valid_orgnr("923609017"))
        with self.assertRaises(InvalidOrganizationNumber):
            normalize_orgnr("923609017")

    def test_wrong_company_is_rejected(self):
        with self.assertRaises(ValueError):
            assert_same_entity("923609016", {"organisasjonsnummer": "914778271"})


if __name__ == "__main__":
    unittest.main()

