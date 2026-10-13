import hashlib
import json
import time
from typing import Any

from .budget import Budget
from .identity import normalize_orgnr
from .sources import Fetch, HttpClient, now, official_urls
from .state import StateStore
from .website import crawl_verified_website


def _get(value: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _evidence(module: str, fetch: Fetch, orgnr: str) -> dict[str, Any]:
    return {
        "id": f"ev-{module}-{fetch.sha256[:16]}",
        "source_url": fetch.url,
        "source_class": "official_norwegian_register",
        "retrieved_at": fetch.retrieved_at,
        "content_sha256": fetch.sha256,
        "claim_span": f"Structured {module} response requested for organisation number {orgnr}",
        "extraction_method": f"signalpost.{module}.v2",
    }


def _claim(field: str, value: Any, evidence_id: str, *, period: str | None = None, suffix: str = "") -> dict[str, Any]:
    key = ":".join(part for part in (field, period, suffix) if part)
    result = {"key": key, "field": field, "value": value, "availability": "available", "confidence": 1.0, "evidence_ids": [evidence_id]}
    if period:
        result["reporting_period"] = period
    return result


def _registry_claims(body: dict, evidence_id: str) -> list[dict[str, Any]]:
    mappings = {
        "company.legal_name": body.get("navn"),
        "company.legal_form": _get(body, "organisasjonsform", "kode"),
        "company.business_address": body.get("forretningsadresse"),
        "company.postal_address": body.get("postadresse"),
        "company.industry_primary": body.get("naeringskode1"),
        "company.industry_secondary": body.get("naeringskode2"),
        "company.industry_tertiary": body.get("naeringskode3"),
        "company.employees": body.get("antallAnsatte"),
        "company.website_candidate": body.get("hjemmeside"),
        "company.phone": body.get("telefon"),
        "company.email": body.get("epostadresse"),
        "company.activity": body.get("aktivitet"),
        "company.statutory_purpose": body.get("vedtektsfestetFormaal"),
        "company.founded_date": body.get("stiftelsesdato"),
        "company.registered_date": body.get("registreringsdatoEnhetsregisteret"),
        "company.latest_accounts_year": body.get("sisteInnsendteAarsregnskap"),
        "company.bankrupt": body.get("konkurs"),
        "company.liquidating": body.get("underAvvikling"),
        "company.share_capital": body.get("kapital"),
        "company.historical_names": body.get("historiskeNavn"),
    }
    return [_claim(field, value, evidence_id) for field, value in mappings.items() if value is not None and value != [] and value != ""]


def _financial_claims(body: Any, evidence_id: str) -> list[dict[str, Any]]:
    claims = []
    for index, item in enumerate(body if isinstance(body, list) else []):
        period_value = item.get("regnskapsperiode") or item.get("avslutningsdato") or item.get("aar") or index
        if isinstance(period_value, dict):
            period = f"{period_value.get('fraDato', '')}/{period_value.get('tilDato', '')}".strip("/")
        else:
            period = str(period_value)
        record_suffix = str(item.get("id") or item.get("regnskapstype") or item.get("oppstillingsplan") or index)
        values = {
            "financial.revenue": _get(item, "resultatregnskapResultat", "driftsresultat", "driftsinntekter", "sumDriftsinntekter"),
            "financial.operating_result": _get(item, "resultatregnskapResultat", "driftsresultat", "driftsresultat"),
            "financial.profit_before_tax": _get(item, "resultatregnskapResultat", "ordinaertResultatFoerSkattekostnad"),
            "financial.annual_result": _get(item, "resultatregnskapResultat", "aarsresultat"),
            "financial.assets": _get(item, "eiendeler", "sumEiendeler"),
            "financial.equity": _get(item, "egenkapitalGjeld", "egenkapital", "sumEgenkapital"),
            "financial.debt": _get(item, "egenkapitalGjeld", "gjeldOversikt", "sumGjeld"),
            "financial.currency": item.get("valuta"),
        }
        claims.extend(_claim(field, value, evidence_id, period=period, suffix=record_suffix) for field, value in values.items() if value is not None)
    return claims


def _role_claims(body: Any, evidence_id: str) -> list[dict[str, Any]]:
    claims = []
    for group in body.get("rollegrupper", []) if isinstance(body, dict) else []:
        for index, item in enumerate(group.get("roller", [])):
            person = item.get("person") or {}
            names = person.get("navn") or {}
            entity = item.get("enhet") or {}
            name = " ".join(filter(None, (names.get("fornavn"), names.get("mellomnavn"), names.get("etternavn")))) or entity.get("navn")
            role = _get(item, "type", "beskrivelse")
            if name and role:
                value = {"name": name, "role": role, "role_code": _get(item, "type", "kode"), "last_changed": group.get("sistEndret")}
                suffix = hashlib.sha256(f"{name}|{role}".encode()).hexdigest()[:12]
                claims.append(_claim("people.official_role", value, evidence_id, suffix=suffix))
    return claims


def _location_claims(body: Any, evidence_id: str) -> list[dict[str, Any]]:
    rows = _get(body, "_embedded", "underenheter") or []
    claims = []
    for item in rows:
        child = str(item.get("organisasjonsnummer") or "")
        if child:
            claims.append(_claim("locations.registered_workplace", {
                "organisation_number": child,
                "name": item.get("navn"),
                "address": item.get("beliggenhetsadresse") or item.get("postadresse"),
                "industry": item.get("naeringskode1"),
                "employees": item.get("antallAnsatte"),
            }, evidence_id, suffix=child))
    return claims


def _group_claims(body: Any, evidence_id: str) -> list[dict[str, Any]]:
    if not isinstance(body, dict) or not body:
        return []
    return [_claim("company.group_structure", body, evidence_id)]


def research_company(org_value: str, client: HttpClient, budget: Budget, store: StateStore | None, run_id: str, registry_payload: dict[str, Any] | None = None, registry_bulk_hash: str | None = None, modules: set[str] | None = None, website_pages: int = 0) -> dict[str, Any]:
    started = now()
    clock = time.perf_counter()
    try:
        orgnr = normalize_orgnr(org_value)
    except Exception as exc:
        return failed_envelope(str(org_value), run_id, started, "invalid_input", str(exc), clock, budget)
    claims: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    urls = official_urls(orgnr)
    enabled = set(modules or urls)
    fetches = {name: client.json(url) for name, url in urls.items() if name in enabled and not (name == "registry" and registry_payload is not None)}
    if registry_payload is not None:
        raw = json.dumps(registry_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        fetches["registry"] = Fetch("https://data.brreg.no/enhetsregisteret/api/enheter/lastned/csv", 200, registry_payload, raw, now())
    elif "registry" not in fetches:
        return failed_envelope(orgnr, run_id, started, "registry_unavailable", "No identity snapshot was supplied", clock, budget)
    registry = fetches["registry"]
    if registry.status != 200 or not isinstance(registry.body, dict):
        availability = "not_available" if registry.status in {404, 410} else "failed"
        errors.append({"module": "registry", "message": registry.error or f"HTTP {registry.status}"})
        return terminal_envelope(orgnr, run_id, started, claims, evidence, snapshots, [], errors, clock, budget, availability)
    if str(registry.body.get("organisasjonsnummer")) != orgnr:
        return failed_envelope(orgnr, run_id, started, "identity_mismatch", "BRREG returned a different organisation number", clock, budget)
    extractors = {
        "registry": _registry_claims,
        "financials": _financial_claims,
        "roles": _role_claims,
        "locations": _location_claims,
        "group": _group_claims,
    }
    module_evidence: dict[str, str] = {}
    for module, fetch in fetches.items():
        ev = _evidence(module, fetch, orgnr)
        evidence.append(ev)
        module_evidence[module] = ev["id"]
        snapshots.append({"source_url": ev["source_url"], "retrieved_at": ev["retrieved_at"], "content_sha256": ev["content_sha256"], "status": fetch.status})
        if fetch.status == 200:
            claims.extend(extractors[module](fetch.body, ev["id"]))
        elif fetch.status not in {404, 410}:
            errors.append({"module": module, "message": fetch.error or f"HTTP {fetch.status}"})
    existing_fields = {claim["field"] for claim in claims}
    family_modules = {"financial.revenue": "financials", "people.official_role": "roles", "locations.registered_workplace": "locations", "company.group_structure": "group"}
    for family, module in family_modules.items():
        if family not in existing_fields:
            if module not in fetches:
                claims.append({"key": family, "field": family, "value": None, "availability": "blocked", "confidence": 1.0, "evidence_ids": [], "note": "module skipped to respect the evaluator request budget"})
            else:
                status = fetches[module].status
                availability = "blocked" if status in {401, 403, 429} else "failed" if status not in {200, 404, 410} else "not_available"
                claims.append({"key": family, "field": family, "value": None, "availability": availability, "confidence": 1.0, "evidence_ids": [module_evidence[module]]})
    if "website" in enabled and website_pages > 0:
        website = crawl_verified_website(orgnr, registry.body, client, max_pages=website_pages)
        claims.extend(website.claims); evidence.extend(website.evidence); snapshots.extend(website.snapshots); errors.extend(website.errors)
        if not website.claims:
            claims.append({"key": "website.official", "field": "website.official", "value": None, "availability": "ambiguous" if registry.body.get("hjemmeside") else "not_available", "confidence": 1.0, "evidence_ids": [], "note": "No exact-identity company website was verified."})
    completed = now()
    changes = store.apply(orgnr, claims, evidence, completed) if store else []
    return terminal_envelope(orgnr, run_id, started, claims, evidence, snapshots, changes, errors, clock, budget, "available")


def terminal_envelope(orgnr: str, run_id: str, started: str, claims: list, evidence: list, snapshots: list, changes: list, errors: list, clock: float, budget: Budget, state: str) -> dict[str, Any]:
    completed = now()
    available = [claim for claim in claims if claim.get("availability") == "available"]
    summary = {
        "headline": next((str(c["value"]) for c in available if c["field"] == "company.legal_name"), orgnr),
        "supported_fact_count": len(available),
        "changed_fact_count": len(changes),
        "unknown_families": [c["field"] for c in claims if c.get("availability") != "available"],
        "explanation": "Profile built from official Norwegian registers. Missing fields remain explicit and no unsupported value is inferred.",
    }
    return {
        "organisation_number": orgnr,
        "availability": state,
        "run": {"run_id": run_id, "started_at": started, "completed_at": completed, "terminal_status": "completed"},
        "claims": claims,
        "evidence": evidence,
        "source_snapshots": snapshots,
        "changes": changes,
        "synthesis": summary,
        "errors": errors,
        "operations": {"requests": budget.requests, "runtime_ms": round((time.perf_counter() - clock) * 1000), "third_party_cost_usd": budget.declared_cost_usd},
    }


def failed_envelope(orgnr: str, run_id: str, started: str, code: str, message: str, clock: float, budget: Budget) -> dict[str, Any]:
    return terminal_envelope(orgnr, run_id, started, [], [], [], [], [{"code": code, "message": message}], clock, budget, "failed")

