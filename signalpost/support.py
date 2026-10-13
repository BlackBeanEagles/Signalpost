import csv
import hashlib
import re
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .budget import Budget


URL = "https://stotte.brreg.no/nb/oppslag/stoettetildeling/totalbestand/csv"
MAX_BYTES = 400_000_000


def _norm(value: str) -> str:
    value = value.casefold().replace("ø", "o").replace("æ", "ae").replace("å", "a")
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))).strip()


def _header(headers: list[str], *words: str, exclude: tuple[str, ...] = ()) -> str | None:
    return next((h for h in headers if all(w in _norm(h) for w in words) and not any(w in _norm(h) for w in exclude)), None)


def _date(value: Any) -> date | None:
    raw = " ".join(str(value or "").split())
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            pass
    return None


def _amount(value: Any) -> str | None:
    raw = "".join(str(value or "").split()).replace("\u00a0", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".") if raw.rfind(",") > raw.rfind(".") else raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    raw = re.sub(r"[^0-9.\-]", "", raw)
    try:
        return str(Decimal(raw)) if raw else None
    except InvalidOperation:
        return None


def fetch_support_awards(targets: set[str], budget: Budget, directory: Path, lookback_days: int = 365, max_per_company: int = 5, total_timeout: float = 180.0) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    budget.reserve()
    directory.mkdir(parents=True, exist_ok=True)
    retrieved = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    started = time.perf_counter()
    digest = hashlib.sha256(); size = 0
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", delete=False, dir=directory, prefix="support-", suffix=".csv") as handle:
            temporary_path = Path(handle.name)
            request = urllib.request.Request(URL, headers={"User-Agent": "SignalPost/2.0"})
            with urllib.request.urlopen(request, timeout=45) as response:
                while True:
                    if time.perf_counter() - started > total_timeout:
                        raise TimeoutError("support registry exceeded total transfer deadline")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("support registry snapshot exceeds safety limit")
                    digest.update(chunk); handle.write(chunk); handle.flush()
        prefix = temporary_path.read_bytes()[:4]
        encoding = "utf-16" if prefix.startswith((b"\xff\xfe", b"\xfe\xff")) or prefix[1:2] == b"\x00" else "utf-8-sig"
        with temporary_path.open("r", encoding=encoding, newline="") as handle:
            sample = handle.read(65536); handle.seek(0)
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            reader = csv.DictReader(handle, dialect=dialect)
            headers = [h for h in (reader.fieldnames or []) if h]
            recipient = _header(headers, "organisasjonsnummer", "mottaker", exclude=("giver", "spesifisert"))
            awarded = _header(headers, "tildelingsdato")
            amount = _header(headers, "tildelt", "belop", exclude=("valuta",))
            currency = _header(headers, "tildelt", "belop", "valuta")
            measure = _header(headers, "stottetiltaksnummer")
            giver = _header(headers, "navn", "stottegiver")
            recipient_name = _header(headers, "navn", "stottemottaker", exclude=("spesifisert",))
            if not recipient or not awarded or not amount:
                raise ValueError("support registry columns changed")
            cutoff = datetime.now(timezone.utc).date() - timedelta(days=lookback_days)
            found: dict[str, list[dict[str, Any]]] = {}
            for row_number, row in enumerate(reader, 2):
                org = re.sub(r"\D", "", str(row.get(recipient) or ""))
                if org not in targets:
                    continue
                event_date = _date(row.get(awarded))
                if not event_date or event_date < cutoff:
                    continue
                row_body = "|".join(str(row.get(h) or "") for h in headers)
                row_hash = hashlib.sha256(row_body.encode("utf-8")).hexdigest()
                value = {"awarded_at": event_date.isoformat(), "amount": _amount(row.get(amount)), "currency": str(row.get(currency) or "").strip() or None, "support_measure_number": str(row.get(measure) or "").strip() or None, "recipient_name": str(row.get(recipient_name) or "").strip() or None, "granting_authority": str(row.get(giver) or "").strip() or None}
                found.setdefault(org, []).append({"row": row_number, "hash": row_hash, "value": value})
        for rows in found.values():
            rows.sort(key=lambda item: item["value"]["awarded_at"], reverse=True); del rows[max_per_company:]
        return found, {"status": "available", "source_url": URL, "retrieved_at": retrieved, "snapshot_sha256": digest.hexdigest(), "bytes": size, "companies": len(found), "claims": sum(map(len, found.values())), "runtime_ms": round((time.perf_counter() - started) * 1000)}
    except Exception as exc:
        return {}, {"status": "failed", "source_url": URL, "retrieved_at": retrieved, "snapshot_sha256": digest.hexdigest(), "bytes": size, "error": f"{type(exc).__name__}: {exc}", "runtime_ms": round((time.perf_counter() - started) * 1000)}
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def attach_support(row: dict[str, Any], awards: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    for award in awards:
        evidence_id = "ev-support-" + award["hash"][:16]
        row["evidence"].append({"id": evidence_id, "source_url": URL, "source_class": "official_support_registry", "retrieved_at": metadata["retrieved_at"], "content_sha256": award["hash"], "source_snapshot_sha256": metadata["snapshot_sha256"], "claim_span": f"primary recipient organisation number {row['organisation_number']}; row {award['row']}; award {award['value']}", "extraction_method": "support_primary_recipient_exact_org_v1"})
        row["claims"].append({"key": f"official.support_award:{award['hash'][:16]}", "field": "official.support_award", "value": award["value"], "availability": "available", "confidence": 1.0, "reporting_period": award["value"]["awarded_at"], "evidence_ids": [evidence_id]})

