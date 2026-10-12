import json
from pathlib import Path

from .identity import is_valid_orgnr


def validate_jsonl(path: Path, minimum: int = 1000) -> dict:
    errors: list[str] = []
    seen: set[str] = set()
    profiles = 0
    facts = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            try:
                profile = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: invalid JSON: {exc}")
                continue
            profiles += 1
            orgnr = str(profile.get("organization_number", ""))
            if not is_valid_orgnr(orgnr):
                errors.append(f"line {line_number}: invalid organisation number {orgnr!r}")
            if orgnr in seen:
                errors.append(f"line {line_number}: duplicate organisation number {orgnr}")
            seen.add(orgnr)
            if not profile.get("legal_name"):
                errors.append(f"line {line_number}: missing legal name")
            for fact in profile.get("facts", []):
                facts += 1
                evidence = fact.get("evidence", {})
                for key in ("source_name", "source_url", "retrieved_at", "json_path"):
                    if not evidence.get(key):
                        errors.append(f"line {line_number}: fact {fact.get('field')!r} missing evidence.{key}")
                if fact.get("confidence") != 1.0:
                    errors.append(f"line {line_number}: official-source fact has unexpected confidence")
    if profiles < minimum:
        errors.append(f"only {profiles} profiles; minimum is {minimum}")
    return {
        "valid": not errors,
        "profile_count": profiles,
        "unique_organization_numbers": len(seen),
        "fact_count": facts,
        "errors": errors[:100],
    }

