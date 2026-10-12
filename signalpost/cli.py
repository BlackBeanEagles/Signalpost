import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .brreg import BrregClient, SourceError
from .budget import Budget, BudgetExceeded
from .identity import InvalidOrganizationNumber
from .pipeline import build_profile, profiles_from_page
from .storage import atomic_write_json, write_jsonl
from .validate import validate_jsonl


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
    except (InvalidOrganizationNumber, SourceError, BudgetExceeded, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 2

