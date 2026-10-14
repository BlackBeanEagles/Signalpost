import json
import re
import statistics
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .agent import build_synthesis, research_company
from .budget import Budget
from .sources import HttpClient, now
from .state import StateStore
from .bulk import read_bulk_selected
from .support import attach_support, fetch_support_awards


def read_inputs(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".json":
        body = json.loads(text)
        rows = body if isinstance(body, list) else body.get("organisation_numbers", body.get("organization_numbers", []))
    elif path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = [line.strip() for line in text.splitlines() if line.strip()]
    values = []
    for row in rows:
        if isinstance(row, dict):
            value = row.get("organisation_number", row.get("organization_number", row.get("orgnr")))
        else:
            value = row
        normalized = "".join(re.findall(r"\d", str(value or "")))
        if len(normalized) != 9:
            raise ValueError(f"Invalid Norwegian organisation number: {value!r}")
        values.append(normalized)
    if not values:
        raise ValueError("Input file contains no organisation numbers")
    if len(values) != len(set(values)):
        raise ValueError("Input file contains duplicate organisation numbers")
    return values


def _atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    temporary = Path(handle.name)
    try:
        with handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def plan_modules(company_count: int, max_requests: int, bulk_identity: bool) -> tuple[set[str], int]:
    if company_count < 1:
        raise ValueError("company count must be positive")
    requests_per_company = max(0, max_requests - 1) // company_count
    remaining = requests_per_company if bulk_identity else max(0, requests_per_company - 1)
    enabled_modules = {"registry"}
    for module in ("financials", "roles"):
        if remaining:
            enabled_modules.add(module); remaining -= 1
    website_pages = min(5, remaining)
    if website_pages:
        enabled_modules.add("website"); remaining -= website_pages
    for module in ("locations", "group"):
        if remaining:
            enabled_modules.add(module); remaining -= 1
    return enabled_modules, website_pages


def run_official_batch(input_path: Path, output_path: Path, report_path: Path, state_path: Path, run_id: str, workers: int = 8, max_requests: int = 17000, bulk_path: Path | None = None) -> dict[str, Any]:
    inputs = read_inputs(input_path)
    if not 1 <= workers <= 32:
        raise ValueError("workers must be between 1 and 32")
    started = now()
    clock = time.perf_counter()
    budget = Budget(max_requests=max_requests, max_cost_usd=10.0)
    bulk_records: dict[str, dict[str, Any]] = {}
    bulk_hash = None
    if bulk_path:
        bulk_records, bulk_hash = read_bulk_selected(bulk_path, set(inputs))
    support_awards, support_report = fetch_support_awards(set(inputs), budget, state_path.parent)
    enabled_modules, website_pages = plan_modules(len(inputs), max_requests, bulk_path is not None)
    indexed: dict[int, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        def enrich(value: str) -> dict[str, Any]:
            company_client = HttpClient(budget)
            row = research_company(value, company_client, budget, None, run_id, bulk_records.get(value, {}) if bulk_path else None, bulk_hash, enabled_modules, website_pages)
            row["operations"]["requests"] = company_client.requests
            return row

        futures = {executor.submit(enrich, value): index for index, value in enumerate(inputs)}
        for future in as_completed(futures):
            index = futures[future]
            try:
                indexed[index] = future.result()
            except Exception as exc:
                indexed[index] = {
                    "organisation_number": inputs[index],
                    "availability": "failed",
                    "run": {"run_id": run_id, "started_at": started, "completed_at": now(), "terminal_status": "completed"},
                    "claims": [], "evidence": [], "source_snapshots": [], "changes": [], "synthesis": {"headline": inputs[index], "supported_fact_count": 0, "changed_fact_count": 0, "unknown_families": [], "explanation": "Company processing failed; no value was inferred."},
                    "errors": [{"code": "unhandled_company_error", "message": type(exc).__name__}],
                    "operations": {"requests": 0, "runtime_ms": 0, "third_party_cost_usd": 0.0},
                }
    rows = [indexed[index] for index in range(len(inputs))]
    for row in rows:
        attach_support(row, support_awards.get(row["organisation_number"], []), support_report)
    store = StateStore(state_path)
    try:
        for row in rows:
            if row["availability"] == "available":
                row["changes"] = store.apply(row["organisation_number"], row["claims"], row["evidence"], row["run"]["completed_at"])
                row["synthesis"] = build_synthesis(row["organisation_number"], row["claims"], row["changes"])
    finally:
        store.close()
    _atomic_jsonl(output_path, rows)
    runtimes = [row["operations"]["runtime_ms"] for row in rows]
    report = {
        "run_id": run_id,
        "started_at": started,
        "completed_at": now(),
        "input_count": len(inputs),
        "output_count": len(rows),
        "unique_output_count": len({row["organisation_number"] for row in rows}),
        "available": sum(row["availability"] == "available" for row in rows),
        "failed": sum(row["availability"] == "failed" for row in rows),
        "total_claims": sum(len(row["claims"]) for row in rows),
        "available_claims": sum(sum(c.get("availability") == "available" for c in row["claims"]) for row in rows),
        "evidence_records": sum(len(row["evidence"]) for row in rows),
        "changes": sum(len(row["changes"]) for row in rows),
        "requests": budget.requests,
        "third_party_cost_usd": budget.declared_cost_usd,
        "wall_runtime_ms": round((time.perf_counter() - clock) * 1000),
        "company_runtime_p50_ms": round(statistics.median(runtimes)) if runtimes else 0,
        "company_runtime_p95_ms": round(sorted(runtimes)[min(len(runtimes) - 1, int(len(runtimes) * 0.95))]) if runtimes else 0,
        "complete": len(rows) == len(inputs),
        "bulk_registry_snapshot": str(bulk_path) if bulk_path else None,
        "enabled_modules": sorted(enabled_modules),
        "website_page_budget_per_company": website_pages,
        "support_registry": support_report,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report

