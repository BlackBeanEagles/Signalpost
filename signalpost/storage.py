import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Iterable

from .models import CompanyProfile


def atomic_write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=path.parent, prefix=path.name + ".", suffix=".tmp") as handle:
        temporary = Path(handle.name)
        handle.write(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)


def write_jsonl(path: Path, profiles: Iterable[CompanyProfile]) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    temporary = Path(temporary_handle.name)
    digest = hashlib.sha256()
    count = 0
    with temporary_handle as handle:
        for profile in profiles:
            line = json.dumps(profile.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n"
            handle.write(line)
            digest.update(line.encode("utf-8"))
            count += 1
    os.replace(temporary, path)
    return count, digest.hexdigest()

