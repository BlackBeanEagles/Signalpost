import hashlib
import json
import urllib.parse
from pathlib import Path
from typing import Any

from .models import ALLOWED_AVAILABILITY


def validate_envelopes(input_path: Path, output_path: Path) -> dict[str, Any]:
    from .competition import read_inputs
    expected = read_inputs(input_path)
    errors: list[str] = []
    rows: list[Any] = []
    for number, line in enumerate(output_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: invalid JSON: {exc}")
    if len(rows) != len(expected):
        errors.append(f"expected {len(expected)} envelopes, got {len(rows)}")
    for index, expected_org in enumerate(expected):
        if index >= len(rows):
            break
        row = rows[index]
        if not isinstance(row, dict):
            errors.append(f"line {index + 1}: envelope must be an object")
            continue
        org = str(row.get("organisation_number", ""))
        if org != expected_org.replace(" ", ""):
            errors.append(f"line {index + 1}: expected {expected_org}, got {org}")
        if row.get("availability") not in ALLOWED_AVAILABILITY:
            errors.append(f"line {index + 1}: invalid availability")
        evidence = row.get("evidence")
        claims = row.get("claims")
        if not isinstance(evidence, list) or not isinstance(claims, list):
            errors.append(f"line {index + 1}: claims and evidence must be arrays")
            continue
        evidence_by_id = {item.get("id"): item for item in evidence if isinstance(item, dict)}
        for claim in claims:
            if not isinstance(claim, dict) or claim.get("availability") not in ALLOWED_AVAILABILITY:
                errors.append(f"line {index + 1}: malformed claim")
                continue
            if claim.get("availability") == "available" and not claim.get("evidence_ids"):
                errors.append(f"line {index + 1}: available claim lacks evidence")
            for evidence_id in claim.get("evidence_ids") or []:
                item = evidence_by_id.get(evidence_id)
                if not item:
                    errors.append(f"line {index + 1}: dangling evidence {evidence_id}")
                    continue
                url = urllib.parse.urlparse(str(item.get("source_url", "")))
                if url.scheme != "https" or url.hostname != "data.brreg.no":
                    errors.append(f"line {index + 1}: non-allowlisted evidence URL")
                if not item.get("content_sha256") or len(item["content_sha256"]) != 64:
                    errors.append(f"line {index + 1}: invalid evidence hash")
        legal_names = [c for c in claims if isinstance(c, dict) and c.get("field") == "company.legal_name" and c.get("availability") == "available"]
        if row.get("availability") == "available" and len(legal_names) != 1:
            errors.append(f"line {index + 1}: available envelope must have exactly one legal name")
    return {
        "valid": not errors,
        "expected_count": len(expected),
        "output_count": len(rows),
        "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
        "errors": errors[:100],
    }

