import hashlib
import json
import os
from pathlib import Path
from typing import Iterable

from .models import CompanyProfile


def atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def write_jsonl(path: Path, profiles: Iterable[CompanyProfile]) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    digest = hashlib.sha256()
    count = 0
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for profile in profiles:
            line = json.dumps(profile.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n"
            handle.write(line)
            digest.update(line.encode("utf-8"))
            count += 1
    os.replace(temporary, path)
    return count, digest.hexdigest()

