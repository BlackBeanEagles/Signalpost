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


def build_synthesis(orgnr: str, claims: list[dict[str, Any]], changes: list[dict[str, Any]]) -> dict[str, Any]:
    """Build useful prose only from published claims and retain its evidence boundary."""
    available = [item for item in claims if item.get("availability") == "available"]
    by_field: dict[str, list[dict[str, Any]]] = {}
    for item in available:
        by_field.setdefault(str(item.get("field")), []).append(item)

    def first(field: str, default: Any = None) -> Any:
        rows = by_field.get(field) or []
        return rows[0].get("value") if rows else default

    name = str(first("company.legal_name", orgnr))
    form = first("company.legal_form")
    industry = first("company.industry_primary") or {}
    address = first("company.business_address") or {}
    employees = first("company.employees")
    description = first("website.description")
    parts = [name]
    if form:
        parts.append(f"is registered as {form}")
    if isinstance(industry, dict) and industry.get("beskrivelse"):
        parts.append(f"in {industry['beskrivelse']}")
    municipality = address.get("kommune") if isinstance(address, dict) else None
    if municipality:
        parts.append(f"with a registered address in {municipality}")
    overview = " ".join(parts) + "."
    if employees is not None:
        overview += f" The register reports {employees} employee{'s' if employees != 1 else ''}."
    if description:
        overview += f" Its verified website describes the business as: {str(description).strip()}"

    financial_rows = sorted(
        by_field.get("financial.revenue", []),
        key=lambda item: str(item.get("reporting_period") or ""),
        reverse=True,
    )
    financial_summary = "No annual-account revenue was available in this run."
    if financial_rows:
        latest = financial_rows[0]
        period = latest.get("reporting_period") or "latest reported period"
        result_rows = [row for row in by_field.get("financial.annual_result", []) if row.get("reporting_period") == latest.get("reporting_period")]
        result_text = f" and annual result {result_rows[0]['value']:,.0f} NOK" if result_rows and isinstance(result_rows[0].get("value"), (int, float)) else ""
        revenue = latest.get("value")
        financial_summary = f"For {period}, reported revenue was {revenue:,.0f} NOK{result_text}." if isinstance(revenue, (int, float)) else f"Revenue for {period} was {revenue}."

    roles = by_field.get("people.official_role", [])
    locations = by_field.get("locations.registered_workplace", [])
    jobs = by_field.get("hiring.job_posting", [])
    news = by_field.get("public.activity_item", [])
    activity_pages = by_field.get("public.activity_page", [])
    public_summary = f"The profile contains {len(roles)} registered role record(s), {len(locations)} registered workplace(s), {len(jobs)} company-attributed job posting(s), {len(news)} dated company news item(s), and {len(activity_pages)} company news page(s)."

    unknowns = sorted({str(item.get("field")) for item in claims if item.get("availability") != "available"})
    if changes:
        labels = ", ".join(str(item.get("claim_key") or item.get("field") or "profile fact") for item in changes[:5])
        change_summary = f"This refresh found {len(changes)} supported change(s): {labels}."
    else:
        change_summary = "No supported material change was detected against the stored profile."
    unknown_summary = "No unresolved claim families remain." if not unknowns else "Not found, blocked, or unresolved in this run: " + ", ".join(unknowns) + "."
    evidence_ids = sorted({evidence_id for item in available for evidence_id in (item.get("evidence_ids") or [])})
    return {
        "headline": name,
        "supported_fact_count": len(available),
        "changed_fact_count": len(changes),
        "unknown_families": unknowns,
        "overview": overview,
        "financial_summary": financial_summary,
        "public_footprint_summary": public_summary,
        "change_summary": change_summary,
        "unknown_summary": unknown_summary,
        "evidence_ids": evidence_ids,
        "explanation": " ".join((overview, financial_summary, public_summary, change_summary, unknown_summary)),
    }


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
    summary = build_synthesis(orgnr, claims, changes)
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

