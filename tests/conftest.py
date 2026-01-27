"""
Pytest configuration for pq-pytest package tests.

These tests use the mock runner by default since they test
the library infrastructure, not actual M code execution.
"""

import pytest
import sys
from pathlib import Path

# Add src to path for testing without install
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


# Override the pq_runner fixture to use mock by default for package tests
@pytest.fixture
def pq_runner():
    """Use mock runner for package tests."""
    from pq_pytest import MockRunner
    return MockRunner()
