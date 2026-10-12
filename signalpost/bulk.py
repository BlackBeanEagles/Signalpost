import csv
import gzip
import hashlib
from pathlib import Path
from typing import Any


def _first(row: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = row.get(name)
        if value not in (None, ""):
            return value
    return None


def _bool(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.casefold() == "true"


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


def read_bulk_selected(path: Path, wanted: set[str]) -> tuple[dict[str, dict[str, Any]], str]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    opener = gzip.open if path.suffix.lower() == ".gz" else open
    selected: dict[str, dict[str, Any]] = {}
    with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
        for row in csv.DictReader(handle, dialect=dialect):
            org = _first(row, "organisasjonsnummer", "Organisasjonsnummer")
            if org not in wanted:
                continue
            selected[org] = {
                "organisasjonsnummer": org,
                "navn": _first(row, "navn", "Navn"),
                "organisasjonsform": {"kode": _first(row, "organisasjonsform.kode", "Organisasjonsform.kode")},
                "antallAnsatte": _int(_first(row, "antallAnsatte", "Antall ansatte")),
                "konkurs": _bool(_first(row, "konkurs", "Konkurs")),
                "underAvvikling": _bool(_first(row, "underAvvikling", "Under avvikling")),
                "hjemmeside": _first(row, "hjemmeside", "Hjemmeside"),
                "telefon": _first(row, "telefon", "Telefon"),
                "epostadresse": _first(row, "epostadresse", "E-postadresse"),
                "naeringskode1": {"kode": _first(row, "naeringskode1.kode", "Næringskode1.kode"), "beskrivelse": _first(row, "naeringskode1.beskrivelse", "Næringskode1.beskrivelse")},
                "sisteInnsendteAarsregnskap": _first(row, "sisteInnsendteAarsregnskap", "Siste innsendte årsregnskap"),
                "forretningsadresse": {"adresse": [_first(row, "forretningsadresse.adresse", "Forretningsadresse.adresse")], "postnummer": _first(row, "forretningsadresse.postnummer", "Forretningsadresse.postnummer"), "poststed": _first(row, "forretningsadresse.poststed", "Forretningsadresse.poststed"), "kommune": _first(row, "forretningsadresse.kommune", "Forretningsadresse.kommune")},
            }
            if len(selected) == len(wanted):
                break
    return selected, digest

