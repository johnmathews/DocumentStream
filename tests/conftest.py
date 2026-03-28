"""Shared test fixtures for DocumentStream."""

import pytest

from generator.scenario import LoanScenario


@pytest.fixture
def scenario() -> LoanScenario:
    """Generate a single loan scenario for testing."""
    return LoanScenario.generate()
