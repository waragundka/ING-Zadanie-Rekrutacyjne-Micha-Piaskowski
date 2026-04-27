"""Allocation validation."""
from __future__ import annotations

import dataclasses

import pytest

from portfolio_sim.allocation import Allocation


def test_from_percentages_normalizes_to_unit_weights() -> None:
    allocation = Allocation.from_percentages({"usd": 30.0, "EUR": 40.0, "huf": 30.0})

    assert allocation.codes == ("USD", "EUR", "HUF")
    assert allocation.as_dict() == {"USD": 0.30, "EUR": 0.40, "HUF": 0.30}


def test_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError, match="must sum to 1.0"):
        Allocation(weights={"USD": 0.5, "EUR": 0.3})


def test_negative_weight_rejected() -> None:
    with pytest.raises(ValueError, match="Negative weight"):
        Allocation(weights={"USD": 1.5, "EUR": -0.5})


def test_empty_allocation_rejected() -> None:
    with pytest.raises(ValueError, match="at least one currency"):
        Allocation(weights={})


def test_invalid_currency_code_rejected() -> None:
    with pytest.raises(ValueError, match="3-letter ISO"):
        Allocation(weights={"DOLLAR": 1.0})


def test_allocation_is_frozen() -> None:
    allocation = Allocation.from_percentages({"USD": 100.0})
    with pytest.raises(dataclasses.FrozenInstanceError):
        allocation.weights = {"EUR": 1.0}  # type: ignore[misc]


def test_allocation_weights_mapping_is_read_only() -> None:
    # Frozen dataclass blocks reassignment of `weights`, MappingProxyType blocks
    # the other mutation vector — writing into the underlying dict.
    allocation = Allocation.from_percentages({"USD": 30.0, "EUR": 40.0, "HUF": 30.0})
    with pytest.raises(TypeError):
        allocation.weights["USD"] = 0.99  # type: ignore[index]


def test_allocation_takes_a_defensive_copy_of_input_dict() -> None:
    # Mutating the source dict after construction must not affect the Allocation.
    source = {"USD": 0.5, "EUR": 0.5}
    allocation = Allocation(weights=source)
    source["USD"] = 0.99  # would have corrupted the allocation pre-fix
    assert allocation.as_dict() == {"USD": 0.5, "EUR": 0.5}


def test_floating_point_tolerance() -> None:
    # 1/3 + 1/3 + 1/3 != 1.0 exactly, but should still pass.
    third = 1.0 / 3.0
    allocation = Allocation(weights={"USD": third, "EUR": third, "HUF": third})

    assert sum(allocation.weights.values()) == pytest.approx(1.0)
