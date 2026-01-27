"""
Pytest configuration for example tests.

The pq-pytest plugin automatically provides fixtures when installed.
This file can be used for project-specific fixtures.
"""

import pytest
from pathlib import Path


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
TRANSFORMS_DIR = PROJECT_ROOT / "transforms"
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def transforms_dir() -> Path:
    """Path to the transforms directory."""
    return TRANSFORMS_DIR


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Path to the test fixtures directory."""
    return FIXTURES_DIR


# Optional: Skip tests if no runtime is available
# Uncomment to enable graceful skipping instead of errors

# @pytest.fixture(scope="session", autouse=True)
# def check_runtime_available():
#     """Skip all tests if no M runtime is available."""
#     from pq_pytest import get_runner
#     try:
#         get_runner()
#     except RuntimeError as e:
#         pytest.skip(str(e), allow_module_level=True)
