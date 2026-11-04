"""Export a compact, source-linked sample for the JBox bonus site."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "reports" / "smoke-300-v25-envelopes.jsonl"
OUTPUT = ROOT / "jbox" / "companies.json"
FIELDS = {
    "company.legal_name", "company.legal_form", "company.industry_primary",
    "company.business_address", "company.employees", "company.phone",
    "company.email", "company.activity", "company.founded_date",
    "financial.revenue", "financial.annual_result", "financial.assets",
    "website.official", "website.description", "public.social_profile",
    "public.activity_item", "hiring.careers_page", "official.support_award",
}
FEATURES = {"website.official", "public.social_profile", "public.activity_item", "hiring.careers_page"}


def export() -> None:
    rows = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines() if line]
    scored = []
    for row in rows:
        claims = [claim for claim in row["claims"] if claim.get("availability") == "available" and claim["field"] in FIELDS]
        fields = {claim["field"] for claim in claims}
        score = 100 * len(fields & FEATURES) + len(claims)
        scored.append((score, row, claims))
    selected = sorted(scored, key=lambda item: (-item[0], item[1]["organisation_number"]))[:120]
    output = []
    for _, row, claims in selected:
        evidence = {item["id"]: item for item in row["evidence"]}
        facts = []
        for claim in claims:
            sources = [
                {"url": evidence[eid]["source_url"], "retrieved_at": evidence[eid]["retrieved_at"],
                 "source_class": evidence[eid]["source_class"]}
                for eid in claim.get("evidence_ids", []) if eid in evidence
            ]
            if sources:
                facts.append({"field": claim["field"], "value": claim["value"],
                              "period": claim.get("reporting_period"), "sources": sources})
        name = next((fact["value"] for fact in facts if fact["field"] == "company.legal_name"), row["organisation_number"])
        output.append({"orgnr": row["organisation_number"], "name": name,
                       "overview": row["synthesis"].get("overview", ""), "facts": facts})
    OUTPUT.write_text(json.dumps({"sample": True, "source_run": "smoke-300-v25", "companies": output}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {len(output)} source-linked companies to {OUTPUT}")


if __name__ == "__main__":
    export()
