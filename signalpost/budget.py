from dataclasses import dataclass, field
from threading import Lock


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    max_requests: int = 2000
    max_cost_usd: float = 10.0
    requests: int = 0
    declared_cost_usd: float = 0.0
    _lock: Lock = field(default_factory=Lock, repr=False)

    def reserve(self, requests: int = 1, cost_usd: float = 0.0) -> None:
        with self._lock:
            if self.requests + requests > self.max_requests:
                raise BudgetExceeded(f"Request budget exceeded ({self.max_requests})")
            if self.declared_cost_usd + cost_usd > self.max_cost_usd:
                raise BudgetExceeded(f"External API cost budget exceeded (${self.max_cost_usd:.2f})")
            self.requests += requests
            self.declared_cost_usd += cost_usd

    def to_dict(self) -> dict:
        return {
            "requests": self.requests,
            "max_requests": self.max_requests,
            "declared_cost_usd": round(self.declared_cost_usd, 6),
            "max_cost_usd": self.max_cost_usd,
        }

