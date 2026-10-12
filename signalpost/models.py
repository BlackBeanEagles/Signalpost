from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Evidence:
    source_name: str
    source_url: str
    retrieved_at: str
    json_path: str
    source_updated_at: Optional[str] = None


@dataclass(frozen=True)
class Fact:
    field: str
    value: Any
    evidence: Evidence
    confidence: float = 1.0
    explanation: str = ""


@dataclass
class CompanyProfile:
    organization_number: str
    legal_name: str
    retrieved_at: str
    facts: list[Fact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    schema_version: str = "1.0"

    def to_dict(self) -> dict:
        return asdict(self)

