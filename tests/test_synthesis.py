import unittest

from signalpost.agent import build_synthesis


class SynthesisTests(unittest.TestCase):
    def test_summary_explains_business_financials_changes_and_unknowns(self):
        claims = [
            {"field": "company.legal_name", "value": "EXAMPLE AS", "availability": "available", "evidence_ids": ["registry"]},
            {"field": "company.legal_form", "value": "AS", "availability": "available", "evidence_ids": ["registry"]},
            {"field": "company.industry_primary", "value": {"beskrivelse": "Software"}, "availability": "available", "evidence_ids": ["registry"]},
            {"field": "company.business_address", "value": {"kommune": "OSLO"}, "availability": "available", "evidence_ids": ["registry"]},
            {"field": "financial.revenue", "value": 1000000, "reporting_period": "2025", "availability": "available", "evidence_ids": ["accounts"]},
            {"field": "website.official", "value": None, "availability": "not_available", "evidence_ids": []},
        ]
        result = build_synthesis("123456789", claims, [{"claim_key": "financial.revenue"}])
        self.assertIn("Software", result["overview"])
        self.assertIn("1,000,000 NOK", result["financial_summary"])
        self.assertIn("financial.revenue", result["change_summary"])
        self.assertIn("website.official", result["unknown_summary"])
        self.assertEqual(result["evidence_ids"], ["accounts", "registry"])


if __name__ == "__main__":
    unittest.main()
