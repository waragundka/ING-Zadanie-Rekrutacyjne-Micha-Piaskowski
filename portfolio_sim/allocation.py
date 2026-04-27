"""Currency allocation value object with validation."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

WEIGHT_TOLERANCE = 1e-6
ISO_CODE_LENGTH = 3


@dataclass(frozen=True)
class Allocation:
    """Immutable mapping of ISO currency codes to fractional weights summing to 1.0.

    `frozen=True` blocks attribute reassignment; wrapping the underlying dict in
    `MappingProxyType` blocks the second mutation vector — `alloc.weights["USD"] = …`
    — so this value object is genuinely immutable end-to-end.
    """

    weights: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.weights:
            raise ValueError("Allocation must contain at least one currency.")

        for code, weight in self.weights.items():
            if not isinstance(code, str) or len(code) != ISO_CODE_LENGTH:
                raise ValueError(f"Currency code must be a 3-letter ISO string, got {code!r}.")
            if weight < 0:
                raise ValueError(f"Negative weight for {code}: {weight}.")

        total = sum(self.weights.values())
        if abs(total - 1.0) > WEIGHT_TOLERANCE:
            raise ValueError(
                f"Allocation weights must sum to 1.0 (got {total:.6f}). "
                "Pass percentages divided by 100, or use Allocation.from_percentages()."
            )

        # Defensive copy + read-only view: callers can't mutate weights through
        # the original reference, and `alloc.weights[k] = v` raises TypeError.
        object.__setattr__(self, "weights", MappingProxyType(dict(self.weights)))

    @classmethod
    def from_percentages(cls, percentages: Mapping[str, float]) -> Allocation:
        """Build an Allocation from a mapping of code -> percent (e.g. {'USD': 30.0})."""
        normalized = {code.upper(): pct / 100.0 for code, pct in percentages.items()}
        return cls(weights=normalized)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(self.weights.keys())

    def as_dict(self) -> dict[str, float]:
        return dict(self.weights)
