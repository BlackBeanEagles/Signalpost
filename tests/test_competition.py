import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from signalpost.competition import plan_modules, read_inputs, run_official_batch
from signalpost.evaluator import validate_envelopes
from signalpost.bulk import read_bulk_selected
from signalpost.website import WebsiteResult


class CompetitionTests(unittest.TestCase):
    def test_registry_listed_site_recovers_after_dns_failure(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            root = Path(directory)
            input_path = root / "input.jsonl"
            input_path.write_text('{"organisation_number":"923609016"}\n', encoding="utf-8")
            registry_url = "https://data.brreg.no/enhetsregisteret/api/enheter/923609016"
            row = {
                "organisation_number": "923609016", "availability": "available",
                "run": {"run_id": "retry-site", "completed_at": "2026-11-03T00:00:00Z"},
                "claims": [
                    {"key": "company.legal_name", "field": "company.legal_name", "value": "Example Company AS", "availability": "available", "evidence_ids": ["registry"]},
                    {"key": "company.website_candidate", "field": "company.website_candidate", "value": "https://example.no", "availability": "available", "evidence_ids": ["registry"]},
                    {"key": "website.official", "field": "website.official", "value": None, "availability": "ambiguous", "evidence_ids": []},
                ],
                "evidence": [{"id": "registry", "source_url": registry_url, "content_sha256": "a" * 64, "retrieved_at": "2026-11-03T00:00:00Z"}],
                "source_snapshots": [{"source_url": registry_url, "status": 200, "content_sha256": "a" * 64, "retrieved_at": "2026-11-03T00:00:00Z"}],
                "changes": [], "synthesis": {}, "errors": [{"module": "website", "message": "gaierror"}],
                "operations": {"requests": 1, "runtime_ms": 1, "third_party_cost_usd": 0.0},
            }
            site = WebsiteResult(
                claims=[{"key": "website.official", "field": "website.official", "value": "https://example.no", "availability": "available", "evidence_ids": ["site"]}],
                evidence=[{"id": "site", "source_url": "https://example.no", "content_sha256": "b" * 64, "retrieved_at": "2026-11-03T00:00:00Z"}],
                snapshots=[{"source_url": "https://example.no", "status": 200, "content_sha256": "b" * 64, "retrieved_at": "2026-11-03T00:00:00Z"}],
            )
            support = {"status": "partial", "retrieved_at": "2026-11-03T00:00:00Z", "snapshot_sha256": "c" * 64, "complete_snapshot": False}
            with patch("signalpost.competition.research_company", return_value=row), patch("signalpost.competition.crawl_verified_website", return_value=site) as retry, patch("signalpost.competition.fetch_support_awards", return_value=({}, support)):
                report = run_official_batch(input_path, root / "output.jsonl", root / "report.json", root / "state.sqlite3", "retry-site", workers=1, max_requests=100)
            output = json.loads((root / "output.jsonl").read_text(encoding="utf-8"))
            self.assertEqual(retry.call_count, 1)
            self.assertEqual(retry.call_args.kwargs["max_pages"], report["website_page_budget_per_company"] - 2)
            self.assertEqual(report["failed"], 0)
            self.assertEqual([claim["value"] for claim in output["claims"] if claim["field"] == "website.official"], ["https://example.no"])
            self.assertFalse([error for error in output["errors"] if error.get("module") == "website"])

    def test_transient_registry_failure_gets_one_retry(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            root = Path(directory)
            input_path = root / "input.jsonl"
            input_path.write_text('{"organisation_number":"923609016"}\n', encoding="utf-8")
            base = {"organisation_number": "923609016", "run": {"run_id": "retry", "completed_at": "2026-11-03T00:00:00Z"}, "claims": [], "evidence": [], "source_snapshots": [], "changes": [], "synthesis": {}, "operations": {"requests": 0, "runtime_ms": 1, "third_party_cost_usd": 0.0}}
            failed = {**base, "availability": "failed", "errors": [{"module": "registry", "message": "URLError"}]}
            recovered = {**base, "availability": "available", "errors": [], "claims": [{"key": "company.legal_name", "field": "company.legal_name", "value": "Example AS", "availability": "available", "evidence_ids": ["registry"]}], "evidence": [{"id": "registry", "source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/923609016", "content_sha256": "a" * 64, "retrieved_at": "2026-11-03T00:00:00Z"}], "source_snapshots": [{"source_url": "https://data.brreg.no/enhetsregisteret/api/enheter/923609016", "content_sha256": "a" * 64, "retrieved_at": "2026-11-03T00:00:00Z", "status": 200}]}
            support = {"status": "partial", "retrieved_at": "2026-11-03T00:00:00Z", "snapshot_sha256": "b" * 64, "complete_snapshot": False}
            with patch("signalpost.competition.research_company", side_effect=[failed, recovered]) as research, patch("signalpost.competition.fetch_support_awards", return_value=({}, support)):
                report = run_official_batch(input_path, root / "output.jsonl", root / "report.json", root / "state.sqlite3", "retry", workers=1, max_requests=100)
            self.assertEqual(research.call_count, 2)
            self.assertEqual((report["output_count"], report["available"], report["failed"]), (1, 1, 0))

    def test_reads_builderr_jsonl(self):
        path = Path("tests/fixtures/smoke-organisations.jsonl")
        self.assertEqual(read_inputs(path), ["923609016", "914778271"])

    def test_duplicate_inputs_fail(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            path = Path(directory) / "inputs.jsonl"
            path.write_text('{"organisation_number":"923609016"}\n{"organisation_number":"923609016"}\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_inputs(path)

    def test_normalizes_formatted_organisation_number(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            path = Path(directory) / "inputs.jsonl"
            path.write_text('{"organisation_number":"923 609 016"}\n', encoding="utf-8")
            self.assertEqual(read_inputs(path), ["923609016"])

    def test_rejects_invalid_organisation_number(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd() / "tests") as directory:
            path = Path(directory) / "inputs.txt"
            path.write_text("123\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_inputs(path)

    def test_reads_frozen_bulk_identity(self):
        records, digest = read_bulk_selected(Path("tests/fixtures/brreg-sample.csv"), {"923609016"})
        self.assertEqual(records["923609016"]["navn"], "EQUINOR ASA")
        self.assertEqual(records["923609016"]["organisasjonsform"]["kode"], "ASA")
        self.assertEqual(len(digest), 64)

    def test_current_official_scale_keeps_high_value_modules(self):
        modules, pages = plan_modules(1500, 17000, True)
        self.assertEqual(modules, {"registry", "financials", "roles", "website", "locations", "group"})
        self.assertEqual(pages, 4)


if __name__ == "__main__":
    unittest.main()

