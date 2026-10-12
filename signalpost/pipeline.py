from datetime import datetime, timezone
from typing import Any, Iterable

from .brreg import BrregClient
from .identity import assert_same_entity, normalize_orgnr
from .models import CompanyProfile, Evidence, Fact


SOURCE_NAME = "Brønnøysundregistrene – Enhetsregisteret"


FIELD_SPECS: tuple[tuple[str, str, str | None], ...] = (
    ("legal_name", "navn", None),
    ("organization_form", "organisasjonsform", None),
    ("business_address", "forretningsadresse", None),
    ("postal_address", "postadresse", None),
    ("website", "hjemmeside", None),
    ("phone", "telefon", None),
    ("email", "epostadresse", None),
    ("activity", "aktivitet", None),
    ("statutory_purpose", "vedtektsfestetFormaal", "vedtektsdato"),
    ("industry_primary", "naeringskode1", None),
    ("industry_secondary", "naeringskode2", None),
    ("industry_tertiary", "naeringskode3", None),
    ("institutional_sector", "institusjonellSektorkode", None),
    ("employees", "antallAnsatte", "registreringsdatoAntallAnsatteEnhetsregisteret"),
    ("share_capital", "kapital", "kapital.innfortDato"),
    ("founded_date", "stiftelsesdato", None),
    ("registered_entity_date", "registreringsdatoEnhetsregisteret", None),
    ("registered_business_date", "registreringsdatoForetaksregisteret", None),
    ("latest_annual_accounts_year", "sisteInnsendteAarsregnskap", None),
    ("historical_names", "historiskeNavn", None),
    ("in_corporate_group", "erIKonsern", None),
    ("bankrupt", "konkurs", None),
    ("in_liquidation", "underAvvikling", None),
    ("forced_liquidation_or_dissolution", "underTvangsavviklingEllerTvangsopplosning", None),
    ("registered_business_register", "registrertIForetaksregisteret", None),
    ("registered_vat", "registrertIMvaregisteret", None),
    ("registered_foundation", "registrertIStiftelsesregisteret", None),
    ("registered_voluntary", "registrertIFrivillighetsregisteret", None),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def get_path(payload: dict, path: str | None) -> Any:
    if not path:
        return None
    value: Any = payload
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def has_value(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def facts_from_entity(payload: dict, source_url: str, retrieved_at: str) -> list[Fact]:
    facts: list[Fact] = []
    for field, source_key, updated_path in FIELD_SPECS:
        value = payload.get(source_key)
        if not has_value(value):
            continue
        updated_at = get_path(payload, updated_path)
        evidence = Evidence(
            source_name=SOURCE_NAME,
            source_url=source_url,
            retrieved_at=retrieved_at,
            source_updated_at=str(updated_at) if updated_at is not None else None,
            json_path=f"$.{source_key}",
        )
        facts.append(Fact(
            field=field,
            value=value,
            evidence=evidence,
            confidence=1.0,
            explanation=f"Reported by the official Norwegian entity register for organisation number {payload['organisasjonsnummer']}.",
        ))
    return facts


def build_profile(client: BrregClient, orgnr: str) -> CompanyProfile:
    canonical = normalize_orgnr(orgnr)
    payload, source_url = client.entity(canonical)
    assert_same_entity(canonical, payload)
    legal_name = payload.get("navn")
    if not legal_name:
        raise ValueError("Canonical BRREG record has no legal name; refusing to publish")
    retrieved_at = utc_now()
    facts = facts_from_entity(payload, source_url, retrieved_at)
    return CompanyProfile(canonical, str(legal_name), retrieved_at, facts)


def profiles_from_page(client: BrregClient, page: int, size: int = 100) -> Iterable[CompanyProfile]:
    payload = client.entity_page(page, size)
    entities = payload.get("_embedded", {}).get("enheter", [])
    retrieved_at = utc_now()
    for entity in entities:
        orgnr = normalize_orgnr(str(entity.get("organisasjonsnummer", "")))
        assert_same_entity(orgnr, entity)
        legal_name = entity.get("navn")
        if not legal_name:
            continue
        url = f"https://data.brreg.no/enhetsregisteret/api/enheter/{orgnr}"
        yield CompanyProfile(orgnr, str(legal_name), retrieved_at, facts_from_entity(entity, url, retrieved_at))

