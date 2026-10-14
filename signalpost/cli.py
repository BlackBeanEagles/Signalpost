import argparse
import json
import sys
import tempfile
from pathlib import Path

from . import __version__
from .brreg import BrregClient, SourceError
from .budget import Budget, BudgetExceeded
from .identity import InvalidOrganizationNumber
from .pipeline import build_profile, profiles_from_page
from .storage import atomic_write_json, write_jsonl
from .validate import validate_jsonl
from .competition import run_official_batch
from .evaluator import validate_envelopes
from .product import build_html


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="signalpost", description="Evidence-first Norwegian company research")
    root.add_argument("--version", action="version", version=__version__)
    sub = root.add_subparsers(dest="command", required=True)

    one = sub.add_parser("profile", help="Build one company profile")
    one.add_argument("organization_number")
    one.add_argument("--output", type=Path)
    one.add_argument("--format", choices=("json", "summary"), default="json")

    batch = sub.add_parser("batch", help="Generate profiles from deterministic BRREG pages")
    batch.add_argument("--count", type=int, default=1000)
    batch.add_argument("--start-page", type=int, default=0)
    batch.add_argument("--page-size", type=int, default=100, choices=range(1, 101), metavar="1..100")
    batch.add_argument("--output", type=Path, default=Path("data/profiles.jsonl"))

    validate = sub.add_parser("validate", help="Audit a generated JSONL dataset")
    validate.add_argument("path", type=Path, nargs="?", default=Path("data/profiles.jsonl"))
    validate.add_argument("--minimum", type=int, default=1000)

    run = sub.add_parser("run", help="Run the Builderr-supplied organisation batch")
    run.add_argument("--organisations", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--report", type=Path, required=True)
    run.add_argument("--state", type=Path, default=Path("state/signalpost.sqlite3"))
    run.add_argument("--run-id", required=True)
    run.add_argument("--workers", type=int, default=8)
    run.add_argument("--max-requests", type=int, default=17000, help="Shared request ceiling; sized for the current 1,500-company official batch")
    run.add_argument("--bulk", type=Path, help="Builderr-supplied frozen BRREG CSV or CSV.GZ identity snapshot")

    audit = sub.add_parser("audit", help="Validate terminal envelopes against an input batch")
    audit.add_argument("--organisations", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)

    smoke = sub.add_parser("smoke-input", help="Create a local smoke batch from the checked-in profile sample")
    smoke.add_argument("--profiles", type=Path, default=Path("data/profiles.jsonl"))
    smoke.add_argument("--count", type=int, default=100)
    smoke.add_argument("--output", type=Path, default=Path("data/smoke-organisations.jsonl"))

    product = sub.add_parser("product", help="Build a responsive verification interface from envelopes")
    product.add_argument("--envelopes", type=Path, required=True)
    product.add_argument("--output", type=Path, default=Path("reports/signalpost.html"))

    return root


def render_summary(profile: dict) -> str:
    lines = [f"{profile['legal_name']} ({profile['organization_number']})", f"Retrieved: {profile['retrieved_at']}"]
    for fact in profile["facts"]:
        value = json.dumps(fact["value"], ensure_ascii=False)
        lines.append(f"- {fact['field']}: {value} [{fact['evidence']['source_url']}]")
    return "\n".join(lines)


def run_batch(args: argparse.Namespace, client: BrregClient, budget: Budget) -> int:
    if args.count < 1:
        raise ValueError("--count must be at least 1")
    profiles = []
    page = args.start_page
    while len(profiles) < args.count:
        batch = list(profiles_from_page(client, page, args.page_size))
        if not batch:
            raise RuntimeError(f"No entities returned on page {page}")
        profiles.extend(batch)
        page += 1
    count, digest = write_jsonl(args.output, profiles[: args.count])
    manifest = {
        "profile_count": count,
        "sha256": digest,
        "output": str(args.output),
        "budget": budget.to_dict(),
        "source": "https://data.brreg.no/enhetsregisteret/api/enheter",
    }
    atomic_write_json(args.output.with_suffix(args.output.suffix + ".manifest.json"), manifest)
    print(json.dumps(manifest, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    budget = Budget()
    client = BrregClient(budget)
    try:
        if args.command == "profile":
            profile = build_profile(client, args.organization_number).to_dict()
            if args.output:
                atomic_write_json(args.output, profile)
            print(render_summary(profile) if args.format == "summary" else json.dumps(profile, ensure_ascii=False, indent=2))
            return 0
        if args.command == "batch":
            return run_batch(args, client, budget)
        if args.command == "validate":
            report = validate_jsonl(args.path, args.minimum)
            print(json.dumps(report, indent=2))
            return 0 if report["valid"] else 2
        if args.command == "run":
            report = run_official_batch(args.organisations, args.output, args.report, args.state, args.run_id, args.workers, args.max_requests, args.bulk)
            print(json.dumps(report, indent=2))
            return 0 if report["complete"] else 2
        if args.command == "audit":
            report = validate_envelopes(args.organisations, args.output)
            print(json.dumps(report, indent=2))
            return 0 if report["valid"] else 2
        if args.command == "smoke-input":
            if not 1 <= args.count <= 1000:
                raise ValueError("--count must be between 1 and 1000")
            orgs = []
            for line in args.profiles.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    orgs.append(json.loads(line)["organization_number"])
                if len(orgs) == args.count:
                    break
            if len(orgs) != args.count:
                raise ValueError("profile sample does not contain the requested number of companies")
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=args.output.parent, prefix=args.output.name + ".", suffix=".tmp") as handle:
                temporary = Path(handle.name)
                for org in orgs:
                    handle.write(json.dumps({"organisation_number": org}, separators=(",", ":")) + "\n")
            temporary.replace(args.output)
            print(json.dumps({"count": len(orgs), "output": str(args.output)}, indent=2))
            return 0
        if args.command == "product":
            build_html(args.envelopes, args.output)
            print(json.dumps({"output": str(args.output)}, indent=2))
            return 0
    except (InvalidOrganizationNumber, SourceError, BudgetExceeded, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2

